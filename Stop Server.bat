@echo off
echo Stopping the Betting Tracker Server...
taskkill /IM waitress-serve.exe /F
echo Server has been stopped successfully!
timeout /t 3
