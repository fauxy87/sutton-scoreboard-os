#!/bin/bash

set -u

PREFERRED_MAC="18:69:45:F3:58:B9"
ADAPTER=""
UUID="5a0d6a15-b664-4304-8530-3a0ec53e5bc1"

# Wait up to 15 seconds for the preferred USB Bluetooth adapter.
for attempt in $(seq 1 15); do
    for adapter_path in /sys/class/bluetooth/hci*; do
        [ -d "$adapter_path" ] || continue

        hci=$(basename "$adapter_path")
        mac=$(hciconfig "$hci" 2>/dev/null |
            awk '/BD Address/ {print toupper($3)}')

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

run_btmgmt() {
    echo "+ btmgmt -i $ADAPTER $*"

    /usr/bin/timeout 5s /usr/bin/btmgmt -i "$ADAPTER" "$@"
    status=$?

    if [ "$status" -eq 124 ]; then
        echo "Warning: btmgmt command timed out: $*"
        return 1
    fi

    if [ "$status" -ne 0 ]; then
        echo "Warning: btmgmt command returned status $status: $*"
        return "$status"
    fi

    return 0
}

run_btmgmt power on || true
run_btmgmt le on || true
run_btmgmt name SCOREOS || true
run_btmgmt connectable on || true

# These may report that nothing was active after a fresh reboot.
run_btmgmt advertising off || true
run_btmgmt clr-adv || true

run_btmgmt add-adv -c -g -n -u "$UUID" 1 || exit 1
run_btmgmt advertising on || exit 1

echo
run_btmgmt advinfo || true
echo "SCOREOS Bluetooth advertisement started on $ADAPTER."
