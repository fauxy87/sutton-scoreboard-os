#!/bin/bash

set -u

PREFERRED_MAC="18:69:45:F3:58:B9"
ADAPTER=""
SELECTION_FILE="/run/scoreos/bluetooth-adapter"
PREFERRED_WAIT_SECONDS="${SCOREOS_PREFERRED_BT_WAIT:-5}"

adapter_mac() {
    local hci="$1"

    /usr/bin/hciconfig "$hci" 2>/dev/null |
        awk '/BD Address/ {print toupper($3)}'
}

find_preferred() {
    for adapter_path in /sys/class/bluetooth/hci*; do
        [ -d "$adapter_path" ] || continue

        hci=$(basename "$adapter_path")

        mac=$(adapter_mac "$hci")

        if [ "$mac" = "$PREFERRED_MAC" ]; then
            printf '%s\n' "$hci"
            return 0
        fi
    done

    return 1
}

# Always move to the preferred field USB adapter when it is
# already present, even if a built-in adapter was selected by
# an earlier home/development run.
ADAPTER=$(find_preferred || true)

# Reuse the previous selection during this boot so every
# btmgmt command targets the same adapter.
if [ -z "$ADAPTER" ] && [ -r "$SELECTION_FILE" ]; then
    saved_adapter=$(head -n 1 "$SELECTION_FILE")

    if [ -d "/sys/class/bluetooth/$saved_adapter" ]; then
        ADAPTER="$saved_adapter"
    fi
fi

# On the first call of a boot, briefly allow the external field
# adapter to enumerate. If it is not connected, fall back to the
# built-in adapter used by the development Pi at home.
if [ -z "$ADAPTER" ]; then
    for attempt in $(seq 0 "$PREFERRED_WAIT_SECONDS"); do
        ADAPTER=$(find_preferred || true)

        if [ -n "$ADAPTER" ]; then
            break
        fi

        if [ "$attempt" -lt "$PREFERRED_WAIT_SECONDS" ]; then
            sleep 1
        fi
    done
fi

if [ -z "$ADAPTER" ]; then
    for adapter_path in /sys/class/bluetooth/hci*; do
        [ -d "$adapter_path" ] || continue
        ADAPTER=$(basename "$adapter_path")
        break
    done
fi

if [ -z "$ADAPTER" ]; then
    echo "No Bluetooth adapter was found"
    exit 1
fi

mkdir -p "$(dirname "$SELECTION_FILE")"
printf '%s\n' "$ADAPTER" > "$SELECTION_FILE"

SELECTED_MAC=$(adapter_mac "$ADAPTER")

if [ "$SELECTED_MAC" = "$PREFERRED_MAC" ]; then
    ADAPTER_KIND="field USB"
else
    ADAPTER_KIND="built-in/fallback"
fi

echo "Using Bluetooth adapter: $ADAPTER ($SELECTED_MAC, $ADAPTER_KIND)"
echo "+ btmgmt -i $ADAPTER $*"

printf -v COMMAND '%q ' /usr/bin/btmgmt -i "$ADAPTER" "$@"

exec /usr/bin/script \
    --quiet \
    --return \
    --command "$COMMAND" \
    /dev/null
