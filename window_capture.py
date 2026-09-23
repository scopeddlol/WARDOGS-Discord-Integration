"""Capture only the WARDOGS process window using Windows Graphics Capture."""
import ctypes
from ctypes import wintypes
import threading
import time

import psutil
from PIL import Image


class CaptureUnavailable(Exception):
    pass


def game_windows():
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            if 'wardogsclient' in psutil.Process(pid.value).name().lower():
                length = user32.GetWindowTextLengthW(hwnd)
                title = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, title, length + 1)
                found.append((hwnd, title.value, bool(user32.IsIconic(hwnd))))
        except psutil.Error:
            pass
        return True

    user32.EnumWindows(visit, 0)
    return found


def game_window(preferred_title=''):
    found = game_windows()
    if preferred_title:
        if preferred_title.startswith('HWND:'):
            found = [item for item in found if str(item[0]) == preferred_title[5:]]
        else:
            found = [item for item in found if item[1] == preferred_title]
    if not found:
        raise CaptureUnavailable('WARDOGS window is not available')
    hwnd, _, minimized = next((item for item in found if not item[2]), found[0])
    if minimized:
        raise CaptureUnavailable('WARDOGS is minimized')
    return hwnd


class GameCapture:
    def __init__(self, preferred_title='', hide_border=False):
        self.preferred_title, self.hide_border = preferred_title, hide_border
        self.lock = threading.Lock()
        self.hwnd = None
        self.capture = self.control = self.frame = None
        self.updated = 0.0

    def close(self):
        with self.lock:
            control = self.control
            self.capture = self.control = self.frame = self.hwnd = None
            self.updated = 0.0
        if control:
            control.stop()

    def read(self, timeout=2.0):
        hwnd = game_window(self.preferred_title)
        with self.lock:
            restart = hwnd != self.hwnd or self.control is None or self.control.is_finished()
        if restart:
            self.close()
            from windows_capture import WindowsCapture
            capture = WindowsCapture(window_hwnd=hwnd, cursor_capture=False, draw_border=not self.hide_border)

            @capture.event
            def on_frame_arrived(frame, _control):
                # The native frame is valid only inside this callback. Copy it here.
                pixels = frame.frame_buffer[:, :, :3][:, :, ::-1].copy()
                image = Image.fromarray(pixels, 'RGB')
                with self.lock:
                    if self.hwnd == hwnd:
                        self.frame, self.updated = image, time.monotonic()

            @capture.event
            def on_closed():
                with self.lock:
                    if self.hwnd == hwnd:
                        self.frame = None

            with self.lock:
                self.hwnd, self.capture = hwnd, capture
            try:
                control = capture.start_free_threaded()
            except Exception as error:
                self.close()
                raise CaptureUnavailable('Window capture could not start') from error
            with self.lock:
                self.control = control
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                if self.frame is not None and time.monotonic() - self.updated < 10:
                    return self.frame.copy()
            time.sleep(0.05)
        raise CaptureUnavailable('No fresh WARDOGS frame')
