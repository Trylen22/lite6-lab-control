@echo off
rem Windows launcher; same as run.sh. Works from any directory.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Create .venv and install requirements.txt; see README.md.
    exit /b 1
)
.venv\Scripts\python.exe scripts\run_lab.py
