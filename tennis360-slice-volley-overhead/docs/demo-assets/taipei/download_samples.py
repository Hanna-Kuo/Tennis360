"""Download and verify this documented CC BY 4.0 research subset."""
from pathlib import Path
import hashlib
import json
import urllib.request

BASE = Path(__file__).resolve().parent
manifest = json.loads((BASE / "manifest.json").read_text())
for record in manifest["files"]:
    path = BASE / record["path"]
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]:
        print("verified", record["path"])
        continue
    with urllib.request.urlopen(record["download_url"], timeout=30) as response:
        data = response.read(record["bytes"] + 1)
    if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise RuntimeError("Unexpected file size or hash: " + record["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print("downloaded and verified", record["path"])
