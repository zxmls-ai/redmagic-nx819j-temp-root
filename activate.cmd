@echo off
setlocal
where py >nul 2>&1
if %errorlevel% equ 0 (
  py -3 "%~dp0nx819j_root.py" --activate %*
) else (
  python "%~dp0nx819j_root.py" --activate %*
)
set result=%errorlevel%
echo.
pause
exit /b %result%
