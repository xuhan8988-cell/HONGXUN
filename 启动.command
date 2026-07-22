#!/bin/bash
# HONGXUN-ZZU · 论文监控工具 v1.0（郑州大学定制版）— 启动脚本
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
exec python3 client/gui_app.py