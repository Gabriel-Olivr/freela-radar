@echo off
REM Liga o radar minimizado. Para ligar junto com o Windows:
REM Win+R -> shell:startup -> cole um atalho deste arquivo nessa pasta.
cd /d "%~dp0"
start "Radar de Freela" /min python radar.py
