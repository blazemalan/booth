#!/usr/bin/env python3
"""Booth voice daemon — keeps Kokoro loaded so synth is fast on every send.

Lifecycle:
  - Spawned on demand by `booth say` when the socket isn't there
  - Listens on /tmp/booth_voice.sock (Unix domain socket)
  - Loads Kokoro once at startup with CoreML+CPU providers (Apple Neural Engine)
  - 30-minute idle timeout: exits cleanly if no requests in 30 min
  - PID file at /tmp/booth_voice.pid

Protocol (newline-delimited JSON):
  request:  {"text": str, "voice": str, "speed": float, "out_wav": str}
  response: {"ok": bool, "samples": int, "sr": int} or {"ok": false, "error": str}
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import wave
from pathlib import Path

HOME = Path.home()
SOCKET_PATH = Path("/tmp/booth_voice.sock")
PID_PATH = Path("/tmp/booth_voice.pid")
LOG_PATH = HOME / ".local/share/booth/voice_daemon.log"
KOKORO_MODEL = HOME / ".local/share/kokoro-tts/kokoro-v1.0.fp16.onnx"
KOKORO_VOICES = HOME / ".local/share/kokoro-tts/voices-v1.0.bin"

DEFAULT_VOICE = "af_heart"
IDLE_TIMEOUT_SEC = 30 * 60


def log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def patch_providers_for_coreml() -> list[str]:
    """Monkey-patch ort.InferenceSession to use CoreML + CPU providers.

    Kokoro-onnx hardcodes CPU; this lets us override before model load.
    Returns the actual provider list applied.
    """
    import onnxruntime as ort
    available = set(ort.get_available_providers())
    preferred = []
    if "CoreMLExecutionProvider" in available:
        preferred.append("CoreMLExecutionProvider")
    preferred.append("CPUExecutionProvider")
    orig = ort.InferenceSession

    def _patched(*args, **kwargs):
        kwargs["providers"] = preferred
        return orig(*args, **kwargs)

    ort.InferenceSession = _patched
    return preferred


def load_kokoro():
    providers = patch_providers_for_coreml()
    log(f"loading Kokoro with providers={providers}")
    from kokoro_onnx import Kokoro
    k = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
    log("Kokoro loaded")
    return k


def synth_to_wav(kokoro, text: str, voice: str, speed: float, out_wav: Path) -> tuple[int, int]:
    import numpy as np
    samples, sr = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
    samples = np.asarray(samples)
    pcm = (samples * 32767.0).clip(-32768, 32767).astype("int16")
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return len(pcm), int(sr)


def handle_client(conn: socket.socket, kokoro, last_request: list[float]) -> None:
    try:
        data = b""
        while not data.endswith(b"\n"):
            chunk = conn.recv(8192)
            if not chunk:
                break
            data += chunk
        if not data.strip():
            return  # empty conn — liveness probe or shutdown wake
        try:
            req = json.loads(data.decode().strip())
            text = req["text"]
            voice = req.get("voice", DEFAULT_VOICE)
            speed = float(req.get("speed", 1.0))
            out_wav = Path(req["out_wav"])
            log(f"synth: voice={voice} speed={speed} text={text[:60]!r}")
            n, sr = synth_to_wav(kokoro, text, voice, speed, out_wav)
            last_request[0] = time.time()
            resp = {"ok": True, "samples": n, "sr": sr}
        except Exception as e:
            log(f"error: {e}")
            resp = {"ok": False, "error": str(e)}
        try:
            conn.sendall((json.dumps(resp) + "\n").encode())
        except (BrokenPipeError, ConnectionResetError):
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def idle_watchdog(last_request: list[float], shutdown: threading.Event) -> None:
    while not shutdown.is_set():
        time.sleep(60)
        idle = time.time() - last_request[0]
        if idle > IDLE_TIMEOUT_SEC:
            log(f"idle for {idle:.0f}s, shutting down")
            shutdown.set()
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.connect(str(SOCKET_PATH))
            except Exception:
                pass
            return


def main():
    if SOCKET_PATH.exists():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(str(SOCKET_PATH))
                log("another daemon alive; exiting")
                return
        except Exception:
            log("stale socket, removing")
            SOCKET_PATH.unlink()

    PID_PATH.write_text(str(os.getpid()))
    log(f"daemon starting, pid={os.getpid()}")

    kokoro = load_kokoro()
    last_request = [time.time()]
    shutdown = threading.Event()

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(SOCKET_PATH))
    sock.listen(4)
    log(f"listening on {SOCKET_PATH}")

    t = threading.Thread(target=idle_watchdog, args=(last_request, shutdown), daemon=True)
    t.start()

    try:
        while not shutdown.is_set():
            try:
                conn, _ = sock.accept()
            except OSError:
                break
            if shutdown.is_set():
                conn.close()
                break
            try:
                handle_client(conn, kokoro, last_request)
            except Exception as e:
                log(f"unexpected error in handler: {e}")
    finally:
        sock.close()
        try:
            SOCKET_PATH.unlink()
        except Exception:
            pass
        try:
            PID_PATH.unlink()
        except Exception:
            pass
        log("daemon exited")


if __name__ == "__main__":
    main()
