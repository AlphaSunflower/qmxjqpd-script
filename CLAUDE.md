# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Desktop automation tool for the mobile game "全明星街球派对" (All-Star Street Basketball Party). Controls Android emulators via ADB to automate in-game actions (match queuing, tactics, etc.) across multiple game modes. Built with Python, using customtkinter for the GUI and RapidOCR (ONNX)/OpenCV for screen understanding.

## Commands

```bash
# Run in development
python main.py

# Package into standalone .exe (PyInstaller, windowed mode)
python package.py --file main.py
python package.py --file main.py --nvidia  # include NVIDIA CUDA/cuDNN

# Activate virtual environment
source myenv/Scripts/activate  # Git Bash
```

## Architecture

```
main.py                          # Entry point — creates MainWindow(customtkinter) and starts the Tk event loop
├── ui/main_window.py            # All UI: mode selection, port config, log display, start/stop controls
├── core/
│   ├── base_strategy.py         # ABC with ADB connect, tap/swipe, OCR, template/SIFT matching, color detection
│   ├── strategy_manager.py      # Thread runner — starts one daemon thread per ADB port, each instantiates strategies
│   └── strategies/              # Concrete strategies, one per game mode
│       ├── chaolian_front.py    #   季前赛 (preseason)
│       ├── chaolian_challenge.py #  挑战赛 (challenge)
│       ├── chaolian_step.py     #   天梯赛 (ladder)
│       ├── dynasty_55.py        #  5v5 (stub)
│       └── dynasty_33.py        #  3v3 (stub)
├── services/
│   ├── adb_service.py           # ADB wrapper: connect, screencap, tap, swipe, shell, get screen size
│   ├── image_service.py         # OpenCV template/SIFT matching, RapidOCR (sync + async thread pool)
│   └── logger_service.py        # Singleton logger — file + console + in-memory queue for UI polling
├── config/settings.json         # User settings (persisted to ~/.qmxChaoLian when packaged)
├── resources/
│   ├── config/mode_config.json  # Declares game modes and their toggleable options
│   └── images/                  # Template images for SIFT/template matching (win, defeat, match, begin, etc.)
├── paths.py                     # Provides resource_path() and save_path() for dev vs PyInstaller-bundled paths
├── package.py                   # PyInstaller packaging script
└── hooks/                       # PyInstaller runtime hooks (currently empty; rthook_paddlex.py removed after RapidOCR migration)
```

## Key Patterns

- **New game mode**: Add a strategy class in `core/strategies/`, register it in `core/strategies/__init__.py` (STRATEGY_MAP), and add its config entry in `resources/config/mode_config.json` under the appropriate group (`dynasty` or `chaolian`).
- **Coordinates**: All tap/swipe/OCR coordinates are designed at 1280×720 resolution. `BaseStrategy` auto-scales them to the actual device resolution.
- **Stop mechanism**: A global `threading.Event` (`stop_event` at `core/strategy_manager.py`) is checked by all strategies in loops and sleep calls. Respect it in new strategy code.
- **Logging in UI**: Log messages go through `LoggerService._log_queue`. The UI polls it every 50ms via `_poll_log_queue()`. Never write directly to Tkinter widgets from worker threads.
- **Strategy configuration**: When the user clicks "开始执行", `MainWindow._on_start` dynamically creates `Configured` strategy subclasses with the user's selected options injected via constructor. Strategies read options from `self.config`.
