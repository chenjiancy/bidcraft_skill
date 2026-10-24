@echo off
rem ============================================
rem CodeBuddy Code CLI login entry (official CLI)
rem Step 1: type /login and press Enter
rem Step 2: choose login method, scan QR / authorize in browser
rem ============================================
chcp 65001 >nul
"C:\Users\hxjlcj\AppData\Local\codebuddy\bin\codebuddy.exe"
echo.
echo Exit code: %ERRORLEVEL%
pause
