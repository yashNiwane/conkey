# ConKey: Control Laptop Keyboard via Mobile Phone

ConKey allows you to use your Android phone as a wireless keyboard, hotkey remote, and trackpad for your Windows laptop over Wi-Fi without any extra hardware.

Built specifically to rescue laptops with broken hardware keys (such as `Ctrl+C`, `Ctrl+V`, `A`, `S`, `!`, navigation keys, etc.).

---

## Quick Start (Two Steps)

### Windows Startup (Automatic Background Service)
ConKey is already registered in your Windows Startup directory.
- It will start automatically in the background using `pythonw.exe` every time your laptop boots or logs in.
- Default persistent PIN: `2026` (stored in `config.json`).
- To re-enable or disable startup at any time:
  - Double-click [`enable_startup.bat`](file:///c:/Users/YashN/Desktop/conkey/enable_startup.bat) to activate.
  - Double-click [`disable_startup.bat`](file:///c:/Users/YashN/Desktop/conkey/disable_startup.bat) to deactivate.

### Manual Launch (Foreground Console)
If you prefer running in an interactive terminal to see connection logs:
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

- **Zero-Config Wi-Fi Auto-Discovery**: Open the app on your home Wi-Fi and it detects your laptop automatically by name (for example, `YashN's Laptop (ave)`). If one laptop is detected, it connects automatically with zero typing required. If multiple are on the network, a 1-tap device picker lets you choose.
- **Full PC 5-Row Desktop Keyboard**: Complete mechanical PC layout including numbers row (`1`-`0`, `-`, `=`), QWERTY, brackets, punctuation, Enter, Backspace, Tab, Caps, and arrow navigation.
- **Sticky Modifiers (`Ctrl`, `Alt`, `Shift`, `Win`)**: Tap any modifier to latch it on with a golden glow indicator. Pressing keys sends the chord (such as `Ctrl+C` or `Alt+Tab`) and automatically clears or latches.
- **Power Shortcuts Deck**: Categorized hotkeys for Clipboard (`Ctrl+C`, `Ctrl+V`, `Ctrl+X`, `Ctrl+A`, `Ctrl+Z`, `Ctrl+Y`), Windows OS (`Alt+Tab`, `Alt+F4`, `Win+D`, `Win+Tab`, `Win+R`, `Win+E`, `Ctrl+Shift+Esc`, `Win+L`), Editing (`Ctrl+S`, `Ctrl+F`), and Browser (`Ctrl+T`, `Ctrl+W`, `Ctrl+R`, `Reopen Tab`, `F5`, `F11`).
- **Function Keys & Calculator Numpad Deck**: Full `F1`-`F12`, system keys (`PrtScn`, `Insert`, `Delete`, `Home`, `End`, `PgUp`, `PgDn`), and a dedicated 10-key numeric keypad (`0`-`9`, `+`, `-`, `*`, `/`, `Enter`, `.`, `=`).
- **Broken Keys Rescue Bar**: Quick one-tap access for `A`, `a`, `S`, `s`, `!`, `@`, `#`, `?`.
- **Direct Phone Keyboard Sync**: Input field for voice-to-text dictation, autocomplete, emojis, or swipe typing directly into the laptop foreground window.
- **Precision Touchpad**: Drag cursor, tap to left-click, two-finger scroll, and dedicated left and right click buttons.

---

## Architecture & Verification

- **Host Engine**: Python 3 with pure Win32 `SendInput` (`ctypes`), supporting Unicode character typing without layout conflicts and virtual key chords.
- **Native Android Client**: Android SDK + Kotlin + OkHttp WebSocket with UDP broadcast discovery.
- **Automated Tests**: Run `python -m pytest tests/` to verify keystroke emulation, protocol parsing, and server communication.
