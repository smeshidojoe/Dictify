"""Prints the PARTS table for dictify/gpu.py: where each needed DLL sits inside NVIDIA's
wheel on PyPI and the SHA-256 of the unpacked file.

    python tools/cuda_parts.py [out_dir]

Downloads the DLLs (~530 MB) to hash them; with out_dir they are kept there for testing.
CTranslate2 only needs cuBLAS: it bundles the cuDNN loader itself and never loads the rest
of cuDNN for Whisper (checked with every cuDNN library available).
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
import sys
import tempfile
import urllib.request
import zipfile
import zlib
from pathlib import Path

WHEELS = [
    ("nvidia-cublas-cu12", "12.9.1.4", ["cublas64_12.dll", "cublasLt64_12.dll"]),
]


def _get(url: str, start: int, end: int) -> bytes:
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end - 1}"})
    with urllib.request.urlopen(req) as resp:
        return resp.read()


class _Remote(io.RawIOBase):
    """Just enough of a seekable file over HTTP range requests for zipfile's directory scan."""

    def __init__(self, url: str):
        self.url, self.pos = url, 0
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as resp:
            self.size = int(resp.headers["Content-Length"])

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = (0, self.pos, self.size)[whence] + offset
        return self.pos

    def readinto(self, b):
        end = min(self.size, self.pos + len(b))
        if end <= self.pos:
            return 0
        data = _get(self.url, self.pos, end)
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for package, version, names in WHEELS:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/{version}/json") as resp:
            files = json.load(resp)["urls"]
        url = next(f["url"] for f in files if f["filename"].endswith("win_amd64.whl"))
        infos = {Path(i.filename).name: i for i in zipfile.ZipFile(io.BufferedReader(_Remote(url), 1 << 16)).infolist()}
        for name in names:
            info = infos[name]
            assert info.compress_type == zipfile.ZIP_DEFLATED, name
            header = _get(url, info.header_offset, info.header_offset + 30)
            name_len, extra_len = struct.unpack("<HH", header[26:30])
            offset = info.header_offset + 30 + name_len + extra_len
            data = zlib.decompress(_get(url, offset, offset + info.compress_size), -15)
            assert len(data) == info.file_size and zlib.crc32(data) == info.CRC, name
            (out / name).write_bytes(data)
            rows.append((name, offset, info.compress_size, hashlib.sha256(data).hexdigest()))
            print(f"{name}: {info.compress_size >> 20} MB packed, {info.file_size >> 20} MB", file=sys.stderr)
        print(f'_WHEEL = "{url}"')
        for name, offset, size, digest in rows:
            print(f'    _Part("{name}", _WHEEL, {offset}, {size},\n          "{digest}"),')
        rows.clear()
    print(f"# saved to {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
