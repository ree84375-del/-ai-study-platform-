Set shell = CreateObject("WScript.Shell")
' Using a bridge to PowerShell which can handle MSIX alias paths better
command = "powershell.exe -WindowStyle Hidden -Command ""Start-Process -FilePath 'C:\Users\Good PC\AppData\Local\Microsoft\WindowsApps\ngrok.exe' -ArgumentList 'http 11434 --config=\""c:\Users\Good PC\.gemini\antigravity\scratch\ai_study_platform\ngrok.yml\""' -WindowStyle Hidden"""
shell.Run command, 0, False
