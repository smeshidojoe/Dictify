"""NVIDIA GPU support for the Windows build, installed from within the app.

faster-whisper's CTranslate2 already comes with CUDA; all it lacks is NVIDIA's cuBLAS
(~730 MB unpacked), too big to ship to everyone. Owners of an NVIDIA card download it on
demand: the two DLLs are fetched straight out of NVIDIA's official wheel on PyPI with HTTP
range requests (the rest of the wheel is skipped), checked against pinned SHA-256 hashes
and unpacked into data_dir()/cuda. An interrupted download resumes where it stopped.

To move to another cuBLAS release, regenerate PARTS with tools/cuda_parts.py.
"""
from __future__ import annotations

import ctypes
import hashlib
import logging
import shutil
import sys
import time
import zlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from dictify.catalog import CHUNK, COMPLETE_MARKER, _open, backend
from dictify.errors import Cancelled
from dictify.paths import data_dir

log = logging.getLogger(__name__)

VERSION = "cublas 12.9.1.4"
MIN_DRIVER = 12000  # cuDriverGetVersion() of a driver that runs CUDA 12


@dataclass(frozen=True)
class _Part:
    name: str
    url: str
    offset: int  # where the file's deflated data starts inside the wheel
    size: int  # deflated size
    sha256: str  # of the unpacked file


_WHEEL = (
    "https://files.pythonhosted.org/packages/45/a1/a17fade6567c57452cfc8f967a40d1035bb9301db52f27808167fbb2be2f/"
    "nvidia_cublas_cu12-12.9.1.4-py3-none-win_amd64.whl"
)
PARTS = [
    _Part("cublas64_12.dll", _WHEEL, 63, 78836264,
          "90052a83efd1b57a8e3616a6590b335855f81b814a4f16eecb7b5bf6d1b1d4eb"),
    _Part("cublasLt64_12.dll", _WHEEL, 78836392, 474117864,
          "c3a05ea244c937314afec09f87b91f814c7e27977681f6c67eb51bb06ced3a4a"),
]
DOWNLOAD_MB = round(sum(p.size for p in PARTS) / 1e6)


def lib_dir() -> Path:
    return data_dir() / "cuda"


def is_installed() -> bool:
    try:
        return (lib_dir() / COMPLETE_MARKER).read_text() == VERSION
    except OSError:
        return False


def installed_mb() -> int:
    return round(sum(f.stat().st_size for f in lib_dir().glob("*") if f.is_file()) / 1e6)


@lru_cache(maxsize=1)
def nvidia_gpu() -> bool:
    """True when this build can use an NVIDIA card: one is present and its driver runs CUDA 12.
    Asks the driver directly (nvcuda.dll), which is cheap and doesn't need the libraries."""
    if sys.platform != "win32" or backend() != "faster":
        return False
    try:
        cuda = ctypes.WinDLL("nvcuda.dll")
        version, count = ctypes.c_int(), ctypes.c_int()
        ok = (
            cuda.cuInit(0) == 0
            and cuda.cuDriverGetVersion(ctypes.byref(version)) == 0
            and cuda.cuDeviceGetCount(ctypes.byref(count)) == 0
        )
    except (OSError, AttributeError):
        return False
    if ok and count.value and version.value < MIN_DRIVER:
        log.info("NVIDIA driver supports CUDA %d.%d only, GPU disabled", version.value // 1000, version.value % 1000 // 10)
    return ok and count.value > 0 and version.value >= MIN_DRIVER


def delete() -> None:
    shutil.rmtree(lib_dir(), ignore_errors=True)


def download(on_progress: Callable[[int, int], None], is_cancelled: Callable[[], bool]) -> None:
    """Fetches and unpacks every part into lib_dir(); on_progress(done, total) in bytes."""
    target = lib_dir()
    target.mkdir(parents=True, exist_ok=True)
    (target / COMPLETE_MARKER).unlink(missing_ok=True)
    total = sum(p.size for p in PARTS)
    done = 0
    log.info("Downloading %s (%d MB) to %s", VERSION, DOWNLOAD_MB, target)
    for part in PARTS:
        dest = target / part.name
        if not (dest.exists() and _sha256(dest) == part.sha256):
            packed = target / (part.name + ".part")
            _fetch(part, packed, lambda n, base=done: on_progress(base + n, total), is_cancelled)
            _unpack(packed, dest, part.sha256)
            packed.unlink()
        done += part.size
    (target / COMPLETE_MARKER).write_text(VERSION)
    on_progress(total, total)
    log.info("%s installed", VERSION)


def _fetch(part: _Part, packed: Path, on_progress: Callable[[int], None], is_cancelled: Callable[[], bool]) -> None:
    have = packed.stat().st_size if packed.exists() else 0
    if have > part.size:
        packed.unlink()
        have = 0
    if have < part.size:
        start, end = part.offset + have, part.offset + part.size - 1
        with _open(part.url, {"Range": f"bytes={start}-{end}"}, timeout=60) as resp:
            if resp.status != 206:  # a plain 200 would be the whole 500 MB wheel
                raise OSError(f"Server does not support partial downloads (HTTP {resp.status})")
            last_report = 0.0
            with open(packed, "ab") as fh:
                while chunk := resp.read(CHUNK):
                    if is_cancelled():
                        raise Cancelled()
                    fh.write(chunk)
                    have += len(chunk)
                    now = time.monotonic()
                    if now - last_report > 0.1:
                        on_progress(have)
                        last_report = now
    on_progress(have)


def _unpack(packed: Path, dest: Path, sha256: str) -> None:
    inflate = zlib.decompressobj(-zlib.MAX_WBITS)  # raw deflate, as stored in zip files
    digest = hashlib.sha256()
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        with open(packed, "rb") as src, open(tmp, "wb") as out:
            while chunk := src.read(CHUNK):
                data = inflate.decompress(chunk)
                digest.update(data)
                out.write(data)
            data = inflate.flush()
            digest.update(data)
            out.write(data)
        ok = digest.hexdigest() == sha256
    except zlib.error:
        ok = False
    if not ok:
        tmp.unlink(missing_ok=True)
        packed.unlink()  # corrupt: start over next time
        raise OSError(f"{dest.name} is damaged (checksum mismatch), try again")
    tmp.replace(dest)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
