#!/bin/sh
# 規則1: レビュー役の名前は、観点の役と --focus の役を合わせて一意にする
# 使い方: sh run.sh <対象のルート>   破れていれば 1、守られていれば 0
exec python3 -B "$(dirname "$0")/repro.py" "$1"
