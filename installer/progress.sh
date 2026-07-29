#!/usr/bin/env bash

TOTAL_STEPS=6
CURRENT_STEP=0

next_step() {
    CURRENT_STEP=$((CURRENT_STEP + 1))
    info "[$CURRENT_STEP/$TOTAL_STEPS] $1"
}
