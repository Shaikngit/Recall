from __future__ import annotations

import io
import json
import os
import queue
import sys
import threading
import webbrowser
import winreg
from functools import partial
from pathlib import Path
from tkinter import Tk

import customtkinter as ctk
import pystray
import requests
from PIL import Image, ImageDraw, ImageGrab
from pynput import keyboard

# ---------------------------------------------------------------------------
# Mode detection: cloud vs local
# ---------------------------------------------------------------------------
# Priority: RECALL_API_URL env var  >  .recall-config.json  >  default local

_PRODUCTION_URL = "https://app-mykbshaikn-th6h7z.azurewebsites.net"
_LOCAL_URL = "http://127.0.0.1:8765"


def _resolve_api_base() -> tuple[str, bool]:
    """Return (api_base_url, is_cloud)."""
    # 1. Env var takes priority
    env_url = os.environ.get("RECALL_API_URL", "").strip().rstrip("/")
    if env_url:
        return env_url, not env_url.startswith("http://127.0.0.1")

    # 2. Config file bundled inside exe (or repo root in dev)
    if getattr(sys, "frozen", False):
        config_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        config_dir = Path(__file__).resolve().parent.parent
    config_file = config_dir / ".recall-config.json"
    if config_file.is_file():
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
            url = cfg.get("api_url", "").strip().rstrip("/")
            if url:
                return url, not url.startswith("http://127.0.0.1")
        except Exception:
            pass

    # 3. Default: local
    return _LOCAL_URL, False


API_BASE, _CLOUD_MODE = _resolve_api_base()

HOTKEY_CAPTURE = "<ctrl>+<alt>+n"
HOTKEY_ASK = "<ctrl>+`"
HOTKEY_VOICE = "<ctrl>+<alt>+v"

_APP_VERSION = "1.1.0"
_STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_REG_NAME = "RecallKB"

CAPTURE_TEMPLATES: dict[str, str] = {
    "Incident": "Issue:\nService:\nICM/Case:\nSymptom:\nFix:\nLearning:",
    "Learning": "Service:\nLearning:\nWhy it mattered:\nNext time:",
    "Case": "Case:\nService:\nCustomer impact:\nCurrent finding:\nNext action:",
    "Meeting": "Topic:\nService:\nDecision:\nFollow-up:\nNotes:",
}

# Brand colours
_GREEN = "#1e6f5c"
_BG_LIGHT = "#f8f5ef"


# ---------------------------------------------------------------------------
# Windows Startup helpers
# ---------------------------------------------------------------------------

def _get_exe_path() -> str | None:
    """Return exe path when frozen, else None."""
    return sys.executable if getattr(sys, "frozen", False) else None


