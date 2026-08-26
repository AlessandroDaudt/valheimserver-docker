# Valheim Server

Docker Compose project for running a dedicated Valheim server and an HTTPS web interface for operation, configuration, and user management.

## Requirements

- Docker Desktop or Docker Engine with Docker Compose v2.24 or later;
- disk space for runtime data, the world, and backups;
- a strong server password and a strong panel password.

## First access

1. Copy `valheim.env.example` to `valheim.env` and adjust at least `SERVER_PASS`.
2. Copy `web.env.example` to `web.env`. Set `WEB_ADMIN_PASSWORD` to at least 12 characters and use a long random key in `WEB_SECRET_KEY`. `web.env` is ignored by Git.
3. Start the services:

   ```powershell
   docker compose up -d --build
   ```

4. Open `https://localhost:8443`. The initial certificate is self-signed, so the browser will show a warning; for real use, mount a trusted certificate.

If `web.env` does not exist, the panel generates a temporary administrator password and prints it once in the logs:

```powershell
docker compose logs web
```

Change this password under **Users** after the first login.

## Web interface

The **Backups** menu (admin only) creates a complete archive containing the world, lists, `config/` settings, and `valheim.env`, including the seed, password, and other server variables. The archive can be downloaded, uploaded again, and restored through the panel. A safety backup is created before restoration so the previous state can be recovered.

The panel manages the `valheim-server` container through the local Docker Engine. It provides a dashboard, start/stop/restart controls, editing for all documented and additional variables, configuration application, player lists, logs, users, and auditing.

The `admin` role has full access, including creating, changing, and deleting users. The `operator` role can operate the server, change its configuration, manage player lists, and view logs, but cannot manage panel accounts or view the audit log.

## Server configuration

Variables live in `valheim.env`. The interface shows the options already documented by the project and preserves existing additional variables.

| Variable | Purpose | Reference value |
|---|---|---|
| `SERVER_NAME` | Displayed server name | `PowerGuido_New` |
| `WORLD_NAME` | World name | `PowerGuido` |
| `SERVER_PASS` | Access password | define locally |
| `SERVER_PUBLIC` | Publish the server in the list | `true` |
| `SERVER_PORT` | Main port; the panel also publishes the next two | `2456` |
| `TZ` | Scheduling timezone | `America/Sao_Paulo` |
| `SEED` | Seed for a new world | `EVpmm24uK8` |
| `BACKUPS` | Enable automatic backups | `true` |
| `BACKUPS_CRON` | Backup schedule | `5 * * * *` |
| `BACKUPS_MAX_AGE` | Retention in days | `7` |
| `CROSSPLAY` | Enable crossplay through the relay | `true` |
| `STATUS_HTTP` / `STATUS_HTTP_PORT` | Internal status used by the panel for connected players | `true` / `80` |
| `UPDATE_CRON` | Update schedule; empty disables it | empty |
| `VALHEIM_LOG_FILTER_CONTAINS_*` | Filters for non-fatal messages | environment-dependent |

After editing through the panel, the service is recreated automatically. Manual changes require:

```powershell
docker compose up -d --force-recreate valheim
```

## Administrative player lists

Enter one identifier per line in the files below or use **Player lists** in the panel:

- `config/adminlist.txt`: Valheim administrators;
- `config/bannedlist.txt`: banned players;
- `config/permittedlist.txt`: permitted players, when used.

Restart the service after changing the lists so the runtime reloads the files.

## HTTPS and operational security

The web service listens on `8443/tcp`. The self-signed certificate lives in `web-certs/`, which is not versioned. For production, replace `web-certs/server.crt` and `web-certs/server.key` with a valid certificate for `WEB_HOSTNAME` and restart the web service.

The panel mounts `/var/run/docker.sock` because it needs to control the server container. This socket is equivalent to elevated permission on the Docker Engine: keep the panel on a trusted network, do not expose port 8443 directly to the internet without trusted TLS, and keep credentials out of Git.

The panel queries `http://valheim:80/status.json` only on the internal Compose network. The presence section shows the live count, fields returned by the query server, and the latest connections identified in the logs. The query server may not provide the player name on every platform.

## Quick operations

```powershell
docker compose ps
docker compose logs -f --tail=100 valheim
docker compose logs -f --tail=100 web
docker compose restart valheim
docker compose pull valheim
docker compose up -d --build --force-recreate
```

Backups, restoration, image updates, and diagnostics are documented in [`docs/OPERACAO.md`](docs/OPERACAO.md). The panel architecture and limits are in [`docs/PAINEL_WEB.md`](docs/PAINEL_WEB.md).

## Structure and versioning

| Path | Purpose | Git |
|---|---|---|
| `docker-compose.yml` | Valheim and web panel services | commit |
| `web/` | Flask application, templates, and web image | commit |
| `valheim.env.example` | Secret-free template | commit |
| `valheim.env` | Credentials and local configuration | ignore |
| `web.env.example` | Panel credential template | commit |
| `web.env` | Credentials and session key | ignore |
| `config/*.txt` | Administrative lists | commit as needed |
| `web-data/` | SQLite user and audit database | ignore |
| `web-certs/` | HTTPS certificate and key | ignore |
| `config/worlds_local/` | World, `.db` files, and world backups | ignore |
| `config/backups/` | Server backup ZIPs | ignore |
| `data/` | Server installation/runtime | ignore |
