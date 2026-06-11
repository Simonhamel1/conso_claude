import tkinter as tk
import threading
import gc
import os
import requests
import psutil
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────
SESSION_KEY = "COLLE_TON_SESSION_KEY_ICI"
USAGE_URL = "COLLE TON URL"
REFRESH_MS = 60_000   # actualisation toutes les 60 s
MEM_LIMIT_MB = 50     # seuil d'alerte mémoire
# ──────────────────────────────────────────────────────────

DARK_BG    = "#16213e"
CARD_BG    = "#0f3460"
ACCENT     = "#e94560"
BLUE       = "#00b4d8"
TEXT_DIM   = "#8892b0"
TEXT_LIGHT = "#ccd6f6"
GREEN      = "#64ffda"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
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
        session_pct   = round(five_hour.get("utilization", 0) or 0, 1)
        weekly_pct    = round(seven_day.get("utilization", 0) or 0, 1)
        session_reset = five_hour.get("resets_at", "")
        weekly_reset  = seven_day.get("resets_at", "")
        return session_pct, session_reset, weekly_pct, weekly_reset
    except Exception as e:
        print(f"Parse error: {e} — raw: {data}")
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
        if h < 24:
            return f"dans {h}h {m:02d}min"
        days = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
        return f"{days[dt.weekday()]}. {dt.strftime('%H:%M')}"
    except Exception:
        return iso_str[:16] if iso_str else "–"


def get_memory_mb():
    try:
        return PROC.memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


