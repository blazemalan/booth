"""Booth — ElevenLabs synth backend.

Pipeline: text → ElevenLabs HTTP API → raw PCM → WAV file. The WAV that
lands on disk has the exact same shape voice_daemon.synth_to_wav produces
(mono, 16-bit PCM, 24 kHz), so the rest of the pipeline — encode_opus,
send_voice — works without modification.

Reads the API key from $BOOTH_HOME/elevenlabs_api_key (mode 600).
Voice id and model come from $BOOTH_HOME/config.json under "elevenlabs",
or via --voice / sane defaults.

Failures are LOUD by design. Quota-exceeded, invalid-key, or network
errors raise SystemExit with the API's own message. The calling agent
decides what to do — drop, retry, or fall back to a text reply on
Telegram. Booth never silently downgrades to Kokoro: voice identity is
the contract, and silent fallback would break it.

This module bypasses the Kokoro daemon entirely. The daemon does not
know about ElevenLabs, has no notion of bot identity, and stays Kokoro-
only. ElevenLabs is just an HTTP call away — there's nothing to keep
loaded between requests, so a daemon would buy us nothing.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import wave
from pathlib import Path

HOME = Path.home()
BOOTH_HOME = Path(os.environ.get("BOOTH_HOME", HOME / ".local/share/booth"))
KEY_FILE = BOOTH_HOME / "elevenlabs_api_key"

# No DEFAULT_VOICE_ID by design. Voice catalogues are per-account on
# ElevenLabs, so any hardcoded default would silently fail for users whose
# account doesn't have that voice — and the API returns a "library voice"
# 402, not a useful "did you mean..." error. Force the user to set their own
# voice_id explicitly via $BOOTH_HOME/config.json or --voice. Matches the
# fail-loud contract: if you can't say the right thing, say nothing and
# point the user at the fix.
DEFAULT_MODEL = "eleven_flash_v2_5"  # cheapest current model, ~0.5 credits/char
SAMPLE_RATE = 24000  # matches output_format=pcm_24000

# Default voice settings. Stability and similarity_boost run 0.0 to 1.0.
# Higher stability = steadier, less emotional variance per call (good for
# multi-sentence broadcast). Higher similarity_boost = closer to the source
# voice's character (also amplifies any quirks). 0.75/0.75 with speaker
# boost on is ElevenLabs's recommended "consistent" preset; without these,
# the API falls back to per-voice defaults that can swing wildly on longer
# inputs. Override per-call via $BOOTH_HOME/config.json under
# "elevenlabs": {"voice_settings": {...}}.
DEFAULT_VOICE_SETTINGS = {
    "stability": 0.75,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}


def load_api_key() -> str:
    if not KEY_FILE.exists():
        raise SystemExit(
            f"ElevenLabs API key not configured. Run:\n"
            f"  echo 'YOUR_KEY' > {KEY_FILE} && chmod 600 {KEY_FILE}\n"
            f"Or switch backends: edit $BOOTH_HOME/config.json and set \"backend\": \"kokoro\"."
        )
    return KEY_FILE.read_text().strip()


def synth_to_wav(
    text: str,
    voice_id: str,
    model: str,
    out_wav: Path,
    voice_settings: dict | None = None,
) -> tuple[int, int]:
    """Synthesize via ElevenLabs and write a WAV file.

    Output WAV is symmetric with voice_daemon.synth_to_wav: mono, 16-bit PCM,
    24 kHz. Returns (sample_count, sample_rate) matching the daemon's signature
    so the rest of say.py doesn't care which backend produced the file.

    voice_settings dict (optional) controls stability/similarity_boost/style/
    use_speaker_boost — see DEFAULT_VOICE_SETTINGS. Caller-supplied values
    are merged onto the defaults so partial overrides work.

    Raises SystemExit on any HTTP/network/auth failure with the API's message
    in the error string. Caller (say.py → Booth's outer agent) decides what
    happens next.
    """
    key = load_api_key()
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=pcm_24000"
    settings = {**DEFAULT_VOICE_SETTINGS, **(voice_settings or {})}
    body = json.dumps({
        "text": text,
        "model_id": model,
        "voice_settings": settings,
    }).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "xi-api-key": key,
            "Content-Type": "application/json",
            "Accept": "audio/pcm",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            pcm_bytes = r.read()
    except urllib.error.HTTPError as e:
        # Read the error body — ElevenLabs returns useful JSON with the failure
        # detail (quota_exceeded, voice_not_found, invalid_api_key, etc.).
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = ""
        raise SystemExit(
            f"ElevenLabs API error {e.code}: {err_body or e.reason}"
        ) from e
    except urllib.error.URLError as e:
        raise SystemExit(f"ElevenLabs network error: {e.reason}") from e
    except OSError as e:
        # Mid-stream failures — connection reset, body-read timeout,
        # IncompleteRead. These don't all wrap in URLError, so catch the
        # OSError parent so they fail loud instead of escaping as bare
        # tracebacks.
        raise SystemExit(f"ElevenLabs connection error: {e}") from e

    # Wrap raw PCM into a WAV with the daemon's shape so encode_opus is happy.
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm_bytes)

    return len(pcm_bytes) // 2, SAMPLE_RATE  # 16-bit samples → 2 bytes each
