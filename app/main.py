"""Pager menu-bar app — TODO.

Mirrors Claudible's main.py pattern (rumps StatusBarApp). Will:
  - Show pulsing green LED in menu bar when listener is running
  - Subprocess.Popen the listener (src/listen.py) and the daemon (src/voice_daemon.py)
  - Tail listen.log + voice_daemon.log into a "View logs" submenu
  - Quit cleanly: kill child processes, unlink sockets, cancel cron entries

Until this lands, run components directly:
    bin/pager daemon       # voice synth daemon
    bin/pager listen       # inbound STT listener
    bin/pager say "..."    # one-shot outbound voice
"""
import sys

if __name__ == "__main__":
    sys.stderr.write(
        "Pager menu-bar app is not yet implemented. "
        "Use the CLI for now — see bin/pager.\n"
    )
    sys.exit(1)
