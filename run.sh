#!/bin/sh
set -eu

cupsd
exec python /app/app/main.py
