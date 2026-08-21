@echo off
rem Launches the app elevated. The game runs as administrator, and Windows UIPI
rem silently discards synthesized input aimed at a higher-integrity window --
rem SendInput returns success, the cursor never moves. Same rule blocks the
rem low-level input hook used for recording. Matching the game's integrity
rem level is the only way around it.
cd /d "%~dp0"
powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~dp0.venv\Scripts\python.exe' -ArgumentList '-m','tiles_survive_automation.app' -WorkingDirectory '%~dp0'"
