@echo off
title JARVIS - Fase 1
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python main.py
pause
