#!/bin/bash
# HONGXUN · 论文监控工具 v2.0 — 启动脚本 (macOS)
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR/.." || exit 1
exec python3 client/gui_app.py