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
`BACKUPS_MAX_AGE`, `CROSSPLAY`, `STATUS_HTTP`, `STATUS_HTTP_PORT`, `UPDATE_CRON` e todos os filtros
`VALHEIM_LOG_FILTER_CONTAINS_*` presentes no ambiente. Variáveis adicionais com
nome em `A-Z`, `0-9` e `_` podem ser preservadas e editadas. Variáveis `WEB_*`
ficam fora desse formulário porque pertencem ao próprio painel.

`SERVER_PASS` nunca é devolvida para o HTML. O operador pode substituí-la
preenchendo o campo; vazio preserva o valor atual.

## Players conectados

O dashboard consulta o endpoint interno `http://valheim:80/status.json` e
atualiza a presença a cada 10 segundos. A resposta fornece contagem, nome
quando disponível, score, duração da conexão e metadados do servidor. A mesma
resposta pode trazer nomes vazios; por isso o painel também exibe as últimas
linhas de conexão encontradas nos logs, incluindo nome e ZDOID quando o log os
fornece. Essas linhas de log são histórico recente, não uma confirmação de
presença atual.

Ao alterar `SERVER_PORT`, a recriação também remapeia as três portas UDP
contíguas usadas pelo Valheim (`SERVER_PORT`, `SERVER_PORT+1` e
`SERVER_PORT+2`).

## Backups completos

O menu **Backups** é exclusivo para administradores porque os arquivos contêm
o `valheim.env`, incluindo a senha do servidor, a seed e todas as variáveis do
ambiente. Um backup inclui `valheim.env` e todo o diretório `config/`, exceto
`config/backups/`, que não é aninhado para evitar duplicação de arquivos.

O botão de criação para o container Valheim somente durante a compactação do
mundo e depois retorna o serviço ao estado anterior. O arquivo `.tar.gz` pode
ser baixado ou enviado pelo painel. Antes de qualquer restauração, o sistema
cria automaticamente um backup `pre-restore` e então substitui o mundo e as
configurações, recriando o container para aplicar o ambiente restaurado.

O backup não inclui `data/`, `web-data/`, `web-certs/` nem `web.env`: esses
diretórios pertencem ao runtime ou ao próprio painel e devem ter sua própria
política de backup.

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
