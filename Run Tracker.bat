@echo off
echo ==========================================
echo       Starting the Betting Tracker
echo ==========================================
echo.
echo Launching the local server...
echo Press Ctrl+C or close this window to stop the server when you are done.
echo.

:: Automatically open the browser to the app
start http://127.0.0.1:5000

:: Change directory to where the batch script is located
cd /d "%~dp0"

:: Start Waitress in the foreground so the window stays open
venv\Scripts\waitress-serve --port=5000 app:app
