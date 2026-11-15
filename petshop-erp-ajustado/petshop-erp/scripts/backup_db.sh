#!/usr/bin/env bash
#
# Backup do banco PostgreSQL do Pet Shop ERP.
#
# Uso:
#   scripts/backup_db.sh            faz o backup agora
#   scripts/backup_db.sh --status   mostra o último backup (saída 1 se tiver mais de 26 horas)
#
# Opções (variáveis de ambiente ou chaves no .env):
#   BACKUP_RETENCAO_DIAS     dias de retenção (padrão 35; nunca menos que 30)
#   BACKUP_MINIMO_ARQUIVOS   quantidade mínima de backups mantidos (padrão 7)
#   BACKUP_COPIA_EXTERNA     pasta onde cada backup também é copiado
#   BACKUP_DIR               pasta dos backups (padrão: var/backups)
#
set -Eeuo pipefail
umask 077

source "$(dirname "${BASH_SOURCE[0]}")/_comum.sh"

PREFIXO="${BACKUP_PREFIXO:-petshop}"
RETENCAO_DIAS="${BACKUP_RETENCAO_DIAS:-$(ler_env BACKUP_RETENCAO_DIAS 35)}"
MINIMO_ARQUIVOS="${BACKUP_MINIMO_ARQUIVOS:-$(ler_env BACKUP_MINIMO_ARQUIVOS 7)}"
COPIA_EXTERNA="${BACKUP_COPIA_EXTERNA:-$(ler_env BACKUP_COPIA_EXTERNA "")}"

case "$RETENCAO_DIAS" in ''|*[!0-9]*) RETENCAO_DIAS=35 ;; esac
case "$MINIMO_ARQUIVOS" in ''|*[!0-9]*) MINIMO_ARQUIVOS=7 ;; esac
if [ "$RETENCAO_DIAS" -lt 30 ]; then
  echo "AVISO: a retenção mínima é de 30 dias; usando 30." >&2
  RETENCAO_DIAS=30
fi

# --- Modo --status ----------------------------------------------------------
if [ "${1:-}" = "--status" ]; then
  ultimo="$(find "$DIR_BACKUP" -maxdepth 1 -type f -name "${PREFIXO}_*.dump" -printf '%T@ %p\n' \
            | sort -n | tail -n 1 | cut -d' ' -f2-)"
  if [ -z "$ultimo" ]; then
    echo "ALERTA: nenhum backup encontrado em $DIR_BACKUP."
    exit 1
  fi
  idade_horas=$(( ( $(date +%s) - $(stat -c %Y "$ultimo") ) / 3600 ))
  total="$(find "$DIR_BACKUP" -maxdepth 1 -type f -name '*.dump' | wc -l)"
  echo "Último backup: $(basename "$ultimo") ($(du -h "$ultimo" | cut -f1)), há ${idade_horas}h."
  echo "Backups guardados: $total."
  if [ "$idade_horas" -gt 26 ]; then
    echo "ALERTA: o último backup tem mais de 26 horas."
    exit 1
  fi
  exit 0
fi

# --- Backup -----------------------------------------------------------------
exigir_comandos pg_dump pg_restore flock sha256sum
carregar_banco

exec 9>"$DIR_BACKUP/.backup.lock"
if ! flock -n 9; then
  log "Já existe um backup em andamento. Nada a fazer."
  exit 0
fi

parcial=""
trap 'log "ERRO: o backup falhou (linha $LINENO)."; if [ -n "$parcial" ]; then rm -f -- "$parcial"; fi; exit 1' ERR

# Remove os 7 dias mais antigos de arquivos parciais que sobraram de falhas.
find "$DIR_BACKUP" -maxdepth 1 -type f -name '*.parcial' -mtime +1 -delete

# Apaga backups mais antigos que a retenção, sempre preservando o mínimo.
podar() {
  local pasta="$1" total
  total="$(find "$pasta" -maxdepth 1 -type f -name '*.dump' | wc -l)"
  if [ "$total" -le "$MINIMO_ARQUIVOS" ]; then
    return 0
  fi
  find "$pasta" -maxdepth 1 -type f -name '*.dump' -mtime +"$RETENCAO_DIAS" -printf '%T@ %p\n' \
    | sort -n | cut -d' ' -f2- \
    | while IFS= read -r arquivo; do
        if [ "$total" -le "$MINIMO_ARQUIVOS" ]; then
          break
        fi
        rm -f -- "$arquivo" "$arquivo.sha256"
        total=$((total - 1))
        log "Removido por retenção: $(basename "$arquivo")"
      done
}

carimbo="$(date '+%Y-%m-%d_%H%M%S')"
destino="$DIR_BACKUP/${PREFIXO}_${carimbo}.dump"
parcial="$destino.parcial"

log "Iniciando backup do banco '$DB_NAME' ($DB_HOST:$DB_PORT)..."
pg_dump --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" --no-password \
        --format=custom --compress=6 --no-owner --no-privileges \
        --file="$parcial" "$DB_NAME"

if [ ! -s "$parcial" ]; then
  log "ERRO: o arquivo de backup ficou vazio."
  rm -f -- "$parcial"
  exit 1
fi
pg_restore --list "$parcial" > /dev/null

mv -- "$parcial" "$destino"
parcial=""
( cd "$DIR_BACKUP" && sha256sum "$(basename "$destino")" > "$(basename "$destino").sha256" )
log "Backup concluído: $(basename "$destino") ($(du -h "$destino" | cut -f1))."

# Só depois de um backup novo ter dado certo é que os antigos podem ser podados.
podar "$DIR_BACKUP"

falha_copia=0
if [ -n "$COPIA_EXTERNA" ]; then
  if [ -d "$COPIA_EXTERNA" ] && [ -w "$COPIA_EXTERNA" ]; then
    cp -- "$destino" "$destino.sha256" "$COPIA_EXTERNA/"
    podar "$COPIA_EXTERNA"
    log "Cópia externa concluída em $COPIA_EXTERNA."
  else
    log "ERRO: pasta de cópia externa indisponível ou sem permissão: $COPIA_EXTERNA"
    falha_copia=1
  fi
fi

total="$(find "$DIR_BACKUP" -maxdepth 1 -type f -name '*.dump' | wc -l)"
log "Backups guardados: $total (retenção de ${RETENCAO_DIAS} dias, mínimo de ${MINIMO_ARQUIVOS} arquivos)."

if [ "$falha_copia" -ne 0 ]; then
  exit 1
fi