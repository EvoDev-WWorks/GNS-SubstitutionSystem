"""
Teacher Substitution System — Desktop Launcher
===============================================
Starts the FastAPI server in a background thread,
then opens the UI in a native desktop window (no browser needed).
"""

import threading
import time
import webview
import uvicorn
import socket


def get_local_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def start_server():
    """Run FastAPI in a background thread."""
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False, log_level="warning")


def wait_for_server(host="127.0.0.1", port=8000, timeout=15):
    """Block until the FastAPI server is ready to accept connections."""
    import socket as s
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with s.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


if __name__ == "__main__":
    # Start FastAPI server in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait until server is up
    ready = wait_for_server()
    if not ready:
        import sys
        print("ERROR: Server did not start in time.")
        sys.exit(1)

    # Open native desktop window
    window = webview.create_window(
        title="Teacher Substitution System — Gyan Niketan Public School",
        url="http://127.0.0.1:8000",
        width=1100,
        height=750,
        min_size=(800, 600),
        resizable=True,
    )

    webview.start(debug=False)
