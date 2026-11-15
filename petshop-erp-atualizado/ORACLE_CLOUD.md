# Pet Shop ERP na Oracle Cloud Always Free

Arquitetura (a mesma que você pediu; só o proxy é o Caddy, que já está no projeto):

```
Internet → Caddy (80/443, SSL automático) → Gunicorn (127.0.0.1:8000) → Django → PostgreSQL (localhost)
```

Tudo roda em **uma única VM**. O PostgreSQL só escuta em `localhost`; nada além de 22, 80 e 443 fica aberto.

## 1. Limites reais da camada gratuita

Conferidos na documentação oficial da Oracle em nov/2026
(<https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm>):

| Recurso | Limite Always Free |
|---|---|
| Ampere A1 (ARM) | **2 OCPU e 12 GB no total** (1.500 OCPU-h e 9.000 GB-h por mês). Atenção: ainda circula a informação antiga de "4 OCPU / 24 GB"; não vale mais. |
| AMD Micro | até 2 VMs de 1/8 OCPU e 1 GB |
| Disco (boot + block) | 200 GB no total; máx. 5 backups de volume |
| Saída de dados | 10 TB/mês |
| Instância ociosa | **pode ser recuperada** se, por 7 dias, CPU (p95) < 20 %, rede < 20 % e (só A1) memória < 20 % |

Outros pontos que você deve saber:

- A criação da conta pede cartão de crédito (verificação). Dentro dos limites acima o custo é zero.
- Passar do limite pode gerar cobrança: crie um **orçamento com alerta** (Billing → Budgets, valor baixo, ex.: US$ 1).
- É comum aparecer "Out of host capacity" ao criar a VM A1. Tente outro horário/domínio de disponibilidade. Plano B: VM AMD Micro (1 GB) com 2 workers do Gunicorn e 2 GB de swap, bem mais apertada.
- O risco de **recuperação por ociosidade** é real num sistema pequeno. Não consegui confirmar na documentação se converter a conta para *Pay As You Go* (continuando só dentro dos limites gratuitos) elimina esse risco; confira com a Oracle antes de depender disso. O que protege de verdade é ter **backup fora da VM** (seção 8).

## 2. Tamanho da VM e sistema

- Shape **VM.Standard.A1.Flex, 1 OCPU, 6 GB**, boot volume 50 GB. Sobra metade da cota para uma segunda VM de teste, e o ERP (Django + PostgreSQL + Caddy) usa pouco.
- **Ubuntu 24.04 LTS (aarch64)**: Python 3.12 e PostgreSQL 16 nos repositórios oficiais. Todas as dependências do projeto têm versão para ARM (`psycopg[binary]`, `gunicorn`, `whitenoise`; `openpyxl` é Python puro).
- Domínio: o SSL do Caddy exige um nome. Opções de custo zero: subdomínio grátis do DuckDNS. Com domínio próprio (.com.br, em torno de R$ 40/ano, confirme no Registro.br) o endereço fica mais profissional.

## 3. Rede e firewall (os dois lugares!)

1. **Console Oracle** (VCN → Security List da subnet pública): entrada TCP **22** (de preferência só do seu IP), **80** e **443** (0.0.0.0/0).
2. **Dentro da VM** (as imagens Ubuntu da Oracle vêm com regras `iptables` que bloqueiam 80/443):

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

Não habilite o `ufw` junto; use um ou outro. SSH somente com chave (padrão da Oracle). Não abra a porta 5432 nem a 8000.

## 4. Pacotes, PostgreSQL e código

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install python3-venv python3-dev git postgresql postgresql-client unattended-upgrades

# banco (troque a senha; ela vai para o .env)
sudo -u postgres psql -c "CREATE USER petshop_user WITH PASSWORD 'TROQUE_ESTA_SENHA';"
sudo -u postgres psql -c "CREATE DATABASE petshop_db OWNER petshop_user ENCODING 'UTF8';"

# código (git clone, ou envie a pasta com scp/rsync)
cd ~ && git clone SEU_REPOSITORIO petshop && cd petshop
```

Ajuste fino opcional em `/etc/postgresql/16/main/conf.d/petshop.conf` (reinicie o serviço depois):
`shared_buffers = 512MB`, `effective_cache_size = 2GB`, `max_connections = 30`.

## 5. Configuração do Django (`.env`)

```bash
cp deploy/env.producao.exemplo .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(60))"   # use como DJANGO_SECRET_KEY
```

Edite no `.env`: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS` (com `https://` e o seu domínio), `DJANGO_ADMIN_URL`, `DB_PASSWORD`, e **`CLIENT_IP_HEADER=HTTP_X_FORWARDED_FOR`** (o Caddy preenche esse cabeçalho; o log de auditoria e o bloqueio de login errado dependem do IP correto). Comece com `DJANGO_HSTS_SECONDS=3600` e só suba para 1 ano depois de tudo funcionando.

