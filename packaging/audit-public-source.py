"""Reject private data and generated payloads before staging public source."""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {".gitignore", ".gitattributes", "LICENSE", "README.md", "SECURITY.md",
              "THIRD_PARTY.md", "pyproject.toml"}
FORBIDDEN_SUFFIXES = {".exe", ".dll", ".zip", ".7z", ".whl", ".log", ".ini", ".db",
                      ".pem", ".key", ".pfx", ".p12", ".mp4", ".mkv", ".webm", ".mov",
                      ".avi", ".mp3", ".m4a", ".wav", ".ts", ".m3u8", ".pyc", ".part"}
SECRET_MARKERS = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,}|"
    r"AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
PRIVATE_PATHS = re.compile(r"[A-Za-z]:[/\\]Users[/\\][^/\\\s]+|/home[/][^/\s]+/")


def audit() -> None:
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=ROOT, check=True, capture_output=True)
    candidates = {name for name in result.stdout.decode("utf-8").split("\0") if name}
    failures = 0
    for name in sorted(candidates):
        path = ROOT / name
        if not path.is_file():
            continue
        parts = Path(name).parts
        unexpected_root = parts[0] not in {"src", "tests", "packaging"} and name not in ROOT_FILES
        private_name = any(part.startswith(".env") or part.lower() in {
            "private", "data", "cache", "profiles", "downloads", "installer", "build", "__pycache__"
        } for part in parts)
        if unexpected_root or private_name or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures += 1
            continue
        if path.suffix in {".py", ".md", ".toml", ".ps1", ".iss", ".sh", ".lock"}:
            content = path.read_text(encoding="utf-8")
            if SECRET_MARKERS.search(content) or PRIVATE_PATHS.search(content):
                failures += 1
    extension = ROOT / "src/video_downloader/assets/ublock-origin-lite.xpi"
    expected = "e963ebbefd12ae36d891393ff61940b8d94b605c2a8510d3749afff176d7ad7a"
    if hashlib.sha256(extension.read_bytes()).hexdigest() != expected:
        failures += 1
    if failures:
        raise SystemExit(f"Public-source audit failed: {failures} finding(s). Values suppressed for privacy.")
    print(f"Public-source audit passed: {len(candidates)} files; no generated payloads, private paths, or secret markers.")


if __name__ == "__main__":
    audit()
