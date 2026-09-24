"""Background transcription job. Lives on one dedicated QThread for the whole session,
so the loaded model stays warm and MLX always runs on the same thread."""
from __future__ import annotations

import logging
import threading
import urllib.error
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from dictify.audio import SAMPLE_RATE, load_audio
from dictify.catalog import download_model, get_model, is_downloaded, model_path
from dictify.engines import create_engine
from dictify.errors import Cancelled, NoAudioError
from dictify.i18n import tr
from dictify.model import Transcript

log = logging.getLogger(__name__)


@dataclass
class Job:
    path: str
    model_id: str
    language: str | None
    vad: bool = True
    device: str = "auto"


class TranscribeWorker(QObject):
    stage = Signal(str, float, str)  # stage, fraction (<0 = indeterminate), detail
    segment = Signal(object)
    finished = Signal(object)  # Transcript
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self):
        super().__init__()
        self._cancel = threading.Event()
        self._engine = None

    def cancel(self) -> None:
        self._cancel.set()

    @Slot(object)
    def run(self, job: Job) -> None:
        self._cancel.clear()
        is_cancelled = self._cancel.is_set
        try:
            spec = get_model(job.model_id)
            if not is_downloaded(spec):
                self.stage.emit("download", 0.0, "")

                def on_download(done: int, total: int) -> None:
                    detail = f"{done / 1e6:,.0f} / {total / 1e6:,.0f} MB".replace(",", " ")
                    self.stage.emit("download", done / total if total else -1, detail)

                download_model(spec, on_download, is_cancelled)

            self.stage.emit("decode", 0.0, "")
            audio = load_audio(job.path, lambda f: self.stage.emit("decode", f, ""), is_cancelled)
            duration = len(audio) / SAMPLE_RATE
            log.info("Transcribing %s (%.1f s) with %s", job.path, duration, job.model_id)

            if self._engine is None:
                self._engine = create_engine()
            segments, language = self._engine.transcribe(
                audio,
                model_path(spec),
                job.language,
                vad=job.vad,
                device=job.device,
                report=lambda stage, f: self.stage.emit(stage, f, ""),
                on_segment=self.segment.emit,
                is_cancelled=is_cancelled,
            )
            for s in segments:
                s.end = min(max(s.end, s.start), duration)
            self.finished.emit(
                Transcript(job.path, segments, language or job.language, duration, spec.name)
            )
        except Cancelled:
            log.info("Job cancelled")
            self.cancelled.emit()
        except NoAudioError:
            self.failed.emit(tr("The file has no audio track or its format is not supported."))
        except urllib.error.URLError as e:
            log.exception("Model download failed")
            self.failed.emit(tr("Could not download the model. Check your internet connection.") + f"\n\n{e}")
        except Exception as e:
            log.exception("Transcription failed")
            self.failed.emit(f"{type(e).__name__}: {e}")
