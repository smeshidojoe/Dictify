"""Whisper model catalog and a resumable downloader from Hugging Face."""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import ssl
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dictify.errors import Cancelled
from dictify.paths import models_dir

log = logging.getLogger(__name__)

HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
SKIP_FILES = {".gitattributes", "README.md"}
COMPLETE_MARKER = ".complete"
CHUNK = 1 << 20


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    size_mb: int
    faster_repo: str
    mlx_repo: str
    recommended: bool = False


MODELS = [
    ModelSpec("tiny", "Tiny", 75, "Systran/faster-whisper-tiny", "mlx-community/whisper-tiny-mlx"),
    ModelSpec("base", "Base", 145, "Systran/faster-whisper-base", "mlx-community/whisper-base-mlx"),
    ModelSpec("small", "Small", 485, "Systran/faster-whisper-small", "mlx-community/whisper-small-mlx"),
    ModelSpec("medium", "Medium", 1530, "Systran/faster-whisper-medium", "mlx-community/whisper-medium-mlx"),
    ModelSpec(
        "large-v3-turbo",
        "Large v3 Turbo",
        1620,
        "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "mlx-community/whisper-large-v3-turbo",
        recommended=True,
    ),
    ModelSpec("large-v3", "Large v3", 3090, "Systran/faster-whisper-large-v3", "mlx-community/whisper-large-v3-mlx"),
]
DEFAULT_MODEL = "large-v3-turbo"


def backend() -> str:
    """'mlx' on Apple Silicon (Metal GPU), 'faster' (CTranslate2) everywhere else."""
    if sys.platform == "darwin" and platform.machine() == "arm64":
        return "mlx"
    return "faster"


def get_model(model_id: str) -> ModelSpec:
    for spec in MODELS:
        if spec.id == model_id:
            return spec
    raise KeyError(model_id)


def repo_for(spec: ModelSpec) -> str:
    return spec.mlx_repo if backend() == "mlx" else spec.faster_repo


def model_path(spec: ModelSpec) -> Path:
    return models_dir() / backend() / spec.id


def is_downloaded(spec: ModelSpec) -> bool:
    return (model_path(spec) / COMPLETE_MARKER).exists()


def delete_model(spec: ModelSpec) -> None:
    shutil.rmtree(model_path(spec), ignore_errors=True)


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _open(url: str, headers: dict | None = None, timeout: float = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "Dictify", **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())


def _list_files(repo: str) -> list[tuple[str, int]]:
    url = f"{HF_ENDPOINT}/api/models/{repo}/tree/main"
    with _open(url) as resp:
        entries = json.load(resp)
    files = []
    for e in entries:
        if e.get("type") != "file" or e["path"] in SKIP_FILES:
            continue
        size = (e.get("lfs") or {}).get("size", e.get("size", 0))
        files.append((e["path"], int(size)))
    return files


def download_model(
    spec: ModelSpec,
    on_progress: Callable[[int, int], None],
    is_cancelled: Callable[[], bool],
) -> Path:
    """Downloads every file of the model repo into model_path(spec).
    Interrupted downloads resume from their .part files."""
    target = model_path(spec)
    if is_downloaded(spec):
        return target
    target.mkdir(parents=True, exist_ok=True)
    repo = repo_for(spec)
    files = _list_files(repo)
    total = sum(size for _, size in files)
    done = 0
    last_report = 0.0
    log.info("Downloading %s (%d files, %d MB) to %s", repo, len(files), total >> 20, target)

    for name, size in files:
        dest = target / name
        if dest.exists() and dest.stat().st_size == size:
            done += size
            continue
        part = dest.with_name(dest.name + ".part")
        have = part.stat().st_size if part.exists() else 0
        if have > size:
            part.unlink()
            have = 0
        done += have
        url = f"{HF_ENDPOINT}/{repo}/resolve/main/{urllib.parse.quote(name)}"
        headers = {"Range": f"bytes={have}-"} if have else {}
        with _open(url, headers, timeout=60) as resp:
            if have and resp.status != 206:  # server ignored Range, start over
                done -= have
                have = 0
            with open(part, "ab" if have else "wb") as fh:
                while chunk := resp.read(CHUNK):
                    if is_cancelled():
                        raise Cancelled()
                    fh.write(chunk)
                    done += len(chunk)
                    now = time.monotonic()
                    if now - last_report > 0.1:
                        on_progress(done, total)
                        last_report = now
        part.replace(dest)

    (target / COMPLETE_MARKER).write_text("ok")
    on_progress(total, total)
    return target
