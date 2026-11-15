# Backup e restauração do Pet Shop ERP

## O que existe

| Item | Detalhe |
|---|---|
| O que é copiado | Todo o banco PostgreSQL (produtos, estoque, vendas, financeiro, usuários e logs) |
| Quando | Todo dia às 02:30 (se a máquina estava desligada, roda ao ligar) |
| Onde | `var/backups/` (e, se configurado, também em `BACKUP_COPIA_EXTERNA`) |
| Arquivos | `petshop_AAAA-MM-DD_HHMMSS.dump` e o `.sha256` correspondente |
| Retenção | 35 dias (padrão). Nunca menos que 30 dias, e sempre pelo menos 7 arquivos |
| Quanto dado posso perder | No máximo o que aconteceu desde o último backup (até 24 horas) |
| Log | `var/log/backup.log` |

O que o backup **não** inclui: o arquivo `.env` (guarde uma cópia protegida em outro lugar, é onde estão as senhas) e o código do sistema (fica no Git).

## Configuração opcional (no `.env`)

```
BACKUP_RETENCAO_DIAS=35
BACKUP_MINIMO_ARQUIVOS=7
BACKUP_COPIA_EXTERNA=/caminho/para/hd-externo-ou-pasta-sincronizada
```

Recomendação forte: configure `BACKUP_COPIA_EXTERNA` para uma pasta que fique **fora da máquina do sistema** (HD externo, pasta sincronizada com um serviço gratuito, disco montado de outro computador). Também é possível puxar os arquivos de vez em quando, por exemplo:

```
scp usuario@servidor:~/petshop/var/backups/petshop_*.dump .
```

## Instalar o agendamento

```
chmod +x scripts/*.sh
./scripts/instalar_backup_agendado.sh
```

## Conferir se está funcionando

```
./scripts/backup_db.sh --status
```

Mostra o último backup. Se ele tiver mais de 26 horas, avisa. Confira isso de vez em quando (por exemplo, toda segunda-feira).

Fazer um backup agora, fora do horário:

```
./scripts/backup_db.sh
```

## Restaurar um backup (dados perdidos ou apagados por engano)

1. **Pare o sistema** (feche o servidor da aplicação). O script recusa continuar se houver conexões abertas no banco.
2. Escolha o backup:
   ```
   ls -lh var/backups/
   ```
3. Restaure:
   ```
   ./scripts/restaurar_db.sh var/backups/petshop_AAAA-MM-DD_HHMMSS.dump
   ```
   O script confere o arquivo, pede que você digite `RESTAURAR`, faz um backup de segurança do banco atual (`antes_restauracao_*.dump`), restaura tudo em uma única transação e aplica as migrations.
4. **Inicie o sistema** e confira: login, lista de produtos, últimas vendas e saldo do caixa.
5. Se a restauração não era o que você queria, volte ao estado anterior restaurando o arquivo `antes_restauracao_*.dump` com o mesmo comando.

Se algo falhar durante a restauração, o banco continua exatamente como estava (a restauração é "tudo ou nada").

## Perdi o servidor inteiro (recuperação total)

1. Prepare uma máquina nova seguindo a instalação do sistema (Etapas 1, 2 e 12): pacotes, PostgreSQL, ambiente virtual e código do Git.
2. Recupere o seu `.env` (a cópia guardada em segurança) e coloque na raiz do projeto.
3. Crie o usuário e o banco vazios, com **o mesmo nome e a mesma senha** do `.env`:
   ```
   sudo -u postgres psql -c "CREATE USER petshop_user WITH PASSWORD 'SENHA_DO_ENV';"
   sudo -u postgres psql -c "CREATE DATABASE petshop_db OWNER petshop_user ENCODING 'UTF8';"
   ```
4. Copie o backup mais recente (da cópia externa) para `var/backups/`.
5. Restaure:
   ```
   ./scripts/restaurar_db.sh var/backups/petshop_AAAA-MM-DD_HHMMSS.dump --sem-seguranca
   ```
6. Suba o sistema, confira os dados e reinstale o agendamento (`./scripts/instalar_backup_agendado.sh`).

Observação: o PostgreSQL da máquina nova deve ser da mesma versão ou mais novo que o da máquina antiga.

## Ensaio mensal (faça pelo menos uma vez por mês)

```
./scripts/testar_restauracao.sh
```

Restaura o último backup em um banco temporário, compara a contagem de registros com o banco real e apaga o temporário. Não mexe no banco real. Se este teste passar, você sabe que o backup serve.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `password authentication failed` | A senha `DB_PASSWORD` do `.env` não é a do usuário no PostgreSQL |
| `pg_dump: command not found` | Instale `postgresql-client` |
| `server version mismatch` | O `pg_dump` instalado é mais antigo que o servidor; instale o cliente da mesma versão |
| `--status` avisa que o backup está velho | Máquina desligada ou timer parado: `systemctl list-timers petshop-backup.timer` e `journalctl -u petshop-backup.service -n 50` |
| Disco cheio | Apague backups muito antigos manualmente ou aumente o disco; o backup falha (e avisa) se não houver espaço |
| Restauração recusada por conexões abertas | Pare o sistema; só use `--forcar` depois de parado |