## 6. Instalar e subir

```bash
chmod +x deploy/*.sh scripts/*.sh
./deploy/atualizar.sh            # venv, pip, backup, check --deploy, migrate, collectstatic, grupos
.venv/bin/python manage.py createsuperuser
./deploy/instalar_servico.sh     # Gunicorn como serviço systemd (inicia com a VM e reinicia se cair)
```

O `atualizar.sh` é também o comando de **todas as futuras atualizações** (`git pull` + migrations + reinício).

## 7. Caddy (proxy + SSL)

```bash
sudo apt -y install debian-keyring debian-archive-keyring apt-transport-https curl gnupg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt -y install caddy
```

`/etc/caddy/Caddyfile` (aponte antes o DNS do domínio, registro A, para o IP público da VM):

```
petshop.seudominio.com {
    encode zstd gzip
    request_body {
        max_size 6MB
    }
    reverse_proxy 127.0.0.1:8000
}
```

`sudo systemctl reload caddy`. O certificado Let's Encrypt é emitido e renovado sozinho. O limite de 6 MB cobre o upload de planilha (o sistema já limita a 5 MB).

**Se preferir Nginx:** `sudo apt install nginx certbot python3-certbot-nginx`, um `server` com `client_max_body_size 6m;`, `proxy_pass http://127.0.0.1:8000;` e os cabeçalhos `Host`, `X-Forwarded-For $remote_addr` e `X-Forwarded-Proto $scheme`; depois `sudo certbot --nginx -d seu.dominio` e `CLIENT_IP_HEADER=HTTP_X_FORWARDED_FOR`. Funciona igual, com mais passos manuais.

## 8. Backups (não pule)

Os scripts do projeto já fazem `pg_dump` diário às 02:30, com retenção de 35 dias:

```bash
./scripts/instalar_backup_agendado.sh
./scripts/backup_db.sh --status
```

Mas uma cópia **na mesma VM** some junto com ela (inclusive em caso de recuperação por ociosidade). Envie para fora, por exemplo com `rclone` (Oracle Object Storage, Google Drive ou Backblaze B2 — confira a cota gratuita de cada um) em uma linha de cron às 03:30:

```
30 3 * * * rclone copy ~/petshop/var/backups REMOTO:petshop-backups --max-age 48h
```

Faça também, uma vez por semana, `scp` de um `.dump` para o seu computador, guarde uma cópia do `.env` em lugar seguro (ele não entra no backup) e **teste a restauração** com `scripts/testar_restauracao.sh` (guia em `scripts/backup_restauracao.md`). Os 5 backups de volume gratuitos da Oracle são um bônus, não o plano principal.

## 9. Levar os dados atuais para a nuvem

No seu computador: `pg_dump -Fc --no-owner -f petshop.dump petshop_db`. Envie com `scp`. Na VM:
`pg_restore --no-owner --role=petshop_user -d petshop_db petshop.dump`.
Atenção: a versão do PostgreSQL do seu computador não pode ser maior que a da VM (16). Depois rode `./deploy/atualizar.sh`.

## 10. O que testar depois de subir

1. `https://seu.dominio` abre com cadeado e redireciona o `http://`.
2. Login funciona; erro de senha 5 vezes bloqueia (tela 429) e aparece em Logs com o **IP real**.
3. Vendedor não vê "Importar/Exportar" e recebe 403 se digitar a URL.
4. Exportar Excel baixa a planilha; importar de volta resulta em "sem alteração".
5. `sudo reboot` e confirme que o sistema volta sozinho (`systemctl is-active petshop caddy postgresql`).
6. `./scripts/backup_db.sh --status` sem alerta e a cópia externa chegou ao destino.
7. `journalctl -u petshop -f` para acompanhar erros; `var/log/petshop.log` guarda o log da aplicação.

## 11. Custos

| Item | Custo |
|---|---|
| VM A1 1 OCPU/6 GB, 50 GB de disco, 10 TB de saída | R$ 0 (dentro do Always Free) |
| SSL (Let's Encrypt via Caddy) | R$ 0 |
| Domínio | R$ 0 (DuckDNS) ou ~R$ 40/ano |
| Backup externo | R$ 0 dentro das cotas gratuitas do destino escolhido |
