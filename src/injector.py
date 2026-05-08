#!/usr/bin/env python3
"""Booth — AppleScript injector for self-triggered slash commands.

Why this exists: when your AI agent's running in Terminal.app and you're not
at the keyboard, slash commands like `/compact` need a way to be typed into
the agent's session remotely. AppleScript can drive Terminal.app to "do
script" arbitrary text into the front window, which the harness then reads
as user input.

Currently this only knows how to drive macOS Terminal.app. iTerm and other
terminals would need their own bindings — see "tell application "iTerm" ..."
in iTerm's AppleScript dictionary.

Limitations:
  - Targets the FRONT Terminal.app window's selected tab. If your agent is
    running in a different window, the keystrokes go to the wrong session.
    Caller is responsible for confirming the window assumption.
  - Requires Accessibility permission for Terminal.app and for whatever
    process is invoking osascript (Booth's app bundle, usually).
  - This is a self-write — you're scripting your OWN terminal session, not
    a remote one. Don't use it to drive other people's processes.

Usage:
    from booth.injector import inject
    inject("/compact")
    inject("echo hello", terminal="Terminal")
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys


def inject(text: str, terminal: str = "Terminal") -> None:
    """Type `text` (followed by Enter) into the front window of `terminal`.

    `terminal` must be the AppleScript-visible application name. macOS's built-in
    Terminal.app uses 'Terminal'.
    """
    if terminal != "Terminal":
        raise NotImplementedError(
            f"Booth only supports Terminal.app for now; got terminal={terminal!r}"
        )

    # The single quotes in our script need to coexist with shell escaping;
    # easiest to use AppleScript's own string concatenation via "do script".
    # We escape any double-quotes inside `text`.
    safe = text.replace('"', '\\"')
    script = (
        f'tell application "Terminal" to do script "{safe}" '
        "in selected tab of front window"
    )

    res = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise RuntimeError(f"osascript failed: {res.stderr.strip()}")


def main():
    ap = argparse.ArgumentParser(description="Type a slash command into your front Terminal session.")
    ap.add_argument("text", help='What to type. e.g. "/compact"')
    ap.add_argument("--terminal", default="Terminal", help="Terminal app name (default: Terminal)")
    args = ap.parse_args()
    inject(args.text, terminal=args.terminal)


if __name__ == "__main__":
    main()
