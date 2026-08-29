@echo off
title JARVIS - Modo Texto
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python main.py --text
pause
