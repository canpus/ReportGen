"""Native notification icons; no separate process or image library required."""

import ctypes as c
import sys


def install(root, image, icon_path, restore, close):
    if sys.platform == "win32":
        return WindowsTray(root, icon_path, restore, close)
    if root.tk.call("tk", "windowingsystem") == "x11":
        return XTray(root, image, restore, close)
    return None


class XTray:
    """Dock a native Tk icon using the freedesktop system tray protocol."""

    def __init__(self, root, image, restore, close):
        import tkinter as tk

        self.root = root
        self.x = c.CDLL("libX11.so.6")
        for name, result, args in [
            ("XOpenDisplay", c.c_void_p, [c.c_char_p]),
            ("XDefaultScreen", c.c_int, [c.c_void_p]),
            ("XInternAtom", c.c_ulong, [c.c_void_p, c.c_char_p, c.c_int]),
            ("XGetSelectionOwner", c.c_ulong, [c.c_void_p, c.c_ulong]),
            (
                "XSendEvent",
                c.c_int,
                [c.c_void_p, c.c_ulong, c.c_int, c.c_long, c.c_void_p],
            ),
            ("XFlush", c.c_int, [c.c_void_p]),
            ("XCloseDisplay", c.c_int, [c.c_void_p]),
        ]:
            fn = getattr(self.x, name)
            fn.argtypes = args
            fn.restype = result
        self.display = self.x.XOpenDisplay(None)
        if not self.display:
            raise OSError("X display unavailable")
        screen = self.x.XDefaultScreen(self.display)
        self.selection = self.x.XInternAtom(
            self.display, f"_NET_SYSTEM_TRAY_S{screen}".encode(), 0
        )
        self.opcode = self.x.XInternAtom(self.display, b"_NET_SYSTEM_TRAY_OPCODE", 0)
        self.manager = 0
        self.win = tk.Toplevel(root, name="tray_icon")
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.geometry("24x24")
        self.icon = image.subsample(4)
        label = tk.Label(self.win, image=self.icon, borderwidth=0, padx=0, pady=0)
        label.pack(fill="both", expand=True)
        label.bind("<Button-1>", lambda _: restore())
        menu = tk.Menu(self.win, tearoff=False)
        menu.add_command(label="打开审校台", command=restore)
        menu.add_command(label="退出", command=close)
        label.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
        self.check()

    def check(self):
        owner = self.x.XGetSelectionOwner(self.display, self.selection)
        if owner and self.manager != owner:
            self.win.deiconify()
            self.win.update_idletasks()

            class Message(c.Structure):
                _fields_ = [
                    ("type", c.c_int),
                    ("serial", c.c_ulong),
                    ("send_event", c.c_int),
                    ("display", c.c_void_p),
                    ("window", c.c_ulong),
                    ("message_type", c.c_ulong),
                    ("format", c.c_int),
                    ("data", c.c_long * 5),
                ]

            # XSendEvent takes the full XEvent union. The data field is five longs for format 32.
            event = (c.c_long * 24)()
            msg = Message.from_buffer(event)
            msg.type = 33
            msg.window = owner
            msg.message_type = self.opcode
            msg.format = 32
            msg.data[2] = int(self.win.tk.call("wm", "frame", self.win), 0)
            self.x.XSendEvent(self.display, owner, 0, 0, c.byref(event))
            self.x.XFlush(self.display)
        elif not owner and self.manager:
            self.win.withdraw()
        self.manager = owner
        self.timer = self.root.after(2500, self.check)

    def stop(self):
        self.root.after_cancel(self.timer)
        self.win.destroy()
        self.x.XCloseDisplay(self.display)


class WindowsTray:
    """Receive Shell_NotifyIcon callbacks on an unmapped Tk window in the UI thread."""

    def __init__(self, root, path, restore, close):
        import tkinter as tk
        from ctypes import wintypes as w

        self.root = root
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.update_idletasks()
        user = c.WinDLL("user32", use_last_error=True)
        shell = c.WinDLL("shell32", use_last_error=True)
        self.user = user
        self.shell = shell

        class GUID(c.Structure):
            _fields_ = [("data", c.c_byte * 16)]

        class Icon(c.Structure):
            _fields_ = [
                ("size", w.DWORD),
                ("hwnd", w.HWND),
                ("id", w.UINT),
                ("flags", w.UINT),
                ("callback", w.UINT),
                ("icon", w.HANDLE),
                ("tip", w.WCHAR * 128),
                ("state", w.DWORD),
                ("state_mask", w.DWORD),
                ("info", w.WCHAR * 256),
                ("version", w.UINT),
                ("title", w.WCHAR * 64),
                ("info_flags", w.DWORD),
                ("guid", GUID),
                ("balloon_icon", w.HANDLE),
            ]

        def signature(lib, name, result, args):
            f = getattr(lib, name)
            f.restype = result
            f.argtypes = args
            return f

        signature(
            user,
            "LoadImageW",
            w.HANDLE,
            [w.HINSTANCE, w.LPCWSTR, w.UINT, c.c_int, c.c_int, w.UINT],
        )
        signature(user, "DestroyIcon", w.BOOL, [w.HANDLE])
        self.setproc = signature(
            user, "SetWindowLongPtrW", c.c_void_p, [w.HWND, c.c_int, c.c_void_p]
        )
        self.callproc = signature(
            user,
            "CallWindowProcW",
            c.c_ssize_t,
            [c.c_void_p, w.HWND, w.UINT, c.c_size_t, c.c_ssize_t],
        )
        self.notify = signature(
            shell, "Shell_NotifyIconW", w.BOOL, [w.DWORD, c.POINTER(Icon)]
        )
        signature(user, "RegisterWindowMessageW", w.UINT, [w.LPCWSTR])
        self.taskbar_created = user.RegisterWindowMessageW("TaskbarCreated")
        hwnd = self.win.winfo_id()
        self.data = Icon()
        self.data.size = c.sizeof(Icon)
        self.data.hwnd = hwnd
        self.data.id = 1
        self.data.flags = 7
        self.data.callback = 0x8001
        self.data.tip = "ReportGen · 订单规格书审校"
        size = user.GetSystemMetrics(49) or 16
        self.data.icon = user.LoadImageW(None, str(path), 1, size, size, 0x10)
        if not self.data.icon:
            raise OSError("Application icon could not be loaded")
        menu = tk.Menu(root, tearoff=False)
        menu.add_command(label="打开审校台", command=restore)
        menu.add_command(label="退出", command=close)

        def dispatch(hwnd, msg, wp, lp):
            if msg == self.data.callback:
                if lp == 0x0202:
                    root.after_idle(restore)
                elif lp == 0x0205:
                    root.after_idle(lambda: menu.tk_popup(*root.winfo_pointerxy()))
                return 0
            if msg == self.taskbar_created:
                self.notify(0, c.byref(self.data))
            return self.callproc(self.previous, hwnd, msg, wp, lp)

        proc = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, c.c_size_t, c.c_ssize_t)
        self.callback = proc(dispatch)
        self.previous = self.setproc(hwnd, -4, c.cast(self.callback, c.c_void_p))
        if not self.previous or not self.notify(0, c.byref(self.data)):
            self.stop()
            raise OSError("Windows notification area unavailable")

    def stop(self):
        self.notify(2, c.byref(self.data))
        if self.previous:
            self.setproc(self.data.hwnd, -4, self.previous)
        self.user.DestroyIcon(self.data.icon)
        self.win.destroy()
