@echo off
rem Starts the MuST Simulator. First run installs the Python packages.
cd /d "%~dp0backend"
py -m pip install -q -r requirements.txt
py run.py %*