class UsageWidget:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.geometry("250x185+20+20")
        self.root.configure(bg=DARK_BG)
        self._drag_x = self._drag_y = 0
        self._build_ui()
        self._refresh()
        self._watch_memory()

    def _build_ui(self):
        bar = tk.Frame(self.root, bg=CARD_BG, height=24)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="  ◆ Claude Usage", bg=CARD_BG, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(side="left", pady=2)
        tk.Button(bar, text="×", bg=CARD_BG, fg=TEXT_DIM, bd=0,
                  font=("Segoe UI", 10), activebackground=CARD_BG,
                  command=self.root.destroy).pack(side="right", padx=4)
        bar.bind("<Button-1>", self._start_drag)
        bar.bind("<B1-Motion>", self._drag)

        body = tk.Frame(self.root, bg=DARK_BG)
        body.pack(fill="both", expand=True, padx=10, pady=6)

        # Session (5h)
        row1 = tk.Frame(body, bg=DARK_BG)
        row1.pack(fill="x", pady=(2, 1))
        tk.Label(row1, text="Session (5h)", bg=DARK_BG, fg=TEXT_LIGHT,
                 font=("Segoe UI", 8)).pack(side="left")
        self.session_pct_lbl = tk.Label(row1, text="–%", bg=DARK_BG, fg=BLUE,
                                         font=("Segoe UI", 8, "bold"))
        self.session_pct_lbl.pack(side="right")
        self.bar_session = tk.Canvas(body, height=7, bg=CARD_BG,
                                      highlightthickness=0, width=230)
        self.bar_session.pack(fill="x", pady=(0, 2))
        self.session_reset_lbl = tk.Label(body, text="Réinit. –", bg=DARK_BG,
                                           fg=TEXT_DIM, font=("Segoe UI", 7))
        self.session_reset_lbl.pack(anchor="e")

        tk.Frame(body, bg=CARD_BG, height=1).pack(fill="x", pady=4)

        # Semaine (7j)
        row2 = tk.Frame(body, bg=DARK_BG)
        row2.pack(fill="x", pady=(2, 1))
        tk.Label(row2, text="Semaine (7j)", bg=DARK_BG, fg=TEXT_LIGHT,
                 font=("Segoe UI", 8)).pack(side="left")
        self.weekly_pct_lbl = tk.Label(row2, text="–%", bg=DARK_BG, fg=BLUE,
                                        font=("Segoe UI", 8, "bold"))
        self.weekly_pct_lbl.pack(side="right")
        self.bar_weekly = tk.Canvas(body, height=7, bg=CARD_BG,
                                     highlightthickness=0, width=230)
        self.bar_weekly.pack(fill="x", pady=(0, 2))
        self.weekly_reset_lbl = tk.Label(body, text="Réinit. –", bg=DARK_BG,
                                          fg=TEXT_DIM, font=("Segoe UI", 7))
        self.weekly_reset_lbl.pack(anchor="e")

        tk.Frame(body, bg=CARD_BG, height=1).pack(fill="x", pady=4)

        # Dernière actualisation (bien visible)
        self.status_lbl = tk.Label(body, text="⟳ Chargement…", bg=DARK_BG,
                                    fg=TEXT_LIGHT, font=("Segoe UI", 8, "bold"))
        self.status_lbl.pack(pady=(2, 0))

        # Mémoire
        self.mem_lbl = tk.Label(body, text="Mém. – Mo", bg=DARK_BG,
                                fg=TEXT_DIM, font=("Segoe UI", 7))
        self.mem_lbl.pack(pady=(1, 0))

    def _draw_bar(self, canvas, pct):
        canvas.delete("all")
        w = canvas.winfo_width() or 230
        canvas.create_rectangle(0, 0, w, 7, fill=CARD_BG, outline="")
        fill_w = max(0, min(int(w * pct / 100), w))
        if fill_w > 0:
            color = ACCENT if pct >= 80 else (BLUE if pct >= 50 else GREEN)
            canvas.create_rectangle(0, 0, fill_w, 7, fill=color, outline="")

    def _apply_data(self, parsed):
        if not parsed:
            self.status_lbl.config(text="⚠ Erreur – vérifie ton sessionKey", fg=ACCENT)
            return
        s_pct, s_reset, w_pct, w_reset = parsed
        self.session_pct_lbl.config(
            text=f"{s_pct}%",
            fg=ACCENT if s_pct >= 80 else (BLUE if s_pct >= 50 else GREEN))
        self.weekly_pct_lbl.config(
            text=f"{w_pct}%",
            fg=ACCENT if w_pct >= 80 else (BLUE if w_pct >= 50 else GREEN))
        self._draw_bar(self.bar_session, s_pct)
        self._draw_bar(self.bar_weekly, w_pct)
        self.session_reset_lbl.config(text=f"Réinit. {format_countdown(s_reset)}")
        self.weekly_reset_lbl.config(text=f"Réinit. {format_countdown(w_reset)}")
        self.status_lbl.config(
            text=f"🕐 Actualisé à {datetime.now().strftime('%H:%M:%S')}",
            fg=GREEN)

    def _refresh(self):
        def worker():
            data   = fetch_usage()
            parsed = parse_usage(data)
            self.root.after(0, self._apply_data, parsed)
        threading.Thread(target=worker, daemon=True).start()
        self.root.after(REFRESH_MS, self._refresh)

    def _watch_memory(self):
        gc.collect()  # libère la mémoire inutilisée pour rester léger
        mem = get_memory_mb()
        if mem >= MEM_LIMIT_MB:
            self.mem_lbl.config(text=f"⚠ Mém. {mem:.1f} / {MEM_LIMIT_MB} Mo", fg=ACCENT)
        else:
            self.mem_lbl.config(text=f"Mém. {mem:.1f} / {MEM_LIMIT_MB} Mo", fg=TEXT_DIM)
        self.root.after(5_000, self._watch_memory)  # vérifie toutes les 5 s

    def _start_drag(self, e):
        self._drag_x, self._drag_y = e.x, e.y

    def _drag(self, e):
        x = self.root.winfo_x() + e.x - self._drag_x
        y = self.root.winfo_y() + e.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if SESSION_KEY == "COLLE_TON_SESSION_KEY_ICI":
        print("Édite ce fichier et remplace SESSION_KEY par ton cookie sessionKey de claude.ai")
    else:
