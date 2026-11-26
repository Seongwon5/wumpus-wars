@echo off
rem 웜퍼스 워즈 토너먼트 프로그램 (더블클릭)
chcp 65001 >nul
cd /d "%~dp0"
python -X utf8 -m wumpus tournament
if errorlevel 1 pause
