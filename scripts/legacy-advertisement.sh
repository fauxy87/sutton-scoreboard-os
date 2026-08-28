#!/bin/bash
set -e

HCITOOL="/usr/bin/hcitool"
ADAPTER="hci0"

if [ "${1:-start}" = "stop" ]; then
    "$HCITOOL" -i "$ADAPTER" cmd 0x08 0x000a 00 || true
    exit 0
fi

"$HCITOOL" -i "$ADAPTER" cmd 0x08 0x000a 00 || true

"$HCITOOL" -i "$ADAPTER" cmd 0x08 0x0006 \
  a0 00 a0 00 00 00 00 \
  00 00 00 00 00 00 \
  07 00

"$HCITOOL" -i "$ADAPTER" cmd 0x08 0x0008 \
  15 \
  02 01 06 \
  11 07 c1 5b 3e c5 0e 3a 30 85 04 43 64 b6 15 6a 0d 5a \
  00 00 00 00 00 00 00 00 00 00

"$HCITOOL" -i "$ADAPTER" cmd 0x08 0x0009 \
  09 \
  08 09 53 43 4f 52 45 4f 53 \
  00 00 00 00 00 00 00 00 00 00 00 \
  00 00 00 00 00 00 00 00 00 00 00

"$HCITOOL" -i "$ADAPTER" cmd 0x08 0x000a 01

echo "SCOREOS legacy advertising active"
