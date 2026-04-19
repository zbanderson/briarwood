#!/usr/bin/env python3
"""Start the Briarwood chat stack with one command.

Runs:
- FastAPI bridge on http://127.0.0.1:8000
- Next.js chat UI on http://127.0.0.1:3000

Usage:
    python3 scripts/dev_chat.py
or:
    make dev
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
VENV_PYTHON = ROOT / "venv" / "bin" / "python"


def _python_bin() -> str:
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable or "python3"


def _reader(name: str, pipe) -> None:
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            print(f"[{name}] {line.rstrip()}", flush=True)
    finally:
        pipe.close()


def _spawn(name: str, command: list[str], *, cwd: Path) -> tuple[subprocess.Popen[str], threading.Thread]:
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        start_new_session=True,
        env=os.environ.copy(),
    )
    assert process.stdout is not None
    thread = threading.Thread(target=_reader, args=(name, process.stdout), daemon=True)
    thread.start()
    return process, thread


def _terminate(processes: list[subprocess.Popen[str]]) -> None:
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def main() -> int:
    api_port = os.environ.get("BRIARWOOD_API_PORT", "8000")
    web_port = os.environ.get("BRIARWOOD_WEB_PORT", "3000")
    api_host = os.environ.get("BRIARWOOD_API_HOST", "127.0.0.1")
    web_host = os.environ.get("BRIARWOOD_WEB_HOST", "127.0.0.1")

    api_cmd = [
        _python_bin(),
        "-m",
        "uvicorn",
        "api.main:app",
        "--reload",
        "--host",
        api_host,
        "--port",
        api_port,
    ]
    web_cmd = [
        "pnpm",
        "dev",
        "--hostname",
        web_host,
        "--port",
        web_port,
    ]

    print("Starting Briarwood chat stack", flush=True)
    print(f"  API: http://{api_host}:{api_port}", flush=True)
    print(f"  Web: http://{web_host}:{web_port}", flush=True)

    api_proc, api_thread = _spawn("api", api_cmd, cwd=ROOT)
    web_proc, web_thread = _spawn("web", web_cmd, cwd=WEB_DIR)
    processes = [api_proc, web_proc]

    try:
        while True:
            for process in processes:
                code = process.poll()
                if code is not None:
                    print(f"Process exited early with code {code}. Shutting down stack.", flush=True)
                    _terminate(processes)
                    api_thread.join(timeout=1)
                    web_thread.join(timeout=1)
                    return code
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\nStopping Briarwood chat stack...", flush=True)
        _terminate(processes)
        api_thread.join(timeout=1)
        web_thread.join(timeout=1)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
