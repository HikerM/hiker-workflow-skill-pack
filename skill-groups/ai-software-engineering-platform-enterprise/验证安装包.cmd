@echo off
py -3 "%~dp0tools\validate_bundle.py"
py -3 "%~dp0tools\run_all_tests.py"
py -3 "%~dp0tools\integration_smoke.py"
pause
