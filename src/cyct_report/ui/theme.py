"""界面主题：配色参考 FloatingKanban（云白底、浅灰圆角分区、白色卡片、蓝紫主色），
控件外观用 Sun Valley（Windows 11 风格）。"""
from tkinter import font as tkfont, ttk

import sv_ttk

FAMILY = "Microsoft YaHei UI"
BASE = (FAMILY, 10)
SMALL = (FAMILY, 9)
BOLD = (FAMILY, 10, "bold")
TITLE = (FAMILY, 11, "bold")
BRAND = (FAMILY, 13, "bold")

SHELL = "#FFFFFF"          # 云白：窗口底色
LANE = "#F6F7F9"           # 分区底色（圆角 11）
CARD = "#FFFFFF"           # 卡片（表格区域）
LINE = "#E4E7EE"
ROW_LINE = "#EEF0F4"
ACCENT = "#4F6EF7"
ACCENT_DEEP = "#3D5AE0"
ACCENT_SOFT = "#E8EDFE"
HOVER = "#ECEEF2"
SELECTED = "#EEF1FE"
GROUP_BG = "#F1F3F7"
TEXT = "#1F2430"
TEXT_BODY = "#3A4150"
MUTED = "#6E788A"
FAINT = "#A0A8B5"
OK = "#1FB27A"
FAIL = "#E5484D"
FAIL_SOFT = "#FDECEC"

ICON_FAMILY = "Segoe MDL2 Assets"
ICONS = {"add": "", "delete": "", "edit": "", "up": "", "down": "",
         "save": "", "reset": "", "clear": "", "group": "", "import": "",
         "folder": "", "settings": "", "search": "", "doc": "",
         "copy": "", "check": "", "close": ""}


def apply(root):
    global ICON_FAMILY
    sv_ttk.set_theme("light", root)
    families = set(tkfont.families(root))
    if "Segoe Fluent Icons" in families:
        ICON_FAMILY = "Segoe Fluent Icons"
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(name, root).configure(family=FAMILY, size=10)
    root.option_add("*Font", BASE)
    root.option_add("*TCombobox*Listbox.font", BASE)
    style = ttk.Style(root)
    # 大部分控件放在浅灰分区上
    for name in ("TFrame", "TLabel", "TRadiobutton", "TCheckbutton", "TLabelframe",
                 "TLabelframe.Label"):
        style.configure(name, background=LANE)
    style.configure("TLabel", foreground=TEXT_BODY)
    style.configure("Field.TLabel", foreground=MUTED, background=LANE, font=SMALL)
    style.configure("Muted.TLabel", foreground=MUTED, background=LANE, font=SMALL)
    style.configure("Shell.TFrame", background=SHELL)
    style.configure("Shell.TLabel", background=SHELL, foreground=TEXT)
    style.configure("Card.TFrame", background=CARD)
    style.configure("Fail.TEntry", foreground=FAIL)
    style.configure("Treeview", rowheight=30, font=BASE, background=CARD, fieldbackground=CARD)
    style.configure("Treeview.Heading", font=BOLD, foreground=MUTED)
    style.map("Treeview", background=[("selected", SELECTED)], foreground=[("selected", TEXT)])
    root.configure(bg=SHELL)


def icon_font(size=10):
    return (ICON_FAMILY, size)
