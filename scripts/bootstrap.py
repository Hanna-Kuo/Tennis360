"""Install project-local dependencies and launch TennisPose on loopback only.

Requires a preinstalled 64-bit Python 3.11. Never installs system software,
deletes an existing environment, or processes student photos during setup.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import urllib.request
import venv

ROOT = Path(__file__).resolve().parent.parent
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
)
MODEL_SHA256 = "64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b"


def run(arguments: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, cwd=ROOT, check=True, **kwargs)


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def environment_python(folder: Path) -> Path:
    return folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_environment(folder: Path) -> Path:
    python = environment_python(folder)
    if not folder.exists():
        print("[1/4] Creating the project Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(folder)
    try:
        run([str(python), "-c", (
            "import sys,struct; from pathlib import Path; "
            "assert sys.version_info[:2] == (3,11); "
            "assert struct.calcsize('P') == 8; "
            "assert sys.prefix != sys.base_prefix; "
            "assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()"
        ), str(folder)], capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError(
            "The existing .venv is incomplete, incompatible, or copied from another "
            "computer. It was not deleted. Close TennisPose, rename .venv to "
            ".venv-backup, and retry with Python 3.11 installed."
        ) from error
    return python


def ensure_dependencies(python: Path, repair: bool) -> None:
    requirements = ROOT / "requirements.txt"
    marker = ROOT / ".venv" / ".tennispose-requirements.sha256"
    expected = digest(requirements)
    installed = marker.read_text().strip() if marker.is_file() else ""
    if repair or installed != expected:
        print("[2/4] Installing packages (internet required; may take several minutes)...", flush=True)
        run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
             "--only-binary=:all:", "-r", str(requirements)])
    else:
        print("[2/4] Reusing installed packages (no download).", flush=True)
    run([str(python), "-m", "pip", "check"])
    run([str(python), "-c", "import streamlit, mediapipe, cv2, numpy, PIL"])
    # pip check verifies dependency compatibility, not our direct version pins.
    run([str(python), "-c", (
        "from importlib.metadata import version; from pathlib import Path; "
        "from packaging.requirements import Requirement; import sys; "
        "requirements = [Requirement(line.strip()) for line in "
        "Path(sys.argv[1]).read_text().splitlines() "
        "if line.strip() and not line.lstrip().startswith('#')]; "
        "bad = [str(r) for r in requirements if version(r.name) not in r.specifier]; "
        "sys.exit('Installed versions do not match: ' + ', '.join(bad) + "
        "'. Run the launcher with --repair.' if bad else 0)"
    ), str(requirements)])
    marker.write_text(expected + "\n")


def ensure_model(python: Path, model: Path) -> None:
    if model.is_file():
        if digest(model) != MODEL_SHA256:
            raise RuntimeError(
                "The existing model failed its SHA-256 check. It was not overwritten. "
                "Rename models/pose_landmarker_heavy.task and retry to download a clean copy."
            )
        print("[3/4] Existing model checksum verified (no download).", flush=True)
        return
    print("[3/4] Downloading the official model (~29 MB)...", flush=True)
    model.parent.mkdir(parents=True, exist_ok=True)
    # Use the installed certificate bundle, including on python.org macOS installs.
    certificates = run([str(python), "-c", "import certifi; print(certifi.where())"],
                       capture_output=True, text=True).stdout.strip()
    context = ssl.create_default_context(cafile=certificates)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=model.parent, suffix=".part", delete=False) as target:
            temporary = Path(target.name)
            with urllib.request.urlopen(MODEL_URL, timeout=60, context=context) as response:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
        if digest(temporary) != MODEL_SHA256:
            raise RuntimeError("Downloaded model failed its SHA-256 check. Please retry.")
        temporary.replace(model)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup-only", action="store_true", help="Install and verify without starting the web app")
    parser.add_argument("--repair", action="store_true", help="Rerun pip installation; requires internet")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 11) or struct.calcsize("P") != 8:
        raise RuntimeError("Install 64-bit Python 3.11 before running this launcher.")
    # Only one setup process may modify the environment at a time.
    lock = ROOT / ".tennispose-setup.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError(
            "Another setup may be running. Wait for it to finish. If it was interrupted, "
            "close all TennisPose terminals before removing .tennispose-setup.lock."
        ) from error
    try:
        os.close(descriptor)
        python = ensure_environment(ROOT / ".venv")
        ensure_dependencies(python, args.repair)
        ensure_model(python, ROOT / "models" / "pose_landmarker_heavy.task")
        print("[4/4] Verifying local model loading...", flush=True)
        run([str(python), "-c", "from tennispose.pose_detector import get_detector; get_detector()"])
    finally:
        lock.unlink(missing_ok=True)
    if args.setup_only:
        print("Setup and model verification complete. Run the launcher again to open TennisPose.")
        return 0
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 8501))
        except OSError as error:
            raise RuntimeError(
                "Port 8501 is already in use. If TennisPose is already running, open "
                "http://127.0.0.1:8501; otherwise stop the other app and retry."
            ) from error
    print("Opening http://127.0.0.1:8501 . Keep this terminal open; press Ctrl+C to stop.", flush=True)
    run([str(python), "-m", "streamlit", "run", "streamlit_app.py",
         "--server.address=127.0.0.1", "--server.port=8501",
         "--server.headless=false", "--browser.serverAddress=127.0.0.1",
         "--browser.gatherUsageStats=false"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nTennisPose stopped.")
        sys.exit(0)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\nSetup/startup failed: {error}", file=sys.stderr)
        print("Check the error above and README.md. Retry after fixing the cause.", file=sys.stderr)
        sys.exit(1)
