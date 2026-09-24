"""Headless check of a built app bundle, run by CI on each platform:

    Dictify --selftest <audio file> <output dir> [model]

Downloads the model, transcribes the file, builds the main window offscreen, loads the
media into the player and exports every format. Writes selftest.json into <output dir>
(windowed builds have no console) and exits non-zero on failure.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path


def run(argv: list[str]) -> int:
    audio_path, out_dir = argv[0], Path(argv[1])
    model_id = argv[2] if len(argv) > 2 else "tiny"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"ok": False, "steps": []}

    def step(name: str, **info) -> None:
        report["steps"].append({"step": name, "t": round(time.monotonic() - started, 2), **info})

    started = time.monotonic()
    try:
        from dictify.audio import SAMPLE_RATE, load_audio
        from dictify.catalog import backend, download_model, get_model, model_path
        from dictify.engines import create_engine
        from dictify.model import Transcript

        report["backend"] = backend()
        spec = get_model(model_id)
        download_model(spec, lambda d, t: None, lambda: False)
        step("download")
        audio = load_audio(audio_path)
        step("decode", seconds=round(len(audio) / SAMPLE_RATE, 2))
        engine = create_engine()
        streamed = []
        segments, language = engine.transcribe(
            audio, model_path(spec), None,
            report=lambda *_: None, on_segment=streamed.append, is_cancelled=lambda: False,
        )
        report["device"] = engine.device
        report["streamed_segments"] = len(streamed)
        report["words"] = [(round(w.start, 2), s.text[w.offset:].split(" ")[0]) for s in segments for w in s.words]
        report["language"] = language
        report["text"] = " ".join(s.text for s in segments)
        step("transcribe", segments=len(segments))
        if not segments:
            raise RuntimeError("no speech recognized")
        if not streamed:
            raise RuntimeError("no segments were streamed during transcription")
        if not report["words"]:
            raise RuntimeError("no word timestamps")

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtMultimedia import QMediaPlayer
        from PySide6.QtWidgets import QApplication

        from dictify import exporters
        from dictify.ui import theme
        from dictify.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        theme.apply(app)
        window = MainWindow()
        t = Transcript(audio_path, segments, language, len(audio) / SAMPLE_RATE, spec.name)
        window.ws.load_media(audio_path, t.duration)
        window.ws.set_transcript(t)
        deadline = time.monotonic() + 10
        player = window.ws.player.player
        while player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadingMedia, QMediaPlayer.MediaStatus.NoMedia):
            app.processEvents()
            if time.monotonic() > deadline:
                break
            time.sleep(0.05)
        report["media_status"] = player.mediaStatus().name
        report["media_error"] = player.errorString()
        step("ui")
        if player.error() != QMediaPlayer.Error.NoError:
            raise RuntimeError(f"media player: {player.errorString()}")

        for fmt in exporters.FORMATS:
            path = out_dir / f"selftest{fmt.ext}"
            exporters.export(t, window.ws.opts, fmt.key, path)
            if path.stat().st_size == 0:
                raise RuntimeError(f"empty export: {fmt.key}")
        step("export")
        window.ws.dirty = False
        window.shutdown(ask=False)

        # The app transcribes in a separate process (spawned from the frozen executable).
        from dictify.worker import Job, TranscribeService

        service = TranscribeService()
        got: dict = {"segments": 0}
        service.segment.connect(lambda _s: got.update(segments=got["segments"] + 1))
        service.finished.connect(lambda tr_: got.update(transcript=tr_))
        service.failed.connect(lambda msg: got.update(error=msg))

        def wait(cond, seconds):
            deadline = time.monotonic() + seconds
            while not cond() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)

        service.run(Job(audio_path, model_id, None))
        wait(lambda: "transcript" in got or "error" in got, 180)
        if "transcript" not in got:
            raise RuntimeError(f"worker process: {got.get('error', 'timed out')}")
        report["worker_text"] = " ".join(s.text for s in got["transcript"].segments)
        step("worker", streamed=got["segments"])

        service.run(Job(audio_path, model_id, None))
        wait(lambda: False, 0.3)
        started = time.monotonic()
        service.cancel()
        report["cancel_seconds"] = round(time.monotonic() - started, 3)
        if service.is_busy() or service._proc is not None or report["cancel_seconds"] > 3:
            raise RuntimeError("cancel did not stop the worker process")
        step("cancel")
        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        (out_dir / "selftest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
