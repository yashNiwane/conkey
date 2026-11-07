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

---

## Architecture & Verification

- **Host Engine**: Python 3 with pure Win32 `SendInput` (`ctypes`), supporting Unicode character typing without layout conflicts and virtual key chords.
- **Native Android Client**: Android SDK + Kotlin + OkHttp WebSocket with UDP broadcast discovery.
- **Automated Tests**: Run `python -m pytest tests/` to verify keystroke emulation, protocol parsing, and server communication.
