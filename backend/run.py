#!/usr/bin/env python3
"""Start the DATS Simulator app: backend + built UI on one port.

    python run.py                 # opens http://127.0.0.1:8765 in your browser
    python run.py --port 9000 --no-browser
    python run.py --window        # own desktop window (needs: pip install pywebview)
"""
import argparse
import threading
import time
import webbrowser

import uvicorn


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to open the UI from another PC on the network")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--window", action="store_true", help="show the UI in a desktop window instead of the browser")
    a = p.parse_args()
    url = f"http://{'127.0.0.1' if a.host == '0.0.0.0' else a.host}:{a.port}"

    from must_sim.app import app

    config = uvicorn.Config(app, host=a.host, port=a.port, log_level="warning")
    server = uvicorn.Server(config)
    if a.window:
        try:
            import webview  # type: ignore
        except ImportError:
            raise SystemExit("--window needs pywebview:  pip install pywebview")
        threading.Thread(target=server.run, daemon=True).start()
        time.sleep(1.0)
        webview.create_window("DATS Simulator", url, width=1500, height=950)
        webview.start()
        server.should_exit = True
        return
    if not a.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"DATS Simulator running at {url}   (Ctrl+C to stop)")
    server.run()


if __name__ == "__main__":
    main()
