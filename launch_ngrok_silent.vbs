Set WshShell = CreateObject("WScript.Shell")
' 0 代表隱藏視窗, false 代表不需要等待執行結束
WshShell.Run "ngrok http 11434 --config=""c:\Users\Good PC\.gemini\antigravity\scratch\ai_study_platform\ngrok.yml""", 0, false
