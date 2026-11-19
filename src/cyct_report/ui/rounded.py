"""圆角组件：tkinter 没有圆角，这里用预先算好的抗锯齿角图贴在矩形四角。

Panel   圆角分区/卡片（可带 1px 边线）
Button  圆角按钮：accent（主按钮）/ soft（浅色）/ ghost（透明，悬停显底色）
"""
import tkinter as tk

from . import theme

_CACHE = {}


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(colors_weights):
    r = g = b = 0.0
    for col, w in colors_weights:
        cr, cg, cb = _hex(col)
        r, g, b = r + cr * w, g + cg * w, b + cb * w
    return "#%02x%02x%02x" % (round(r), round(g), round(b))


def corner(master, radius, fill, outside, border=None, quadrant="nw"):
    """生成一个角的图片（4×4 超采样抗锯齿）。"""
    key = (radius, fill, outside, border, quadrant)
    if key in _CACHE:
        return _CACHE[key]
    img = tk.PhotoImage(master=master, width=radius, height=radius)
    n, rows = 4, []
    for y in range(radius):
        row = []
        for x in range(radius):
            f_in = f_line = 0
            for sy in range(n):
                for sx in range(n):
                    px, py = x + (sx + 0.5) / n, y + (sy + 0.5) / n
                    # 以 nw 角计算：圆心在 (radius, radius)
                    d = ((radius - px) ** 2 + (radius - py) ** 2) ** 0.5
                    if d <= radius - (1 if border else 0):
                        f_in += 1
                    elif border and d <= radius:
                        f_line += 1
            t = n * n
            parts = [(fill, f_in / t), (outside, (t - f_in - f_line) / t)]
            if border:
                parts.append((border, f_line / t))
            row.append(_mix(parts))
        rows.append(row)
    if "e" in quadrant:
        rows = [list(reversed(r)) for r in rows]
    if "s" in quadrant:
        rows = list(reversed(rows))
    img.put(" ".join("{" + " ".join(r) + "}" for r in rows))
    _CACHE[key] = img
    return img


class Panel(tk.Frame):
    """圆角矩形容器。内容放进 self.inner（四周留出 pad）。"""

    def __init__(self, master, fill=theme.LANE, outside=None, radius=11, border=None, pad=12):
        outside = outside or master.cget("bg")
        super().__init__(master, bg=fill, highlightthickness=1 if border else 0,
                         highlightbackground=border or fill, highlightcolor=border or fill)
        self.radius, self.outside, self.border = radius, outside, border
        self.inner = tk.Frame(self, bg=fill)
        self.inner.pack(fill="both", expand=True, padx=pad, pady=pad)
        self._corners = {q: tk.Label(self, bd=0, highlightthickness=0, bg=fill)
                         for q in ("nw", "ne", "sw", "se")}
        pos = {"nw": (0, 0), "ne": (1, 0), "sw": (0, 1), "se": (1, 1)}
        for q, lbl in self._corners.items():
            lbl.place(relx=pos[q][0], rely=pos[q][1], anchor=q, bordermode="outside")
        self.set_fill(fill)

    def set_fill(self, fill, border=None):
        border = border or self.border
        self.configure(bg=fill, highlightbackground=border or fill, highlightcolor=border or fill)
        self.inner.configure(bg=fill)
        for q, lbl in self._corners.items():
            lbl.configure(image=corner(self, self.radius, fill, self.outside, border, q), bg=fill)
            lbl.lift()


class Button(Panel):
    """圆角按钮。kind: accent / soft / ghost / danger。"""

    STYLES = {
        "accent": (theme.ACCENT, theme.ACCENT_DEEP, "#FFFFFF"),
        "soft": (theme.ACCENT_SOFT, "#DCE3FD", theme.ACCENT_DEEP),
        "ghost": (None, theme.HOVER, theme.TEXT_BODY),
        "danger": (None, theme.FAIL_SOFT, theme.FAIL),
    }

    def __init__(self, master, text, command, kind="ghost", icon=None, font=None, padx=10, pady=5,
                 radius=8):
        self.base, self.hover_fill, fg = self.STYLES[kind]
        outside = master.cget("bg")
        self.base = self.base or outside
        super().__init__(master, fill=self.base, outside=outside, radius=radius, pad=0)
        self.command, self.enabled = command, True
        self.fg = fg
        box = self.inner
        self.labels = []
        if icon:
            self.labels.append(tk.Label(box, text=theme.ICONS.get(icon, icon), font=theme.icon_font(10),
                                        bg=self.base, fg=fg))
        if text:
            self.labels.append(tk.Label(box, text=text, font=font or theme.BASE, bg=self.base, fg=fg))
        for i, lbl in enumerate(self.labels):
            lbl.pack(side="left", padx=(padx if i == 0 else 4, padx if i == len(self.labels) - 1 else 0),
                     pady=pady)
        for w in [self, box] + self.labels:
            w.bind("<Enter>", lambda e: self._paint(self.hover_fill))
            w.bind("<Leave>", lambda e: self._paint(self.base))
            w.bind("<ButtonRelease-1>", self._click)
            w.configure(cursor="hand2")
        self.lift_corners()

    def lift_corners(self):
        for lbl in self._corners.values():
            lbl.lift()

    def _paint(self, fill):
        if not self.enabled:
            return
        self.set_fill(fill)
        for lbl in self.labels:
            lbl.configure(bg=fill)

    def _click(self, _e):
        if self.enabled and self.command:
            self.command()

    def set_kind(self, kind):
        """切换样式（用于分段选择器的选中/未选中）。"""
        base, self.hover_fill, self.fg = self.STYLES[kind]
        self.base = base or self.outside
        for lbl in self.labels:
            lbl.configure(fg=self.fg)
        self._paint(self.base)

    def set_enabled(self, enabled, text=None):
        self.enabled = enabled
        for lbl in self.labels:
            lbl.configure(fg=self.fg if enabled else theme.FAINT)
        if text and self.labels:
            self.labels[-1].configure(text=text)
        self._paint(self.base) if enabled else None
