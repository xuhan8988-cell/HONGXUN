@echo off
chcp 65001 >nul
cd /d "%~dp0.."
python client\gui_app.py
pause
