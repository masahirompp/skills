#!/bin/sh
# 使い方: sh run.sh <対象のルート>
[ -n "$1" ] || { echo "対象のルートを渡す"; exit 2; }
command -v python3 >/dev/null || { echo "python3 がない"; exit 2; }
exec python3 "$(dirname "$0")/check.py" "$1"
