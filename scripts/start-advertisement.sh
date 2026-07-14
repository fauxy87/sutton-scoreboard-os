#!/bin/bash
set -e

BTMGMT="/usr/bin/btmgmt"
UUID="5a0d6a15-b664-4304-8530-3a0ec53e5bc1"

echo "Waiting for Bluetooth controller..."

for attempt in $(seq 1 15); do
    if timeout 3 "$BTMGMT" info </dev/null >/dev/null 2>&1; then
        echo "Bluetooth controller ready."
        break
    fi

    if [ "$attempt" -eq 15 ]; then
        echo "Bluetooth controller did not become ready."
        exit 1
    fi

    sleep 1
done

echo "Preparing BLE advertisement..."

timeout 10 "$BTMGMT" connectable on </dev/null
timeout 10 "$BTMGMT" power on </dev/null

# This can return Invalid Parameters when no advert exists, which is harmless.
timeout 10 "$BTMGMT" clr-adv </dev/null || true

timeout 10 "$BTMGMT" add-adv \
    -c \
    -g \
    -n \
    -u "$UUID" \
    1 </dev/null

echo "BLE advertisement started."
"$BTMGMT" advinfo </dev/null
