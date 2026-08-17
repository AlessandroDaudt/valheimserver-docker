# Painel web: arquitetura e operação

## Componentes

O serviço `web` é uma aplicação Flask executada por Gunicorn com TLS direto na
porta 8443. Ele monta:

- `valheim.env` em `/runtime/valheim.env`, para leitura e edição atômica;
- `config/` em `/config`, para as três listas administrativas;
- `web-data/` em `/app/data`, para SQLite, chave de sessão e auditoria;
- `web-certs/` em `/certs`, para a chave e o certificado HTTPS;
- `/var/run/docker.sock`, para controlar o container `valheim-server`.

O painel não executa comandos shell recebidos do navegador. As operações Docker
são uma lista fechada de iniciar, parar, reiniciar e recriar o container
inspecionado. Na recriação, o aplicativo copia do container atual as portas,
volumes, rede, capabilities, imagem e política de restart; a única alteração de
ambiente vem do `valheim.env` validado pela interface.

## Autenticação e autorização

Usuários são armazenados em SQLite com hash de senha Werkzeug. Sessões são
assinadas por `WEB_SECRET_KEY` ou por uma chave persistente gerada em
`web-data/.secret-key`. Formulários POST usam token CSRF. Há dois papéis:

| Ação | admin | operator |
| --- | ---: | ---: |
| Ver dashboard e status | sim | sim |
| Iniciar, parar e reiniciar Valheim | sim | sim |
| Alterar parâmetros e recriar Valheim | sim | sim |
| Editar listas de jogadores | sim | sim |
| Ver logs | sim | sim |
| Criar, alterar e excluir usuários | sim | não |
| Consultar auditoria | sim | não |

O aplicativo impede desativar o próprio usuário, excluir a própria conta ou
deixar o sistema sem um administrador ativo.

## Parâmetros expostos

Os parâmetros documentados são `SERVER_NAME`, `WORLD_NAME`, `SERVER_PASS`,
`SERVER_PUBLIC`, `SERVER_PORT`, `TZ`, `SEED`, `BACKUPS`, `BACKUPS_CRON`,
`BACKUPS_MAX_AGE`, `CROSSPLAY`, `UPDATE_CRON` e todos os filtros
`VALHEIM_LOG_FILTER_CONTAINS_*` presentes no ambiente. Variáveis adicionais com
nome em `A-Z`, `0-9` e `_` podem ser preservadas e editadas. Variáveis `WEB_*`
ficam fora desse formulário porque pertencem ao próprio painel.

`SERVER_PASS` nunca é devolvida para o HTML. O operador pode substituí-la
preenchendo o campo; vazio preserva o valor atual.

Ao alterar `SERVER_PORT`, a recriação também remapeia as três portas UDP
contíguas usadas pelo Valheim (`SERVER_PORT`, `SERVER_PORT+1` e
`SERVER_PORT+2`).

## HTTPS

Sem `web.env`, o entrypoint gera certificado autoassinado e a aplicação gera
uma senha temporária. Para ambiente compartilhado, crie `web.env` antes do
primeiro start:

```dotenv
WEB_ADMIN_USERNAME=admin
WEB_ADMIN_PASSWORD=uma-senha-com-pelo-menos-12-caracteres
WEB_SECRET_KEY=uma-chave-aleatoria-longa-e-secreta
WEB_HOSTNAME=valheim.exemplo.local
WEB_TLS_AUTO_GENERATE=true
```

Para certificado próprio, monte `web-certs/server.crt` e
`web-certs/server.key`, defina `WEB_TLS_AUTO_GENERATE=false` e reinicie `web`.
O certificado deve conter o hostname usado pelos operadores.

## Limites e cuidados

- o socket Docker dá ao painel controle equivalente a uma permissão elevada no
  host; não exponha o painel à Internet sem TLS confiável, firewall e
  credenciais fortes;
- a aplicação roda com um único worker por padrão para simplificar o acesso ao
  SQLite e ao lock das operações Docker;
- a recriação do Valheim é interrompida pelo período de parada de dois minutos;
  evite alterações durante uma gravação do mundo;
- a auditoria registra usuário, ação, detalhe resumido e horário UTC, mas não
  registra senhas;
- `web-data/`, `web-certs/` e `web.env` devem entrar em uma política de backup e
  nunca no Git.
