"""Transcription runs in a separate process.

The process stays alive between jobs so the loaded model stays warm, and cancelling
simply kills it: model inference sits in native code for seconds at a time and can't be
interrupted from Python, but a killed process stops (and frees the CPU/GPU) at once.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import urllib.error
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)


@dataclass
class Job:
    path: str
    model_id: str
    language: str | None
    vad: bool = True
    device: str = "auto"


# ----- child process ------------------------------------------------------------------------


def run_job(job: Job, engine, emit) -> None:
    """The whole pipeline: download model if needed, decode, transcribe. `emit(kind, *args)`
    reports ("stage", name, fraction, detail), ("segment", Segment), ("finished", Transcript)
    or ("failed", message)."""
    from dictify.audio import SAMPLE_RATE, load_audio
    from dictify.catalog import download_model, get_model, is_downloaded, model_path
    from dictify.errors import NoAudioError
    from dictify.i18n import tr
    from dictify.model import Transcript

    never = lambda: False  # noqa: E731 - cancelling kills the process instead
    try:
        spec = get_model(job.model_id)
        if not is_downloaded(spec):
            emit("stage", "download", 0.0, "")

            def on_download(done: int, total: int) -> None:
                detail = f"{done / 1e6:,.0f} / {total / 1e6:,.0f} MB".replace(",", " ")
                emit("stage", "download", done / total if total else -1, detail)

            download_model(spec, on_download, never)

        emit("stage", "decode", 0.0, "")
        audio = load_audio(job.path, lambda f: emit("stage", "decode", f, ""), never)
        duration = len(audio) / SAMPLE_RATE
        log.info("Transcribing %s (%.1f s) with %s", job.path, duration, job.model_id)
        segments, language = engine.transcribe(
            audio,
            model_path(spec),
            job.language,
            vad=job.vad,
            device=job.device,
            report=lambda stage, f: emit("stage", stage, f, ""),
            on_segment=lambda seg: emit("segment", seg),
            is_cancelled=never,
        )
        for s in segments:
            s.end = min(max(s.end, s.start), duration)
        emit("finished", Transcript(job.path, segments, language or job.language, duration, spec.name))
    except NoAudioError:
        emit("failed", tr("The file has no audio track or its format is not supported."))
    except urllib.error.URLError as e:
        log.exception("Model download failed")
        emit("failed", tr("Could not download the model. Check your internet connection.") + f"\n\n{e}")
    except Exception as e:
        log.exception("Transcription failed")
        emit("failed", f"{type(e).__name__}: {e}")


def _child_main(jobs, events, ui_language: str) -> None:
    from logging.handlers import RotatingFileHandler

    from dictify import i18n
    from dictify.app import _fix_std_streams
    from dictify.engines import create_engine
    from dictify.paths import logs_dir

    _fix_std_streams()
    handler = RotatingFileHandler(logs_dir() / "worker.log", maxBytes=2_000_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    i18n.set_language(ui_language)

    parent = mp.parent_process()
    engine = None
    while True:
        try:
            job = jobs.get(timeout=2)
        except queue.Empty:
            if parent is not None and not parent.is_alive():  # the app died without telling us
                return
            continue
        if job is None:
            return
        if engine is None:
            engine = create_engine()
        run_job(job, engine, lambda *event: events.put(event))


# ----- GUI side -----------------------------------------------------------------------------


class TranscribeService(QObject):
    stage = Signal(str, float, str)  # stage, fraction (<0 = indeterminate), detail
    segment = Signal(object)
    finished = Signal(object)  # Transcript
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ctx = mp.get_context("spawn")
        self._proc = None
        self._jobs = None
        self._events = None
        self._busy = False
        self._timer = QTimer(self, interval=40, timeout=self._poll)

    def is_busy(self) -> bool:
        return self._busy

    def run(self, job: Job) -> None:
        from dictify.i18n import current_language

        if self._proc is None or not self._proc.is_alive():
            self._jobs, self._events = self._ctx.Queue(), self._ctx.Queue()
            self._proc = self._ctx.Process(
                target=_child_main, args=(self._jobs, self._events, current_language()), daemon=True
            )
            self._proc.start()
            log.info("Worker process %s started", self._proc.pid)
        self._busy = True
        self._jobs.put(job)
        self._timer.start()

    def cancel(self) -> None:
        if not self._busy:
            return
        self._busy = False
        self._timer.stop()
        self._kill()
        log.info("Job cancelled")
        self.cancelled.emit()

    def shutdown(self) -> None:
        self._busy = False
        self._timer.stop()
        self._kill()

    def _kill(self) -> None:
        if self._proc is not None:
            self._proc.kill()
            self._proc.join(3)
            self._proc = None
        for q in (self._jobs, self._events):
            if q is not None:
                q.cancel_join_thread()
                q.close()
        self._jobs = self._events = None

    def _poll(self) -> None:
        for _ in range(500):
            try:
                kind, *args = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "stage":
                self.stage.emit(*args)
            elif kind == "segment":
                self.segment.emit(args[0])
            elif kind in ("finished", "failed"):
                self._busy = False
                self._timer.stop()
                (self.finished if kind == "finished" else self.failed).emit(args[0])
                return
        if self._busy and self._proc is not None and not self._proc.is_alive():
            code = self._proc.exitcode
            self._busy = False
            self._timer.stop()
            self._kill()
            from dictify.i18n import tr

            self.failed.emit(tr("The transcription process stopped unexpectedly (exit code {code}).", code=code))
