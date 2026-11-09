"""
ConKey Desktop Application (Windows & Linux).
Graphical dashboard and server manager with real-time status,
pairing PIN display, connection monitor, and live dictation log.
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

# Ensure repo root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from host.config import load_config
from host.server import ConKeyServer
from host.startup import enable_startup, disable_startup, is_startup_enabled


class ConKeyDesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ConKey Desktop")
        self.root.geometry("720x620")
        self.root.minsize(620, 500)
        self.root.configure(bg="#0f1115")

        self.cfg = load_config()
        self.server: ConKeyServer | None = None
        self.server_thread: threading.Thread | None = None
        self.server_loop: asyncio.AbstractEventLoop | None = None
        self.is_running = False

        self._build_ui()
        self.start_server_thread()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#0f1115")
        style.configure("Card.TFrame", background="#181b21", relief="flat")
        style.configure("Header.TLabel", background="#0f1115", foreground="#38bdf8", font=("Segoe UI", 16, "bold"))
        style.configure("Sub.TLabel", background="#0f1115", foreground="#94a3b8", font=("Segoe UI", 9))
        style.configure("CardTitle.TLabel", background="#181b21", foreground="#e2e8f0", font=("Segoe UI", 11, "bold"))
        style.configure("CardText.TLabel", background="#181b21", foreground="#94a3b8", font=("Segoe UI", 9))
        style.configure("Value.TLabel", background="#181b21", foreground="#38bdf8", font=("Consolas", 11, "bold"))
        style.configure("Pin.TLabel", background="#1e293b", foreground="#f8fafc", font=("Segoe UI", 14, "bold"))

        main_container = tk.Frame(self.root, bg="#0f1115", padx=16, pady=14)
        main_container.pack(fill=tk.BOTH, expand=True)

        # Header bar
        header_frame = tk.Frame(main_container, bg="#0f1115")
        header_frame.pack(fill=tk.X, pady=(0, 12))

        title_box = tk.Frame(header_frame, bg="#0f1115")
        title_box.pack(side=tk.LEFT)
        tk.Label(
            title_box,
            text="ConKey Desktop",
            font=("Segoe UI", 18, "bold"),
            fg="#38bdf8",
            bg="#0f1115",
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="Wireless Keyboard, Precision Touchpad & System-Wide Live Voice Remote",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#0f1115",
        ).pack(anchor="w")

        # Status Badge Pill
        self.status_badge = tk.Label(
            header_frame,
            text="● INITIALIZING",
            font=("Segoe UI", 10, "bold"),
            fg="#fbbf24",
            bg="#27272a",
            padx=12,
            pady=4,
        )
        self.status_badge.pack(side=tk.RIGHT)

        # Cards Row
        cards_frame = tk.Frame(main_container, bg="#0f1115")
        cards_frame.pack(fill=tk.X, pady=(0, 10))

        # Card 1: Connection & LAN Address
        c1 = tk.Frame(cards_frame, bg="#181b21", padx=14, pady=12, highlightthickness=1, highlightbackground="#2b303c")
        c1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        tk.Label(c1, text="DEVICE & NETWORK", font=("Segoe UI", 9, "bold"), fg="#64748b", bg="#181b21").pack(anchor="w")
        self.lbl_device_name = tk.Label(c1, text=self.cfg.device_name, font=("Segoe UI", 11, "bold"), fg="#f1f5f9", bg="#181b21")
        self.lbl_device_name.pack(anchor="w", pady=(2, 6))

        tk.Label(c1, text="Host URL:", font=("Segoe UI", 9), fg="#94a3b8", bg="#181b21").pack(anchor="w")
        self.lbl_url = tk.Label(c1, text=f"http://127.0.0.1:{self.cfg.port}/", font=("Consolas", 10), fg="#38bdf8", bg="#181b21")
        self.lbl_url.pack(anchor="w")

        # Card 2: Pairing PIN & Voice Status
        c2 = tk.Frame(cards_frame, bg="#181b21", padx=14, pady=12, highlightthickness=1, highlightbackground="#2b303c")
        c2.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        tk.Label(c2, text="PAIRING PIN", font=("Segoe UI", 9, "bold"), fg="#64748b", bg="#181b21").pack(anchor="w")
        pin_frame = tk.Frame(c2, bg="#181b21")
        pin_frame.pack(anchor="w", pady=(2, 6))
        self.lbl_pin = tk.Label(pin_frame, text=self.cfg.pin, font=("Consolas", 16, "bold"), fg="#10b981", bg="#1e293b", padx=10, pady=2)
        self.lbl_pin.pack(side=tk.LEFT)

        tk.Label(c2, text="Voice Engine:", font=("Segoe UI", 9), fg="#94a3b8", bg="#181b21").pack(anchor="w")
        self.lbl_voice_status = tk.Label(c2, text="Phonon-2 Streaming", font=("Segoe UI", 10, "bold"), fg="#a855f7", bg="#181b21")
        self.lbl_voice_status.pack(anchor="w")

        # Action Buttons Toolbar
        action_bar = tk.Frame(main_container, bg="#0f1115")
        action_bar.pack(fill=tk.X, pady=(0, 10))

        btn_copy = tk.Button(
            action_bar,
            text="Copy Web Link",
            font=("Segoe UI", 9, "bold"),
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=self.copy_web_link,
        )
        btn_copy.pack(side=tk.LEFT, padx=(0, 6))

        btn_browser = tk.Button(
            action_bar,
            text="Open Remote in Browser",
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#e2e8f0",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=self.open_browser,
        )
        btn_browser.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_toggle_server = tk.Button(
            action_bar,
            text="Restart Server",
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#e2e8f0",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=self.restart_server,
        )
        self.btn_toggle_server.pack(side=tk.LEFT, padx=(0, 6))

        self.chk_startup_var = tk.BooleanVar(value=is_startup_enabled())
        chk_startup = tk.Checkbutton(
            action_bar,
            text="Start with System",
            variable=self.chk_startup_var,
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#0f1115",
            selectcolor="#181b21",
            activebackground="#0f1115",
            activeforeground="#f8fafc",
            command=self.toggle_startup,
        )
        chk_startup.pack(side=tk.RIGHT)

        # Activity Log Frame
        log_frame = tk.Frame(main_container, bg="#181b21", padx=10, pady=10, highlightthickness=1, highlightbackground="#2b303c")
        log_frame.pack(fill=tk.BOTH, expand=True)

        log_header = tk.Frame(log_frame, bg="#181b21")
        log_header.pack(fill=tk.X, pady=(0, 6))
        tk.Label(log_header, text="LIVE ACTIVITY & DICTATION MONITOR", font=("Segoe UI", 9, "bold"), fg="#64748b", bg="#181b21").pack(side=tk.LEFT)
        btn_clear = tk.Button(
            log_header,
            text="Clear Log",
            font=("Segoe UI", 8),
            bg="#181b21",
            fg="#64748b",
            relief="flat",
            cursor="hand2",
            command=self.clear_log,
        )
        btn_clear.pack(side=tk.RIGHT)

        self.log_text = tk.Text(
            log_frame,
            bg="#0f1115",
            fg="#cbd5e1",
            font=("Consolas", 9),
            relief="flat",
            padx=8,
            pady=8,
            wrap=tk.WORD,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, message: str, tag: str = "info"):
        timestamp = time.strftime("%H:%M:%S")
        self.root.after(0, lambda: self._append_log(f"[{timestamp}] {message}\n"))

    def _append_log(self, text: str):
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)

    def clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def copy_web_link(self):
        url = self.get_direct_url()
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self.log(f"Copied to clipboard: {url}")
        messagebox.showinfo("Copied", f"Direct Remote URL copied to clipboard:\n\n{url}")

    def open_browser(self):
        url = self.get_direct_url()
        webbrowser.open(url)

    def get_direct_url(self) -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return f"http://{ip}:{self.cfg.port}/?pin={self.cfg.pin}"

    def toggle_startup(self):
        enabled = self.chk_startup_var.get()
        if enabled:
            ok = enable_startup()
            self.log("Auto-start on system boot enabled." if ok else "Failed to enable startup.")
        else:
            ok = disable_startup()
            self.log("Auto-start on system boot disabled." if ok else "Failed to disable startup.")

    def start_server_thread(self):
        if self.is_running:
            return
        self.is_running = True
        self.server_thread = threading.Thread(target=self._run_async_server, daemon=True)
        self.server_thread.start()

    def _run_async_server(self):
        self.server_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.server_loop)
        self.server = ConKeyServer(
            port=self.cfg.port,
            discovery_port=self.cfg.discovery_port,
            pin=self.cfg.pin,
            voice_enabled=self.cfg.voice_enabled,
            phonon_port=self.cfg.phonon_port,
            phonon_model=self.cfg.phonon_model,
        )

        def on_server_ready():
            direct_url = self.get_direct_url()
            self.lbl_url.config(text=direct_url)
            self.status_badge.config(text="● RUNNING", fg="#10b981", bg="#064e3b")
            self.log(f"ConKey Server online on port {self.cfg.port}")
            self.log(f"Pairing PIN: {self.cfg.pin} | Bluetooth: Active")
            self.log(f"Mobile Browser URL: {direct_url}")

        self.root.after(800, on_server_ready)

        try:
            self.server_loop.run_until_complete(self.server.start())
            self.server_loop.run_forever()
        except Exception as exc:
            self.log(f"Server error: {exc}")
        finally:
            if self.server:
                self.server_loop.run_until_complete(self.server.stop())
            self.server_loop.close()

    def restart_server(self):
        self.log("Restarting server...")
        self.status_badge.config(text="● RESTARTING", fg="#fbbf24", bg="#27272a")
        if self.server_loop and self.server_loop.is_running():
            self.server_loop.call_soon_threadsafe(self.server_loop.stop)
        self.root.after(1200, self.start_server_thread)

    def on_close(self):
        if self.server_loop and self.server_loop.is_running():
            self.server_loop.call_soon_threadsafe(self.server_loop.stop)
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ConKeyDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
