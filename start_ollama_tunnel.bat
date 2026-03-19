@echo off
title Ollama Tunnel (Keep this open)
echo ==========================================
echo Starting Ollama Public Tunnel via Ngrok...
echo ==========================================
"C:\Users\Good PC\AppData\Local\Microsoft\WindowsApps\ngrok.exe" http 11434 --config="c:\Users\Good PC\.gemini\antigravity\scratch\ai_study_platform\ngrok.yml"
echo.
echo Tunnel stopped. Press any key to exit.
pause
