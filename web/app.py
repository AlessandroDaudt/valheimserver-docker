from __future__ import annotations

import os
import re
import secrets
import sqlite3
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from functools import lru_cache, wraps
from pathlib import Path
from typing import Any, Callable

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import docker
except ImportError:  # pragma: no cover - the image installs the dependency.
    docker = None


DATA_DIR = Path(os.environ.get("WEB_DATA_DIR", "/app/data"))
DATABASE_PATH = DATA_DIR / "web.sqlite3"
ENV_FILE = Path(os.environ.get("VALHEIM_ENV_FILE", "/runtime/valheim.env"))
CONFIG_DIR = Path(os.environ.get("VALHEIM_CONFIG_DIR", "/config"))
CONTAINER_NAME = os.environ.get("VALHEIM_CONTAINER_NAME", "valheim-server")
SESSION_HOURS = int(os.environ.get("WEB_SESSION_HOURS", "8"))
SERVER_ACTION_LOCK = threading.Lock()

PLAYER_FILES = {
    "adminlist": ("adminlist.txt", "Administradores do Valheim"),
    "bannedlist": ("bannedlist.txt", "Jogadores banidos"),
    "permittedlist": ("permittedlist.txt", "Jogadores permitidos"),
}

SETTING_DEFINITIONS = [
    ("SERVER_NAME", "Nome do servidor", "text", "Nome exibido na lista do Valheim."),
    ("WORLD_NAME", "Nome do mundo", "text", "Nome do mundo salvo em config/worlds_local/."),
    ("SERVER_PASS", "Senha do servidor", "password", "Senha exigida para entrar no servidor."),
    ("SERVER_PUBLIC", "Servidor público", "boolean", "Publica o servidor na lista pública."),
    ("SERVER_PORT", "Porta principal", "number", "Porta UDP principal do servidor."),
    ("TZ", "Fuso horário", "text", "Fuso horário usado pelos agendamentos."),
    ("SEED", "Seed", "text", "Seed usada ao criar um mundo novo."),
    ("BACKUPS", "Backups automáticos", "boolean", "Ativa os backups automáticos do mundo."),
    ("BACKUPS_CRON", "Agenda de backups", "text", "Expressão cron dos backups automáticos."),
    ("BACKUPS_MAX_AGE", "Retenção de backups", "number", "Quantidade máxima de dias para manter backups."),
    ("CROSSPLAY", "Crossplay", "boolean", "Ativa o acesso por relay do crossplay."),
    ("UPDATE_CRON", "Agenda de atualização", "text", "Expressão cron para atualização; vazio desativa."),
    (
        "VALHEIM_LOG_FILTER_CONTAINS_EXTERNAL_IP",
        "Filtro de log: external IP",
        "text",
        "Mensagem não fatal filtrada dos logs do Valheim.",
    ),
    (
        "VALHEIM_LOG_FILTER_CONTAINS_PUBLIC_IP_HTTP",
        "Filtro de log: public IP HTTP",
        "text",
        "Mensagem não fatal filtrada dos logs do Valheim.",
    ),
    (
        "VALHEIM_LOG_FILTER_CONTAINS_PUBLIC_IP_HTTP2",
        "Filtro de log: public IP HTTP 2",
        "text",
        "Mensagem não fatal filtrada dos logs do Valheim.",
    ),
    (
        "VALHEIM_LOG_FILTER_CONTAINS_PUBLIC_IP_HTTP3",
        "Filtro de log: public IP HTTP 3",
        "text",
        "Mensagem não fatal filtrada dos logs do Valheim.",
    ),
    (
        "VALHEIM_LOG_FILTER_CONTAINS_PUBLIC_IP_STACK",
        "Filtro de log: public IP stack",
        "text",
        "Mensagem não fatal filtrada dos logs do Valheim.",
    ),
    (
        "VALHEIM_LOG_FILTER_CONTAINS_PUBLIC_IP_TIMEOUT",
        "Filtro de log: public IP timeout",
        "text",
        "Mensagem não fatal filtrada dos logs do Valheim.",
    ),
    (
        "VALHEIM_LOG_FILTER_CONTAINS_PUBLIC_IP_GETIP",
        "Filtro de log: public IP get IP",
        "text",
        "Mensagem não fatal filtrada dos logs do Valheim.",
    ),
]
KNOWN_SETTING_KEYS = {item[0] for item in SETTING_DEFINITIONS}
SETTING_LABELS = {item[0]: item[1] for item in SETTING_DEFINITIONS}
ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
PLAYER_ID_RE = re.compile(r"^[^\s]{2,128}$")

