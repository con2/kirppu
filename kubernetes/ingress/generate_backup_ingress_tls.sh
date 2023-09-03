#!/bin/bash
set -xueo pipefail

KEY_FILE=backup-ingress-tls.key
CERT_FILE=backup-ingress-tls.crt
HOST=${HOST:-vara.kirppu.tracon.fi}
SECRET_NAME=ingress-backup
NAMESPACE=${NAMESPACE:-kirppu}

openssl req -x509 -nodes -days 3650 -newkey rsa:4096 -keyout ${KEY_FILE} -out ${CERT_FILE} -subj "/CN=${HOST}/O=${HOST}" -addext "subjectAltName = DNS:${HOST}"
kubectl create secret tls ${SECRET_NAME} --key ${KEY_FILE} --cert ${CERT_FILE} --namespace ${NAMESPACE}