def _is_startup_enabled() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_REG_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, _STARTUP_REG_NAME)
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def _set_startup(enable: bool) -> None:
    exe = _get_exe_path()
    if not exe:
        return
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, _STARTUP_REG_NAME, 0, winreg.REG_SZ, f'"{exe}" --startup')
        else:
            try:
                winreg.DeleteValue(key, _STARTUP_REG_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Toast notifications (winotify)
# ---------------------------------------------------------------------------

def _get_icon_path() -> str | None:
    """Return absolute path to recall.ico if it exists."""
    if getattr(sys, "frozen", False):
        p = Path(sys.executable).parent / "kb_app" / "static" / "recall.ico"
    else:
        p = Path(__file__).resolve().parent / "static" / "recall.ico"
    return str(p) if p.exists() else None


def _show_toast(title: str, body: str) -> None:
    try:
        from winotify import Notification
        kwargs: dict = {"app_id": "Recall KB", "title": title, "msg": body, "duration": "short"}
        icon = _get_icon_path()
        if icon:
            kwargs["icon"] = icon
        Notification(**kwargs).show()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Appearance (follows Windows light / dark automatically)
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("green")

# ---------------------------------------------------------------------------
# Flask server thread (only used in local mode)
# ---------------------------------------------------------------------------


class ServerThread(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        from werkzeug.serving import make_server
        from kb_app.app import create_app
        self.server = make_server("127.0.0.1", 8765, create_app())

    def run(self) -> None:
        self.server.serve_forever()

    def stop(self) -> None:
        self.server.shutdown()


# ===================================================================
#  Q&A Chat Window
# ===================================================================


class AskWindow:
    """Multi-turn Q&A window backed by /api/ask."""

    def __init__(self, root: Tk) -> None:
        self._root = root
        self._win: ctk.CTkToplevel | None = None
        self._history: list[dict[str, str]] = []  # [{role, content}, ...]
        # widgets stored after build
        self._conversation_frame: ctk.CTkScrollableFrame | None = None
        self._input_entry: ctk.CTkEntry | None = None
        self._send_btn: ctk.CTkButton | None = None
        self._followup_switch: ctk.CTkSwitch | None = None
        self._status_label: ctk.CTkLabel | None = None
        self._followup_var: ctk.StringVar | None = None
        self._busy = False

    # -- public API --------------------------------------------------

    def show(self) -> None:
        if self._win is not None and self._win.winfo_exists():
            self._win.deiconify()
            self._win.lift()
            self._win.focus_force()
            if self._input_entry:
                self._input_entry.focus_set()
            return
        self._build()

    # -- build UI ----------------------------------------------------

    def _build(self) -> None:
        win = ctk.CTkToplevel(self._root)
        win.title("Recall Q&A")
        win.geometry("660x520")
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        self._win = win

        # Title
        ctk.CTkLabel(win, text="Recall Q&A", font=ctk.CTkFont(size=16, weight="bold")).pack(
            padx=16, pady=(14, 4), anchor="w"
        )

        # Conversation scroll area
        self._conversation_frame = ctk.CTkScrollableFrame(win, corner_radius=8)
        self._conversation_frame.pack(fill="both", expand=True, padx=14, pady=(4, 6))

        # Welcome message
        self._append_bubble("assistant", "Ask me anything about your KB. I'll search your notes and answer.")

        # Bottom controls
        bottom = ctk.CTkFrame(win, fg_color="transparent")
        bottom.pack(fill="x", padx=14, pady=(0, 6))

        # Follow-up toggle
        self._followup_var = ctk.StringVar(value="off")
        self._followup_switch = ctk.CTkSwitch(
            bottom, text="Follow-up", variable=self._followup_var,
            onvalue="on", offvalue="off", width=48
        )
        self._followup_switch.pack(side="left", padx=(0, 8))

        # New chat button
        ctk.CTkButton(bottom, text="New Chat", width=80, fg_color="gray40",
                       hover_color="gray30", command=self._new_chat).pack(side="left", padx=(0, 8))

        # Input row
        input_frame = ctk.CTkFrame(win, fg_color="transparent")
        input_frame.pack(fill="x", padx=14, pady=(0, 10))

        self._input_entry = ctk.CTkEntry(input_frame, placeholder_text="Type your question...",
                                          height=38, font=ctk.CTkFont(size=13))
        self._input_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._input_entry.bind("<Return>", lambda _e: self._on_send())
        self._input_entry.focus_set()

        self._send_btn = ctk.CTkButton(input_frame, text="Send", width=70, command=self._on_send)
        self._send_btn.pack(side="right")

        # Status
        self._status_label = ctk.CTkLabel(win, text="Ctrl+` to toggle  |  Enter to send  |  Esc to hide",
                                           font=ctk.CTkFont(size=11), text_color="gray50")
        self._status_label.pack(padx=14, pady=(0, 8), anchor="w")

        win.bind("<Escape>", lambda _e: win.withdraw())

    # -- conversation bubbles ----------------------------------------

    def _append_bubble(self, role: str, text: str) -> None:
        frame = self._conversation_frame
        if frame is None:
            return

        is_user = role == "user"
        anchor = "e" if is_user else "w"
        fg = ("#dceefb", "#1a3d5c") if is_user else ("#e8f5e9", "#1b3a26")  # (light, dark)
        text_clr = ("#1a1a1a", "#eaeaea")

        bubble_frame = ctk.CTkFrame(frame, corner_radius=10, fg_color=fg)
        bubble_frame.pack(anchor=anchor, padx=(60 if is_user else 4, 4 if is_user else 60),
                          pady=4, fill="x" if not is_user else "none")

        ctk.CTkLabel(bubble_frame, text=text, wraplength=480, justify="left",
                     font=ctk.CTkFont(size=12), text_color=text_clr,
                     anchor="w").pack(padx=12, pady=8, anchor="w")

        # Scroll to bottom
        self._root.after(50, lambda: frame._parent_canvas.yview_moveto(1.0))

    def _append_sources(self, results: list[dict]) -> None:
        """Add clickable source pills below the last answer."""
        if not results or self._conversation_frame is None:
            return
        src_frame = ctk.CTkFrame(self._conversation_frame, fg_color="transparent")
        src_frame.pack(anchor="w", padx=4, pady=(0, 4))
        ctk.CTkLabel(src_frame, text="Sources:", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray50").pack(side="left", padx=(0, 6))
        for i, r in enumerate(results[:5], 1):
            path = r.get("path", "")
            title = r.get("title", f"Source {i}")
            btn = ctk.CTkButton(src_frame, text=title, width=0, height=24,
                                font=ctk.CTkFont(size=11), fg_color="gray30",
                                hover_color=_GREEN,
                                command=partial(webbrowser.open,
                                                f"{API_BASE}/api/note?path={requests.utils.quote(path)}"))
            btn.pack(side="left", padx=2)

    # -- actions ------------------------------------------------------

    def _on_send(self) -> None:
        if self._busy or self._input_entry is None:
            return
        query = self._input_entry.get().strip()
        if not query:
            return

        self._append_bubble("user", query)
        self._input_entry.delete(0, "end")
        self._set_busy(True)

        use_history = self._followup_var and self._followup_var.get() == "on"
        history = list(self._history) if use_history else []

        thread = threading.Thread(target=self._call_ask, args=(query, history), daemon=True)
        thread.start()

    def _call_ask(self, query: str, history: list[dict]) -> None:
        try:
            resp = requests.post(f"{API_BASE}/api/ask",
                                 json={"query": query, "history": history}, timeout=60)
            data = resp.json()
            answer = data.get("answer", "No answer returned.")
            results = data.get("results", [])
            # Update history
            self._history.append({"role": "user", "content": query})
            self._history.append({"role": "assistant", "content": answer})
            self._root.after(0, self._on_answer, answer, results)
        except Exception as exc:
            self._root.after(0, self._on_answer, f"Error: {exc}", [])

    def _on_answer(self, answer: str, results: list[dict]) -> None:
        self._append_bubble("assistant", answer)
        self._append_sources(results)
        self._set_busy(False)
        # Auto-enable follow-up after first exchange
        if self._followup_var and len(self._history) >= 2:
            self._followup_var.set("on")

    def _new_chat(self) -> None:
        self._history.clear()
        if self._conversation_frame:
            for child in self._conversation_frame.winfo_children():
                child.destroy()
            self._append_bubble("assistant", "New conversation started. Ask me anything!")
        if self._followup_var:
            self._followup_var.set("off")
        if self._status_label:
            self._status_label.configure(text="Conversation cleared.")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if self._send_btn:
            self._send_btn.configure(text="..." if busy else "Send", state="disabled" if busy else "normal")
        if self._input_entry:
            self._input_entry.configure(state="disabled" if busy else "normal")
        if self._status_label:
            self._status_label.configure(text="Thinking..." if busy else "Ctrl+` to toggle  |  Enter to send  |  Esc to hide")


# ===================================================================
#  Enhanced Capture Window  (Quick Line / Detailed Note)
# ===================================================================


class CaptureWindow:
    """Capture window with Quick / Detailed modes, templates, and image paste."""

    def __init__(self, root: Tk) -> None:
        self._root = root
        self._win: ctk.CTkToplevel | None = None
        self._mode = "Quick Line"
        self._attached_image: bytes | None = None
        self._attached_mime: str = "image/png"
        # widgets
        self._mode_selector: ctk.CTkSegmentedButton | None = None
        self._quick_frame: ctk.CTkFrame | None = None
        self._detail_frame: ctk.CTkFrame | None = None
        self._quick_entry: ctk.CTkEntry | None = None
        self._detail_textbox: ctk.CTkTextbox | None = None
        self._image_label: ctk.CTkLabel | None = None
        self._status_label: ctk.CTkLabel | None = None
        self._save_btn: ctk.CTkButton | None = None
        self._busy = False

    # -- public API --------------------------------------------------

    def show(self) -> None:
        if self._win is not None and self._win.winfo_exists():
            self._win.deiconify()
            self._win.lift()
            self._win.focus_force()
            self._focus_active_input()
            return
        self._build()

    # -- build UI ----------------------------------------------------

    def _build(self) -> None:
        win = ctk.CTkToplevel(self._root)
        win.title("Recall — Capture Note")
        win.geometry("640x500")
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self._on_close)
        self._win = win

        # Mode selector
        self._mode_selector = ctk.CTkSegmentedButton(
            win, values=["Quick Line", "Detailed Note"],
            command=self._on_mode_change
        )
        self._mode_selector.set("Quick Line")
        self._mode_selector.pack(padx=16, pady=(14, 8))

        # ── Quick Line frame ──
        self._quick_frame = ctk.CTkFrame(win, fg_color="transparent")

        ctk.CTkLabel(self._quick_frame, text="One-liner tip or quick note:",
                     font=ctk.CTkFont(size=12)).pack(padx=16, pady=(8, 4), anchor="w")
        self._quick_entry = ctk.CTkEntry(self._quick_frame, placeholder_text="Type a quick tip...",
                                          height=38, font=ctk.CTkFont(size=13))
        self._quick_entry.pack(fill="x", padx=16, pady=(0, 8))
        self._quick_entry.bind("<Return>", lambda _e: self._on_save())

        # ── Detailed Note frame ──
        self._detail_frame = ctk.CTkFrame(win, fg_color="transparent")

        # Template buttons
        tmpl_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        tmpl_row.pack(fill="x", padx=16, pady=(6, 4))
        ctk.CTkLabel(tmpl_row, text="Templates:", font=ctk.CTkFont(size=11),
                     text_color="gray50").pack(side="left", padx=(0, 6))
        for name in CAPTURE_TEMPLATES:
            ctk.CTkButton(tmpl_row, text=name, width=0, height=26,
                          font=ctk.CTkFont(size=11), fg_color="gray35", hover_color=_GREEN,
                          command=partial(self._insert_template, name)).pack(side="left", padx=2)

        # Textbox
        self._detail_textbox = ctk.CTkTextbox(self._detail_frame, wrap="word",
                                               font=ctk.CTkFont(family="Segoe UI", size=12),
                                               corner_radius=8, height=240)
        self._detail_textbox.pack(fill="both", expand=True, padx=16, pady=(4, 4))

        # Helper text
        ctk.CTkLabel(self._detail_frame,
                     text="Tip: add #hashtag for topic routing  |  Ctrl+V to paste screenshot",
                     font=ctk.CTkFont(size=11), text_color="gray50").pack(padx=16, anchor="w")

        # Image indicator
        self._image_label = ctk.CTkLabel(self._detail_frame, text="",
                                          font=ctk.CTkFont(size=11), text_color=_GREEN)
        self._image_label.pack(padx=16, anchor="w")

        # Show Quick frame by default
        self._quick_frame.pack(fill="both", expand=True)

        # ── Bottom bar (shared) ──
        bottom = ctk.CTkFrame(win, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(6, 10))

        self._status_label = ctk.CTkLabel(bottom, text="Ctrl+Alt+N to toggle  |  Ctrl+Enter to save  |  Esc to hide",
                                           font=ctk.CTkFont(size=11), text_color="gray50")
        self._status_label.pack(side="left")

        self._save_btn = ctk.CTkButton(bottom, text="Save", width=80, command=self._on_save)
        self._save_btn.pack(side="right")

        # Bindings
        win.bind("<Control-Return>", lambda _e: self._on_save())
        win.bind("<Escape>", lambda _e: self._on_close())
        win.bind("<Control-v>", self._on_paste)
        win.bind("<Control-V>", self._on_paste)

        self._focus_active_input()

    # -- mode switching -----------------------------------------------

    def _on_mode_change(self, mode: str) -> None:
        self._mode = mode
        if mode == "Quick Line":
            self._detail_frame.pack_forget()
            self._quick_frame.pack(fill="both", expand=True,
                                    before=self._win.winfo_children()[-1])  # before bottom bar
        else:
            self._quick_frame.pack_forget()
            self._detail_frame.pack(fill="both", expand=True,
                                     before=self._win.winfo_children()[-1])
        self._focus_active_input()

    def _focus_active_input(self) -> None:
        if self._mode == "Quick Line" and self._quick_entry:
            self._quick_entry.focus_set()
        elif self._detail_textbox:
            self._detail_textbox.focus_set()

    # -- templates ----------------------------------------------------

    def _insert_template(self, name: str) -> None:
        if self._detail_textbox is None:
            return
        self._detail_textbox.delete("1.0", "end")
        self._detail_textbox.insert("1.0", CAPTURE_TEMPLATES[name])
        # Switch to detailed if not already
        if self._mode != "Detailed Note" and self._mode_selector:
            self._mode_selector.set("Detailed Note")
            self._on_mode_change("Detailed Note")
        self._detail_textbox.focus_set()

    # -- image paste --------------------------------------------------

    def _on_paste(self, _event: object = None) -> str | None:
        """Check clipboard for an image; if found, attach it."""
        try:
            img = ImageGrab.grabclipboard()
        except Exception:
            img = None
        if img is not None and isinstance(img, Image.Image):
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            self._attached_image = buf.getvalue()
            self._attached_mime = "image/png"
            if self._image_label:
                self._image_label.configure(text=f"\U0001f4f7  Image attached ({len(self._attached_image) // 1024} KB)")
            # Switch to detailed if not already
            if self._mode != "Detailed Note" and self._mode_selector:
                self._mode_selector.set("Detailed Note")
                self._on_mode_change("Detailed Note")
            return None  # let default paste proceed for text
        return None

    def _clear_image(self) -> None:
        self._attached_image = None
        if self._image_label:
            self._image_label.configure(text="")

    # -- save ---------------------------------------------------------

    def _on_save(self) -> None:
        if self._busy:
            return

        if self._mode == "Quick Line":
            note = self._quick_entry.get().strip() if self._quick_entry else ""
            mode = "quick"
        else:
            note = self._detail_textbox.get("1.0", "end").strip() if self._detail_textbox else ""
            mode = "detailed"

        if not note:
            self._set_status("Nothing to save.")
            return

        self._set_busy(True)
        image_bytes = self._attached_image
        thread = threading.Thread(target=self._call_capture, args=(note, mode, image_bytes), daemon=True)
        thread.start()

    def _call_capture(self, note: str, mode: str, image_bytes: bytes | None) -> None:
        try:
            if image_bytes:
                resp = requests.post(
                    f"{API_BASE}/api/capture",
                    data={"note": note, "mode": mode},
                    files={"image": ("screenshot.png", image_bytes, "image/png")},
                    timeout=60,
                )
            else:
                resp = requests.post(
                    f"{API_BASE}/api/capture",
                    json={"note": note, "mode": mode},
                    timeout=60,
                )
            data = resp.json()
            saved_path = data.get("savedTo", data.get("inboxPath", ""))
            msg = f"Saved to {saved_path}" if saved_path else "Saved."
            if data.get("needsClarification"):
                msg += "  (Open dashboard to finalize destination)"
            self._root.after(0, self._on_saved, msg)
        except Exception as exc:
            self._root.after(0, self._on_saved, f"Error: {exc}")

    def _on_saved(self, message: str) -> None:
        self._set_status(message)
        if not message.startswith("Error"):
            _show_toast("Note Captured", message)
        # Clear fields
        if self._mode == "Quick Line" and self._quick_entry:
            self._quick_entry.delete(0, "end")
        elif self._detail_textbox:
            self._detail_textbox.delete("1.0", "end")
        self._clear_image()
        self._set_busy(False)

    # -- helpers ------------------------------------------------------

    def _set_status(self, text: str) -> None:
        if self._status_label:
            self._status_label.configure(text=text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if self._save_btn:
            self._save_btn.configure(text="Saving..." if busy else "Save",
                                      state="disabled" if busy else "normal")

    def _on_close(self) -> None:
        if self._win:
            self._win.withdraw()


# ===================================================================
#  Tray Runtime (enhanced)
# ===================================================================


class TrayRuntime:
    def __init__(self) -> None:
        self.server: ServerThread | None = None
        if not _CLOUD_MODE:
            self.server = ServerThread()

        self.root = Tk()
        self.root.withdraw()
        self.actions: queue.Queue[str] = queue.Queue()

        self.ask_window = AskWindow(self.root)
        self.capture_window = CaptureWindow(self.root)
        self._voice_busy = False
        self._voice_overlay: ctk.CTkToplevel | None = None

        mode_label = "Cloud" if _CLOUD_MODE else "Local"
        self.icon = pystray.Icon(
            "mykb",
            self._build_icon(),
            f"Recall KB ({mode_label})",
            menu=pystray.Menu(
                pystray.MenuItem("Open Dashboard", lambda *_a: self.enqueue("dashboard")),
                pystray.MenuItem("Ask a Question  (Ctrl+`)", lambda *_a: self.enqueue("ask")),
                pystray.MenuItem("Capture Note  (Ctrl+Alt+N)", lambda *_a: self.enqueue("capture")),
                pystray.MenuItem("Voice Input  (Ctrl+Alt+V)", lambda *_a: self.enqueue("voice")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Start with Windows",
                    lambda *_a: self.enqueue("toggle_startup"),
                    checked=lambda _item: _is_startup_enabled(),
                ),
                pystray.MenuItem("Quit", lambda *_a: self.enqueue("quit")),
            ),
        )
        self.listener = keyboard.GlobalHotKeys({
            HOTKEY_CAPTURE: partial(self.enqueue, "capture"),
            HOTKEY_ASK: partial(self.enqueue, "ask"),
            HOTKEY_VOICE: partial(self.enqueue, "voice"),
        })

    def start(self) -> None:
        if self.server:
            self.server.start()
        self.listener.start()
        self.icon.run_detached()
        # Auto-update check (background, frozen exe only)
        if getattr(sys, "frozen", False):
            threading.Thread(target=self._check_for_update, daemon=True).start()
        self.root.after(250, self.process_actions)
        # Open dashboard unless launched via --startup (Windows auto-start)
        if "--startup" not in sys.argv:
            self.enqueue("dashboard")
        self.root.mainloop()

    def enqueue(self, action: str) -> None:
        self.actions.put(action)

    def process_actions(self) -> None:
        while not self.actions.empty():
            action = self.actions.get()
            if action == "dashboard":
                webbrowser.open(API_BASE)
            elif action == "ask":
                self.ask_window.show()
            elif action == "capture":
                self.capture_window.show()
            elif action == "voice":
                self._start_voice()
            elif action == "organize":
                self.organize_now()
            elif action == "toggle_startup":
                _set_startup(not _is_startup_enabled())
            elif action == "quit":
                self.shutdown()
                return
        self.root.after(250, self.process_actions)

    # -- Voice input ------------------------------------------------

    def _start_voice(self) -> None:
        if self._voice_busy:
            return
        self._voice_busy = True
        self._show_voice_overlay()
        threading.Thread(target=self._record_voice, daemon=True).start()

    def _show_voice_overlay(self) -> None:
        overlay = ctk.CTkToplevel(self.root)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        overlay.geometry(f"260x56+{sw // 2 - 130}+{sh - 130}")
        overlay.configure(fg_color=_GREEN)
        ctk.CTkLabel(
            overlay, text="\U0001f3a4  Listening \u2026 speak now",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="white",
        ).pack(expand=True)
        self._voice_overlay = overlay

    def _hide_voice_overlay(self) -> None:
        if self._voice_overlay:
            self._voice_overlay.destroy()
            self._voice_overlay = None

    def _record_voice(self) -> None:
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            recognizer.dynamic_energy_threshold = True
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)
            wav_bytes = audio.get_wav_data()
            resp = requests.post(
                f"{API_BASE}/api/transcribe",
                files={"audio": ("recording.wav", wav_bytes, "audio/wav")},
                timeout=30,
            )
            text = resp.json().get("text", "") if resp.ok else ""
            self.root.after(0, self._on_voice_result, text)
        except Exception:
            self.root.after(0, self._on_voice_result, "")

    def _on_voice_result(self, text: str) -> None:
        self._hide_voice_overlay()
        self._voice_busy = False
        if not text.strip():
            _show_toast("Voice Input", "No speech detected.")
            return
        # Insert into whichever window is visible
        ask_win = self.ask_window._win
        cap_win = self.capture_window._win
        if ask_win and ask_win.winfo_exists() and ask_win.state() != "withdrawn":
            entry = self.ask_window._input_entry
            if entry:
                cur = entry.get()
                entry.delete(0, "end")
                entry.insert(0, (cur + " " + text).strip())
                entry.focus_set()
            return
        if cap_win and cap_win.winfo_exists() and cap_win.state() != "withdrawn":
            if self.capture_window._mode == "Quick Line" and self.capture_window._quick_entry:
                e = self.capture_window._quick_entry
                cur = e.get()
                e.delete(0, "end")
                e.insert(0, (cur + " " + text).strip())
            elif self.capture_window._detail_textbox:
                self.capture_window._detail_textbox.insert("end", text)
            return
        # No window open → open Ask with voice text
        self.ask_window.show()
        self.root.after(100, self._insert_voice_text, text)

    def _insert_voice_text(self, text: str) -> None:
        if self.ask_window._input_entry:
            self.ask_window._input_entry.insert(0, text)

    # -- Auto-update ------------------------------------------------

    def _check_for_update(self) -> None:
        try:
            resp = requests.get(f"{API_BASE}/api/desktop-version", timeout=10)
            if not resp.ok:
                return
            latest = resp.json().get("version", _APP_VERSION)
            if latest != _APP_VERSION:
                self.root.after(0, lambda: _show_toast(
                    "Update Available",
                    f"Recall KB v{latest} is available. Right-click tray \u2192 Open Dashboard to download.",
                ))
        except Exception:
            pass

    # -- Organize / messages ----------------------------------------

    def organize_now(self) -> None:
        if _CLOUD_MODE:
            def _do() -> None:
                try:
                    resp = requests.post(f"{API_BASE}/api/organize", json={}, timeout=60)
                    data = resp.json()
                    summary = f"Organized {len(data.get('organized', []))} entries.\nKept {len(data.get('keptFiles', []))} inbox files."
                    self.root.after(0, self._show_message, "Inbox Organized", summary)
                except Exception as exc:
                    self.root.after(0, self._show_message, "Error", str(exc))
            threading.Thread(target=_do, daemon=True).start()
        else:
            from kb_app.core import organize_inbox
            result = organize_inbox()
            summary = f"Organized {len(result['organized'])} entries.\nKept {len(result['keptFiles'])} inbox files."
            self._show_message("Inbox Organized", summary)

    def _show_message(self, title: str, text: str) -> None:
        popup = ctk.CTkToplevel(self.root)
        popup.title(title)
        popup.geometry("420x160")
        popup.attributes("-topmost", True)
        ctk.CTkLabel(popup, text=text, wraplength=380, justify="left",
                     font=ctk.CTkFont(size=13)).pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkButton(popup, text="Close", width=80, command=popup.destroy).pack(pady=(0, 14))

    def shutdown(self) -> None:
        self.listener.stop()
        self.icon.stop()
        if self.server:
            self.server.stop()
        self.root.quit()

    @staticmethod
    def _build_icon() -> Image.Image:
        image = Image.new("RGB", (64, 64), "#efe6d8")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=14, fill=_GREEN)
        draw.rectangle((18, 18, 46, 24), fill=_BG_LIGHT)
        draw.rectangle((18, 30, 46, 36), fill=_BG_LIGHT)
        draw.rectangle((18, 42, 38, 48), fill=_BG_LIGHT)
        return image


def main() -> None:
    TrayRuntime().start()


if __name__ == "__main__":
    main()
