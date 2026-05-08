#!/usr/bin/env python3
"""Pager menu-bar app.

Lives in the macOS menu bar, manages the voice daemon and the inbound listener,
and gives you Quit + log access.

Mirrors Claudible's pattern (rumps + py2app + ~/.local/share state).
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

import rumps

HOME = Path.home()
PAGER_HOME = Path(os.environ.get("PAGER_HOME", HOME / ".local/share/pager"))
TOKEN_FILE = PAGER_HOME / "telegram_bot_token"
LISTEN_LOG = PAGER_HOME / "listen.log"
DAEMON_LOG = PAGER_HOME / "voice_daemon.log"
DAEMON_SOCKET = Path("/tmp/pager_voice.sock")

# Resolve src/ both in dev (alongside app/) and in the bundled .app
HERE = Path(__file__).resolve().parent
SRC_DEV = HERE.parent / "src"
SRC_BUNDLED = HERE.parent / "Resources" / "src"
SRC_DIR = SRC_DEV if SRC_DEV.exists() else SRC_BUNDLED


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
        # Use template image so macOS auto-inverts in dark mode.
        icon_path = HERE / "menubarTemplate.png"
        super().__init__(
            "Pager",
            title="📟",  # placeholder until icon ships
            icon=str(icon_path) if icon_path.exists() else None,
            template=True,
            quit_button=None,
        )
        self.listener_proc: subprocess.Popen | None = None
        self.menu = [
            rumps.MenuItem("Status: starting…"),
            None,
            rumps.MenuItem("Pause listener", callback=self._toggle_listener),
            None,
            rumps.MenuItem("Open listener log", callback=self._open_listen_log),
            rumps.MenuItem("Open daemon log", callback=self._open_daemon_log),
            None,
            rumps.MenuItem("Quit Pager", callback=self._on_quit),
        ]
        threading.Thread(target=self._init_bg, daemon=True).start()

    # ── lifecycle ─────────────────────────────────────────────────────
    def _init_bg(self):
        if not TOKEN_FILE.exists():
            self.menu["Status: starting…"].title = "Status: no bot token"
            rumps.notification(
                "Pager", "Setup needed",
                f"Drop your Telegram bot token at {TOKEN_FILE}",
            )
            return
        self._start_listener()
        threading.Thread(target=self._poll_status, daemon=True).start()

    def _start_listener(self):
        if self.listener_proc and self.listener_proc.poll() is None:
            return
        py = self._python_for_subprocess()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC_DIR.parent)
        self.listener_proc = subprocess.Popen(
            [py, str(SRC_DIR / "listen.py")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )

    def _stop_listener(self):
        p = self.listener_proc
        if not p:
            return
        if p.poll() is None:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:
                try:
                    p.terminate()
                except Exception:
                    pass
        self.listener_proc = None

    def _python_for_subprocess(self) -> str:
        # In a py2app bundle, sys.executable points to the app's python.
        # In dev, fall back to whatever python the user has.
        import sys
        return sys.executable

    # ── menu actions ──────────────────────────────────────────────────
    def _toggle_listener(self, sender):
        if self.listener_proc and self.listener_proc.poll() is None:
            self._stop_listener()
            sender.title = "Resume listener"
        else:
            self._start_listener()
            sender.title = "Pause listener"

    def _open_listen_log(self, _):
        if LISTEN_LOG.exists():
            subprocess.Popen(["open", str(LISTEN_LOG)])
        else:
            rumps.notification("Pager", "No log yet", str(LISTEN_LOG))

    def _open_daemon_log(self, _):
        if DAEMON_LOG.exists():
            subprocess.Popen(["open", str(DAEMON_LOG)])
        else:
            rumps.notification("Pager", "No log yet", str(DAEMON_LOG))

    def _on_quit(self, _):
        self._stop_listener()
        # Daemon will idle out on its own (30 min). We don't kill it here
        # so the user can still send voice with `pager say` after quitting.
        rumps.quit_application()

    # ── status loop ───────────────────────────────────────────────────
    def _poll_status(self):
        while True:
            listener_running = (
                self.listener_proc is not None
                and self.listener_proc.poll() is None
            )
            daemon = daemon_alive()
            status = "Status: "
            if listener_running and daemon:
                status += "🟢 listening + daemon up"
            elif listener_running:
                status += "🟡 listening, daemon idle"
            elif daemon:
                status += "🟡 daemon up, listener paused"
            else:
                status += "⚪ stopped"
            self.menu["Status: starting…"].title = status
            time.sleep(3)


if __name__ == "__main__":
    App().run()
