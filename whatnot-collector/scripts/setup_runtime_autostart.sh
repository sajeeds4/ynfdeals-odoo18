#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

units=(
  "deploy/systemd/user/whatnot-redis.service"
  "deploy/systemd/user/whatnot-fastapi.service"
  "deploy/systemd/user/whatnot-celery-default.service"
  "deploy/systemd/user/whatnot-celery-analytics.service"
  "deploy/systemd/user/whatnot-celery-ingest.service"
  "deploy/systemd/user/whatnot-celery-business.service"
  "deploy/systemd/user/whatnot-celery-beat.service"
  "whatnot-scanner.service"
)

enabled_units=()

echo "Installing user systemd units from: $REPO_ROOT"
mkdir -p "$USER_SYSTEMD_DIR"

for unit_path in "${units[@]}"; do
  source_path="$REPO_ROOT/$unit_path"
  unit_name="$(basename "$unit_path")"
  if [[ ! -f "$source_path" ]]; then
    echo "Skipping missing unit template: $unit_path"
    continue
  fi
  cp "$source_path" "$USER_SYSTEMD_DIR/$unit_name"
  enabled_units+=("$unit_name")
  echo "Installed $unit_name"
done

systemctl --user daemon-reload

if command -v loginctl >/dev/null 2>&1; then
  linger_state="$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || true)"
  if [[ "$linger_state" != "yes" ]]; then
    if loginctl enable-linger "$USER" 2>/dev/null; then
      echo "Enabled lingering for $USER so user services can survive logout/reboot."
    else
      echo "Warning: could not enable lingering automatically. Run: loginctl enable-linger $USER"
    fi
  fi
fi

for unit_name in "${enabled_units[@]}"; do
  systemctl --user enable "$unit_name" >/dev/null
  systemctl --user restart "$unit_name"
done

echo
echo "Runtime service status:"
systemctl --user --no-pager --plain --full status "${enabled_units[@]}" || true
