#!/usr/bin/env bash
# Configuração e funções compartilhadas pelos scripts de backup e restauração.
# Este arquivo é carregado com "source" pelos outros scripts.

PROJETO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARQUIVO_ENV="$PROJETO/.env"

# Lê uma chave do .env sem executá-lo (os valores podem ter caracteres especiais).
ler_env() {
  local chave="$1" padrao="${2:-}" linha valor
  linha="$(grep -E "^[[:space:]]*${chave}[[:space:]]*=" "$ARQUIVO_ENV" 2>/dev/null | tail -n 1 || true)"
  if [ -z "$linha" ]; then
    printf '%s' "$padrao"
    return 0
  fi
  valor="${linha#*=}"
  valor="$(printf '%s' "$valor" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  case "$valor" in
    \"*\") valor="${valor#\"}"; valor="${valor%\"}" ;;
    \'*\') valor="${valor#\'}"; valor="${valor%\'}" ;;
  esac
  if [ -z "$valor" ]; then
    valor="$padrao"
  fi
  printf '%s' "$valor"
}

DIR_BACKUP="${BACKUP_DIR:-$(ler_env BACKUP_DIR "$PROJETO/var/backups")}"
DIR_LOG="$PROJETO/var/log"
mkdir -p "$DIR_BACKUP" "$DIR_LOG"
chmod 700 "$DIR_BACKUP" 2>/dev/null || true

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$DIR_LOG/backup.log"
}

# Carrega as credenciais do banco a partir do .env.
carregar_banco() {
  if [ ! -f "$ARQUIVO_ENV" ]; then
    echo "ERRO: arquivo .env não encontrado em $PROJETO" >&2
    exit 1
  fi
  DB_NAME="${BACKUP_DB_NOME:-$(ler_env DB_NAME petshop_db)}"
  DB_USER="$(ler_env DB_USER petshop_user)"
  DB_HOST="$(ler_env DB_HOST localhost)"
  DB_PORT="$(ler_env DB_PORT 5432)"
  DB_PASSWORD="$(ler_env DB_PASSWORD)"
  if [ -z "$DB_PASSWORD" ]; then
    echo "ERRO: DB_PASSWORD não está definido no .env" >&2
    exit 1
  fi
  export PGPASSWORD="$DB_PASSWORD"
}

exigir_comandos() {
  local comando
  for comando in "$@"; do
    if ! command -v "$comando" >/dev/null 2>&1; then
      echo "ERRO: comando '$comando' não encontrado (instale o pacote postgresql-client)." >&2
      exit 1
    fi
  done
}