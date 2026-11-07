# ConKey: Control Laptop Keyboard via Mobile Phone

ConKey allows you to use your Android phone as a wireless keyboard, hotkey remote, and trackpad for your Windows laptop over Wi-Fi without any extra hardware.

Built specifically to rescue laptops with broken hardware keys (such as `Ctrl+C`, `Ctrl+V`, `A`, `S`, `!`, navigation keys, etc.).

---

## Quick Start (Two Steps)

### Step 1: Start Host on Laptop
Double-click `start_conkey.bat` or run:
```powershell
python host\run_host.py
```
The console will print your local IP and pairing PIN:
```text
======================================================
          CONKEY LAPTOP RECEIVER ACTIVE
======================================================
  Mobile Browser URL:  http://192.168.1.100:8765/
  Direct Web Auth:     http://192.168.1.100:8765/?pin=4821
  Host IP for App:     192.168.1.100:8765
  Pairing PIN:         4821
======================================================
```

### Step 2: Connect Phone
You have two immediate options:

#### Option A: Instant Browser Companion (Zero Install)
Open your phone's browser and go to the URL shown in the console (e.g. `http://192.168.1.100:8765/?pin=4821`).
- You can begin typing and using hotkeys immediately.
- Works on Chrome, Firefox, Edge, Safari on any phone.

#### Option B: Native Android App
1. Install `conkey.apk` (located in the project root, or downloaded directly from the web companion page).
2. Open the ConKey app on your phone.
3. Tap **Auto Detect** (or enter the IP and PIN) and tap **Connect**.

---

## Features

- **Broken Hotkeys Bar**: One-tap buttons for `Ctrl+C`, `Ctrl+V`, `Ctrl+Z`, `Ctrl+X`, `Ctrl+A`, `Ctrl+S`, `Ctrl+F`, `Alt+Tab`, `Win`.
- **Dead-Key Quick Rescue**: Dedicated keys for `A`, `a`, `S`, `s`, `!`, `@`, `#`, `?`.
- **Direct Phone Keyboard Typing**: Type sentences, use phone voice dictation, emojis, or swiping directly into the active window on your laptop.
- **Editing & Navigation Cluster**: `Backspace`, `Enter`, `Tab`, `Esc`, `Space`, `Delete`, and arrow keys (`▲`, `◀`, `▼`, `▶`).
- **Laptop Trackpad Mode**: Drag to move cursor, tap to left-click, two-finger scroll, dedicated left and right click buttons.
- **Clean Security**: Local Wi-Fi WebSocket connection authenticated with a PIN code and brute-force lockout protection.

---

## Architecture & Verification

- **Host Engine**: Python 3 with pure Win32 `SendInput` (`ctypes`), supporting Unicode character typing without layout conflicts and virtual key chords.
- **Native Android Client**: Android SDK + Kotlin + OkHttp WebSocket with UDP broadcast discovery.
- **Automated Tests**: Run `python -m pytest tests/` to verify keystroke emulation, protocol parsing, and server communication.
