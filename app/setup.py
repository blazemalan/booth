"""py2app build config for Booth.app.

Build:
    cd app
    python -m pip install py2app
    python setup.py py2app -A     # alias mode (fast, dev)
    python setup.py py2app        # standalone (slower, distributable)

The standalone build copies ../src/ into the bundle's Resources/ so the
menu-bar app can find listen.py + voice_daemon.py at runtime.
"""
import shutil
from pathlib import Path
from setuptools import setup

APP = ["main.py"]

# Bundle the entire src/ tree as a Resources subfolder so the .app can
# subprocess-launch listen.py / voice_daemon.py / say.py from anywhere.
HERE = Path(__file__).resolve().parent
SRC_PARENT = HERE.parent / "src"
RESOURCE_SRC_COPIES: list[str] = []
if SRC_PARENT.exists():
    for f in sorted(SRC_PARENT.glob("*.py")):
        RESOURCE_SRC_COPIES.append(str(f))

OPTIONS = {
    "iconfile": "icon.icns",
    "plist": {
        "CFBundleName": "Booth",
        "CFBundleDisplayName": "Booth",
        "CFBundleIdentifier": "io.github.blazemalan.booth",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,
        "NSHumanReadableCopyright": "MIT",
    },
    # The bundled python only needs rumps (the menu-bar UI library). The
    # heavy runtime deps (kokoro_onnx, onnxruntime, numpy) live in a separate
    # user venv at ~/.local/share/booth/.venv that install.sh creates. main.py
    # subprocesses listen.py and voice_daemon.py through that venv's python,
    # which keeps the .app bundle small and avoids the transitive-dep hell of
    # py2app trying to follow numpy/onnxruntime native chains.
    "packages": ["rumps"],
    "resources": ["menubarTemplate.png"] + RESOURCE_SRC_COPIES,
}

setup(
    app=APP,
    name="Booth",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
