"""Verify only this portable's hidden window, without capturing the screen."""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

executable = Path(sys.argv[1]).resolve()
user32 = ctypes.WinDLL("user32", use_last_error=True)
callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0
process = subprocess.Popen([str(executable)], startupinfo=startup, cwd=executable.parent,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           env={key: value for key, value in os.environ.items()
                                if key != "QT_QPA_PLATFORM"})
try:
    deadline = time.monotonic() + 15
    main_window = None
    while time.monotonic() < deadline and process.poll() is None:
        windows = []

        @callback
        def visit(window, _):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
            if owner.value == process.pid:
                text = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(window) + 1)
                user32.GetWindowTextW(window, text, len(text))
                windows.append((window, text.value))
            return True

        user32.EnumWindows(visit, 0)
        exception_window = next((window for window, title in windows
                                 if title == "Unhandled exception in script"), None)
        if exception_window:
            messages = []
            @callback
            def read_exception(control, _):
                text = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(control) + 1)
                user32.GetWindowTextW(control, text, len(text))
                messages.append(text.value)
                return True
            user32.EnumChildWindows(exception_window, read_exception, 0)
            raise RuntimeError("The portable displayed a startup exception: " + " ".join(messages)[-2400:])
        main_window = next((window for window, title in windows if title == "VideoDownloader"), None)
        if main_window:
            break
        time.sleep(0.1)
    if not main_window:
        raise RuntimeError("The portable did not create its application window")
    for size in (0, 1):  # WM_GETICON: native caption and taskbar icon handles.
        if not user32.SendMessageW(main_window, 0x007F, size, 0):
            raise RuntimeError("The portable window is missing a native icon")
    user32.PostMessageW(main_window, 0x0010, 0, 0)  # WM_CLOSE on our own test process only.
    if process.wait(timeout=5) != 0:
        raise RuntimeError("The application did not close cleanly")
    print("Portable GUI startup, native caption/taskbar icons, and clean close: OK")
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=5)