def load_secret_key() -> str:
    configured = os.environ.get("WEB_SECRET_KEY", "").strip()
    if configured:
        return configured
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    secret_path = DATA_DIR / ".secret-key"
    if secret_path.exists():
        stored = secret_path.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    generated = secrets.token_hex(32)
    secret_path.write_text(generated + "\n", encoding="utf-8")
    try:
        os.chmod(secret_path, 0o600)
    except OSError:
        pass
    return generated


app = Flask(__name__)
app.config.update(
    SECRET_KEY=load_secret_key(),
    PERMANENT_SESSION_LIFETIME=timedelta(hours=SESSION_HOURS),
    MAX_CONTENT_LENGTH=1024 * 1024,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exception: BaseException | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'operator')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        """
    )
    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        username = (os.environ.get("WEB_ADMIN_USERNAME") or "admin").strip()
        password = os.environ.get("WEB_ADMIN_PASSWORD", "").strip()
        generated = False
        if not password:
            password = secrets.token_urlsafe(18)
            generated = True
        validate_username(username)
        validate_password(password)
        db.execute(
            "INSERT INTO users (username, password_hash, role, active, created_at) VALUES (?, ?, 'admin', 1, ?)",
            (username, generate_password_hash(password), utc_now()),
        )
        db.commit()
        if generated:
            print(
                f"[valheim-web] Primeiro acesso: usuário={username} "
                f"senha temporária={password}. Altere-a em Usuários.",
                flush=True,
            )
    db.close()


def validate_username(username: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,63}", username):
        raise ValueError("usuário deve ter 3-64 caracteres alfanuméricos, ponto, hífen ou sublinhado")


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("a senha deve ter pelo menos 12 caracteres")
    if "\n" in password or "\r" in password:
        raise ValueError("a senha não pode conter quebras de linha")


def current_user() -> sqlite3.Row | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone()


def record_audit(action: str, detail: str = "") -> None:
    user = current_user()
    username = user["username"] if user else "system"
    db = get_db()
    db.execute(
        "INSERT INTO audit_log (username, action, detail, created_at) VALUES (?, ?, ?, ?)",
        (username, action, detail[:500], utc_now()),
    )
    db.commit()


def csrf_value() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def check_csrf() -> None:
    if request.method == "POST" and request.form.get("_csrf") != session.get("csrf_token"):
        abort(400, description="token CSRF inválido ou ausente")


def role_required(*roles: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            user = current_user()
            if user is None:
                return redirect(url_for("login", next=request.path))
            if user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


@app.context_processor
def inject_template_helpers() -> dict[str, Any]:
    user = current_user()
    return {"current_user": user, "csrf_token": csrf_value}


@app.before_request
def protect_requests() -> Any:
    if request.endpoint in {"healthz", "static", "login"}:
        if request.method == "POST" and request.endpoint == "login":
            check_csrf()
        return None
    if current_user() is None:
        return redirect(url_for("login", next=request.path))
    check_csrf()
    return None


@app.get("/healthz")
def healthz() -> Any:
    return jsonify({"status": "ok"})


@app.route("/login", methods=["GET", "POST"])
def login() -> Any:
    if current_user() is not None:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and user["active"] and check_password_hash(user["password_hash"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            get_db().execute("UPDATE users SET last_login = ? WHERE id = ?", (utc_now(), user["id"]))
            get_db().commit()
            record_audit("login")
            destination = request.args.get("next", "")
            safe_destination = destination if destination.startswith("/") and not destination.startswith("//") else url_for("dashboard")
            return redirect(safe_destination)
        flash("Usuário ou senha inválidos.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout() -> Any:
    record_audit("logout")
    session.clear()
    return redirect(url_for("login"))


def read_env_values() -> dict[str, str]:
    if not ENV_FILE.exists():
        raise RuntimeError(f"arquivo de configuração não encontrado: {ENV_FILE}")
    values: dict[str, str] = {}
    for raw_line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if ENV_KEY_RE.fullmatch(key):
            values[key] = value
    return values


def encode_env_value(value: str) -> str:
    if value == "":
        return ""
    if re.search(r"[\s#\\\"']", value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def write_env_values(values: dict[str, str]) -> None:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    keys = [key for key, *_rest in SETTING_DEFINITIONS if key in values]
    keys += sorted(key for key in values if key not in keys)
    content = [
        "# Gerenciado pela interface Valheim Web. Edite por aqui para manter o estado sincronizado.",
        "# Valores sensíveis, como SERVER_PASS, não são exibidos depois de salvos.",
        "",
    ]
    content.extend(f"{key}={encode_env_value(values[key])}" for key in keys)
    content.append("")
    fd, temp_name = tempfile.mkstemp(prefix="valheim-env-", dir=ENV_FILE.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temp_file:
            temp_file.write("\n".join(content))
        try:
            os.chmod(temp_name, 0o600)
        except OSError:
            pass
        os.replace(temp_name, ENV_FILE)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def validate_setting(key: str, value: str) -> str | None:
    if "\n" in value or "\r" in value or "\x00" in value:
        return "não pode conter quebras de linha ou bytes nulos"
    if key in {"SERVER_NAME", "WORLD_NAME", "SEED"} and not value.strip():
        return "não pode ficar vazio"
    if key == "SERVER_PASS" and len(value) < 5:
        return "deve ter pelo menos 5 caracteres"
    if key in {"SERVER_PUBLIC", "BACKUPS", "CROSSPLAY"} and value.lower() not in {"true", "false"}:
        return "use true ou false"
    if key == "SERVER_PORT":
        try:
            port = int(value)
        except ValueError:
            return "deve ser um número"
        if not 1 <= port <= 65533:
            return "deve estar entre 1 e 65533 para reservar as três portas do Valheim"
    if key == "BACKUPS_MAX_AGE":
        try:
            age = int(value)
        except ValueError:
            return "deve ser um número"
        if age < 1:
            return "deve ser pelo menos 1 dia"
    return None


def read_player_entries(kind: str) -> list[str]:
    filename, _label = PLAYER_FILES[kind]
    path = CONFIG_DIR / filename
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("//"):
            entries.append(line)
    return entries


def write_player_entries(kind: str, raw_entries: str) -> None:
    filename, label = PLAYER_FILES[kind]
    entries: list[str] = []
    for line in raw_entries.splitlines():
        value = line.strip()
        if not value:
            continue
        if not PLAYER_ID_RE.fullmatch(value):
            raise ValueError(f"identificador inválido em {filename}: {value}")
        if value not in entries:
            entries.append(value)
    path = CONFIG_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    content = [f"# {label} - um identificador por linha", *entries, ""]
    fd, temp_name = tempfile.mkstemp(prefix=f"{filename}-", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as temp_file:
            temp_file.write("\n".join(content))
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


@lru_cache(maxsize=1)
def docker_client() -> Any:
    if docker is None:
        raise RuntimeError("biblioteca Docker indisponível")
    return docker.from_env(timeout=10)


def get_valheim_container() -> Any:
    return docker_client().containers.get(CONTAINER_NAME)


def server_status() -> dict[str, Any]:
    try:
        container = get_valheim_container()
        image = container.image
        tags = image.tags if image else []
        return {
            "available": True,
            "status": container.status,
            "name": container.name,
            "image": tags[0] if tags else container.attrs.get("Config", {}).get("Image", "desconhecida"),
            "started_at": container.attrs.get("State", {}).get("StartedAt", ""),
        }
    except Exception as exc:  # Docker may be stopped or the container may not exist.
        return {"available": False, "status": "indisponível", "error": str(exc)}


def perform_server_action(action: str) -> None:
    if action not in {"start", "stop", "restart"}:
        raise ValueError("operação não permitida")
    with SERVER_ACTION_LOCK:
        container = get_valheim_container()
        if action == "start":
            container.start()
        elif action == "stop":
            container.stop(timeout=120)
        else:
            container.restart(timeout=120)


def recreate_valheim_container() -> None:
    """Recreate the existing Compose-managed container with the new env file.

    The old container is renamed first, so a failed creation can be rolled back.
    All mounts, ports, capabilities, restart policy and networks are copied from
    the current container inspected through the Docker socket.
    """
    values = read_env_values()
    environment = [f"{key}={value}" for key, value in values.items()]
    with SERVER_ACTION_LOCK:
        client = docker_client()
        old = client.containers.get(CONTAINER_NAME)
        old.reload()
        attrs = old.attrs
        backup_name = f"{CONTAINER_NAME}-previous-{secrets.token_hex(4)}"
        old.stop(timeout=120)
        old.rename(backup_name)
        try:
            config = attrs.get("Config", {})
            host = attrs.get("HostConfig", {})
            binds: dict[str, dict[str, str]] = {}
            for mount in attrs.get("Mounts", []):
                source = mount.get("Source")
                destination = mount.get("Destination")
                if source and destination:
                    binds[source] = {
                        "bind": destination,
                        "mode": "rw" if mount.get("RW", True) else "ro",
                    }
            host_kwargs: dict[str, Any] = {
                "binds": binds,
                "port_bindings": host.get("PortBindings") or {},
                "restart_policy": host.get("RestartPolicy") or {"Name": "unless-stopped"},
                "cap_add": host.get("CapAdd") or [],
                "cap_drop": host.get("CapDrop") or [],
                "network_mode": host.get("NetworkMode") or "default",
                "privileged": host.get("Privileged", False),
                "read_only": host.get("ReadonlyRootfs", False),
                "init": host.get("Init"),
            }
            try:
                server_port = int(values.get("SERVER_PORT", "2456"))
                host_kwargs["port_bindings"] = {
                    f"{server_port + offset}/udp": [{"HostIp": "0.0.0.0", "HostPort": str(server_port + offset)}]
                    for offset in range(3)
                }
            except ValueError:
                # Validation normally prevents this; retain the inspected
                # bindings if an operator edits the env file concurrently.
                pass
            network_attrs = attrs.get("NetworkSettings", {}).get("Networks") or {}
            networks = list(network_attrs.keys())
            networking_config = None
            if networks:
                # The Docker API accepts either a network mode or an explicit
                # network during creation, not the Compose network in both fields.
                host_kwargs["network_mode"] = "default"
                endpoints = {}
                for network_name, network in network_attrs.items():
                    endpoints[network_name] = client.api.create_endpoint_config(
                        aliases=network.get("Aliases") or None,
                    )
                networking_config = client.api.create_networking_config(endpoints)
            host_config = client.api.create_host_config(**host_kwargs)
            create_kwargs: dict[str, Any] = {
                "image": config.get("Image"),
                "name": CONTAINER_NAME,
                "command": config.get("Cmd"),
                "entrypoint": config.get("Entrypoint"),
                "environment": environment,
                "labels": config.get("Labels") or {},
                "working_dir": config.get("WorkingDir") or None,
                "user": config.get("User") or None,
                "hostname": config.get("Hostname") or None,
                "tty": config.get("Tty", False),
                "stdin_open": config.get("OpenStdin", False),
                "stop_timeout": config.get("StopTimeout") or 120,
                "stop_signal": config.get("StopSignal") or None,
                "host_config": host_config,
                "networking_config": networking_config,
            }
            response = client.api.create_container(**create_kwargs)
            new_container = client.containers.get(response["Id"])
            new_container.start()
            client.containers.get(backup_name).remove(force=True)
        except Exception:
            try:
                replacement = client.containers.get(CONTAINER_NAME)
                replacement.remove(force=True)
            except Exception:
                pass
            rollback = client.containers.get(backup_name)
            rollback.rename(CONTAINER_NAME)
            rollback.start()
            raise


@app.get("/")
@role_required("admin", "operator")
def dashboard() -> Any:
    return render_template("dashboard.html", status=server_status(), env=read_env_values())


@app.route("/settings", methods=["GET", "POST"])
@role_required("admin", "operator")
def settings() -> Any:
    values = read_env_values()
    if request.method == "POST":
        updated = dict(values)
        errors: list[str] = []
        for key, _label, _field_type, _description in SETTING_DEFINITIONS:
            field_name = f"setting_{key}"
            if field_name not in request.form:
                continue
            value = request.form.get(field_name, "")
            if key == "SERVER_PASS" and value == "":
                continue
            error = validate_setting(key, value)
            if error:
                errors.append(f"{SETTING_LABELS[key]}: {error}")
            else:
                updated[key] = value.lower() if _field_type == "boolean" else value
        for key, value in request.form.items():
            if not key.startswith("custom_") or key == "custom_new_key":
                continue
            custom_key = key.removeprefix("custom_")
            if custom_key not in values:
                continue
            error = validate_setting(custom_key, value)
            if error:
                errors.append(f"{custom_key}: {error}")
            else:
                updated[custom_key] = value
        new_key = request.form.get("custom_new_key", "").strip().upper()
        new_value = request.form.get("custom_new_value", "")
        if new_key:
            if not ENV_KEY_RE.fullmatch(new_key):
                errors.append("a variável adicional deve usar apenas A-Z, 0-9 e sublinhado")
            elif new_key.startswith("WEB_"):
                errors.append("variáveis WEB_ pertencem à configuração do painel e não ao servidor")
            elif new_key in KNOWN_SETTING_KEYS:
                errors.append("a variável adicional já está na lista documentada")
            else:
                error = validate_setting(new_key, new_value)
                if error:
                    errors.append(f"{new_key}: {error}")
                else:
                    updated[new_key] = new_value
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            try:
                write_env_values(updated)
                recreate_valheim_container()
                record_audit("settings.update", f"{len(updated)} variáveis salvas e container recriado")
                flash("Configurações salvas e container do Valheim recriado.", "success")
                values = updated
            except Exception as exc:
                flash(f"Configuração salva, mas não foi possível recriar o container: {exc}", "error")
                record_audit("settings.update.error", str(exc))
    documented = [
        {"key": key, "label": label, "type": field_type, "description": description, "value": values.get(key, "")}
        for key, label, field_type, description in SETTING_DEFINITIONS
    ]
    custom = [(key, value) for key, value in values.items() if key not in KNOWN_SETTING_KEYS]
    return render_template("settings.html", settings=documented, custom=custom)


@app.route("/players", methods=["GET", "POST"])
@role_required("admin", "operator")
def players() -> Any:
    if request.method == "POST":
        kind = request.form.get("list_type", "")
        if kind not in PLAYER_FILES:
            abort(400, description="lista de jogadores inválida")
        try:
            write_player_entries(kind, request.form.get("entries", ""))
            record_audit("players.update", kind)
            flash("Lista salva. Reinicie o servidor para garantir que o runtime recarregue os IDs.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
    lists = [
        {"key": key, "label": label, "entries": "\n".join(read_player_entries(key))}
        for key, (_filename, label) in PLAYER_FILES.items()
    ]
    return render_template("players.html", lists=lists)


@app.post("/server/action")
@role_required("admin", "operator")
def server_action() -> Any:
    action = request.form.get("action", "")
    labels = {"start": "iniciado", "stop": "parado", "restart": "reiniciado"}
    try:
        perform_server_action(action)
        record_audit(f"server.{action}")
        flash(f"Container do Valheim {labels.get(action, action)}.", "success")
    except Exception as exc:
        record_audit(f"server.{action}.error", str(exc))
        flash(f"Não foi possível executar a operação: {exc}", "error")
    return redirect(url_for("dashboard"))


@app.get("/logs")
@role_required("admin", "operator")
def logs() -> Any:
    try:
        output = get_valheim_container().logs(tail=250, timestamps=True).decode("utf-8", errors="replace")
    except Exception as exc:
        output = f"Não foi possível ler os logs: {exc}"
    return render_template("logs.html", logs=output)


@app.route("/users", methods=["GET", "POST"])
@role_required("admin")
def users() -> Any:
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            if action == "create":
                username = request.form.get("username", "").strip()
                password = request.form.get("password", "")
                role = request.form.get("role", "operator")
                validate_username(username)
                validate_password(password)
                if role not in {"admin", "operator"}:
                    raise ValueError("papel inválido")
                db.execute(
                    "INSERT INTO users (username, password_hash, role, active, created_at) VALUES (?, ?, ?, 1, ?)",
                    (username, generate_password_hash(password), role, utc_now()),
                )
                db.commit()
                record_audit("users.create", username)
                flash("Usuário criado.", "success")
            elif action == "update":
                target_id = int(request.form.get("user_id", "0"))
                target = db.execute("SELECT * FROM users WHERE id = ?", (target_id,)).fetchone()
                if target is None:
                    raise ValueError("usuário não encontrado")
                role = request.form.get("role", "operator")
                active = request.form.get("active") == "1"
                password = request.form.get("password", "")
                if role not in {"admin", "operator"}:
                    raise ValueError("papel inválido")
                if target_id == session.get("user_id") and not active:
                    raise ValueError("não é possível desativar o próprio usuário")
                if target["role"] == "admin" and (role != "admin" or not active):
                    admin_count = db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1").fetchone()[0]
                    if admin_count <= 1:
                        raise ValueError("mantenha pelo menos um administrador ativo")
                if password:
                    validate_password(password)
                    db.execute(
                        "UPDATE users SET role = ?, active = ?, password_hash = ? WHERE id = ?",
                        (role, int(active), generate_password_hash(password), target_id),
                    )
                else:
                    db.execute("UPDATE users SET role = ?, active = ? WHERE id = ?", (role, int(active), target_id))
                db.commit()
                record_audit("users.update", target["username"])
                flash("Usuário atualizado.", "success")
            elif action == "delete":
                target_id = int(request.form.get("user_id", "0"))
                target = db.execute("SELECT * FROM users WHERE id = ?", (target_id,)).fetchone()
                if target is None:
                    raise ValueError("usuário não encontrado")
                if target_id == session.get("user_id"):
                    raise ValueError("não é possível excluir o próprio usuário")
                if target["role"] == "admin":
                    admin_count = db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1").fetchone()[0]
                    if admin_count <= 1:
                        raise ValueError("mantenha pelo menos um administrador ativo")
                db.execute("DELETE FROM users WHERE id = ?", (target_id,))
                db.commit()
                record_audit("users.delete", target["username"])
                flash("Usuário excluído.", "success")
            else:
                raise ValueError("operação inválida")
        except (ValueError, sqlite3.IntegrityError) as exc:
            flash(str(exc), "error")
    user_rows = db.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE").fetchall()
    return render_template("users.html", users=user_rows)


@app.get("/audit")
@role_required("admin")
def audit() -> Any:
    rows = get_db().execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200").fetchall()
    return render_template("audit.html", entries=rows)


@app.get("/documentation")
@role_required("admin", "operator")
def documentation() -> Any:
    return render_template("documentation.html", settings=SETTING_DEFINITIONS)


@app.errorhandler(400)
def bad_request(error: Any) -> Any:
    return render_template("error.html", code=400, message=getattr(error, "description", "requisição inválida")), 400


@app.errorhandler(403)
def forbidden(_error: Any) -> Any:
    return render_template("error.html", code=403, message="você não tem permissão para esta operação"), 403


@app.errorhandler(404)
def not_found(_error: Any) -> Any:
    return render_template("error.html", code=404, message="página não encontrada"), 404


with app.app_context():
    init_db()
