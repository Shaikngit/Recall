from __future__ import annotations

import queue
import threading
import webbrowser
from functools import partial
from tkinter import BOTH, END, Button, Label, Text, Tk, Toplevel

import pystray
from PIL import Image, ImageDraw
from pynput import keyboard
from werkzeug.serving import make_server

from kb_app.app import create_app
from kb_app.core import append_to_daily_inbox, organize_inbox


HOTKEY = "<ctrl>+<alt>+n"


class ServerThread(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.server = make_server("127.0.0.1", 8765, create_app())

    def run(self) -> None:
        self.server.serve_forever()

    def stop(self) -> None:
        self.server.shutdown()


class TrayRuntime:
    def __init__(self) -> None:
        self.server = ServerThread()
        self.root = Tk()
        self.root.withdraw()
        self.actions: queue.Queue[str] = queue.Queue()
        self.capture_window: Toplevel | None = None
        self.icon = pystray.Icon(
            "mykb",
            self._build_icon(),
            "MyKB",
            menu=pystray.Menu(
                pystray.MenuItem("Open Dashboard", lambda *_args: self.enqueue("dashboard")),
                pystray.MenuItem("Quick Capture", lambda *_args: self.enqueue("capture")),
                pystray.MenuItem("Organize Inbox", lambda *_args: self.enqueue("organize")),
                pystray.MenuItem("Quit", lambda *_args: self.enqueue("quit")),
            ),
        )
        self.listener = keyboard.GlobalHotKeys({HOTKEY: partial(self.enqueue, "capture")})

    def start(self) -> None:
        self.server.start()
        self.listener.start()
        self.icon.run_detached()
        self.root.after(250, self.process_actions)
        self.enqueue("dashboard")
        self.root.mainloop()

    def enqueue(self, action: str) -> None:
        self.actions.put(action)

    def process_actions(self) -> None:
        while not self.actions.empty():
            action = self.actions.get()
            if action == "dashboard":
                webbrowser.open("http://127.0.0.1:8765")
            elif action == "capture":
                self.open_capture_window()
            elif action == "organize":
                self.organize_now()
            elif action == "quit":
                self.shutdown()
                return
        self.root.after(250, self.process_actions)

    def open_capture_window(self) -> None:
        if self.capture_window is not None and self.capture_window.winfo_exists():
            self.capture_window.deiconify()
            self.capture_window.lift()
            self.capture_window.focus_force()
            return

        window = Toplevel(self.root)
        window.title("MyKB Quick Capture")
        window.geometry("560x360")
        window.attributes("-topmost", True)

        Label(window, text="Paste rough notes. Save with the button or Ctrl+Enter.", padx=14, pady=10).pack(anchor="w")
        textbox = Text(window, wrap="word", font=("Segoe UI", 11), padx=12, pady=12)
        textbox.pack(fill=BOTH, expand=True, padx=14, pady=(0, 12))
        textbox.focus_set()
        status = Label(window, text="Hotkey: Ctrl+Alt+N", padx=14, pady=8)
        status.pack(anchor="w")

        def save_note(_event: object | None = None) -> str | None:
            content = textbox.get("1.0", END).strip()
            if not content:
                status.config(text="Nothing to save.")
                return "break"
            saved, _capture_id = append_to_daily_inbox(content)
            textbox.delete("1.0", END)
            status.config(text=f"Saved to {saved.name}")
            return "break"

        Button(window, text="Save Note", command=save_note).pack(anchor="e", padx=14, pady=(0, 14))
        textbox.bind("<Control-Return>", save_note)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)
        self.capture_window = window

    def organize_now(self) -> None:
        result = organize_inbox()
        summary = f"Organized {len(result['organized'])} entries. Kept {len(result['keptFiles'])} inbox files."
        self.show_message("Inbox Organized", summary)

    def show_message(self, title: str, text: str) -> None:
        popup = Toplevel(self.root)
        popup.title(title)
        popup.geometry("420x160")
        popup.attributes("-topmost", True)
        Label(popup, text=text, wraplength=380, justify="left", padx=18, pady=18).pack(fill=BOTH, expand=True)
        Button(popup, text="Close", command=popup.destroy).pack(pady=(0, 14))

    def shutdown(self) -> None:
        self.listener.stop()
        self.icon.stop()
        self.server.stop()
        self.root.quit()

    @staticmethod
    def _build_icon() -> Image.Image:
        image = Image.new("RGB", (64, 64), "#efe6d8")
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=14, fill="#1e6f5c")
        draw.rectangle((18, 18, 46, 24), fill="#f8f5ef")
        draw.rectangle((18, 30, 46, 36), fill="#f8f5ef")
        draw.rectangle((18, 42, 38, 48), fill="#f8f5ef")
        return image


def main() -> None:
    TrayRuntime().start()


if __name__ == "__main__":
    main()
