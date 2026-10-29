#!/usr/bin/env python3
"""Build a single-file desktop program with PyInstaller (run this on Windows for a .exe).

    pip install pyinstaller pywebview
    cd frontend && npm install && npm run build && cd ..
    cd backend && python build_exe.py

Result: backend/dist/MuST_Simulator(.exe) and backend/dist/config/commands.json.
Edit dist/config/commands.json next to the program to change command IDs.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parent
dist_ui = root / "frontend" / "dist"
if not (dist_ui / "index.html").is_file():
    sys.exit("Build the UI first:  cd frontend && npm install && npm run build")

sep = os.pathsep
cmd = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--name", "MuST_Simulator",
    "--paths", str(here),
    "--add-data", f"{dist_ui}{sep}web",
    "--add-data", f"{here / 'must_sim' / 'default_commands.json'}{sep}must_sim",
    "--collect-submodules", "uvicorn",
    "--collect-submodules", "websockets",
    "--hidden-import", "must_sim.app",
    str(here / "run.py"),
]
print(" ".join(cmd))
subprocess.run(cmd, cwd=here, check=True)
out = here / "dist" / "config"
out.mkdir(parents=True, exist_ok=True)
shutil.copy(root / "config" / "commands.json", out / "commands.json")
print("\nDone. Run dist/MuST_Simulator (add --window for a desktop window; needs pywebview).")
