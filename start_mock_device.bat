@echo off
rem Fake simulator for testing without hardware: listens on 127.0.0.1:7000 (TCP and UDP).
cd /d "%~dp0backend"
py mock_device.py --port 7000 %*
