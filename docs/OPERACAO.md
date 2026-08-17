# Runbook operacional

Execute os comandos a partir da raiz do projeto. O Compose possui dois
serviços: `valheim`, que executa o servidor dedicado, e `web`, que oferece a
interface HTTPS de administração.

## Ciclo de vida

```powershell
# Subir e construir o painel
docker compose up -d --build

# Ver estado e logs
docker compose ps
docker compose logs -f --tail=100 valheim
docker compose logs -f --tail=100 web

# Parar com o período de encerramento configurado
docker compose stop valheim

# Reiniciar somente o servidor
docker compose restart valheim

# Reiniciar somente o painel
docker compose restart web
```

O `valheim` usa `restart: unless-stopped`, `sys_nice` e período de parada de
dois minutos, permitindo que o servidor salve o estado antes de encerrar. O
`web` mantém usuários, auditoria e certificados em `web-data/` e `web-certs/`.

## Painel web

Abra `https://<host>:8443`. No primeiro start, o certificado é autoassinado e a
senha administrativa temporária (se `WEB_ADMIN_PASSWORD` não estiver definida)
é impressa em `docker compose logs web`.

As responsabilidades são:

- `admin`: todas as operações, incluindo contas, listas, configuração, logs e
  auditoria;
- `operator`: configuração do servidor, listas de jogadores, logs e ações de
  iniciar/parar/reiniciar o container do Valheim.

A tela **Configurações** grava `valheim.env` de forma atômica e recria o
container `valheim-server`, preservando imagem, volumes, portas, rede,
capabilities e política de restart. Evite executar uma atualização pelo painel
ao mesmo tempo que o workflow de deploy.

O painel consulta o status interno em `http://valheim:80/status.json`. Com
`STATUS_HTTP=true`, o container Valheim atualiza esse JSON a cada 10 segundos;
nenhuma porta de status é publicada no host. O dashboard mostra contagem,
score, duração, metadados e últimas conexões identificadas nos logs. O nome do
player pode ficar vazio porque o query server não garante esse campo.

## Alterar a configuração

O painel apresenta as opções do `valheim.env.example`, os filtros de log
presentes no `valheim.env` e variáveis adicionais. A senha do servidor não é
exibida após ser salva; campo vazio significa manter a senha atual.

Para uma alteração manual:

1. confirme que existe um backup recente;
2. pare ou reinicie o serviço conforme a alteração;
3. edite `valheim.env` sem colocar segredos no Git;
4. recrie o container:

   ```powershell
   docker compose up -d --force-recreate valheim
   ```

## Backups automáticos

Os backups estão habilitados por `BACKUPS=true`, agendados por
`BACKUPS_CRON=5 * * * *` — minuto 5 de cada hora — e têm retenção configurada
por `BACKUPS_MAX_AGE=7`. Os arquivos são gravados em `config/backups/`.

Confirme a geração:

```powershell
Get-ChildItem .\config\backups -File | Sort-Object LastWriteTime -Descending | Select-Object -First 10 Name,Length,LastWriteTime
```

Backups são a proteção de recuperação do mundo e não devem ser armazenados no
Git. Mantenha uma cópia em destino separado do computador do servidor. Inclua
`web-data/` no backup se precisar preservar contas e auditoria do painel.

## Restauração de um backup

O ZIP atual contém o caminho `config/worlds_local/`. Para restaurar:

1. escolha o ZIP correto em `config/backups/`;
2. pare o serviço:

   ```powershell
   docker compose stop valheim
   ```

3. faça uma cópia temporária de `config/worlds_local/` fora do projeto;
4. extraia o ZIP na raiz, preservando os caminhos:

   ```powershell
   Expand-Archive -LiteralPath .\config\backups\worlds-AAAAmmdd-HHMMSS.zip -DestinationPath . -Force
   ```

5. inicie o servidor e acompanhe os logs:

   ```powershell
   docker compose up -d valheim
   docker compose logs -f --tail=100 valheim
   ```

O `-Force` substitui os arquivos do mundo. Verifique o nome do arquivo e
preserve o estado atual antes da extração.

## Atualização da imagem e deploy

O workflow `.github/workflows/test-runner.yml` executa no runner self-hosted
`valheim`, constrói a imagem do painel, atualiza a imagem do Valheim, recria os
serviços e verifica `https://127.0.0.1:8443/healthz`.

Para atualizar manualmente:

```powershell
docker compose pull valheim
docker compose build --pull web
docker compose up -d --build --force-recreate --remove-orphans
docker compose logs -f --tail=100 web
```

Antes de atualizar, confirme backup recente. Como o Compose usa `latest`, uma
atualização pode alterar a versão do servidor. Se houver problema, restaure o
mundo e avalie fixar uma tag conhecida da imagem no `docker-compose.yml`.

## HTTPS

O certificado autoassinado é gerado em `web-certs/` e persiste entre reinícios.
Para usar certificado próprio, coloque `server.crt` e `server.key` nesse
diretório, defina `WEB_TLS_AUTO_GENERATE=false` em `web.env` e reinicie o
serviço web. A chave deve permanecer fora do Git e com permissões restritas.

## Diagnóstico rápido

- `docker compose ps`: confirma o estado dos dois containers;
- `docker compose logs --tail=200 valheim`: mostra inicialização, autenticação e
  salvamento;
- `docker compose logs --tail=200 web`: mostra login, senha temporária,
  certificado e erros da aplicação;
- `curl -k https://127.0.0.1:8443/healthz`: verifica HTTPS sem autenticação;
- se a alteração de ambiente não aparecer, use
  `docker compose up -d --force-recreate valheim`;
- com `CROSSPLAY=true`, o acesso utiliza relay; se desativar, revise rede e
  encaminhamento de portas;
- o painel depende de `/var/run/docker.sock`, portanto o socket precisa estar
  disponível para o serviço web. Esse acesso é privilegiado e a porta 8443
  deve ficar restrita a uma rede confiável.
