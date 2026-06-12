import tkinter as tk
from tkinter import font as tkfont
import threading
import gc
import os
import requests
import psutil
from datetime import datetime, timezone
import math
import ctypes

# ─── CONFIG ───────────────────────────────────────────────
SESSION_KEY = "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"
USAGE_URL = "https://claude.ai/api/organizations/a18ab5b5-f998-4de4-bdb0-2752c6d6c3bc/usage"
REFRESH_MS = 60_000
MEM_LIMIT_MB = 50
# ──────────────────────────────────────────────────────────

# Palette
BG          = "#0d1117"
CARD        = "#1c2230"
BORDER      = "#2d3748"
ACCENT      = "#79b8ff"
CYAN        = "#56d8e4"
GREEN       = "#56d364"
YELLOW      = "#e3b341"
RED         = "#ff7b72"
TEXT        = "#ffffff"
TEXT_SUB    = "#cdd5e0"
TEXT_MUTED  = "#8fa3bf"

SIZES = [
    ("S",  240, 195),
    ("M",  300, 225),
    ("L",  380, 265),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "ApplWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

PROC = psutil.Process(os.getpid())


def fetch_usage():
    try:
        cookies = {"sessionKey": SESSION_KEY}
        r = requests.get(USAGE_URL, headers=HEADERS, cookies=cookies, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Fetch error: {e}")
    return None


def parse_usage(data):
    if not data:
        return None
    try:
        five_hour = data.get("five_hour") or {}
        seven_day = data.get("seven_day") or {}
        return (
            round(five_hour.get("utilization", 0) or 0, 1),
            five_hour.get("resets_at", ""),
            round(seven_day.get("utilization", 0) or 0, 1),
            seven_day.get("resets_at", ""),
        )
    except Exception as e:
        print(f"Parse error: {e}")
    return None


def format_countdown(iso_str):
    if not iso_str:
        return "–"
    try:
        dt  = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo)
        diff = dt - now
        if diff.total_seconds() < 0:
            return "bientôt"
        total = int(diff.total_seconds())
        h, rem = divmod(total, 3600)
        m = rem // 60
        return f"dans {h}h {m:02d}min"
    except Exception:
        return "–"


def format_reset_local(iso_str):
    """Return local time string for a reset timestamp."""
    if not iso_str:
        return "–"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()  # convert to local timezone
        days = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
        tz_name = local_dt.strftime("%Z")
        return f"{days[local_dt.weekday()]}. {local_dt.strftime('%H:%M')} ({tz_name})"
    except Exception:
        return "–"


def get_memory_mb():
    try:
        return PROC.memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


def pct_color(pct):
    if pct >= 80:
        return RED
    if pct >= 50:
        return YELLOW
    return CYAN


class RoundedCanvas(tk.Canvas):
    """Canvas helper to draw rounded rectangles as progress bars."""
    pass


class UsageWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.configure(bg=BG)

        self._size_idx = 1  # default M
        self._drag_x = self._drag_y = 0
        self._anim_session = 0.0
        self._anim_weekly  = 0.0
        self._target_session = 0.0
        self._target_weekly  = 0.0

        w, h = SIZES[self._size_idx][1], SIZES[self._size_idx][2]
        self.root.geometry(f"{w}x{h}+20+20")

        self._build_ui()
        self.root.after(100, self._apply_rounded_corners)
        self._refresh()
        self._watch_memory()

    # ── UI BUILD ──────────────────────────────────────────

    def _build_ui(self):
        self._build_titlebar()
        self._build_body()

    def _build_titlebar(self):
        self.titlebar = tk.Frame(self.root, bg=CARD, height=28)
        self.titlebar.pack(fill="x")
        self.titlebar.pack_propagate(False)

        # Diamond icon + title
        tk.Label(self.titlebar, text="◆ Claude Usage",
                 bg=CARD, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=10)

        # Size toggle buttons (right side, before close)
        size_frame = tk.Frame(self.titlebar, bg=CARD)
        size_frame.pack(side="right", padx=(0, 2))

        self._size_btns = []
        for i, (label, _, _) in enumerate(SIZES):
            btn = tk.Label(size_frame, text=label, bg=CARD, fg=TEXT_MUTED,
                           font=("Segoe UI", 7, "bold"), cursor="hand2",
                           padx=3)
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, idx=i: self._set_size(idx))
            self._size_btns.append(btn)

        self._update_size_btns()

        # Close button
        close = tk.Label(self.titlebar, text="✕", bg=CARD, fg=TEXT_MUTED,
                         font=("Segoe UI", 9), cursor="hand2", padx=8)
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.root.destroy())
        close.bind("<Enter>", lambda e: close.config(fg=RED))
        close.bind("<Leave>", lambda e: close.config(fg=TEXT_MUTED))

        self.titlebar.bind("<Button-1>", self._start_drag)
        self.titlebar.bind("<B1-Motion>", self._drag)

        # Thin border line below titlebar
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

    def _build_body(self):
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=12, pady=8)

        self._build_metric_block(
            self.body,
            label="Session  (5h)",
            attr_pct="session_pct_lbl",
            attr_bar="bar_session",
            attr_reset="session_reset_lbl",
            attr_local="session_local_lbl",
        )

        # Divider
        tk.Frame(self.body, bg=BORDER, height=1).pack(fill="x", pady=6)

        self._build_metric_block(
            self.body,
            label="Semaine  (7j)",
            attr_pct="weekly_pct_lbl",
            attr_bar="bar_weekly",
            attr_reset="weekly_reset_lbl",
            attr_local="weekly_local_lbl",
        )

        tk.Frame(self.body, bg=BORDER, height=1).pack(fill="x", pady=6)

        # Footer row
        footer = tk.Frame(self.body, bg=BG)
        footer.pack(fill="x")

        self.status_lbl = tk.Label(footer, text="⟳ Chargement…",
                                   bg=BG, fg=TEXT_SUB,
                                   font=("Segoe UI", 8))
        self.status_lbl.pack(side="left")

        self.mem_lbl = tk.Label(footer, text="– Mo",
                                bg=BG, fg=TEXT_MUTED,
                                font=("Segoe UI", 8))
        self.mem_lbl.pack(side="right")

    def _build_metric_block(self, parent, label,
                             attr_pct, attr_bar, attr_reset, attr_local):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 3))

        tk.Label(row, text=label, bg=BG, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="left")

        pct_lbl = tk.Label(row, text="– %", bg=BG, fg=CYAN,
                           font=("Segoe UI", 10, "bold"))
        pct_lbl.pack(side="right")
        setattr(self, attr_pct, pct_lbl)

        bar = tk.Canvas(parent, height=9, bg=BG,
                        highlightthickness=0)
        bar.pack(fill="x", pady=(0, 4))
        setattr(self, attr_bar, bar)

        sub = tk.Frame(parent, bg=BG)
        sub.pack(fill="x")

        reset_lbl = tk.Label(sub, text="Réinit. –", bg=BG, fg=TEXT_SUB,
                             font=("Segoe UI", 7))
        reset_lbl.pack(side="left")
        setattr(self, attr_reset, reset_lbl)

        local_lbl = tk.Label(sub, text="–", bg=BG, fg=TEXT_MUTED,
                             font=("Segoe UI", 7))
        local_lbl.pack(side="right")
        setattr(self, attr_local, local_lbl)

    # ── SIZE CONTROL ──────────────────────────────────────

    def _set_size(self, idx):
        self._size_idx = idx
        _, w, h = SIZES[idx]
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self._update_size_btns()
        self.root.after(50, self._redraw_bars)

    def _update_size_btns(self):
        for i, btn in enumerate(self._size_btns):
            if i == self._size_idx:
                btn.config(fg=ACCENT)
            else:
                btn.config(fg=TEXT_MUTED)

    # ── BAR DRAWING ───────────────────────────────────────

    def _draw_bar(self, canvas, pct, color):
        canvas.delete("all")
        canvas.update_idletasks()
        w = canvas.winfo_width() or SIZES[self._size_idx][1] - 24
        h = 8
        r = 4  # corner radius

        # Background pill
        self._draw_pill(canvas, 0, 0, w, h, r, CARD)

        # Foreground fill
        fill_w = max(0, min(int(w * pct / 100), w))
        if fill_w > r * 2:
            self._draw_pill(canvas, 0, 0, fill_w, h, r, color)
        elif fill_w > 0:
            canvas.create_rectangle(0, 0, fill_w, h, fill=color, outline="")

    def _draw_pill(self, canvas, x1, y1, x2, y2, r, color):
        canvas.create_arc(x1, y1, x1+2*r, y2, start=90, extent=180,
                          fill=color, outline="")
        canvas.create_arc(x2-2*r, y1, x2, y2, start=270, extent=180,
                          fill=color, outline="")
        canvas.create_rectangle(x1+r, y1, x2-r, y2, fill=color, outline="")

    def _redraw_bars(self):
        self._draw_bar(self.bar_session, self._anim_session,
                       pct_color(self._anim_session))
        self._draw_bar(self.bar_weekly, self._anim_weekly,
                       pct_color(self._anim_weekly))

    # ── ANIMATION ─────────────────────────────────────────

    def _animate_bars(self):
        changed = False

        def step(current, target):
            nonlocal changed
            if abs(current - target) < 0.3:
                return target
            changed = True
            return current + (target - current) * 0.15

        self._anim_session = step(self._anim_session, self._target_session)
        self._anim_weekly  = step(self._anim_weekly,  self._target_weekly)

        self._draw_bar(self.bar_session, self._anim_session,
                       pct_color(self._target_session))
        self._draw_bar(self.bar_weekly, self._anim_weekly,
                       pct_color(self._target_weekly))

        if changed:
            self.root.after(16, self._animate_bars)

    # ── DATA ──────────────────────────────────────────────

    def _apply_data(self, parsed):
        if not parsed:
            self.status_lbl.config(text="⚠ sessionKey invalide", fg=RED)
            return

        s_pct, s_reset, w_pct, w_reset = parsed

        self.session_pct_lbl.config(text=f"{s_pct} %", fg=pct_color(s_pct))
        self.weekly_pct_lbl.config(text=f"{w_pct} %",  fg=pct_color(w_pct))

        self.session_reset_lbl.config(text=f"⏱ {format_countdown(s_reset)}")
        self.weekly_reset_lbl.config(text=f"⏱ {format_countdown(w_reset)}")

        self.session_local_lbl.config(text=format_reset_local(s_reset))
        self.weekly_local_lbl.config(text=format_reset_local(w_reset))

        self.status_lbl.config(
            text=f"⟳ {datetime.now().strftime('%H:%M:%S')}",
            fg=TEXT_SUB)

        self._target_session = s_pct
        self._target_weekly  = w_pct
        self._animate_bars()

    def _refresh(self):
        def worker():
            data   = fetch_usage()
            parsed = parse_usage(data)
            self.root.after(0, self._apply_data, parsed)
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(REFRESH_MS, self._refresh)

    def _watch_memory(self):
        gc.collect()
        mem = get_memory_mb()
        color = RED if mem >= MEM_LIMIT_MB else TEXT_MUTED
        self.mem_lbl.config(
            text=f"{'⚠ ' if mem >= MEM_LIMIT_MB else ''}{mem:.1f} / {MEM_LIMIT_MB} Mo",
            fg=color)
        self.root.after(5_000, self._watch_memory)

    # ── ROUNDED CORNERS (Windows 11 DWM) ─────────────────

    def _apply_rounded_corners(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if hwnd == 0:
                hwnd = self.root.winfo_id()
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(DWMWCP_ROUND),
                ctypes.sizeof(DWMWCP_ROUND),
            )
        except Exception:
            pass  # non-Windows 11 : silently skip

    # ── DRAG ──────────────────────────────────────────────

    def _start_drag(self, e):
        self._drag_x, self._drag_y = e.x, e.y

    def _drag(self, e):
        x = self.root.winfo_x() + e.x - self._drag_x
        y = self.root.winfo_y() + e.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    UsageWidget().run()
