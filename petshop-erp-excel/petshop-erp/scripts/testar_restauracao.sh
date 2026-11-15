#!/usr/bin/env bash
#
# Ensaio de restauração: restaura o último backup (ou o informado) em um banco
# temporário, compara com o banco real e apaga o temporário.
# Não altera o banco real. Precisa de sudo (para criar o banco temporário).
#
# Uso: scripts/testar_restauracao.sh [ARQUIVO.dump]
#
set -Eeuo pipefail
umask 077

source "$(dirname "${BASH_SOURCE[0]}")/_comum.sh"

exigir_comandos psql pg_restore sudo
carregar_banco

DB_TESTE="petshop_teste_restore"
ARQUIVO="${1:-$(find "$DIR_BACKUP" -maxdepth 1 -type f -name 'petshop_*.dump' | sort | tail -n 1)}"
if [ -z "$ARQUIVO" ]; then
  echo "ERRO: nenhum backup encontrado em $DIR_BACKUP" >&2
  exit 1
fi

# Comandos de administração do PostgreSQL (executados como o usuário postgres).
admin_pg() {
  ( cd /tmp && sudo -u postgres "$@" )
}

limpar() {
  admin_pg dropdb --if-exists "$DB_TESTE" > /dev/null 2>&1 || true
}
trap limpar EXIT

contar() {
  psql --host="$DB_HOST" --port="$DB_PORT" --username="$DB_USER" --dbname="$1" \
       --no-password -qtAc "SELECT count(*) FROM $2;" 2>/dev/null || echo "?"
}

log "Ensaio de restauração com $(basename "$ARQUIVO")..."
admin_pg dropdb --if-exists "$DB_TESTE"
admin_pg createdb --owner "$DB_USER" "$DB_TESTE"

RESTAURAR_PARA="$DB_TESTE" "$PROJETO/scripts/restaurar_db.sh" "$ARQUIVO" --sim --sem-seguranca

echo
printf '%-34s %12s %12s\n' "Tabela" "Banco real" "Restaurado"
for tabela in auth_user produtos_produto estoque_movimentacaoestoque vendas_venda \
              financeiro_fluxocaixa financeiro_contapagar financeiro_contareceber logs_logacao; do
  printf '%-34s %12s %12s\n' "$tabela" "$(contar "$DB_NAME" "$tabela")" "$(contar "$DB_TESTE" "$tabela")"
done
echo
log "Ensaio concluído: o backup foi restaurado com sucesso em um banco temporário (removido ao final)."
echo "Obs.: diferenças são normais se o sistema recebeu dados depois do backup."