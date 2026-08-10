#!/bin/sh
set -eu
if [ -f /data/options.json ]; then
  exit 0
fi
exit 1
