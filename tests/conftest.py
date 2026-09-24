import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dictify.model import Segment, Transcript  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from dictify.ui import theme

    theme.apply(app)
    yield app


@pytest.fixture
def transcript():
    return Transcript(
        media_path="/tmp/interview.mp3",
        segments=[
            Segment(0.0, 4.0, "Hello and welcome."),
            Segment(4.2, 8.0, "Tell me about yourself."),
            Segment(12.0, 16.0, "I love working with people."),
            Segment(16.1, 20.0, "I was a teacher."),
        ],
        language="en",
        duration=20.0,
        model="tiny",
    )
