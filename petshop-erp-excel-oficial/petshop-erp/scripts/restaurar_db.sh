#!/usr/bin/env bash
#
# Restaura um backup do Pet Shop ERP, substituindo o banco atual.
# Leia docs/backup_restauracao.md antes de usar em produção.
#
set -Eeuo pipefail
umask 077

source "$(dirname "${BASH_SOURCE[0]}")/_comum.sh"

uso() {
  cat <<'TEXTO'
Uso: scripts/restaurar_db.sh ARQUIVO.dump [--sim] [--forcar] [--sem-seguranca]

  --sim             não pede confirmação (para automação)
  --forcar          encerra as conexões abertas no banco antes de restaurar
  --sem-seguranca   não faz o backup de segurança do banco atual (não recomendado)

Variável opcional:
  RESTAURAR_PARA=outro_banco   restaura em outro banco (usado nos ensaios)
TEXTO
}

ARQUIVO=""
CONFIRMADO=0
FORCAR=0
SEM_SEGURANCA=0
for argumento in "$@"; do
  case "$argumento" in
    --sim) CONFIRMADO=1 ;;
    --forcar) FORCAR=1 ;;
    --sem-seguranca) SEM_SEGURANCA=1 ;;
    -h|--help) uso; exit 0 ;;
    -*) echo "Opção desconhecida: $argumento" >&2; uso; exit 1 ;;
    *) ARQUIVO="$argumento" ;;
  esac
done

if [ -z "$ARQUIVO" ]; then
  uso
  exit 1
fi
if [ ! -f "$ARQUIVO" ]; then
  echo "ERRO: arquivo não encontrado: $ARQUIVO" >&2
  exit 1
fi
ARQUIVO="$(cd "$(dirname "$ARQUIVO")" && pwd)/$(basename "$ARQUIVO")"

exigir_comandos pg_restore psql sha256sum
carregar_banco
DB_DESTINO="${RESTAURAR_PARA:-$DB_NAME}"

trap 'log "ERRO: a restauração falhou (linha $LINENO). A restauração é feita em uma única transação: se o erro ocorreu durante ela, o banco continua como estava."; exit 1' ERR

# 1) Confere o arquivo
if [ -f "$ARQUIVO.sha256" ]; then
  if ( cd "$(dirname "$ARQUIVO")" && sha256sum --check --status "$(basename "$ARQUIVO").sha256" ); then
    log "Checksum do backup conferido."
  else
    log "ERRO: o checksum não confere. O arquivo pode estar corrompido."
    exit 1
  fi
else
  log "AVISO: arquivo .sha256 não encontrado; a conferência do checksum foi pulada."
fi
pg_restore --list "$ARQUIVO" > /dev/null

# 2) Confirmação
echo "Backup a restaurar: $(basename "$ARQUIVO")"
echo "Banco que será SUBSTITUÍDO: $DB_DESTINO em $DB_HOST:$DB_PORT"
if [ "$CONFIRMADO" -ne 1 ]; then
  read -r -p "Digite RESTAURAR para continuar: " resposta
  if [ "$resposta" != "RESTAURAR" ]; then
    echo "Cancelado."
    exit 1
  fi
fi

PSQL=(psql --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" --dbname="$DB_DESTINO" \
      --no-password -v ON_ERROR_STOP=1 -qtA)

# 3) O sistema precisa estar parado
conexoes="$("${PSQL[@]}" -c "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid();")"
if [ "$conexoes" -gt 0 ]; then
  if [ "$FORCAR" -eq 1 ]; then
    log "Encerrando $conexoes conexão(ões) aberta(s) no banco..."
    "${PSQL[@]}" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid();" > /dev/null
    sleep 2
  else
    echo "ERRO: há $conexoes conexão(ões) aberta(s) no banco. Pare o sistema antes de restaurar" >&2
    echo "      (ou use --forcar para encerrá-las, depois de parar o sistema)." >&2
    exit 1
  fi
fi

# 4) Backup de segurança do estado atual
if [ "$SEM_SEGURANCA" -ne 1 ]; then
  log "Fazendo o backup de segurança do banco atual..."
  BACKUP_PREFIXO=antes_restauracao BACKUP_DB_NOME="$DB_DESTINO" "$PROJETO/scripts/backup_db.sh"
fi

# 5) Restauração (tudo ou nada)
log "Restaurando '$(basename "$ARQUIVO")' em '$DB_DESTINO'..."
pg_restore --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" --dbname="$DB_DESTINO" \
           --no-password --clean --if-exists --no-owner --no-privileges \
           --single-transaction --exit-on-error "$ARQUIVO"
log "Restauração concluída."

# 6) Migrations (o backup pode ser de uma versão anterior do sistema)
if [ "$DB_DESTINO" = "$DB_NAME" ]; then
  if [ -x "$PROJETO/.venv/bin/python" ]; then
    log "Aplicando migrations pendentes..."
    "$PROJETO/.venv/bin/python" "$PROJETO/manage.py" migrate --noinput
  else
    log "AVISO: ambiente virtual não encontrado. Execute 'python manage.py migrate' manualmente."
  fi
fi

# 7) Conferência
echo
echo "Registros por tabela em '$DB_DESTINO':"
for tabela in auth_user produtos_produto estoque_movimentacaoestoque vendas_venda \
              financeiro_fluxocaixa financeiro_contapagar financeiro_contareceber logs_logacao; do
  quantidade="$("${PSQL[@]}" -c "SELECT count(*) FROM $tabela;" 2>/dev/null || echo '?')"
  printf '  %-34s %s\n' "$tabela" "$quantidade"
done
echo
log "Pronto. Inicie o sistema novamente e confira o login, os produtos e o saldo do caixa."