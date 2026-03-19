@echo off
echo ====================================================
echo   Yukine Ngrok Service Setup (Run as Administrator)
echo ====================================================
cd /d "%~dp0"
echo Stopping existing ngrok...
taskkill /F /IM ngrok.exe /T >nul 2>&1
echo Installing ngrok service...
ngrok service install --config="%cd%\ngrok.yml"
echo Starting ngrok service...
ngrok service start
echo Done! You can now close this window.
pause
