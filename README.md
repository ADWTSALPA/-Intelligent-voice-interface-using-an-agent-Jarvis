<h1 align="center">JARVIS</h1>
<h3 align="center">Intelligent Voice Interface with Agents</h3>
<p align="center"><em>A voice-controlled AI desktop assistant for Microsoft Windows, powered by large language models.</em></p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11-blue.svg" alt="Python"></a>
  <a href="https://www.microsoft.com/windows"><img src="https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D6.svg" alt="Platform"></a>
  <a href="#license"><img src="https://img.shields.io/badge/License-Academic-green.svg" alt="License"></a>
</p>

---

## Overview

JARVIS is a desktop voice assistant that lets you control Microsoft Windows through natural conversation. Say the wake word "Jarvis", give a command in plain English, and the assistant launches apps, opens files, searches the web, or answers your question with a natural-sounding voice.

It combines real-time speech recognition, an OpenAI language model for understanding intent, and a multi-layered system for finding and launching virtually any application installed on your PC — including classic `.exe` programs, Microsoft Office, and Microsoft Store apps.

This project was developed as a BSc Computer Science thesis at the University of East London.

---

## Features

- **Wake word activation** — listens passively until you say "Jarvis"
- **Natural language understanding** via OpenAI Responses API (GPT-4.1-mini)
- **Offline fallback** — works without internet through a rule-based parser
- **Smart application launcher** — finds apps through six layered mechanisms:
  - Hardcoded common apps (Word, Chrome, Settings, etc.)
  - Microsoft Store / UWP apps (Netflix, Spotify, WhatsApp, Disney+)
  - Windows Registry (installed programs like Discord, Zoom, VLC, OBS)
  - Start Menu shortcuts (Steam games, portable apps, tools)
  - App Paths registry (anything that runs from Win+R, including Office)
  - Fuzzy matching for typos and abbreviations
- **Instant voice interruption** — say "Jarvis stop" to cut off the response immediately
- **Graceful exit** — waits for the farewell to finish before closing
- **Multi-action commands** — execute several commands from one sentence
- **Voice synthesis** with natural British English voice (Edge TTS, en-GB-RyanNeural)
- **Graphical interface** built with PySide6/Qt, including microphone mute toggle
- **Web actions** — Google search, YouTube playback
- **Information queries** — time, date, weather, general knowledge questions

---

## Quick Start (For Users)

If you just want to use JARVIS without setting up a development environment:

