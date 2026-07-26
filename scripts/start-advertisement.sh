#!/bin/bash

PREFERRED_MAC="18:69:45:F3:58:B9"

for adapter in /sys/class/bluetooth/hci*; do
    [ -d "$adapter" ] || continue

    hci=$(basename "$adapter")

    mac=$(hciconfig "$hci" 2>/dev/null | awk '/BD Address/ {print $3}')

    if [ "$mac" = "$PREFERRED_MAC" ]; then
        exec /usr/bin/expect \
            /home/pi/sutton-scoreboard-os/scripts/start-advertisement.exp \
            "$hci"
    fi
done

echo "Preferred adapter not found"
exit 1
