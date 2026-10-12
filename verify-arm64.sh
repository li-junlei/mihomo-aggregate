#!/bin/sh
set -eu
for image in metacubex/mihomo:v1.19.32 python:3.12-slim-bookworm caddy:2.11.7-alpine; do
  echo "Checking $image"
  docker manifest inspect "$image" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert any(m.get("platform",{}).get("os")=="linux" and m["platform"].get("architecture")=="arm64" for m in d.get("manifests",[])), "No linux/arm64 manifest"; print("linux/arm64 confirmed")'
done
