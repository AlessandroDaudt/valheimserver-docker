# Runbook operacional

Este documento cobre as tarefas de manutenção do servidor Valheim. Execute os
comandos a partir da raiz do projeto.

## Ciclo de vida

```powershell
# Subir em segundo plano
docker compose up -d

# Ver estado e logs
docker compose ps
docker compose logs -f --tail=100 valheim

# Parar com o período de encerramento configurado
docker compose stop valheim

# Reiniciar
docker compose restart valheim
```

O `docker-compose.yml` usa `restart: unless-stopped` e um período de parada de
dois minutos, permitindo que o servidor salve o estado antes de encerrar.

## Alterar a configuração

1. Pare ou reinicie o serviço conforme a alteração.
2. Edite `valheim.env` localmente.
3. Recrie o container:

   ```powershell
   docker compose up -d --force-recreate
   ```

Não coloque senhas ou outros segredos em `docker-compose.yml`, no README ou em
arquivos que serão versionados.

## Backups automáticos

Os backups estão habilitados por `BACKUPS=true`, são agendados por
`BACKUPS_CRON=5 * * * *` — minuto 5 de cada hora — e têm retenção configurada
por `BACKUPS_MAX_AGE=7`. Os arquivos são gravados em
`config/backups/` como ZIPs.

Confirme a geração de backups com:

```powershell
Get-ChildItem .\config\backups -File | Sort-Object LastWriteTime -Descending | Select-Object -First 10 Name,Length,LastWriteTime
```

Backups são a proteção de recuperação do mundo e não devem ser armazenados no
Git. Mantenha uma cópia em um destino de backup apropriado e separado do
computador do servidor.

## Restauração de um backup

O ZIP atual contém o caminho `config/worlds_local/`. Para restaurar:

1. Escolha o ZIP correto em `config/backups/`.
2. Pare o serviço:

   ```powershell
   docker compose stop valheim
   ```

3. Faça uma cópia temporária de `config/worlds_local/` fora do projeto.
4. Extraia o ZIP na raiz do projeto, preservando os caminhos:

   ```powershell
   Expand-Archive -LiteralPath .\config\backups\worlds-AAAAmmdd-HHMMSS.zip -DestinationPath . -Force
   ```

5. Inicie o servidor e acompanhe os logs:

   ```powershell
   docker compose up -d
   docker compose logs -f --tail=100 valheim
   ```

O `-Force` substitui os arquivos do mundo. Verifique o nome do arquivo e
preserve uma cópia do estado atual antes de executar a extração.

## Atualização da imagem

Como o Compose usa a tag `latest`, uma atualização pode alterar a versão do
servidor. Antes de atualizar, confirme que existe um backup recente e, então:

```powershell
docker compose pull valheim
docker compose up -d
docker compose logs -f --tail=100 valheim
```

Se houver problema, pare o serviço, restaure o mundo a partir de um backup e
avalie voltar para uma tag de imagem conhecida no `docker-compose.yml`.

## Diagnóstico rápido

- `docker compose ps`: confirma se o container está em execução.
- `docker compose logs --tail=200 valheim`: mostra erros de inicialização,
  autenticação ou salvamento.
- Se a alteração de ambiente não aparecer, use
  `docker compose up -d --force-recreate`.
- Com `CROSSPLAY=true`, o acesso utiliza o relay do crossplay. Se essa opção
  for desativada, revise a rede e o encaminhamento de portas antes de testar.

