@echo off
rem 一键启动（Windows 双击）：通过 WSL 调用当前目录下的 start.sh
chcp 65001 >nul
set "REPO=%~dp0"
set "REPO=%REPO:~0,-1%"
echo ============================================================
echo   空气质量时序分析 Agent · 一键启动
echo ============================================================
wsl.exe bash -lc "cd \"$(wslpath '%REPO%')\" && chmod +x ./start.sh && ./start.sh %*"
pause
