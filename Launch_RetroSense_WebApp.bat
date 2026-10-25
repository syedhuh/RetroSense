@echo off
cd /d "%~dp0"
python launch_webapp.py
if errorlevel 1 pause
