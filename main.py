"""Run DineSmartAI from the project root: python main.py

Opens the chat UI (/) in your default browser only after the server is accepting connections.

Enable file-watch reload for development:
  UVICORN_RELOAD=1 python main.py
"""

from __future__ import annotations

import errno
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser

import uvicorn


def pick_bind_port(host: str, preferred: int, attempts: int = 20) -> int:
    """Use preferred port, or the next free port in range, to avoid EADDRINUSE."""
    for port in range(preferred, preferred + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError as e:
                if e.errno == errno.EADDRINUSE:
                    continue
                raise
            return port
    raise RuntimeError(
        f"No free port found starting at {preferred} (tried {attempts} ports)."
    )


def wait_until_port_listening(port: int, timeout_sec: float = 90.0) -> bool:
    """Return True once something accepts TCP on 127.0.0.1:port (server is up)."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except (OSError, socket.timeout):
            time.sleep(0.1)
    return False


def schedule_open_browser_when_ready(port: int, path: str = "/docs") -> None:
    """After the server is listening, open the default browser (background thread)."""

    def _worker() -> None:
        if not wait_until_port_listening(port):
            print(
                "DineSmartAI: server did not become ready in time; open the URL manually.",
                flush=True,
            )
            return
        url = f"http://127.0.0.1:{port}{path}"
        try:
            webbrowser.open(url)
            print(f"Opened browser: {url}", flush=True)
        except Exception as exc:
            print(f"Could not open browser ({exc}). Open manually: {url}", flush=True)

    threading.Thread(target=_worker, daemon=True).start()


def _reload_enabled() -> bool:
    return os.getenv("UVICORN_RELOAD", "0").lower() in ("1", "true", "yes")


def _open_browser_enabled() -> bool:
    return os.getenv("SMARTDINE_OPEN_BROWSER", "1").lower() in ("1", "true", "yes")


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    preferred = int(os.getenv("PORT", "8000"))
    port = pick_bind_port(host, preferred)
    use_reload = _reload_enabled()

    if port != preferred:
        print(f"Port {preferred} in use; using {port} instead.", flush=True)
    print(f"DineSmartAI → http://127.0.0.1:{port}", flush=True)
    print(f"Chat UI → http://127.0.0.1:{port}/  ·  API docs → http://127.0.0.1:{port}/docs", flush=True)
    print("Stop the server: press Ctrl+C in this window.", flush=True)
    if use_reload:
        print("Reload mode on (UVICORN_RELOAD=1); file changes restart the server.", flush=True)
    else:
        print("Single process (no auto-reload). Set UVICORN_RELOAD=1 to watch files.", flush=True)

    if _open_browser_enabled():
        schedule_open_browser_when_ready(port, "/")
        print("Browser will open when the server is ready…", flush=True)
    else:
        print("Browser auto-open off (set SMARTDINE_OPEN_BROWSER=1 to enable).", flush=True)

    try:
        if use_reload:
            uvicorn.run(
                "app.main:app",
                host=host,
                port=port,
                reload=True,
                reload_dirs=[os.path.dirname(os.path.abspath(__file__))],
            )
        else:
            from app.main import app as fastapi_app

            uvicorn.run(fastapi_app, host=host, port=port, reload=False)
    except KeyboardInterrupt:
        print("\nServer stopped.", flush=True)
    except Exception:
        traceback.print_exc()
        if os.getenv("SMARTDINE_PAUSE_ON_ERROR", "1").lower() in ("1", "true", "yes"):
            try:
                input("Press Enter to exit...")
            except EOFError:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
