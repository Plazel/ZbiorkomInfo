@echo off
rem Uruchamia iRozklad na tym komputerze (http://localhost:8765) z odjazdami na zywo dla Trojmiasta.
rem Zostaw okno otwarte; zamkniecie okna wylacza strone.
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo Nie znaleziono Pythona. Zainstaluj Python 3 ze strony https://www.python.org/downloads/
  pause
  exit /b 1
)
%PY% serwer.py
