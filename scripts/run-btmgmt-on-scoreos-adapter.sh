#!/bin/bash

set -u

PREFERRED_MAC="18:69:45:F3:58:B9"
ADAPTER=""

for attempt in $(seq 1 15); do
    for adapter_path in /sys/class/bluetooth/hci*; do
        [ -d "$adapter_path" ] || continue

        hci=$(basename "$adapter_path")

        mac=$(
            /usr/bin/hciconfig "$hci" 2>/dev/null |
            awk '/BD Address/ {print toupper($3)}'
        )

        if [ "$mac" = "$PREFERRED_MAC" ]; then
            ADAPTER="$hci"
            break 2
        fi
    done

    sleep 1
done

if [ -z "$ADAPTER" ]; then
    echo "Preferred Bluetooth adapter $PREFERRED_MAC was not found"
    exit 1
fi

echo "Using Bluetooth adapter: $ADAPTER ($PREFERRED_MAC)"
echo "+ btmgmt -i $ADAPTER $*"

printf -v COMMAND '%q ' /usr/bin/btmgmt -i "$ADAPTER" "$@"

exec /usr/bin/script \
    --quiet \
    --return \
    --command "$COMMAND" \
    /dev/null
