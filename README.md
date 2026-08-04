# Servidor Valheim

Configuração do servidor dedicado de Valheim executado com Docker Compose. O
container usa a imagem `ghcr.io/community-valheim-tools/valheim-server:latest`
e monta os diretórios locais `config/` e `data/`.

## Requisitos

- Docker Desktop ou Docker Engine com Docker Compose v2;
- espaço em disco para a instalação do servidor, o mundo e os backups;
- uma senha forte para o servidor.

## Instalação e primeiro acesso

1. Copie `valheim.env.example` para `valheim.env`.
2. Edite `valheim.env`, principalmente `SERVER_PASS`.
3. Inicie o servidor:

   ```powershell
   docker compose up -d
   ```

4. Acompanhe a inicialização:

   ```powershell
   docker compose logs -f --tail=100 valheim
   ```

O servidor é público (`SERVER_PUBLIC=true`), usa crossplay (`CROSSPLAY=true`) e
o mundo atual é `PowerGuido`. O primeiro start pode demorar enquanto o runtime
do servidor é baixado e preparado.

## Operação rápida

```powershell
# Estado dos serviços
docker compose ps

# Parar e iniciar novamente
docker compose stop valheim
docker compose start valheim

# Reiniciar após alterar configuração
docker compose restart valheim

# Atualizar a imagem e recriar o container
docker compose pull valheim
docker compose up -d
```

O procedimento de atualização e restauração está detalhado em
[`docs/OPERACAO.md`](docs/OPERACAO.md).

## Configuração

As variáveis ficam em `valheim.env`, que é local e não deve ser versionado.

| Variável | Função | Valor atual/documentado |
| --- | --- | --- |
| `SERVER_NAME` | Nome exibido do servidor | `PowerGuido_New` |
| `WORLD_NAME` | Nome do mundo | `PowerGuido` |
| `SERVER_PASS` | Senha de acesso | definir localmente |
| `SERVER_PUBLIC` | Publica o servidor na lista | `true` |
| `SERVER_PORT` | Porta principal | `2456` |
| `TZ` | Fuso horário dos agendamentos | `America/Sao_Paulo` |
| `SEED` | Seed usada ao criar o mundo | `EVpmm24uK8` |
| `BACKUPS` | Ativa backups automáticos | `true` |
| `BACKUPS_CRON` | Agenda dos backups | `5 * * * *` |
| `BACKUPS_MAX_AGE` | Retenção em dias | `7` |
| `CROSSPLAY` | Ativa crossplay via relay | `true` |

Depois de alterar variáveis, recrie o container com:

```powershell
docker compose up -d --force-recreate
```

## Administração de jogadores

Coloque um Steam ID por linha nos arquivos abaixo e reinicie o serviço para
aplicar as alterações:

- `config/adminlist.txt`: administradores;
- `config/bannedlist.txt`: jogadores banidos;
- `config/permittedlist.txt`: lista de permitidos, quando usada.

Os comentários de exemplo já existentes nesses arquivos podem permanecer.

## Estrutura e versionamento

| Caminho | Finalidade | Git |
| --- | --- | --- |
| `docker-compose.yml` | definição do serviço e dos volumes | versionar |
| `valheim.env.example` | modelo sem segredo | versionar |
| `valheim.env` | credenciais e configuração local | ignorar |
| `config/*.txt` | listas administrativas | versionar conforme necessário |
| `config/worlds_local/` | mundo, bancos `.db` e backups automáticos do mundo | ignorar |
| `config/backups/` | ZIPs de backup do servidor | ignorar |
| `config/prefs` | preferências geradas pelo runtime | ignorar |
| `data/` | instalação/runtime do servidor | ignorar |

O `.gitignore` evita que esses arquivos sejam adicionados ao Git. Ele não
remove arquivos locais nem tira arquivos que já tenham sido versionados; nesse
último caso, seria necessário removê-los do índice com cuidado.

> **Atenção sobre a nuvem:** este projeto está dentro de uma pasta do
> OneDrive. O `.gitignore` controla apenas o Git; arquivos ignorados ainda
> podem ser sincronizados pelo OneDrive. Para impedir essa sincronização,
> mantenha os dados do servidor fora de uma pasta sincronizada ou configure a
> exclusão no próprio OneDrive.

