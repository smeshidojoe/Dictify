"""Tiny translation layer: English source strings, Russian dictionary."""
from __future__ import annotations

_lang = "en"

UI_LANGUAGES = [("system", "System"), ("en", "English"), ("ru", "Русский")]

# Spoken languages offered for transcription (Whisper codes). Endonyms need no translation.
SPEECH_LANGUAGES = [
    ("en", "English"),
    ("ru", "Русский"),
    ("uk", "Українська"),
    ("be", "Беларуская"),
    ("kk", "Қазақ тілі"),
    ("de", "Deutsch"),
    ("fr", "Français"),
    ("es", "Español"),
    ("it", "Italiano"),
    ("pt", "Português"),
    ("pl", "Polski"),
    ("cs", "Čeština"),
    ("nl", "Nederlands"),
    ("tr", "Türkçe"),
    ("ar", "العربية"),
    ("hi", "हिन्दी"),
    ("zh", "中文"),
    ("ja", "日本語"),
    ("ko", "한국어"),
]


def set_language(code: str) -> None:
    global _lang
    if code == "system":
        from PySide6.QtCore import QLocale

        code = "ru" if QLocale.system().language() == QLocale.Language.Russian else "en"
    _lang = code if code in ("en", "ru") else "en"


def current_language() -> str:
    return _lang


def tr(text: str, **kwargs) -> str:
    if _lang == "ru":
        text = RU.get(text, text)
    return text.format(**kwargs) if kwargs else text


def speech_language_name(code: str | None) -> str:
    for c, name in SPEECH_LANGUAGES:
        if c == code:
            return name
    return (code or "—").upper()


RU = {
    # start screen
    "Drop an audio or video file here": "Перетащите сюда аудио- или видеофайл",
    "or click to choose a file": "или нажмите, чтобы выбрать файл",
    "Model": "Модель",
    "Language": "Язык",
    "Detect automatically": "Определить автоматически",
    "Compute on": "Вычисления",
    "Automatic": "Автоматически",
    "CPU": "Процессор (CPU)",
    "GPU (NVIDIA CUDA)": "Видеокарта (NVIDIA CUDA)",
    "Interface": "Интерфейс",
    "System": "Системный",
    "Logs": "Логи",
    "recommended": "рекомендуется",
    "downloaded": "скачана",
    "Choose an audio or video file": "Выберите аудио- или видеофайл",
    "Audio and video": "Аудио и видео",
    "All files": "Все файлы",
    # progress
    "Downloading model…": "Скачивание модели…",
    "Reading audio…": "Чтение аудио…",
    "Loading model…": "Загрузка модели…",
    "Transcribing…": "Распознавание…",
    "Recognized text will appear here…": "Здесь появится распознанный текст…",
    "less than a minute": "меньше минуты",
    "~{n} min": "~{n} мин",
    "{t} left": "осталось {t}",
    "elapsed {t}": "прошло {t}",
    "Cancel": "Отмена",
    "Cancelling…": "Отмена…",
    # transcript screen
    "Edit": "Править",
    "Edit the transcript text (Esc to finish)": "Редактировать текст (Esc — закончить)",
    "Copy": "Копировать",
    "Copy the whole transcript": "Скопировать весь текст",
    "Export": "Экспорт",
    "Search in transcript": "Поиск по тексту",
    "Show or hide the sidebar": "Показать или скрыть панель",
    "No matches": "Нет совпадений",
    "Transcript copied to clipboard": "Текст скопирован в буфер обмена",
    "Export transcript": "Экспорт текста",
    "Export failed": "Не удалось экспортировать",
    "Saved {name}": "Сохранено: {name}",
    "Plain text (.txt)": "Текст (.txt)",
    "Markdown (.md)": "Markdown (.md)",
    "Subtitles (.srt)": "Субтитры (.srt)",
    "Word (.docx)": "Word (.docx)",
    "PDF (.pdf)": "PDF (.pdf)",
    "Play / pause (Space)": "Воспроизведение / пауза (пробел)",
    "Playback speed": "Скорость воспроизведения",
    "Playback unavailable": "Воспроизведение недоступно",
    # sidebar
    "Display mode": "Режим отображения",
    "Transcript": "Сплошной текст",
    "Segments": "Сегменты",
    "Options": "Параметры",
    "Timestamps": "Таймкоды",
    "Show end time": "Время окончания",
    "New paragraph after pause": "Новый абзац после паузы",
    " s": " с",
    "Paragraph length": "Длина абзаца",
    "Short": "Короткие",
    "Medium": "Средние",
    "Long": "Длинные",
    "Text size": "Размер текста",
    "Info": "Информация",
    "Duration": "Длительность",
    "Words": "Слов",
    # models dialog
    "Models": "Модели",
    "Models are downloaded automatically the first time you use them. Larger models are more accurate but slower.":
        "Модели скачиваются автоматически при первом использовании. Большие модели точнее, но медленнее.",
    "Open models folder": "Открыть папку моделей",
    "Close": "Закрыть",
    "Delete": "Удалить",
    "Delete model": "Удаление модели",
    "Delete {name} from disk? It will be downloaded again when needed.":
        "Удалить {name} с диска? При необходимости она скачается снова.",
    "Some files could not be removed. Close the app and try again.":
        "Не удалось удалить часть файлов. Закройте приложение и попробуйте снова.",
    # messages
    "File not found:\n{path}": "Файл не найден:\n{path}",
    "No speech was recognized in this file.": "В этом файле не удалось распознать речь.",
    "Transcription failed": "Ошибка распознавания",
    "The transcript hasn't been exported or copied.": "Текст ещё не экспортирован и не скопирован.",
    "Discard it?": "Удалить его?",
    "Discard": "Удалить",
    "The file has no audio track or its format is not supported.":
        "В файле нет звуковой дорожки, или его формат не поддерживается.",
    "Could not download the model. Check your internet connection.":
        "Не удалось скачать модель. Проверьте подключение к интернету.",
    # single-window flow
    "Transcription": "Распознавание",
    "Manage models": "Управление моделями",
    "will be downloaded on first use": "скачается при первом использовании",
    "Skip silence": "Пропускать тишину",
    "Fewer hallucinations on long pauses": "Меньше галлюцинаций на длинных паузах",
    "Transcribe": "Распознать",
    "Transcribe again": "Распознать заново",
    "No paragraphs": "Без абзацев",
    "Close file": "Закрыть файл",
    "Press “Transcribe” to start.": "Нажмите «Распознать», чтобы начать.",
    "Wait for the transcription to finish or cancel it first.": "Дождитесь окончания распознавания или отмените его.",
    "The interface language will change after the file is closed.": "Язык интерфейса сменится после закрытия файла.",
    "Drop the file to transcribe it": "Отпустите файл, чтобы распознать его",
}
