#!/bin/bash

synchronised=$(
    timedatectl show       --property=NTPSynchronized       --value       2>/dev/null
)

if [ "$synchronised" = "yes" ]; then
    exit 0
fi

echo
echo "========================================"
echo "       OFFLINE CLOCK CHECK"
echo "========================================"
echo
echo "The Pi has not synchronized its clock."
echo "This is expected at the field without internet."
echo
echo "Current Pi date and time:"
date '+%A %d %B %Y  %H:%M:%S %Z'
echo

while true
do
    read -r -p "Is this date and time correct? [Y/n]: " answer

    case "${answer:-y}" in
        y|Y|yes|YES|Yes)
            echo "Clock accepted."
            echo
            exit 0
            ;;
        n|N|no|NO|No)
            break
            ;;
        *)
            echo "Please enter Y or N."
            ;;
    esac
done

while true
do
    echo
    read -r -p "Enter date and time (YYYY-MM-DD HH:MM): " entered

    corrected=$(
        date -d "$entered"           '+%Y-%m-%d %H:%M:00'           2>/dev/null
    )

    if [ -z "$corrected" ]; then
        echo "That date/time was not recognised. Please try again."
        continue
    fi

    echo
    echo "Setting Pi clock to: $corrected"

    sudo timedatectl set-ntp false

    if sudo timedatectl set-time "$corrected"; then
        sudo timedatectl set-ntp true

        echo
        echo "Clock updated successfully:"
        date '+%A %d %B %Y  %H:%M:%S %Z'
        echo
        exit 0
    fi

    sudo timedatectl set-ntp true

    echo
    echo "Unable to update the clock."
    echo "The existing time has been left unchanged."
    echo
    exit 1
done
