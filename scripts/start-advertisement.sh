#!/bin/bash
set -e

btmgmt power off || true
btmgmt le on
btmgmt bredr on
btmgmt connectable on
btmgmt power on
btmgmt clr-adv || true
btmgmt add-adv -c -g -n \
  -u 5a0d6a15-b664-4304-8530-3a0ec53e5bc1 \
  1
