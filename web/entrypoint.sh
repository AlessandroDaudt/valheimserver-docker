#!/bin/sh
set -eu

CERT_DIR="${WEB_TLS_DIR:-/certs}"
CERT_FILE="${WEB_TLS_CERT_FILE:-${CERT_DIR}/server.crt}"
KEY_FILE="${WEB_TLS_KEY_FILE:-${CERT_DIR}/server.key}"
HOSTNAME_VALUE="${WEB_HOSTNAME:-localhost}"
AUTO_GENERATE="${WEB_TLS_AUTO_GENERATE:-true}"

mkdir -p "${CERT_DIR}"
if [ ! -f "${CERT_FILE}" ] && [ ! -f "${KEY_FILE}" ]; then
  if [ "${AUTO_GENERATE}" = "false" ]; then
    echo "[valheim-web] Certificados ausentes e WEB_TLS_AUTO_GENERATE=false." >&2
    exit 1
  fi
  echo "[valheim-web] Gerando certificado HTTPS autoassinado para ${HOSTNAME_VALUE}."
  openssl req -x509 -nodes -newkey rsa:4096 -days "${WEB_TLS_DAYS:-825}" \
    -keyout "${KEY_FILE}" -out "${CERT_FILE}" \
    -subj "/CN=${HOSTNAME_VALUE}" \
    -addext "subjectAltName=DNS:${HOSTNAME_VALUE},DNS:localhost,IP:127.0.0.1"
  chmod 600 "${KEY_FILE}"
elif [ ! -f "${CERT_FILE}" ] || [ ! -f "${KEY_FILE}" ]; then
  echo "[valheim-web] WEB_TLS_CERT_FILE e WEB_TLS_KEY_FILE precisam existir juntos." >&2
  exit 1
fi

exec gunicorn \
  --bind 0.0.0.0:8443 \
  --workers "${WEB_WORKERS:-1}" \
  --threads 4 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  --certfile "${CERT_FILE}" \
  --keyfile "${KEY_FILE}" \
  app:app
