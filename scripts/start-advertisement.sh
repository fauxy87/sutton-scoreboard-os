#!/bin/bash
set -e

UUID="5a0d6a15-b664-4304-8530-3a0ec53e5bc1"
NAME="SCOREOS"

echo "Starting Bluetooth advertisement..."

btmgmt --index 0 name "$NAME"
btmgmt --index 0 connectable on

# Remove any previous advertisement
btmgmt --index 0 rm-adv 1 >/dev/null 2>&1 || true

# Create advertisement
btmgmt --index 0 add-adv \
    -c \
    -g \
    -n \
    -u "$UUID" \
    1

echo "Bluetooth advertisement started"

# Keep the service alive
while true
do
    sleep 3600
done
