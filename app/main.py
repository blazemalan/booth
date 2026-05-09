#!/usr/bin/env python3
"""Booth menu-bar app.

Lives in the macOS menu bar. Booth doesn't bridge Telegram itself — that's
the MCP plugin's job. Booth is the voice on-ramp/off-ramp that drops in
alongside whichever Telegram bridge you already run (Anthropic's Claude Code
Telegram channel, OpenClaw's Telegram skill, etc.).

The .app's job is just to keep the voice daemon warm so synth is fast on
every `booth say` call, and surface the daemon's health in the menu bar.

Mirrors Claudible's pattern (rumps + py2app + ~/.local/share state).
"""
from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import rumps

HOME = Path.home()
BOOTH_HOME = Path(os.environ.get("BOOTH_HOME", HOME / ".local/share/booth"))
TOKEN_FILE = BOOTH_HOME / "telegram_bot_token"
# Daemon socket + PID + log are SHARED across every bot on this Mac (one
# daemon serves all). They live outside $BOOTH_HOME on purpose — see
# voice_daemon.py for the per-agent vs shared breakdown.
DAEMON_SOCKET = Path(tempfile.gettempdir()) / "booth_voice.sock"
DAEMON_LOG = HOME / ".local/share/booth/voice_daemon.log"
DAEMON_STDERR = HOME / ".local/share/booth/daemon.stderr.log"

# Resolve src/ both in dev (alongside app/) and in the bundled .app.
# In the bundle py2app copies the source files directly into Resources/, not
# into a src/ subfolder, so "bundled src" is just the same dir as main.py.
HERE = Path(__file__).resolve().parent
SRC_DEV = HERE.parent / "src"
SRC_DIR = SRC_DEV if SRC_DEV.exists() else HERE


def daemon_alive() -> bool:
    if not DAEMON_SOCKET.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.connect(str(DAEMON_SOCKET))
        return True
    except Exception:
        return False


class App(rumps.App):
    def __init__(self):
        icon_path = HERE / "menubarTemplate.png"
        # rumps shows BOTH title and icon side-by-side when both are set —
        # leave title empty so the Booth template icon stands alone.
        super().__init__(
            "Booth",
            title="" if icon_path.exists() else "📟",
            icon=str(icon_path) if icon_path.exists() else None,
            template=True,
            quit_button=None,
        )
        self.daemon_proc: subprocess.Popen | None = None
        self.menu = [
            rumps.MenuItem("Status: starting…"),
            None,
            rumps.MenuItem("Restart voice daemon", callback=self._restart_daemon),
            None,
            rumps.MenuItem("Open daemon log", callback=self._open_daemon_log),
            None,
            rumps.MenuItem("Quit Booth", callback=self._on_quit),
        ]
        threading.Thread(target=self._init_bg, daemon=True).start()

    # ── lifecycle ─────────────────────────────────────────────────────
    def _init_bg(self):
        if not TOKEN_FILE.exists():
            self.menu["Status: starting…"].title = "Status: no bot token"
            rumps.notification(
                "Booth", "Setup needed",
                f"Drop your Telegram bot token at {TOKEN_FILE}",
            )
            return
        self._start_daemon()
        threading.Thread(target=self._poll_status, daemon=True).start()

    def _start_daemon(self):
        if daemon_alive():
            return
        py = self._python_for_subprocess()
        # The .app inherits a polluted env from py2app's launcher (DYLD_*,
        # PYTHONPATH, PYTHONHOME) that breaks the runtime venv's openssl
        # lookup. Start the subprocess from a MINIMAL env so the venv python
        # resolves its own paths cleanly.
        env = {
            "HOME": str(HOME),
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "BOOTH_HOME": str(BOOTH_HOME),
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        }
        DAEMON_STDERR.parent.mkdir(parents=True, exist_ok=True)
        err = open(DAEMON_STDERR, "ab", buffering=0)
        self.daemon_proc = subprocess.Popen(
            [py, str(SRC_DIR / "voice_daemon.py")],
            stdout=err,
            stderr=err,
            env=env,
            start_new_session=True,
        )

    def _python_for_subprocess(self) -> str:
        # Prefer the user-runtime venv that install.sh creates at
        # ~/.local/share/booth/.venv — it has kokoro_onnx, onnxruntime, numpy.
        # The .app's bundled python only has rumps.
        venv_py = BOOTH_HOME / ".venv" / "bin" / "python"
        if venv_py.exists():
            return str(venv_py)
        import sys
        return sys.executable

    # ── menu actions ──────────────────────────────────────────────────
    def _restart_daemon(self, _):
        # Killing via the socket — daemon's idle watchdog handles cleanup
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                s.connect(str(DAEMON_SOCKET))
        except Exception:
            pass
        # Wait for shutdown, then respawn
        time.sleep(2)
        self._start_daemon()

    def _open_daemon_log(self, _):
        if DAEMON_LOG.exists():
            subprocess.Popen(["open", str(DAEMON_LOG)])
        else:
            rumps.notification("Booth", "No log yet", str(DAEMON_LOG))

    def _on_quit(self, _):
        # Let the daemon idle out on its own — it'll stick around for any CLI
        # `booth say` calls after the menu-bar app is quit.
        rumps.quit_application()

    # ── status loop ───────────────────────────────────────────────────
    def _poll_status(self):
        while True:
            status = "Status: 🟢 daemon up" if daemon_alive() else "Status: ⚪ daemon idle"
            self.menu["Status: starting…"].title = status
            time.sleep(3)


if __name__ == "__main__":
    App().run()
