@echo off
if "%~1"=="" (echo 请把项目目录拖到本脚本上或作为第一个参数 & pause & exit /b 2)
py -3 "%~dp0install_repo.py" "%~1"
pause
