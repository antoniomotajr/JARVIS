@echo off
title JARVIS - Painel Web
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python web_app.py
pause
