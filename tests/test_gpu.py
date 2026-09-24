"""The CUDA libraries downloader, against a fake wheel served with HTTP range requests."""
import hashlib
import io
import os
import zipfile

import pytest

from dictify import gpu
from dictify.errors import Cancelled


class _Response(io.BytesIO):
    def __init__(self, data: bytes, status: int):
        super().__init__(data)
        self.status = status

    def __exit__(self, *exc):
        self.close()
        return False


@pytest.fixture
def wheel(tmp_path, monkeypatch):
    """Builds a zip like NVIDIA's wheel, points gpu.PARTS into it and serves it."""
    files = {"nvidia/cublas/bin/a.dll": os.urandom(300_000) + bytes(700_000), "nvidia/cublas/bin/b.dll": b"b" * 50_000}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    blob = buf.getvalue()
    parts = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for info in z.infolist():
            offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
            parts.append(gpu._Part(info.filename.rsplit("/", 1)[1], "https://example/wheel.whl", offset,
                                   info.compress_size, hashlib.sha256(files[info.filename]).hexdigest()))
    requests = []

    def fake_open(url, headers=None, timeout=30):
        start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        requests.append((start, end))
        return _Response(blob[start:end + 1], 206)

    monkeypatch.setattr(gpu, "PARTS", parts)
    monkeypatch.setattr(gpu, "_open", fake_open)
    monkeypatch.setattr(gpu, "CHUNK", 4096)
    monkeypatch.setattr(gpu, "lib_dir", lambda: tmp_path / "cuda")
    return {"files": files, "blob": blob, "requests": requests, "dir": tmp_path / "cuda"}


def test_download_unpacks_only_the_parts(wheel):
    progress = []
    gpu.download(lambda done, total: progress.append((done, total)), lambda: False)
    assert gpu.is_installed()
    assert (wheel["dir"] / "a.dll").read_bytes() == wheel["files"]["nvidia/cublas/bin/a.dll"]
    assert (wheel["dir"] / "b.dll").read_bytes() == wheel["files"]["nvidia/cublas/bin/b.dll"]
    assert not list(wheel["dir"].glob("*.part"))
    total = sum(p.size for p in gpu.PARTS)
    assert progress[-1] == (total, total)
    assert sum(end - start + 1 for start, end in wheel["requests"]) == total  # nothing else fetched


def test_download_resumes_after_cancel(wheel):
    calls = {"n": 0}

    def cancel_soon():
        calls["n"] += 1
        return calls["n"] > 3

    with pytest.raises(Cancelled):
        gpu.download(lambda *_: None, cancel_soon)
    assert not gpu.is_installed()
    part = wheel["dir"] / "a.dll.part"
    have = part.stat().st_size
    assert have > 0
    wheel["requests"].clear()
    gpu.download(lambda *_: None, lambda: False)
    assert gpu.is_installed()
    first = gpu.PARTS[0]
    assert wheel["requests"][0] == (first.offset + have, first.offset + first.size - 1)


def test_damaged_download_is_discarded(wheel, monkeypatch):
    bad = [gpu._Part(p.name, p.url, p.offset, p.size, "0" * 64) for p in gpu.PARTS]
    monkeypatch.setattr(gpu, "PARTS", bad)
    with pytest.raises(OSError, match="damaged"):
        gpu.download(lambda *_: None, lambda: False)
    assert not gpu.is_installed()
    assert not list(wheel["dir"].glob("a.dll*"))


def test_server_without_ranges_is_rejected(wheel, monkeypatch):
    monkeypatch.setattr(gpu, "_open", lambda *a, **k: _Response(wheel["blob"], 200))
    with pytest.raises(OSError, match="partial"):
        gpu.download(lambda *_: None, lambda: False)


def test_delete(wheel):
    gpu.download(lambda *_: None, lambda: False)
    gpu.delete()
    assert not gpu.is_installed() and not wheel["dir"].exists()


def test_pinned_parts_are_consistent():
    assert gpu.DOWNLOAD_MB == round(sum(p.size for p in gpu.PARTS) / 1e6)
    for p in gpu.PARTS:
        assert p.url.startswith("https://files.pythonhosted.org/") and len(p.sha256) == 64
