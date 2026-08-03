#!/usr/bin/env bash

# --------------------------------------------------
# SCOREOS Environment
# --------------------------------------------------

SCOREOS_USER="$(whoami)"
SCOREOS_HOME="$HOME"
SCOREOS_DIR="$HOME/sutton-scoreboard-os"

export SCOREOS_USER
export SCOREOS_HOME
export SCOREOS_DIR

info "User        : $SCOREOS_USER"
info "Home        : $SCOREOS_HOME"
info "Install Dir : $SCOREOS_DIR"
