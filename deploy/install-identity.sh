#!/bin/sh
# Optional signed-token dependencies. Does not enable a provider or open ports.
set -eu
[ "$(id -u)" = 0 ]
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-jwt python3-cryptography
python3 -c 'import jwt; from cryptography.hazmat.primitives.asymmetric import rsa; print("Signed OIDC dependencies available; configure your optional provider in Settings.")'
