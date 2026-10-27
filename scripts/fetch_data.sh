#!/usr/bin/env bash
# Download the Meridian simulated geo dataset and verify its checksum.
set -euo pipefail
URL="https://raw.githubusercontent.com/google/meridian/main/meridian/data/simulated_data/csv/geo_all_channels.csv"
SHA256="d9ee016f7cd21f5c90b50da10a794af91a372b69f881d3caa266edd41fdafbf6"
OUT="data/raw/geo_all_channels.csv"
mkdir -p "$(dirname "$OUT")"
[ -f "$OUT" ] || curl -sSL -o "$OUT" "$URL"
if command -v sha256sum >/dev/null; then
  echo "$SHA256  $OUT" | sha256sum -c -
else
  echo "$SHA256  $OUT" | shasum -a 256 -c -
fi
