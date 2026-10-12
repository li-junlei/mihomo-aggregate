#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p state public config caddy-data caddy-config
chmod 700 state config
if [ ! -f config/sources.yaml ]; then
  cp config/sources.example.yaml config/sources.yaml
fi
if [ ! -f .env ]; then
  token=$(openssl rand -hex 32)
  password=$(openssl rand -hex 24)
  sed -e "s/REPLACE_WITH_64_HEX_CHARACTERS/$token/g" -e "s/REPLACE_WITH_RANDOM_PASSWORD/$password/g" .env.example > .env
fi
chmod 600 .env config/sources.yaml
echo 'Edit .env and config/sources.yaml before starting.'
