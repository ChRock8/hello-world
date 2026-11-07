"""On-screen overlay: a small card next to the item tooltip, plus short toasts.

Click-through and always on top. Diablo 3 must run in Windowed Fullscreen,
otherwise Windows can't draw anything over it.
"""
import queue
import tkinter as tk

from . import config, winutil
from .overlay_layout import place_card

BG = "#15110d"
FG = "#eadfce"
MUTED = "#9c907f"
ACTION_COLORS = {
    "EQUIP": "#4cc46a", "UPGRADE": "#4cc46a", "EQUIPPED": "#4cc46a",
    "KEEP": "#e0b04f", "CUBE": "#b88cf0", "SALVAGE": "#e45c5c", "CHECK": "#a0a0a0",
}
ACTION_HINT = {
    "EQUIP": "Wear it", "UPGRADE": "Better than what you wear", "EQUIPPED": "You're wearing this",
    "KEEP": "Not better - keep as a backup or salvage", "CUBE": "Extract in Kanai's Cube",
    "SALVAGE": "Salvage it", "CHECK": "Not sure - press F9 to ask Claude",
}
FONT = "Segoe UI"


def _nb(text: str) -> str:
    """Keep multi-word stat names on one line when the card wraps."""
    return text.replace(" ", "\u00a0")


class Overlay:
    def __init__(self, ui_queue: queue.Queue, hotkey_hint: str = ""):
        self.q = ui_queue
        self.hint = hotkey_hint
        self.root = tk.Tk()
        self.root.withdraw()
        self.card = self._window(alpha=0.94)
        self.toast = self._window(alpha=0.9)
        self.toast_label = tk.Label(self.toast, bg=BG, fg=FG, font=(FONT, 11), padx=14, pady=8)
        self.toast_label.pack()
        self._toast_job = None
        self.root.after(40, self._poll)

    def _window(self, alpha):
        w = tk.Toplevel(self.root, bg=BG, highlightthickness=2, highlightbackground="#3a332b")
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        try:
            w.attributes("-alpha", alpha)
        except tk.TclError:
            pass
        w.withdraw()
        winutil.make_click_through(w)
        return w

    def _show(self, w):
        w.deiconify()
        w.attributes("-topmost", True)
        w.lift()
        winutil.make_click_through(w)

    # ---- messages ------------------------------------------------------
    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "show":
                    self.show_reading(msg[1])
                elif msg[0] == "hide":
                    self.card.withdraw()
                elif msg[0] == "toast":
                    self.show_toast(msg[1])
                elif msg[0] == "quit":
                    self.root.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(40, self._poll)

    def show_reading(self, r):
        v = r.verdict
        color = ACTION_COLORS.get(v.action, FG)
        for child in self.card.winfo_children():
            child.destroy()
        self.card.configure(highlightbackground=color)
        f = tk.Frame(self.card, bg=BG, padx=12, pady=8)
        f.pack()

        top = tk.Frame(f, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text=v.action, fg=color, bg=BG, font=(FONT, 16, "bold")).pack(side="left")
        if v.action not in ("CUBE", "SALVAGE", "CHECK"):
            tk.Label(top, text=f"{v.score}/100", fg=FG, bg=BG, font=(FONT, 14, "bold")).pack(side="right", padx=(16, 0))
        tk.Label(f, text=ACTION_HINT.get(v.action, ""), fg=MUTED, bg=BG, font=(FONT, 9)).pack(anchor="w")

        quality = r.item.get("quality", "normal")
        title = (v.name or r.item.get("name", "?")) + ("" if quality == "normal" else f"  ({quality})")
        tk.Label(f, text=title, fg=FG, bg=BG, font=(FONT, 11, "bold")).pack(anchor="w", pady=(4, 0))

        if v.have:
            tk.Label(f, text="   ".join("✓\u00a0" + _nb(h) for h in v.have), fg="#7fd18f", bg=BG, font=(FONT, 10),
                     wraplength=380, justify="left").pack(anchor="w")
        if v.missing:
            tk.Label(f, text="   ".join("✗\u00a0" + _nb(m) for m in v.missing), fg="#e88a8a", bg=BG, font=(FONT, 10),
                     wraplength=380, justify="left").pack(anchor="w")
        if v.reroll:
            tk.Label(f, text=f"Mystic: {v.reroll}", fg="#e0b04f", bg=BG, font=(FONT, 10)).pack(anchor="w")
        for reason in v.reasons[:2]:
            tk.Label(f, text=reason, fg=FG, bg=BG, font=(FONT, 10), wraplength=380, justify="left").pack(anchor="w")
        foot = self.hint + ("   · read by Claude" if r.source == "claude" else "")
        tk.Label(f, text=foot, fg=MUTED, bg=BG, font=(FONT, 8)).pack(anchor="w", pady=(6, 0))

        self.card.update_idletasks()
        cw, ch = self.card.winfo_reqwidth(), self.card.winfo_reqheight()
        if config.CARD_POS != "auto":
            x, y = (int(n) for n in config.CARD_POS.split(","))
        else:
            x, y = place_card(r.box, cw, ch, *r.screen)
        self.card.geometry(f"+{x}+{y}")
        self._show(self.card)

    def show_toast(self, text, ms=2500):
        self.toast_label.configure(text=text)
        self.toast.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = self.toast.winfo_reqwidth()
        self.toast.geometry(f"+{(sw - w) // 2}+{int(sh * 0.78)}")  # just above the skill bar
        self._show(self.toast)
        if self._toast_job:
            self.root.after_cancel(self._toast_job)
        self._toast_job = self.root.after(ms, self.toast.withdraw)

    def run(self):
        self.root.mainloop()

    def quit(self):
        self.q.put(("quit",))
