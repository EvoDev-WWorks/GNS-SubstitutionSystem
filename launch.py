"""
Teacher Substitution System — Desktop Launcher
===============================================
Starts the FastAPI server in a background thread,
then opens the UI in a native desktop window (no browser needed).

Works both as a normal Python script AND as a PyInstaller .exe
"""

import sys
import os
import threading
import time
import socket

# ── PyInstaller compatibility ──────────────────────────────────────────────
# When running as a bundled .exe, sys.frozen is True and sys._MEIPASS
# points to the temp folder where files are extracted.
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    # Also set working dir to where the executable lives (so .env is found)
    os.chdir(os.path.dirname(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Load .env credentials ─────────────────────────────────────────────────
_env_paths = [
    os.path.join(os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__), '.env'),
    os.path.join(os.getcwd(), '.env'),
    os.path.join(BASE_DIR, '.env'),
]
for _p in _env_paths:
    if os.path.exists(_p):
        with open(_p) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith('#') and '=' in _line:
                    _k, _v = _line.split('=', 1)
                    os.environ.setdefault(_k.strip(), _v.strip())
        break


def get_local_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def start_server():
    """Run FastAPI in a background thread."""
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, log_level="warning")


def wait_for_server(host="127.0.0.1", port=8000, timeout=20):
    """Block until the FastAPI server is ready to accept connections."""
    import socket as s
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with s.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


if __name__ == "__main__":
    local_ip = get_local_ip()

    # Print startup info in terminal (visible when run via console)
    print("=" * 52)
    print("  Teacher Substitution System")
    print("  Gyan Niketan School — 2026-27")
    print("=" * 52)
    print(f"  Starting server...")

    # Start FastAPI server in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait until server is up
    ready = wait_for_server()
    if not ready:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Startup Error",
            "The server failed to start within 20 seconds.\n\n"
            "Please check:\n"
            "  • Your .env file has valid Supabase credentials\n"
            "  • Port 8000 is not blocked by another app"
        )
        sys.exit(1)

    print(f"  This PC    :  http://localhost:8000")
    print(f"  School LAN :  http://{local_ip}:8000")
    print("  Opening app window...")
    print("=" * 52)

    # Try to open in pywebview (native desktop window)
    try:
        import webview
        window = webview.create_window(
            title="Teacher Substitution System — Gyan Niketan School",
            url="http://127.0.0.1:8000",
            width=1200,
            height=800,
            min_size=(900, 650),
            resizable=True,
        )
        webview.start(debug=False)

    except Exception:
        # Fallback: open in default browser if pywebview fails
        import webbrowser
        webbrowser.open("http://127.0.0.1:8000")
        print("  Opened in browser. Close this window to stop the server.")
        # Keep server alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