1. Download the latest `Jarvis.exe` from the release folder
2. Place it in any directory along with a `.env` file (see [Configuration](#configuration))
3. Double-click `Jarvis.exe` to launch
4. Click the **Start** button in the window that appears
5. Say "Jarvis" followed by your command

That's it — no Python installation required.

---

## Build From Source (For Developers / Evaluators)

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Operating System | Windows 10 or 11 | Required (uses Windows-specific APIs) |
| Python | 3.11.x | Other versions may work but are untested |
| Microphone | Any | Built-in laptop mics work fine |
| Internet connection | Required | For speech recognition and OpenAI |
| OpenAI API key | Optional | App falls back to offline parser without it |

### Installation

Clone or download the repository, then open a terminal in the project folder and run:

```cmd
build.bat
```

This script will:

1. Verify that Python 3.11 is installed (downloads it if not)
2. Create a virtual environment (`build_venv`)
3. Install all required packages from `requirements.txt`
4. Install PyInstaller
5. Build a self-contained `Jarvis.exe` in the `dist/` folder

The build takes 2–5 minutes the first time. Subsequent builds are faster because the venv is reused.

### Running the built application

Once `build.bat` finishes, open the **`dist`** folder that was created in the project directory. Inside it you will find **`Jarvis.exe`** — double-click it to launch the assistant. You can also move this `.exe` anywhere you like (just keep a `.env` file next to it if you want OpenAI features).

```
project folder/
└── dist/
    └── Jarvis.exe   ←  run this
```

> **Note:** If you copy the project to a different PC, delete the `build_venv` folder first. Virtual environments are not portable across machines — `build.bat` will automatically detect a broken venv and recreate it.

### Manual run (without building an exe)

If you prefer to run the source directly without building:

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python run_jarvis.py
```

---

## Configuration

Create a `.env` file in the project root with your OpenAI API key:

```env
OPENAI_API_KEY=sk-your-key-here
```

If no API key is provided, JARVIS automatically falls back to its offline rule-based parser. The offline mode handles most basic commands (open apps, web search, time, date) but lacks the conversational understanding of the LLM brain.

You can get an API key from <https://platform.openai.com/api-keys>.

---

## Usage

### Starting the assistant

1. Launch `Jarvis.exe` (or run `python run_jarvis.py`)
2. Click **Start** in the GUI
3. Wait for the status to change to "Listening"

### Wake word

All commands must begin with the wake word **"Jarvis"**. The assistant ignores everything that does not contain it.

### Example commands

| What you say | What happens |
|--------------|--------------|
| "Jarvis, open Word" | Launches Microsoft Word (via App Paths registry) |
| "Jarvis, open PowerPoint" | Launches PowerPoint |
| "Jarvis, open Netflix" | Opens the Netflix Store app (UWP) |
| "Jarvis, open Discord" | Launches Discord (found via registry) |
| "Jarvis, open obs" | Opens OBS Studio (fuzzy match) |
| "Jarvis, play despacito on YouTube" | Searches YouTube and plays the video |
| "Jarvis, search for cats" | Opens Google search |
| "Jarvis, what time is it?" | Speaks the current time |
| "Jarvis, what is the capital of France?" | Answers via the language model |
| "Jarvis, close Chrome" | Closes the Chrome browser |
| "Jarvis, open Word and Chrome" | Multi-action — opens both |
| "Jarvis stop" | Interrupts speech immediately |
| "Jarvis goodbye" | Closes the application (after the farewell finishes) |

### Just the wake word

If you say only "Jarvis" without a command, the assistant will respond "Yes, sir?" and wait for your follow-up question or instruction.

### Microphone mute

Click the **Mute Microphone** button in the GUI to stop the assistant from listening. Click again to resume.

---

## Architecture

JARVIS processes each voice command through a pipeline of specialized components:

![JARVIS System Architecture](JARVIS_Architecture.png)

The flow at a high level:

1. **Voice (Input)** — the microphone captures audio
2. **Speech-to-Text** — SpeechRecognition library + Google API converts audio to text
3. **Wake Word Detection** — filters out everything that does not contain "Jarvis"
4. **Agent Brain** — OpenAI Responses API parses the command into a structured intent (JSON)
5. **Offline Brain** — rule-based fallback used automatically if the API fails
6. **Processing (Executor)** — dispatches the intent to the appropriate action
7. **Microsoft Windows OS** — actions are executed on the operating system
8. **Text-to-Speech** — Edge TTS generates speech, played back via pygame.mixer
9. **Voice (Output)** — the response is spoken back to the user

---

## How App Discovery Works

One of the core technical features of JARVIS is its ability to locate and launch almost any application by name, without manual configuration. When you say "Jarvis, open X", the resolver tries six strategies in order, from fastest to most exhaustive, and stops at the first match:

1. **Known apps list** — a small hardcoded map of the most common applications (Word, Chrome, Settings, Calculator, File Explorer). Instant lookup.

2. **Microsoft Store / UWP apps** — Store apps are not regular `.exe` files; they launch through a special URI (`shell:AppsFolder\<PackageFamilyName>!App`). JARVIS queries the PowerShell cmdlet `Get-StartApps` to enumerate them dynamically, so apps like Netflix, Spotify, and WhatsApp work out of the box.

3. **Windows Registry (installed programs)** — reads the uninstall registry keys (`HKLM` and `HKCU`) to find programs installed with an installer, such as Discord, Zoom, VLC, OBS, and most desktop software.

4. **Start Menu shortcuts** — scans the system and user Start Menu folders for `.lnk` shortcuts. This catches Steam/Epic games, portable apps with shortcuts, and older programs.

5. **App Paths registry** — the same registry key the Windows "Run" dialog (Win+R) uses. This resolves command-line tools and registered executables, and is the key that makes Microsoft Office (`winword.exe`, `excel.exe`, `powerpnt.exe`) launch reliably even though Office is not on the system PATH.

6. **Fuzzy matching** — as a last resort, all discovered app names are compared against the spoken name using string similarity (with a strict threshold to avoid wrong matches). This means "obs" still finds "OBS Studio" and small typos like "discrd" still find "Discord".

Once an application is resolved, its path is cached so that subsequent launches are instant. The first time you request a UWP/Store app, there is a brief (~1 second) delay while PowerShell enumerates the Store apps; after that, the result stays in memory.

---

## Voice Interruption & Graceful Exit

JARVIS uses `pygame.mixer` for audio playback specifically so that speech can be interrupted instantly. While the assistant is speaking, a background worker checks every 50 milliseconds whether a stop has been requested. Saying "Jarvis stop" cuts off the response immediately, rather than waiting for the sentence to finish.

When you say "Jarvis goodbye", the application does not close abruptly. It waits until the farewell message has finished playing (tracking both the speech queue and the speaking state, with a safety timeout) before shutting down cleanly, so the full message is always heard.

---

## Project Structure

```
jarvis/
├── run_jarvis.py          # Entry point
├── build.bat              # Build script (creates Jarvis.exe via PyInstaller)
├── requirements.txt       # Python dependencies
├── .env                   # Your OpenAI API key (not in repo)
├── jarvis.ico             # Application icon
│
└── Jarvis/                # Main package
    ├── __init__.py
    ├── config.py          # Constants, OpenAI client, shared state, Qt signals
    ├── voice.py           # Speech recognition + Edge TTS + pygame playback
    ├── brain.py           # OpenAI agent + offline rule-based parser
    ├── executor.py        # Intent dispatch + wake word callback
    ├── finder.py          # App / file / folder discovery and launching
    ├── cache.py           # Persistent cache of resolved app paths
    └── ui.py              # PySide6 GUI
```

---

## Dependencies

Core packages installed by `requirements.txt`:

| Package | Purpose |
|---------|---------|
| `PySide6` | Qt-based graphical interface |
| `SpeechRecognition` | Voice-to-text via Google API |
| `PyAudio` | Microphone audio capture |
| `edge-tts` | Microsoft Edge text-to-speech synthesis |
| `pygame` | Audio playback with interruption support |
| `openai` | Official OpenAI API client |
| `python-dotenv` | Loads `OPENAI_API_KEY` from `.env` |

---

## Troubleshooting

### Microphone is not detected

Make sure your microphone is enabled in **Windows Settings → Privacy → Microphone**, and that your default recording device is the one you intend to use. Restart JARVIS after changing devices.

### "Yes, sir?" responds slowly

The first response after launch may take 1–2 seconds because the Edge TTS service has to download the audio. Subsequent responses are faster.

### A Microsoft Store app (Netflix, Spotify, WhatsApp) won't open

The first time you ask for a Store app, JARVIS queries PowerShell to enumerate installed UWP apps. This takes about 1 second. After that, the result is cached in memory and launches are instant.

### Microsoft Office apps (Word, Excel, PowerPoint) won't open

If Office is installed but does not launch, your installation may not be registered in the App Paths registry. Try opening it manually once from the Start menu — Windows will then register it correctly.

### Build fails with "Python was not found"

Delete the `build_venv` folder and run `build.bat` again. This usually happens when the project is copied from a different machine, because virtual environments hardcode the original Python path.

### The assistant keeps hearing its own voice

This is a limitation of using the same microphone that picks up the speakers. Use headphones for the most reliable experience, especially when issuing "Jarvis stop" commands while it is still speaking.

---

## Limitations

- **English only** — speech recognition and synthesis are configured for English (`en-US` and `en-GB-RyanNeural`)
- **Windows only** — the app uses Windows-specific APIs (registry, UWP launcher, App Paths)
- **Cloud dependent** — speech recognition uses Google's free API and the brain uses OpenAI; both require internet
- **No echo cancellation** — the assistant may detect its own voice when responding through speakers

---

## Credits

**Author:** Tsalpatouros Andreas (UEL No. 2673025)
**Supervisor:** Dr. Grivokostopoulou Foteini
**Institution:** University of East London — BSc Computer Science
**Submission date:** 31 May 2026

---

## License

This software was developed as part of an academic thesis project. All rights reserved. For academic evaluation and educational purposes only.
