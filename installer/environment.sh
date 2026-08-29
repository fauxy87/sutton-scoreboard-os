#!/usr/bin/env bash

# --------------------------------------------------
# SCOREOS Environment
# --------------------------------------------------

SCOREOS_USER="$(whoami)"
SCOREOS_HOME="$HOME"

# Use the directory that actually contains install.sh. This keeps
# service paths correct when the repository is installed somewhere
# other than /home/pi/sutton-scoreboard-os.
SCOREOS_DIR="$(
    cd "$(dirname "${BASH_SOURCE[1]}")"
    pwd -P
)"

export SCOREOS_USER
export SCOREOS_HOME
export SCOREOS_DIR

info "User        : $SCOREOS_USER"
info "Home        : $SCOREOS_HOME"
info "Install Dir : $SCOREOS_DIR"
