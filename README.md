# Servidor Valheim

Projeto Docker Compose para executar o servidor dedicado de Valheim e uma
interface web HTTPS para operação, configuração e controle de usuários.

## Requisitos

- Docker Desktop ou Docker Engine com Docker Compose v2.24 ou mais recente;
- espaço em disco para runtime, mundo e backups;
- senha forte para o servidor e senha forte para o painel.

## Primeiro acesso

1. Copie `valheim.env.example` para `valheim.env` e ajuste principalmente
   `SERVER_PASS`.
2. Copie `web.env.example` para `web.env`. Defina `WEB_ADMIN_PASSWORD` com pelo
   menos 12 caracteres e uma chave aleatória longa em `WEB_SECRET_KEY`. O arquivo
   `web.env` é ignorado pelo Git.
3. Suba os serviços:

   ```powershell
   docker compose up -d --build
   ```

4. Abra `https://localhost:8443`. O certificado inicial é autoassinado e o
   navegador exibirá um aviso; para uso real, monte um certificado confiável.

Se `web.env` não existir, o painel gera uma senha administrativa temporária e a
imprime uma vez nos logs:

```powershell
docker compose logs web
```

Altere essa senha em **Usuários** depois do primeiro login.

## Interface web

O painel administra o container `valheim-server` através do Docker Engine local.
Ele oferece dashboard, iniciar/parar/reiniciar, edição de todas as variáveis
documentadas e adicionais, aplicação das configurações, listas de jogadores,
logs, usuários e auditoria.

O papel `admin` possui acesso total, incluindo criação, alteração e exclusão de
usuários. O papel `operator` pode operar o servidor, alterar sua configuração,
gerenciar listas de jogadores e consultar logs, mas não pode administrar contas
do painel nem consultar a auditoria.

## Configuração do servidor

As variáveis ficam em `valheim.env`. A interface apresenta as opções já
documentadas no projeto e preserva variáveis adicionais existentes.

| Variável | Função | Valor de referência |
| --- | --- | --- |
| `SERVER_NAME` | Nome exibido do servidor | `PowerGuido_New` |
| `WORLD_NAME` | Nome do mundo | `PowerGuido` |
| `SERVER_PASS` | Senha de acesso | definir localmente |
| `SERVER_PUBLIC` | Publica o servidor na lista | `true` |
| `SERVER_PORT` | Porta principal; o painel publica também as duas seguintes | `2456` |
| `TZ` | Fuso dos agendamentos | `America/Sao_Paulo` |
| `SEED` | Seed para mundo novo | `EVpmm24uK8` |
| `BACKUPS` | Ativa backups automáticos | `true` |
| `BACKUPS_CRON` | Agenda dos backups | `5 * * * *` |
| `BACKUPS_MAX_AGE` | Retenção em dias | `7` |
| `CROSSPLAY` | Ativa crossplay via relay | `true` |
| `UPDATE_CRON` | Agenda de atualização; vazio desativa | vazio |
| `VALHEIM_LOG_FILTER_CONTAINS_*` | Filtros de mensagens não fatais | conforme ambiente |

Depois de editar pelo painel, o serviço é recriado automaticamente. Alterações
manuais exigem:

```powershell
docker compose up -d --force-recreate valheim
```

## Listas administrativas de jogadores

Informe um identificador por linha nos arquivos abaixo ou use **Listas de
jogadores** no painel:

- `config/adminlist.txt`: administradores do Valheim;
- `config/bannedlist.txt`: jogadores banidos;
- `config/permittedlist.txt`: jogadores permitidos, quando usada.

Reinicie o serviço depois de alterar as listas para garantir que o runtime
recarregue os arquivos.

## HTTPS e segurança operacional

O serviço web escuta `8443/tcp`. O certificado autoassinado fica em
`web-certs/`, que não é versionado. Para produção, substitua
`web-certs/server.crt` e `web-certs/server.key` por um certificado válido para
`WEB_HOSTNAME` e reinicie o serviço web.

O painel monta `/var/run/docker.sock` porque precisa controlar o container do
servidor. Esse socket equivale a uma permissão elevada no Docker Engine:
mantenha o painel em uma rede confiável, não publique a porta 8443 diretamente
na Internet sem TLS confiável e mantenha as credenciais fora do Git.

## Operação rápida

```powershell
docker compose ps
docker compose logs -f --tail=100 valheim
docker compose logs -f --tail=100 web
docker compose restart valheim
docker compose pull valheim
docker compose up -d --build --force-recreate
```

Backups, restauração, atualização da imagem e diagnóstico estão em
[`docs/OPERACAO.md`](docs/OPERACAO.md). A arquitetura e os limites do painel
estão em [`docs/PAINEL_WEB.md`](docs/PAINEL_WEB.md).

## Estrutura e versionamento

| Caminho | Finalidade | Git |
| --- | --- | --- |
| `docker-compose.yml` | serviços Valheim e painel web | versionar |
| `web/` | aplicação Flask, templates e imagem web | versionar |
| `valheim.env.example` | modelo sem segredo | versionar |
| `valheim.env` | credenciais e configuração local | ignorar |
| `web.env.example` | modelo de credenciais do painel | versionar |
| `web.env` | credenciais e chave de sessão | ignorar |
| `config/*.txt` | listas administrativas | versionar conforme necessário |
| `web-data/` | banco SQLite de usuários e auditoria | ignorar |
| `web-certs/` | certificado e chave HTTPS | ignorar |
| `config/worlds_local/` | mundo, bancos `.db` e backups do mundo | ignorar |
| `config/backups/` | ZIPs de backup do servidor | ignorar |
| `data/` | instalação/runtime do servidor | ignorar |
