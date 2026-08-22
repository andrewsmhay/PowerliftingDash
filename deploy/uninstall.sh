#!/usr/bin/env bash
# Removes the systemd service and installed code for a native
# PowerliftingDash install. Does NOT delete /var/lib/powerliftingdash
# (your SQLite database) unless you pass --purge-data.
#
# Usage:
#   sudo ./deploy/uninstall.sh [--purge-data]

set -euo pipefail

APP_USER="powerliftingdash"
INSTALL_DIR="/opt/powerliftingdash"
CONFIG_DIR="/etc/powerliftingdash"
DATA_DIR="/var/lib/powerliftingdash"
SERVICE_NAME="powerliftingdash"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root, e.g.: sudo ./deploy/uninstall.sh" >&2
  exit 1
fi

echo "==> Stopping and disabling ${SERVICE_NAME}"
systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload

echo "==> Removing installed code at ${INSTALL_DIR}"
rm -rf "${INSTALL_DIR}"

echo "==> Removing config at ${CONFIG_DIR}"
rm -rf "${CONFIG_DIR}"

if [[ "${1:-}" == "--purge-data" ]]; then
  echo "==> Purging data directory ${DATA_DIR} (this deletes your database)"
  rm -rf "${DATA_DIR}"
else
  echo "==> Leaving ${DATA_DIR} in place (pass --purge-data to also delete it)"
fi

if id "${APP_USER}" >/dev/null 2>&1; then
  echo "==> Removing system user ${APP_USER}"
  userdel "${APP_USER}" 2>/dev/null || true
fi

echo "==> Done."
