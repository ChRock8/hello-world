"""Small Windows helpers (ctypes). Everything is a safe no-op on other systems."""
import ctypes
import ctypes.wintypes
import sys

IS_WINDOWS = sys.platform == "win32"


def init_dpi():
    """Use real pixels everywhere, so the cursor, screenshots and overlay line up
    on screens with Windows scaling (125%, 150%...). Call before creating windows."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def cursor_pos():
    if not IS_WINDOWS:
        return None
    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def foreground_title() -> str:
    if not IS_WINDOWS:
        return ""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000


def make_click_through(tk_window):
    """Mouse clicks pass through the window to the game; it never takes focus
    and stays out of the taskbar / Alt-Tab."""
    if not IS_WINDOWS:
        return
    tk_window.update_idletasks()
    user32 = ctypes.windll.user32
    hwnd = user32.GetParent(tk_window.winfo_id()) or tk_window.winfo_id()
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)


def chime():
    """A short, non-blocking system sound (for upgrades)."""
    if not IS_WINDOWS:
        return
    try:
        import winsound
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass
