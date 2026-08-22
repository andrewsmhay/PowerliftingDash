#!/usr/bin/env bash
# Installs PowerliftingDash as a systemd service on a native Linux host
# (tested against Ubuntu/Debian and Amazon Linux/RHEL family cloud images -
# the usual defaults on AWS EC2, GCP Compute Engine and Azure VMs).
#
# Run as root (or with sudo) from anywhere; it copies the repo you run it
# from into /opt/powerliftingdash.
#
# Usage:
#   sudo ./deploy/install.sh
#
# Re-running this script is safe: it updates the code and Python
# dependencies in place and restarts the service, so it also doubles as
# the update procedure (see README "Updating a native install").

set -euo pipefail

APP_USER="powerliftingdash"
INSTALL_DIR="/opt/powerliftingdash"
CONFIG_DIR="/etc/powerliftingdash"
DATA_DIR="/var/lib/powerliftingdash"
SERVICE_NAME="powerliftingdash"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root, e.g.: sudo ./deploy/install.sh" >&2
  exit 1
fi

echo "==> Installing OS packages (python3, venv, pip, rsync)"
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip rsync
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y python3 python3-pip rsync
elif command -v yum >/dev/null 2>&1; then
  yum install -y python3 python3-pip rsync
else
  echo "Could not detect apt-get, dnf or yum. Install Python 3.10+, pip and rsync manually, then re-run this script." >&2
  exit 1
fi

PYTHON_BIN="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3)"
PY_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "==> Using ${PYTHON_BIN} (Python ${PY_VERSION})"
if ! "${PYTHON_BIN}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "PowerliftingDash needs Python 3.10 or newer; found ${PY_VERSION}." >&2
  exit 1
fi

echo "==> Creating system user ${APP_USER}"
if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

echo "==> Copying application code to ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude '.pytest_cache' --exclude 'data' --exclude 'docs' --exclude 'tests' \
  "${REPO_ROOT}/" "${INSTALL_DIR}/"

echo "==> Creating virtual environment and installing dependencies"
if [[ ! -d "${INSTALL_DIR}/.venv" ]]; then
  "${PYTHON_BIN}" -m venv "${INSTALL_DIR}/.venv"
fi
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip -q
"${INSTALL_DIR}/.venv/bin/pip" install -q -r "${INSTALL_DIR}/requirements.txt"

echo "==> Preparing data directory ${DATA_DIR}"
mkdir -p "${DATA_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${DATA_DIR}" "${INSTALL_DIR}"

# Config lives in /etc, separate from the code in /opt, so re-running this
# script to pick up a code update (which resyncs /opt with --delete) never
# touches your customised settings.
mkdir -p "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_DIR}/powerliftingdash.env" ]]; then
  echo "==> Writing default environment file ${CONFIG_DIR}/powerliftingdash.env"
  cp "${REPO_ROOT}/deploy/powerliftingdash.env.example" "${CONFIG_DIR}/powerliftingdash.env"
else
  echo "==> Keeping existing ${CONFIG_DIR}/powerliftingdash.env (not overwriting your settings)"
fi
chown -R "${APP_USER}:${APP_USER}" "${CONFIG_DIR}"
chmod 750 "${CONFIG_DIR}"
chmod 640 "${CONFIG_DIR}/powerliftingdash.env"

echo "==> Installing systemd unit"
cp "${REPO_ROOT}/deploy/systemd/powerliftingdash.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo
echo "==> Done. Checking service status:"
systemctl --no-pager --full status "${SERVICE_NAME}" || true
echo
echo "Edit ${CONFIG_DIR}/powerliftingdash.env then run 'systemctl restart ${SERVICE_NAME}' to change host/port/data location."
echo "Dashboard should be reachable at http://<this-host-ip>:8080/ once the firewall/security group allows that port."
