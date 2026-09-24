# Dictify

Офлайн-расшифровка аудио и видео в текст для macOS (Apple Silicon) и Windows. Упрощённый аналог MacWhisper.

*Offline audio/video transcription for macOS (Apple Silicon) and Windows, powered by Whisper.*

![Dictify](assets/Dictify.png)

## Возможности

- Любой аудио- или видеофайл на входе: mp3, wav, m4a, flac, ogg, opus, mp4, mov, mkv, webm и т. д. Декодирование через FFmpeg, встроенный в PyAV.
- Распознавание полностью на компьютере, моделями Whisper от Tiny до Large v3. Модель скачивается при первом использовании.
  - **Mac (Apple Silicon):** [mlx-whisper](https://github.com/ml-explore/mlx-examples), расчёт на GPU через Metal.
  - **Windows:** [faster-whisper](https://github.com/SYSTRAN/faster-whisper), CPU или NVIDIA GPU (CUDA).
- Английский, русский и ещё 90+ языков, с автоопределением языка.
- Два режима отображения: **сплошной текст** (абзацы делятся по паузам) и **сегменты** (строки с таймкодами).
- Настройки вида: таймкоды вкл/выкл, время окончания, порог паузы для нового абзаца, длина абзаца, размер шрифта.
- Встроенный плеер: подсвечивает текущий фрагмент, клик по тексту переходит к этому месту, скорость 0.5–2×.
- Поиск по тексту с подсветкой всех совпадений.
- Редактирование текста. Таймкоды защищены от случайной правки.
- Экспорт в TXT, Markdown, SRT, Word (DOCX), PDF. Кнопка «Копировать» копирует весь текст, а в режиме чтения можно выделить и скопировать любой фрагмент.
- Интерфейс на русском и английском, светлая и тёмная темы (по системной).

## Установка (для пользователей)

Готовые сборки лежат в [Releases](https://github.com/smeshidojoe/Dictify/releases), а свежие сборки с каждого коммита во вкладке [Actions](https://github.com/smeshidojoe/Dictify/actions) (артефакты `Dictify-macOS-arm64` / `Dictify-Windows-x64`).

### macOS

1. Скачайте `Dictify-macOS-arm64.dmg` и перетащите Dictify в «Программы».
2. Приложение не подписано сертификатом Apple, поэтому при первом запуске macOS его заблокирует. Откройте **Системные настройки → Конфиденциальность и безопасность** и нажмите **«Всё равно открыть»**. Другой способ — выполнить в Терминале:
   ```bash
   xattr -dr com.apple.quarantine /Applications/Dictify.app
   ```

Нужен Mac с чипом M1 или новее и macOS 13.5+.

### Windows

Распакуйте `Dictify-Windows-x64.zip` и запустите `Dictify\Dictify.exe`. SmartScreen может предупредить о неизвестном издателе: «Подробнее → Выполнить в любом случае».

Готовая сборка считает на процессоре. Как включить видеокарту NVIDIA, описано ниже в разделе «GPU на Windows».

## Модели

| Модель | Размер | Комментарий |
|---|---|---|
| Tiny | 75 MB | очень быстро, низкое качество |
| Base | 145 MB | |
| Small | 485 MB | |
| Medium | 1.5 GB | |
| **Large v3 Turbo** | 1.6 GB | рекомендуется: почти как Large v3, но в разы быстрее |
| Large v3 | 3.1 GB | максимальная точность, медленно |

Модели хранятся здесь:
- macOS: `~/Library/Application Support/Dictify/models`
- Windows: `%LOCALAPPDATA%\Dictify\models`

Удалить скачанные модели можно кнопкой «Модели…». Если Hugging Face недоступен, задайте зеркало переменной окружения `HF_ENDPOINT`.

Логи лежат в папке `logs` рядом с моделями. Открыть её можно кнопкой «Логи» на главном экране.

## Горячие клавиши

| | |
|---|---|
| Пробел | воспроизведение / пауза (в режиме чтения) |
| ← / → | перемотка ±5 с |
| Клик по тексту | перейти к этому месту |
| Ctrl/Cmd + E | режим редактирования, Esc — выйти |
| Ctrl/Cmd + F | поиск, Enter / Shift+Enter — следующее / предыдущее |
| Ctrl/Cmd + Shift + C | скопировать весь текст |

## Разработка

Нужен Python 3.12 (подходит и 3.10–3.13).

**Windows:**
```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-win.txt -r requirements-dev.txt
.venv\Scripts\python -m dictify
```

**macOS (Apple Silicon):**
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-mac.txt -r requirements-dev.txt
.venv/bin/pip install --no-deps mlx-whisper==0.4.3
.venv/bin/python -m dictify
```
mlx-whisper ставится с `--no-deps`: в его зависимостях есть torch, numba и scipy, а они нужны только для пословных таймкодов, которые Dictify не использует.

**Тесты:**
```bash
python -m pytest
```

### GPU на Windows

```bash
.venv\Scripts\pip install -r requirements-gpu.txt
```
Этот пакет ставит библиотеки CUDA 12 (cuBLAS и cuDNN, ~1 ГБ). В режиме «Автоматически» Dictify сам попробует GPU, а если не получится, перейдёт на CPU.

### Сборка

```bash
pyinstaller --noconfirm Dictify.spec
```
Результат: `dist/Dictify/` (Windows) или `dist/Dictify.app` (macOS). Собирать нужно на той ОС, для которой нужна сборка. Mac-версию собирает GitHub Actions на раннере `macos-14` (Apple Silicon).

Собранное приложение проверяется самотестом без интерфейса:
```bash
Dictify --selftest sample.wav out-dir tiny
```
Самотест скачивает модель, распознаёт файл, создаёт окно offscreen, загружает медиа в плеер, экспортирует все форматы и пишет `out-dir/selftest.json`. CI запускает его на обеих платформах с речью, сгенерированной TTS. Так Mac-сборка проверяется без Mac под рукой.

Выпустить релиз: создать тег `vX.Y.Z` и сделать push. CI соберёт оба варианта и приложит их к GitHub Release.

## Устройство

```
dictify/
  app.py           точка входа, логирование, открытие файлов из Finder
  audio.py         декодирование любого файла в 16 кГц моно (PyAV)
  catalog.py       список моделей, докачиваемая загрузка с Hugging Face
  engines.py       faster-whisper / mlx-whisper за общим интерфейсом
  worker.py        фоновая задача: загрузка → декодирование → распознавание
  formatting.py    абзацы, таймкоды, TXT/Markdown/SRT
  exporters.py     DOCX (python-docx), PDF (Qt)
  i18n.py          русский словарь интерфейса
  selftest.py      проверка собранного приложения
  ui/              PySide6: стартовый экран, прогресс, редактор, плеер, панель
```

Каждый символ текста в редакторе (`ui/editor.py`) хранит номер своего сегмента в свойстве формата. Поэтому правки, клики по тексту и подсветка при воспроизведении однозначно привязаны к таймкодам при любой раскладке абзацев.
