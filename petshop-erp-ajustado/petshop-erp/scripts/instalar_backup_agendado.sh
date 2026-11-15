#!/usr/bin/env bash
#
# Agenda o backup diário (02:30). Usa systemd timer quando disponível
# (com Persistent=true: se a máquina estava desligada, roda ao ligar)
# e cron como alternativa.
#
# Execute como o usuário dono do projeto (não como root).
#
set -Eeuo pipefail

PROJETO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USUARIO="$(id -un)"

if [ "$(id -u)" -eq 0 ]; then
  echo "Execute como o usuário do projeto, não como root." >&2
  exit 1
fi
if [ ! -x "$PROJETO/scripts/backup_db.sh" ]; then
  echo "Torne os scripts executáveis antes: chmod +x scripts/*.sh" >&2
  exit 1
fi

if [ -d /run/systemd/system ] && command -v systemctl > /dev/null 2>&1; then
  echo "Instalando o agendamento via systemd (será pedida a senha do sudo)..."

  sudo tee /etc/systemd/system/petshop-backup.service > /dev/null <<EOF
[Unit]
Description=Backup diario do PostgreSQL do Pet Shop ERP

[Service]
Type=oneshot
User=$USUARIO
WorkingDirectory=$PROJETO
ExecStart=$PROJETO/scripts/backup_db.sh
Nice=10
EOF

  sudo tee /etc/systemd/system/petshop-backup.timer > /dev/null <<EOF
[Unit]
Description=Agenda o backup diario do Pet Shop ERP

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now petshop-backup.timer
  echo
  systemctl list-timers petshop-backup.timer --no-pager || true
  echo
  echo "Pronto. Para testar agora:  sudo systemctl start petshop-backup.service"
  echo "Para ver o resultado:       journalctl -u petshop-backup.service -n 20 --no-pager"
else
  echo "systemd não disponível: usando o cron."
  linha="30 2 * * * $PROJETO/scripts/backup_db.sh >> $PROJETO/var/log/backup_cron.log 2>&1"
  ( crontab -l 2>/dev/null | grep -vF "scripts/backup_db.sh" || true; echo "$linha" ) | crontab -
  echo "Agendamento criado no cron do usuário $USUARIO:"
  crontab -l | grep -F "scripts/backup_db.sh"
  echo
  echo "Lembre-se: o serviço cron precisa estar ativo (no WSL: sudo service cron start)"
  echo "e a máquina precisa estar ligada às 02:30. Backups perdidos não são recuperados."
fi