## ConKey: Control Laptop Keyboard via Mobile Phone (Bluetooth & Wi-Fi)

ConKey allows you to use your Android phone as a wireless keyboard, hotkey remote, and mouse for your Windows laptop over **direct Bluetooth** or Wi-Fi without any extra hardware.

Built specifically to rescue laptops with broken hardware keys (`Ctrl+C`, `Ctrl+V`, `A`, `S`, `!`, navigation keys, etc.).

---

## Bluetooth Pair & Play Quick Start (Zero Router Issues)

### 1. Pair Once via Windows & Phone
1. On your laptop, make sure Bluetooth is ON (laptop name: `ave`).
2. On your phone, go to **Settings -> Bluetooth** and pair with your laptop.
3. Done!

### 2. Open the ConKey App
1. Install or update [`conkey.apk`](file:///c:/Users/YashN/Desktop/conkey/conkey.apk).
2. Open ConKey. It automatically detects your paired laptop and connects immediately over Bluetooth.
3. The top indicator turns green (`🟢 ave (Bluetooth)`). You can begin typing immediately.

---

## Features

- **Direct Bluetooth Radio Connection**: Completely bypasses home Wi-Fi routers and client isolation issues. Provides rock-solid, sub-5ms low latency.
- **Official Virtual Keyboard Engine**: Integrates the industry-standard `simple-keyboard` package with mechanical key styling, smooth animations, and tactile feedback.
- **Laptop Controls Included**: Features `Ctrl`, `Shift`, `Tab`, `Alt`, `Win`, `Esc`, `Caps`, `Enter`, `Backspace`, `Space`, `Del`, and arrow keys (`▲`, `◀`, `▼`, `▶`).
- **Sticky Modifiers**: Tap `Ctrl`, `Alt`, `Shift`, or `Win` to latch it on with a golden highlight. Pressing keys sends the combined chord (such as `Ctrl+C` or `Alt+Tab`) and unlatches automatically.
- **Quick Hotkeys Deck**: Instant one-tap buttons for `Ctrl+C`, `Ctrl+V`, `Ctrl+X`, `Ctrl+Z`, `Ctrl+A`, `Ctrl+S`, `Alt+Tab`, and `TaskMgr`.
- **Direct Phone Keyboard Typing**: Type or dictate sentences using your favorite Android keyboard into the laptop's foreground window.
- **Mouse Buttons**: Dedicated left and right click buttons at the bottom.
- **Dual Transport Host**: The Windows background service accepts direct Bluetooth RFCOMM connections and Wi-Fi WebSockets simultaneously.
- **Real-Time Voice Typing**: Streams microphone audio from the phone to the laptop and shows Phonon-2 transcripts in the input field while you speak. Fully local and offline; requires Wi-Fi.

---

## Real-Time Voice Typing with Phonon-2

Voice typing streams your microphone from the phone to the laptop and back as text while you speak. The ConKey host runs Fermion Research's [Phonon-2](https://huggingface.co/FermionResearch/Phonon-2) speech model locally on the laptop CPU and relays live partial transcripts over the same authenticated Wi-Fi WebSocket used by the keyboard. Nothing is recorded to disk or sent to a cloud service.

### One-Time Setup (laptop)

1. Install Python 3.10–3.14, then run [`setup_voice.bat`](setup_voice.bat), or do it manually:

   ```bat
   python -m pip install --user fermion-research
   python host\voice_setup.py
   ```

2. The script downloads the ~158 MB model into `%USERPROFILE%\.cache\fermion\speech\FermionResearch__Phonon-2\`, prints the selected CPU kernel tier, and boots the local speech server once to verify `/health`.
3. Start ConKey as usual (`start_conkey.bat`). The banner shows `Voice Typing: phonon-2 (streaming on 127.0.0.1:8010)`.

### Using It (phone or browser)

- Connect over **Wi-Fi**. Bluetooth HID-only mode cannot transcribe because the host software and model run on the laptop.
- Tap the **mic** button in the typing bar. The app shows `Listening` and partial words appear in the input field as you speak.
- Pauses finish a segment. With **AUTO** off (default), finalized text stays in the input field so you can review it and press **Send**. Tap **AUTO** to type each finalized segment directly into the laptop's focused window.
- Tap the mic again to stop. The last segment is finalized, and the full transcript remains in the input field.

### How It Streams

- The phone captures 16 kHz mono PCM16 with Android `AudioRecord` and sends 100 ms frames over the existing authenticated WebSocket as binary messages.
- The host relays each frame to Phonon-2's `/v1/audio/stream` WebSocket and translates its streaming events back to ConKey messages.
- The first partial usually arrives in 0.3–0.5 s and updates about every 0.5 s. Roughly 0.7 s of silence finalizes a segment; 30 s caps a segment.
- `voice_partial`, `voice_final`, and `voice_done` events update the UI live. The model server starts lazily on first use (a few seconds of load time) and stops with the host.

### Configuration

| Key in `config.json` | Default | Meaning |
| --- | --- | --- |
| `voice_enabled` | `true` | Offer voice typing to connected clients |
| `phonon_model` | `"phonon-2"` | Fermion model name |
| `phonon_port` | `8010` | Local speech server port |
| `phonon_threads` | `0` | CPU threads (`0` = automatic) |
| `phonon_command` | `""` | Optional explicit `fermion` command |

Host flags: `--no-voice`, `--phonon-port`, `--phonon-model`, `--phonon-threads`, `--phonon-command`.

### Privacy

Audio travels only from the phone to the host over your local network, authenticated with the ConKey PIN, and from the host to the speech server on loopback (`127.0.0.1`). The model runs offline; neither audio nor transcripts are uploaded or persisted.

Phonon-2 is by Fermion Research and licensed **CC-BY-4.0**, derived from NVIDIA's `parakeet-tdt-0.6b-v3`. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for details.

---

## Desktop Applications (Windows & Linux)

ConKey provides graphical desktop applications for Windows and Linux hosts with status monitors, pairing PIN displays, link copiers, and auto-start management.

### Windows Desktop (`conkey-windows.zip`)
- **Executable**: Includes standalone `ConKey.exe` (no Python installation required) and `Start-ConKey.bat`.
- **System-Wide Input**: Low-level Win32 `SendInput` driver typing directly into active foreground applications.
- **Auto-Start**: One-click startup toggle in the GUI dashboard.

### Linux Desktop (`conkey-linux.tar.gz`)
- **Launcher & Installer**: Comes with `conkey` launcher script, `install.sh`, and `conkey.desktop` XDG menu entry.
- **Input Drivers**: Native support for X11 (`xdotool`) and Wayland/Kernel `/dev/uinput` input simulation.

### Direct Downloads
Users can download client and host applications directly from the ConKey web dashboard header via the **Download** menu:
- **Android APK**: [`/download/conkey.apk`](file:///c:/Users/YashN/Desktop/conkey/downloads/conkey.apk)
- **Windows Desktop**: [`/download/conkey-windows.zip`](file:///c:/Users/YashN/Desktop/conkey/downloads/conkey-windows.zip)
- **Linux Desktop**: [`/download/conkey-linux.tar.gz`](file:///c:/Users/YashN/Desktop/conkey/downloads/conkey-linux.tar.gz)

---

## Architecture & Verification

- **Host Engine**: Python 3 cross-platform driver (`win_keyboard` on Windows, `linux_keyboard` on Linux with uinput/xdotool fallback).
- **Native Android Client**: Android SDK + Kotlin + OkHttp WebSocket with UDP broadcast discovery.
- **UI Architecture**: Fully icon-driven modern dark interface powered by Lucide vector icons (zero emojis).
- **Automated Tests**: Run `python -m pytest tests/` to verify keystroke emulation, protocol parsing, server communication, desktop routing, and the streaming voice relay.
