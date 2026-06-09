"""
core/gui/overlay.py
Tkinter borderless overlay widget (status indicator).
INVARIANT: No imports of keyboard, pynput, or platform.system().
"""

import tkinter as tk

from core.state import (
    STATE_IDLE,
    STATE_RECORDING,
    STATE_PROCESSING,
    STATE_DONE,
    STATE_ERROR,
    STATE_SYNTHESIS,
)


class Overlay:
    """
    Borderless always-on-top Tkinter window that shows recording/processing status.
    Communicates with the engine exclusively through the shared queue — never calls
    platform adapters directly.
    """

    # Catppuccin-inspired color palette
    BG = "#1e1e2e"
    TEXT = "#cdd6f4"
    BORDER = "#313244"
    ACCENT_BLUE = "#89b4fa"
    ACCENT_RED = "#f38ba8"
    ACCENT_YELLOW = "#f9e2af"
    ACCENT_GREEN = "#a6e3a1"
    ACCENT_PURPLE = "#6272a4"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root

        # Borderless, always-on-top
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        # Position: bottom-right corner above taskbar
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 280, 70
        self.root.geometry(f"{w}x{h}+{sw - w - 30}+{sh - h - 80}")

        self.root.configure(bg=self.BG)

        # Main frame with subtle border
        self.frame = tk.Frame(
            self.root,
            bg=self.BG,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Canvas: status indicator dot (VU meter)
        self.canvas = tk.Canvas(
            self.frame, width=36, height=36, bg=self.BG, bd=0, highlightthickness=0
        )
        self.canvas.pack(side=tk.LEFT, padx=(12, 10))
        self.indicator = self.canvas.create_oval(8, 8, 28, 28, fill="gray", outline="")
        self.current_radius = 10.0

        # Labels
        self.label_title = tk.Label(
            self.frame, text="TLL-Voice", font=("Segoe UI", 10, "bold"),
            fg=self.ACCENT_BLUE, bg=self.BG,
        )
        self.label_title.pack(anchor=tk.W, pady=(10, 0))

        self.label_status = tk.Label(
            self.frame, text="Запуск...", font=("Segoe UI", 9),
            fg=self.TEXT, bg=self.BG,
        )
        self.label_status.pack(anchor=tk.W, pady=(2, 10))

        self.dot_count = 0
        self.current_state = STATE_IDLE
        self._fade_id = None

        # Start hidden
        self.root.attributes("-alpha", 0.0)
        self.root.withdraw()

    # ------------------------------------------------------------------
    # Public state API
    # ------------------------------------------------------------------

    def set_state(self, state: str, details: str = "") -> None:
        self.current_state = state

        if state == STATE_IDLE:
            self._hide()
            return

        self._show()

        if state == STATE_RECORDING:
            mode_name = "Умный Редактор" if details == "mode1" else "Буквально"
            self.label_title.configure(text=f"ЗАПИСЬ [{mode_name}]", fg=self.ACCENT_RED)
            self.label_status.configure(text="Говорите... Нажмите хоткей ещё раз")
            self.canvas.itemconfigure(self.indicator, fill=self.ACCENT_RED)

        elif state == STATE_PROCESSING:
            self.label_title.configure(text="ОБРАБОТКА", fg=self.ACCENT_YELLOW)
            self.label_status.configure(text="Отправка в Gemini...")
            self.canvas.itemconfigure(self.indicator, fill=self.ACCENT_YELLOW)
            self._animate_dots("Отправка в Gemini")

        elif state == STATE_DONE:
            self.label_title.configure(text="УСПЕШНО", fg=self.ACCENT_GREEN)
            self.label_status.configure(text="Текст вставлен!")
            self.canvas.itemconfigure(self.indicator, fill=self.ACCENT_GREEN)

        elif state == STATE_ERROR:
            short = details[:35] + "..." if len(details) > 35 else details
            self.label_title.configure(text="ОШИБКА", fg=self.ACCENT_RED)
            self.label_status.configure(text=short)
            self.canvas.itemconfigure(self.indicator, fill=self.ACCENT_RED)

        elif state == STATE_SYNTHESIS:
            self.label_title.configure(text="СИНТЕЗ РЕЧИ", fg=self.ACCENT_PURPLE)
            self.label_status.configure(text="Генерация аудио...")
            self.canvas.itemconfigure(self.indicator, fill=self.ACCENT_PURPLE)
            self._animate_dots("Генерация аудио")

    # ------------------------------------------------------------------
    # VU Meter animation (called from engine via root.after)
    # ------------------------------------------------------------------

    def update_vu_indicator(self, recorder) -> None:
        if self.current_state != STATE_RECORDING:
            cx, cy = 18, 18
            self.canvas.coords(self.indicator, cx - 10, cy - 10, cx + 10, cy + 10)
            return

        rms = getattr(recorder, "current_rms", 0.0)
        norm = min(1.0, max(0.0, (rms - 100.0) / (3000.0 - 100.0)))
        target_r = 10.0 + norm * 7.0
        self.current_radius += 0.15 * (target_r - self.current_radius)

        cx, cy, r = 18, 18, self.current_radius
        self.canvas.coords(self.indicator, cx - r, cy - r, cx + r, cy + r)
        self.root.after(30, lambda: self.update_vu_indicator(recorder))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _show(self) -> None:
        if self._fade_id:
            self.root.after_cancel(self._fade_id)
            self._fade_id = None
        if self.root.state() != "normal":
            self.root.attributes("-alpha", 0.0)
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
        self._fade_in()

    def _hide(self) -> None:
        if self._fade_id:
            self.root.after_cancel(self._fade_id)
            self._fade_id = None
        self._fade_out()

    def _fade_in(self) -> None:
        try:
            alpha = float(self.root.attributes("-alpha"))
        except Exception:
            alpha = 0.0
        if alpha < 0.9:
            self.root.attributes("-alpha", min(alpha + 0.1, 0.9))
            self._fade_id = self.root.after(20, self._fade_in)
        else:
            self._fade_id = None

    def _fade_out(self) -> None:
        try:
            alpha = float(self.root.attributes("-alpha"))
        except Exception:
            alpha = 0.0
        if alpha > 0.0:
            self.root.attributes("-alpha", max(alpha - 0.1, 0.0))
            self._fade_id = self.root.after(20, self._fade_out)
        else:
            self.root.withdraw()
            self._fade_id = None

    def _animate_dots(self, base_text: str) -> None:
        if self.current_state not in (STATE_PROCESSING, STATE_SYNTHESIS):
            return
        self.dot_count = (self.dot_count + 1) % 4
        self.label_status.configure(text=base_text + "." * self.dot_count)
        self.root.after(400, lambda: self._animate_dots(base_text))
