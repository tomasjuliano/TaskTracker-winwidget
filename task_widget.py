"""
Task Widget - un tracker de tareas para el escritorio de Windows.

- Vive pegado al escritorio: DETRAS de las ventanas normales, no se superpone.
  Al hacerle clic sube; al hacer clic afuera vuelve a bajar.
- Colapsado queda como una barrita SIEMPRE VISIBLE (arriba de todo): siempre
  se puede volver a abrir con doble clic en el título o el botón "–".
- Atajo global  Ctrl + Alt + T  para traerlo al frente desde cualquier lado.
- Icono en la bandeja del sistema: clic izq = mostrar/traer al frente; clic der =
  menú (mostrar/ocultar, opciones, salir). El icono acompaña el tema del widget.
- La ✕ minimiza a la bandeja (configurable en Opciones); "Salir" cierra de verdad.
- Ventana redimensionable (arrastrar la franja fina de abajo).
- Editar: doble clic en el texto o en la fecha de una tarea; clic derecho = menú.
- Botón "⚙" (o clic derecho en la barra): tema, iniciar con Windows, opacidad.
- Todo se guarda en tasks.json, al lado de este archivo.

Requisitos: solo Python 3.8+ (tkinter viene con el instalador de Windows).
Arranque:  pythonw task_widget.py
"""

import base64
import json
import os
import queue
import sys
import tempfile
import threading
import uuid
from datetime import date, datetime
import tkinter as tk
from tkinter import font as tkfont

IS_WIN = sys.platform == "win32"
if IS_WIN:
    import winreg
if IS_WIN:
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.windll.user32

    GWL_EXSTYLE      = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW  = 0x00040000
    HWND_BOTTOM      = 1
    SWP_NOSIZE       = 0x0001
    SWP_NOMOVE       = 0x0002
    SWP_NOACTIVATE   = 0x0010
    GA_ROOT          = 2
    MOD_ALT      = 0x0001
    MOD_CONTROL  = 0x0002
    MOD_NOREPEAT = 0x4000
    WM_HOTKEY    = 0x0312
    WM_QUIT      = 0x0012
    VK_T         = 0x54

    # argtypes correctos: sin esto, en Windows de 64 bits los HWND se truncan
    # a 32 bits y las llamadas fallan en silencio (era el bug del atajo).
    u32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    u32.GetAncestor.restype = wintypes.HWND
    u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u32.SetWindowPos.restype = wintypes.BOOL
    u32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    u32.RegisterHotKey.restype = wintypes.BOOL
    u32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    u32.UnregisterHotKey.restype = wintypes.BOOL
    u32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                wintypes.UINT, wintypes.UINT]
    u32.GetMessageW.restype = ctypes.c_int
    u32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                       ctypes.c_size_t, ctypes.c_ssize_t]
    u32.PostThreadMessageW.restype = wintypes.BOOL
    ctypes.windll.kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    _GWLP = getattr(u32, "GetWindowLongPtrW", u32.GetWindowLongW)
    _SWLP = getattr(u32, "SetWindowLongPtrW", u32.SetWindowLongW)
    _GWLP.argtypes = [wintypes.HWND, ctypes.c_int]
    _GWLP.restype = ctypes.c_ssize_t
    _SWLP.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _SWLP.restype = ctypes.c_ssize_t

    # --- multi-monitor: para no perder la ventana fuera de pantalla ---
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN  = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
    MONITOR_DEFAULTTONEAREST = 2
    u32.GetSystemMetrics.argtypes = [ctypes.c_int]
    u32.GetSystemMetrics.restype = ctypes.c_int

    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT),
                    ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    u32.MonitorFromPoint.argtypes = [_POINT, ctypes.c_ulong]
    u32.MonitorFromPoint.restype = wintypes.HANDLE
    u32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)]
    u32.GetMonitorInfoW.restype = wintypes.BOOL

    # --- estética "liquid glass": acrylic blur + dark mode + esquinas redondeadas ---
    ACCENT_DISABLED                = 0
    ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
    WCA_ACCENT_POLICY              = 19
    DWMWA_USE_IMMERSIVE_DARK_MODE  = 20
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_ROUND                   = 2

    class _ACCENTPOLICY(ctypes.Structure):
        _fields_ = [("AccentState", ctypes.c_uint), ("AccentFlags", ctypes.c_uint),
                    ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_uint)]

    class _WINCOMPATTR(ctypes.Structure):
        _fields_ = [("Attribute", ctypes.c_int),
                    ("Data", ctypes.POINTER(_ACCENTPOLICY)),
                    ("SizeOfData", ctypes.c_size_t)]

    _set_wca = getattr(u32, "SetWindowCompositionAttribute", None)
    if _set_wca:
        _set_wca.argtypes = [wintypes.HWND, ctypes.POINTER(_WINCOMPATTR)]
        _set_wca.restype = wintypes.BOOL
    try:
        _dwm = ctypes.windll.dwmapi
    except OSError:
        _dwm = None

    # --- icono en la bandeja del sistema (Shell_NotifyIcon) ---
    _shell32 = ctypes.windll.shell32
    _k32 = ctypes.windll.kernel32
    NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
    NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
    NIIF_INFO = 0x01
    WM_TRAY, WM_TRAY_SYNC, WM_TRAY_QUIT = 0x8001, 0x8002, 0x8003   # WM_APP + n
    WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x0202, 0x0203, 0x0205
    WM_DESTROY, WM_SETTINGCHANGE = 0x0002, 0x001A
    IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x0010, 0x0040
    TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100
    MF_STRING, MF_SEPARATOR = 0x0000, 0x0800
    HWND_MESSAGE = -3
    WS_POPUP = 0x80000000
    ERROR_ALREADY_EXISTS = 183
    TRAY_CLASS = "TaskTrackerTrayWnd"                    # también lo busca la 2da instancia
    _SINGLE_NAME = r"Local\TaskTracker.SingleInstance"
    _SINGLE_MUTEX = None

    _WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                  ctypes.c_size_t, ctypes.c_ssize_t)

    class _WNDCLASS(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", _WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    class _NID(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                    ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                    ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                    ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                    ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                    ("dwInfoFlags", wintypes.DWORD)]

    _H = ctypes.c_void_p          # cualquier HANDLE/HWND/HINSTANCE (tamaño puntero)
    _k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _k32.GetModuleHandleW.restype = _H
    u32.RegisterClassW.argtypes = [ctypes.c_void_p]
    u32.RegisterClassW.restype = wintypes.ATOM
    u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                    wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, _H, _H, _H, ctypes.c_void_p]
    u32.CreateWindowExW.restype = _H
    u32.DefWindowProcW.argtypes = [_H, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
    u32.DefWindowProcW.restype = ctypes.c_ssize_t
    u32.DestroyWindow.argtypes = [_H]
    u32.LoadImageW.argtypes = [_H, wintypes.LPCWSTR, wintypes.UINT,
                               ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u32.LoadImageW.restype = _H
    u32.CreatePopupMenu.restype = _H
    u32.DestroyMenu.argtypes = [_H]
    u32.AppendMenuW.argtypes = [_H, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
    u32.TrackPopupMenu.argtypes = [_H, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, _H, ctypes.c_void_p]
    u32.TrackPopupMenu.restype = ctypes.c_int
    u32.SetForegroundWindow.argtypes = [_H]
    u32.PostMessageW.argtypes = [_H, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
    u32.GetCursorPos.argtypes = [ctypes.c_void_p]
    _shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]
    _shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u32.FindWindowW.restype = _H
    u32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    u32.RegisterWindowMessageW.restype = wintypes.UINT
    _k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.CreateMutexW.restype = _H
    try:
        _shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
        _shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
    except AttributeError:
        pass

    WM_SHOW = u32.RegisterWindowMessageW("TaskTracker.ShowWindow")   # id único por sesión


def single_instance_or_exit():
    """Si ya hay otra instancia: le avisa que se muestre y termina esta."""
    global _SINGLE_MUTEX
    if not IS_WIN:
        return
    _SINGLE_MUTEX = _k32.CreateMutexW(None, False, _SINGLE_NAME)   # se mantiene viva
    if _k32.GetLastError() != ERROR_ALREADY_EXISTS:
        return
    import time as _t
    for _ in range(25):                       # la ventana del tray tarda un toque en existir
        hwnd = u32.FindWindowW(TRAY_CLASS, None)
        if hwnd:
            u32.PostMessageW(hwnd, WM_SHOW, 0, 0)
            break
        _t.sleep(0.1)
    sys.exit(0)


def win_acrylic(hwnd, gradient_abgr, enabled=True):
    """Aplica (o quita) el blur acrylic de Windows detrás de la ventana."""
    if not (IS_WIN and _set_wca and hwnd) or os.environ.get("TW_NOACRYLIC"):
        return
    state = ACCENT_ENABLE_ACRYLICBLURBEHIND if enabled else ACCENT_DISABLED
    pol = _ACCENTPOLICY(state, 0, gradient_abgr & 0xFFFFFFFF, 0)
    data = _WINCOMPATTR(WCA_ACCENT_POLICY, ctypes.pointer(pol), ctypes.sizeof(pol))
    try:
        _set_wca(hwnd, ctypes.byref(data))
    except OSError:
        pass


def win_dwm_flags(hwnd, dark):
    """Modo oscuro del marco + esquinas redondeadas (Win11; en Win10 se ignora)."""
    if not (IS_WIN and _dwm and hwnd):
        return
    for attr, val in ((DWMWA_USE_IMMERSIVE_DARK_MODE, 1 if dark else 0),
                      (DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)):
        try:
            v = ctypes.c_int(val)
            _dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
        except OSError:
            pass


def win_register_app_id(icon_path=None):
    """AUMID explícito del proceso. Sin esto, los globos del tray se muestran
    como el globo viejo y se pierden; con un AUMID registrado pasan a ser
    toasts que quedan en el Centro de notificaciones (Win+N), con nombre e
    icono propios. Solo escribe en HKCU (sin admin, sin accesos directos)."""
    if not IS_WIN:
        return
    try:
        _shell32.SetCurrentProcessExplicitAppUserModelID(APP_AUMID)
    except (OSError, AttributeError):
        pass
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              r"Software\Classes\AppUserModelId\%s" % APP_AUMID) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            if icon_path and os.path.exists(icon_path):
                winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, icon_path)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
#  Icono en la bandeja del sistema (tray)  —  Shell_NotifyIcon vía ctypes.
#  Iconos: variante clara para barra oscura y viceversa (assets/tray_*.ico,
#  embebidos en base64). Corre en su propio hilo con una ventana top-level oculta
#  las acciones vuelven al hilo principal por una cola.
# --------------------------------------------------------------------------- #

_TRAY_ICO_B64 = {
    "light": (
        'AAABAAQAEBAAAAAAIADZAQAARgAAABgYAAAAACAACQMAAB8CAAAgIAAAAAAgACYEAAAoBQAAMDAAAAAAIADYBgAATgkAAIlQTkcN'
        'ChoKAAAADUlIRFIAAAAQAAAAEAgGAAAAH/P/YQAAAaBJREFUeJytUTsvBGEUPbOzsw/vt4JoFRqR0AiFZCkkKh0dHYJK4gcoEUEn'
        'QRQKUeiQKG2sZrOFaFhE4rWKfdnXfPfKN3bGe5A4ySnmzjln7twD/AfC4bBHCLFERFFiZlsSRaVWeqwAXdeXBRH/hVldX5ZeBYBD'
        'CIoCKPrL1gwknKqj1AlAZeYfzbE0QAyUea2R9KiOfJot42lG36KC0XXdCDHnEg4jgL8nEWNqCwhdCjSV3YOZrXdvAtjiWYSw4mfo'
        'gozntUPGZkBFe9UlRnorXv4/r5VwmhuY2PFHMHtUi9AVYaCVML2toYavsDBUjgKv+53WbEFLZXJZc3D7EMfg7AVOcs1QZcXRCDaG'
        'E+hqq4eiSPkrvG7N9ekGNZXFWB1rQCMHkHx8xGTHNTpb6oxvfbyPtUEylbU2MFu5uYvhIHCOfl8TPB7ty2oLvS6XERB/yqYV5eWg'
        'vwUzqLjA5ZEmTqYyAbsqv6L0SK8MEMfB0/FYInMr8tXZUWqk1h88HZde86zOiem56u4en0/T1BK71XM5Edvb3d+fn5l8kCU9AzzC'
        'aog5bOsiAAAAAElFTkSuQmCCiVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAC0ElEQVR4nLVUS0hUURj+zr13nJnU'
        'UbOcEbExTcugIgiCSqFcZgYRQYtoFRgVQW2CVtXGhUitAmsZRQs3JqNILyGFonCREZjmg1DH0kavOq9zzx/nzsMZZzSHpm/4Ocx5'
        'fN/9/+8/B/jPYGsniOgoABlbMuRaAdDPGOtPu+rz+YqIqFsIon8JIuqWXCmZcC56hBCUjeBc9CRVR9f1esMQlM3Qdb1ecitSSdNy'
        '6kjWP4uhaVqd5DYFOOd2UHQpSyOXnDEBgwQzp+V6BuP774TzjxgGJyhl3SDTA6ZFXJA6mcG7QGh+omDqN0P11jAOlFvAWGLXRzgj'
        'AiKa2SbBDcKVpww/5hmCyzpq8hdB5EreJLAqICAQSfLvICK0eBj6hhXwEEejexInD7vNpkzkkJyreZgnkyMYIlx6xnDXAxhGrLhA'
        '7xBw/7UKgwNu+op7F5zIz7OltlEUUQ+S5kwMjS3i5RcHDGiYXzLQeoYw5ZOl0UAcsOrDeHDNgTKXA2Bs3fwTPEjeUl6soWB2AL+K'
        'jqDjo4Zw2MDIjALfEoNYnMad0wEcqt0BVVVSzkY4abVE0oG1KHTY0H7VjeKfbxEKcTz/oOLTmALyr+DcnhGcbaiE1RYvQCp/dIx7'
        'YPZwQsgv21/jQvv1XSiZ6wWFOcAJNeoAbl/ci7xca8qZxIhhwwugWVRT5PHNWjjnOpA704G25ko4t+Wv6fkNOMx00ngQg0WK7C6F'
        'p/UEhBBwbS+AorB198dLlHQPRDoXkjMpKy2M/9/MjZGc8RItLIWms/qUUpQzKkCevv6ulUDYL29iNn7LgbBfckpu88UDkPNucOxy'
        'tbukzW7VNuce0sMf5PRtYvbGsYM7HwIIxchUwGnrevPqVFWF85bdbt3HMnxiCRB+f/Dz6Li3pfF4wwvAGwBgJH6tClRYgGJrU1Nj'
        'blWV05aJwOioN9DZ2bUMzAWB8bAkl/N/ABq6j34Fd1aYAAAAAElFTkSuQmCCiVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABz'
        'enr0AAAD7UlEQVR4nO2WT2hcVRTGf+++N+lMMonSNrTYsUlDsTELSWOUikq7EHeKlrqQ6iraFlsCUhRxpRvR6sYKxZVuYl20pWCQ'
        'FtFFxYV/SA1qQhNrTJhIkhqIRicz8/7cI/dlXiZpZjL50+nK73G4d3jvne+7535z7oP/cRNEJB4EwUmtdZ+I5GTjyJlcJqfJzUrI'
        'ZrNNWusBrUWqE3rAcJQkT6fTiXlyLVWOAcMV8arCaDU2Np4QaBOzDdWNNsNlOBcLULYde7bazFGEXAVuqyAg5vtBBsuKcTsg4jmO'
        'XQd4TkGEwiI2L/E2IOQKK2AVBKSU3Cpuge9GwVbQuVPAiop8M1IKxq3IA7eGW4RzfZqDZxRPnlZ8O6IrvqMWCd/YKDA8Kbx+0UE0'
        '5APoG55Dayn5fASnKH9jImazAcd6bP7NghuAPzNB61YLkWQorpwIpzhdvwnMKl+7YDMwofADCOZmeX7vNHt3NxcsUD63s0C/An+4'
        'whwkN4FtLd/3j76B81cVQQDie7TXDXHyUDNJ80KF3Go1q3vzMnScsuk+Z5H3lma7Oia80euE5Ggh+dePvNu1ne1b63Fse20mlBLh'
        'ej6X+l0kgN6fFUc/VeRcHd6byWiO9DhkXUMO/o1B3jqcZE/TFmI1zooNcXkFpHT4viZ+ox/P80J3fzWoQrPN5QKOn1WM/WmB2fe/'
        'J3nxoRkef3AHtbU1WKa9rEKBKvKXvhxH8cpTm5Ffv0RcL1zp5UHFI6ccvvjFDn9Lfo59m3+i+5lW7rwjERpPKlyr9kAsZvPwfXfx'
        '/pEU8tslXNfF9yE9rUJyfGHLP1d4++i9NG5OYpsWuAaohQpI6TCdOpmMc6CzidPHmrBHPgPPLZCDnviad7pStKTMvttl8yzPu8oK'
        'GChl0VCf4EDnLj44vhtn9AL+7AT5ie/pfizPox07SSTM+VKu75eHiiaV9sycGvUNcfY/0MKHL7fRrj6na98kXQc7qK+Ph9yVcpTy'
        'gDUvIrUpkx2ZW41iLUIu55HJ5ok5NsnaeGjUtaIu0VIL43lncWKr7NFZhHkmkagJo1i9tcF0zwgqmriezizJVsVxgYsFAeOSyeZ/'
        'CB0a/SOqOBouwxkJMBN9fWzqY9N2q/1F6voBhmu+eSPRpjuwJ9E/fOWTu7c1PFHjVD5E1gNDnp6a7W2/Z/9hGMqaThJ5QMOQ++qJ'
        '9164np45Oz2bI+cFoTE3umbzQWRymZwmt+EwXIUKsNj2ZtkxaI/3XDxzf/OuHYccx25VyirafR3QWlzfD66N/v7H+eeefqkP+nPm'
        'c5zwCFsqoNATjJBtMUg5kFAQrL29LYEtkNUw7sNURBzuv7n7H1L9tcuZKKmtAAAAAElFTkSuQmCCiVBORw0KGgoAAAANSUhEUgAA'
        'ADAAAAAwCAYAAABXAvmHAAAGn0lEQVR4nO1aW2xURRj+5lz20t3ttkBbUkAQr0VJxMRqlBgfEEU0UbCgiMRokBAiUaI+GGLiBRIf'
        'NPGJxAcwKKgIRYgRRU28IAUMFEMUVMTa0lIpLGy7t3OZGfOf7m7PQgs9va4JX/JnunvOnvm++b/5Z+akwBVcwaDALnVRSsk45/cz'
        'xp5QFOVOABMB6BheWABOCiH2Sik3qar6JWNMen6KYRjThJT7hJBSSClHsd1HXLxkgGUsa5ZP1bYDCKE4kDRN+5FAQP+GjHEpAcww'
        'jBpd1w8UEfkckpZl1fr9/qNuEUr+MsDq6uoUXdfXFyF5QkjV9fXE0T3w7gwoyWRyTiAY/BxFjEw6/WAoFNoFQLgzQEKYrvsXOckp'
        '4tCJY5avW4Dzt6IwKpVFDaWbo3KhhegL3eYiAUBDccPWVCWcXS9EbkJQKP8D8shyzPPOEWZANYP0vuANFrKHgAdUM6DN+YlrxPkA'
        '1uvB4XxK4oN93dQX3yFRXtJfGTx/46hZJpnhWPCehl9bmZOGr45IfLbChqapnp7jrkIjBm5zrN6p5MlLAextYjjbadMG0tOzCjIw'
        'ElNACIGth4AtP6sOeSEAQwA8lUAqxSGiPihKkWaARvfYKYnVOzRnHbWy5KXNEU2eQCjg3OXpmSMoQCKe4li+SUMqwxziNic/SWRa'
        'j+HFhwPQFG/+v9hCHtV7AbcFXvxUxV+nGTI06rSTkYDZ0YTHb8tgbu04BAIaGGOeeBRWITl8vt/wE/DFERUG9UEjT00ihhvCLXh+'
        '3lSMKQ3B51M989AG6uV9TcAnhxVMikosu0si7Gd93tv4j8SaL3yObZw9JFUey4A/dhhrX56M8WMjCIVo8np3tGcBRKj1nMAzH/tg'
        'OLsR4GCzwLqFHNFgIQEayHMJgWWbdXSZPeQhJIzm/XjjqXGYNqUMkXAAqjqw6Vjwq/7saIWQONRs58kLCfx4QsHSzSriKVFwr2lx'
        'rPhYRdMZ5iIPGKeOYPFMhvtrq1BWWgKdrON4v38c+hTQH3Ah0dneBjuZoAICO2uLBhKxSUUniZASggu8+62Cr3/trveOAKo8509i'
        'xthmrHz0aoyNhhDwd0/cgeLinNNqdqkWEtdW+xFr3AUzlewhx4GG4wqWblQRTwr88IfE27u1nuu0aGWSCMf3Ys2yGlSWR1BSQr5n'
        '/evX3fYlgMqXvExLozVlfBgv1VUjfnAHeDrRYw+y03EFSzaoeO4jHZyqTV6ggPnP13jzmetwTXUZwmE/VE25bH+9tX1noB8gAaES'
        'Hx6bNRWr5lcj3rgNPN3lkDR59+ra8JeK9jgryE6mZQ+evS+Mu2+tRpR8r3tftHqDZwGU8kBAR0V5BIvnXI9V8yYh3rgFmXQXDXLe'
        '6zniFFbsGO6c0IqlD9dgrFPvB+f7vi0k+xdUr6luV46J4IkHbsQLdVch9csmyExnQbWh4OmzqEh+j9eW16KiLIxgie4MQn/7kr1E'
        'nwK8gOp2KORH1ZgIFs+9CS/UXY3MLxt7RNB2gdvgf9djzYpaTK4qR4h8rw6NdYbkQJMTUUknqrnTnaF/56P34Zt0L6AFYbTucSxW'
        'e/MEREuD0D0eVgawmfMORaVJ7Uel7BahMIZ3P6xHxrCxcE4NnnxoOsqj2X1OdrEaSrBsqECVP5luodcqAwLnEsmkgY7zXTh1phOG'
        'YWPi+DJUjSlFxLHO0O3cQ8FJYeBfg7odsjOxqjKEI34EgzomVJU5I60pikPcWayGCZr7gzPDB9EXlUZNV6FRQt3PxdBBXqoK2bRx'
        'L3LYvJBjgQDD4O2j/fIWlwnT5O19CFBlPJE+iCLHOYejKi8UIIE22dIWq0+b9oA2WCPRpk0brW2xeuKam1okIKdGrl711s7TseSf'
        'wjlxZ3UVSSukBHEjju4LrgxANDR8bvx+tHll+9mURSev0fY7skFciBNxI46uw2m+aOZer+vA7b7dezYuqJ44bl1lNKgFcm8KRgkZ'
        'k+N0PG23nTyzfPbMJVuA/XS6zh5oCzNAwYEWe/bMZVt/O9q04GRHoqU9lkIibcHidFQcfsJSwumL+jwVS4E4EBfiRNyym/T8HHAv'
        'W7ks0LZCB2r0e+bUhl959elF5dHS+bpPvwWADyMD0zKtw+findvWvr5+83e7DiSAoxbwr5UVcJGFehFBcYMGVGiAps6YMdX3yMLZ'
        'FYpPG9Z/NRCmbW3/ZHdHY+MJs/vlY4cN/J4b+QLyvQlwi8iFCkxTgAgFA+xsDAc02R1dFAL4LXeuc5/zCoz8H0+BlXndF1P8AAAA'
        'AElFTkSuQmCC'
    ),
    "dark": (
        'AAABAAQAEBAAAAAAIADrAQAARgAAABgYAAAAACAADgMAADECAAAgIAAAAAAgACkEAAA/BQAAMDAAAAAAIADrBgAAaAkAAIlQTkcN'
        'ChoKAAAADUlIRFIAAAAQAAAAEAgGAAAAH/P/YQAAAbJJREFUeJyVkz9oFFEQxn/v3e55uT+rSTgSRFGDXQrTC4KFELAI2HhqZ6GB'
        'CDb2Kv4BIU1KIY2I2KiFWJnOgLZWliEECReXKLnbYG5P38js7uU4c+biB1+xw3zfzOzMM3RhMh4EkpFEUK1Wy5XKyLwxXAGCAeKG'
        'CC+bze93wjCMLOCVSocXQG6KSCAiDGCguakGTw2OALUDCHsIUlOtB4yCFNPgv1EuWqyFRuQ6oaJqLVAYVK2QF14tBDycs391QUEN'
        'cE725aPbQ0yM/eTd+xDn3G5cYZOdiNvlyeM+1y8PY41WcVy96HHpPCy+qPP201BWPc1VeKlBd/6p07+4e2uYyVO/efZmi/uzOZY/'
        'hjx+7pHL5Xpy+xq8XoqYPPGFG9fGmDmbJ9zYYu5JjKOsiXt+rtc1kOyufO49bRHvrFKbPsTsg22+NQKs7Yg7eem3Ac6Mjx/9vOdW'
        'XYtjIy3WNktJ6/1Qr69PJR0458QY0/sOTJ6vP/LJ7vvdiGRB3cJOHLdW/vcSVaNaNdiMou3FOI6jdMeDqbmqUa22rWNMABd83z8n'
        'IpV9nrWO2my32x+AJWDlD651cNI/WrV/AAAAAElFTkSuQmCCiVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAC1UlE'
        'QVR4nLWWzUsUYRzHv88zL7tOq7toqSwIQgZBQYegojqUtf0H0smIoEsdCgIPJV6ChN7A8BJkGVJ0yA6eioguFVjhoUsRG0iCqCmt'
        '7rY7M88888RvZteXZX1r7QcPzDzP8Pn+XmcG+M/Gyq55a2vbUc75YcaYtRmQUirv+/6H8fH0OwA+bS0X4I2NjTtiscQQYyxVjcdK'
        'qde5XKZzZmbmFwnxokg0Fqt7CiCllEI1C0DKsgJWlNgkYCSTLSmAtYdRVb84Z+0hEwYJRBljx6v1XJUtYhJbB1CjlEqE0W2dKaUS'
        'xKYITKWk+S9e7t+jYbC3FnvbWIVzaRKbImC+T4XeXAgNCYb+7lo010t8HJP48j1Iy+J5yAQjgaBtix2wIWNM4d7VOJrrPWRmF/D2'
        'fQZK1ZU9RaMABAK+j00JdJ2L4sg+QBQKuHV/GmM/6mCaKxnEJKMaBFaeQ10HHt5uRc+lpsDj0n77QQ0XTxuAtPF8ZAqPXtVA141K'
        '87AUAeW/PIKmhMSxAxHoh3TELRdXeufQ3MDQ1xUBpIPRT3PoeUAu0jxVyoBaEqiUnZ9TAoMDYzh7Zhc6TpmAZ2Fn0kfcEpiYyOLy'
        'HRtZJw5dX0zCSnyRuWqRfaXh+oANIb7ifGcLOk4yQEr8ydq41jeP9BTlna9Ru3WKzBiHLS3ceJyHEOO40NkADQL9Q7/x8rMFXdeL'
        'XlYWKBV51RqQcc7h+jW4+SSP7MIkarcB/S8i4BrN0Hqdt6wGyzcqikgLd4e14F7TTWgazdDG2rpY5LUHjXMGbobdsr7npWeWaqAc'
        'x80YRhj2VpnjuBliU4+5jlMY9TxPkGNbsTzPE8QkNgkUpJTpXC47IqVX9cdGSg8hS6aJTSmyAUy4rvNsft4X0WjkhGEY28t+CDZi'
        'Sggxa9vOGynFMDGJHbxS6cMAIAlgN4A2elMAoL+K0vma4OLKA5gGQJ5/AzBJEfwFJhw1EzhR/JEAAAAASUVORK5CYIKJUE5HDQoa'
        'CgAAAA1JSERSAAAAIAAAACAIBgAAAHN6evQAAAPwSURBVHicxZddaBxVFMd/c+djZzebtItpKmlLEa3RYhEEpS9CoX0QfEjRB+tb'
        '8UmEPqgvIgqaqlUEpYhVY9FIBJEgRB+Eog9qQPQltaWNET8KqQmx3Xy02d3MzmTuyJnM1BTdzW43iQcOe+fr/v/nnP89ey/8z2bU'
        'uK+SZ7WeN2tR4roeAUO8s7OzraPjpieUMh6BaDcYmRaxq2CMaR19evXqzIlisVheQYiUgPya3d3dt7puftgwjDtaA61BJYrGPa90'
        'cGpq6ncglFtpms18Pl/o6uoeAXpYX/vl0qWp+0ul0pyQSGvtFgpbjmwAuFhPguUKthCwgHal1MNRFLERLliCKdgC7gCblDJuT3Sx'
        '7raMxSZgQQjYchFFcSY2yqyEwF8pgdxaRR9FcO8emzCMGB1bwqjdSXKCLQREB7bUZi2sd7/L8Wc7QAccPDLPT+M155XAVboKlOC3'
        '6rdsMzj2ZBuEQezbC14ivH+/m3Zba0XyWoo860a8+0KBnBPG0f/x62V+PBsQRXa9MnCNQCslkE9feypPz07p9j5zMyWO9c8zUSzg'
        'OPWDU40CdLSb/xmJED/c69C7z4LQx/c83v94ms9/yGNZVt3oryNQu3FoXny6m3Nf7ebE0W1Y5vXP9+xSPPe4G0cehT5ffDnNW8Mu'
        'ppWRhlNz3oYzEIaa/XuduK4P7svS/3IXtrX8Z5bPRrzzfJaMEtH5jJ4u8spHEb52MU2zkeSyaga0Dhn+7DyB58VRHthr09+3GVNp'
        'jj/jsnOrjslNTpbpe2+RiZkclmWvktWocREahsHbQx6b287w6KFdOKbmwH0mIwPt7EjAKyWPNz6cZWSsjUzGaUrUarUXDEMxV87S'
        'd9JncHAc36uCrrKjK4zXehRWGRiaZfBrF8eRuje3ibLSQT3GktIrXo6XBsoESxd47NDNONbyej/1zTxvDilQbiK6eLbmCVDnI1lK'
        'tm2zUM3x6mCFpWCShx7oYOJihaMnA2bL7ThOKrroRjPAKmbEmRASr39S4fvTRabnTc5flLqL6IwG5qhDgAaYiyAlE5WlPKfO5uLr'
        'TMZM6n5jndS6Bt8EfVnjK9d5K23cSvfrYairSqkWt+CNmda6mpwRIpUMAt/3L/yzXV9fX8YiEGwhsARUFhdL32mtW94TrOaCIViC'
        'KdhCwAeuBEHwbaVSHpPWu16Ry9yCIViCKdhWSgD4s1Ipf6B1eNh1s3cpJepWa1XzGNzzFs95njcgWCkBI2nHskHcCtwG3KmUuse2'
        '7btN0+wU0beIH4ZhWAyC4IzWehT4GfhNdsRShrRxSyaExBZge+IylsPDcpdp/qSc5l7EtgBcTiIXl3Gsgb8BPuLL5MUhRGcAAAAA'
        'SUVORK5CYIKJUE5HDQoaCgAAAA1JSERSAAAAMAAAADAIBgAAAFcC+YcAAAaySURBVHic1VprbBRVFP7uPLu7bdEIkoZCg0AkQVBA'
        'I2L8o4ixPzT8ICqNJkQT/qg/NDHGmJiQKPGPJpKYEE2jPMSIokjDy2iJGAWhEiAgJEDti1dLS9t9zHTm3mvOzJ3tthS77XbL+iU3'
        'uzudvfude75zz5l7CvzPwSb4vomGLIQYyxkEbdj9rIhkJQCR8z4aI5Ic6RpThPXZs+c+pWnGCwCWMYYZAEwUF56U6ADEYSHE9ubm'
        '8/sBcGXQTYYMNyBLvKamZoGu25sYYw/hNkJKeZRzd11LS8vpYYZkCee+1wEYM2fOXmma1leMIYESgJRIed7Amra25gMAfGWIzDUg'
        'Im9WV1cvsqzYL4yxOEoIUsp0KpV5/OrV9pMks8gII0c2pO24ZcU+BVhcjhr/kw0WTySIG1YCSEeBruWsvl1VNaMWYEtQsmBLQo6w'
        'FWdm5K6+adqrZekt/RCYprUawM9KRoEHaFgAyjVNW4oSh6bpxLFccdaMSD7hRTkdJQ85XRnQB8DJNSABML3EFQTiGHIN4yAygNwR'
        'y6P0KBXEFOesAYayaNJAnq4sZ6h7Jg4mBbbuzqA/lffXiWvAPcoDgRGTJx8Jy5TY/tE0LJijAZLjyWU6nn2tD5pGe8qoMHK30Zzi'
        'bXIsEEJg/etTsGAOA6RPF7B4PlAe50hlAMZGLXSj/BUYgOjDZHiA8syqFWV4vrYMEDxYfRo3upLgngcpaWFHRbbMN4ZNXxzW0exS'
        'Ys4sDRveqACED0gRvPoDHhobO3AjeScsS2J0BwximAHFA3k3ZgOfrZ+CuE3EaeV9SMFx7EgbNu02AumMhfxNBhSzjCDdf/x2JeZW'
        'M7X6oQfOnu5E/Q8ejp6vgG3rY+aQV8jfGvn9GJFau6oMtY9ZijgFLse1K0l8v68HOw/HYRhmsAPlEcD/5YH8iT+ytAJ1q+5Ca7uD'
        'jV9cRca59b0L52l4d10ckF42cJ2Mh70HruDz/TEwzYKuhxIaqwjGFcR3TzWw5ZN7YBsSkAksWWDh5bdagy1wOMpjEpveq4Bt8Cx5'
        'KXw0Nl7GpgYDvZkyWFa4+mPhMG4JkZbvm2fCNoSSA8ejS2zUf1iFBCX4HDAIbHwngZnTRY50fDQ1dWPzHo4zbWUwzfFJZ0QDSKv5'
        'jCvtXejrSQYJKArI5Yst1G+YikSM7hGBoa+usbFiWZhpg/sER0tLCl839GHf8Rgsy6LyWEknv98eHuRj9gBNcPGSwHfb/kR/Lxmh'
        'pCF8LH/AQP37UxAvk1i2SMObL1mKeOipZL+LHQ2d2HYwDl0Pda9phR0vjTkGyNM9SR1b9wtw/heeW7MQFRV6Vt/L7zew5YMK1FRJ'
        '6ExlWiEguIddezvx5U82XG4VpPsCdyEWuL3pQhkg0/D5Saypm4/Kcj2bWR9eqCZTdQ69Nv7Wgy37JNq6LNj2IHlZYOoZcyYmD+i6'
        'Ts+mOHZBQsgMOP8bL9bNQWV5pPfBGofInzmXwraGDH4/m4BtR7ovjHhBmZiCjvRrmhJNFxAY4fPzWFs3K6jxQ+KhN653D2Dzzj7s'
        'OhILjB6630sUinHXQhR8lD0Jxy+SUsiIFrxSV4Up9MQqBXzPx9ad3dhxyIJkFkzDHPd2eSsUVI0SGcMIpzjxj4QQDiS/hKefCAu2'
        'g3+k8E2jhutJWwVtVKxNXM1lDKE/jnkZ05ScgFOtgPjVQWf3dRg6ecbAqdZ4zo4z9lJhNEzI80Aop/Bs4HQ7cK7DgKlLpD0zSFYU'
        '9KF0Jr7aNSZqIvIElQUkqSBjBkd9JJncHsnEw7h5Fyrkx0LCI8XpxElHjmhA0PkQQkit0NxeZAghhrScjJwPwvP8Xsuy7kAJw/P8'
        '3tx2k6beULPA832veWhPrfSGH3AcbHBo6g21bQZc120SVAaUKITgII7ENWo1kYS4upDxPPeo4zjPxmLxaShBOI7TSRyJq+LMIw+4'
        'AOhksieTSX/rug4VMygdSBAn4kYcFVd3uAFJ+iPn/EQq5fzoOI6gp6po+7tdr0IIWnlBnIibMiAZGWCoiB5QF7vpOZxz91A67Q8I'
        'IWoNQ6/QNHpyGmzUF5+0DIgLOrXzeb/jZPZwzo8AuKo4JhVnERngqc5ftzp3NznnSKWSHbZtP6jr+r2apk9jrNBzpPwgA/68k3N+'
        'znXdYwDa1biiOKajHlmUB0hGdLLTr46toaI87boufeGI6opUqoZgMeoDqQYRo/YR6Zz2/C4A1wBcBtCpOBLXbJ84+seKgLCaLNqZ'
        '6GYygIhT4ztqLBTLExEP0jdxIUNI88SBBvGh63RPkMz+BSVkxt+YqKOGAAAAAElFTkSuQmCC'
    ),
}


def _tray_ico_file(name):
    """Escribe el .ico embebido a %TEMP% y devuelve la ruta (o None)."""
    try:
        p = os.path.join(tempfile.gettempdir(), f"tasktracker_tray_{name}.ico")
        if not os.path.exists(p):
            with open(p, "wb") as fh:
                fh.write(base64.b64decode(_TRAY_ICO_B64[name]))
        return p
    except OSError:
        return None


class Tray:
    """Icono de bandeja. Clic izq = mostrar/traer al frente; clic der = menú."""

    MENU = ((1, "Mostrar / ocultar"), (2, "Opciones"), (0, None), (3, "Salir"))
    ACTIONS = {1: "toggle", 2: "options", 3: "quit"}

    def __init__(self):
        self.queue = queue.Queue()
        self._hwnd = None
        self._tip = "Tareas"
        self._dark = True
        self._icons = {}
        self._nid = None
        self._proc = None            # ref viva del callback (si no, lo barre el GC)
        self._balloon = None
        self.ok = False
        threading.Thread(target=self._run, daemon=True).start()

    # -- API desde el hilo principal --
    def update(self, tip, dark):
        self._tip = (tip or "Tareas")[:127]
        self._dark = bool(dark)
        if self._hwnd:
            u32.PostMessageW(self._hwnd, WM_TRAY_SYNC, 0, 0)

    def balloon(self, title, msg):
        self._balloon = (title[:63], msg[:255])
        if self._hwnd:
            u32.PostMessageW(self._hwnd, WM_TRAY_SYNC, 0, 0)

    def stop(self):
        if self._hwnd:
            u32.PostMessageW(self._hwnd, WM_TRAY_QUIT, 0, 0)

    # -- interno (hilo del tray) --
    def _icon(self):
        want = "dark" if self._dark else "light"        # el icono acompaña al tema del widget
        h = self._icons.get(want)
        if not h:
            path = _tray_ico_file(want)
            if path:
                h = u32.LoadImageW(None, path, IMAGE_ICON, 0, 0,
                                   LR_LOADFROMFILE | LR_DEFAULTSIZE)
            self._icons[want] = h
        return h or 0

    def _run(self):
        try:
            hinst = _k32.GetModuleHandleW(None)
            self._proc = _WNDPROC(self._wndproc)
            wc = _WNDCLASS()
            wc.lpfnWndProc = self._proc
            wc.hInstance = hinst
            wc.lpszClassName = TRAY_CLASS
            if not u32.RegisterClassW(ctypes.byref(wc)):
                return
            # ventana top-level oculta (no message-only) para que FindWindow la vea
            self._hwnd = u32.CreateWindowExW(WS_EX_TOOLWINDOW, wc.lpszClassName, APP_NAME,
                                             WS_POPUP, -10000, -10000, 0, 0,
                                             None, None, hinst, None)
            if not self._hwnd:
                return
            nid = _NID()
            nid.cbSize = ctypes.sizeof(_NID)
            nid.hWnd = self._hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_TRAY
            nid.hIcon = self._icon()
            nid.szTip = self._tip
            self._nid = nid
            if not _shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                return
            self.ok = True
            msg = wintypes.MSG()
            while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                u32.TranslateMessage(ctypes.byref(msg))
                u32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:                       # el tray no debe tumbar la app
            print("Tray:", exc)
        finally:
            if self._nid:
                _shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))

    def _wndproc(self, hwnd, msg, wp, lp):
        if msg == WM_TRAY:
            ev = lp & 0xFFFF
            if ev in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self.queue.put("show")
            elif ev == WM_RBUTTONUP:
                self._popup()
            return 0
        if msg == WM_SHOW:                     # 2da instancia pidió mostrar
            self.queue.put("show")
            return 0
        if msg == WM_TRAY_SYNC:
            if self._nid:
                self._nid.uFlags = NIF_ICON | NIF_TIP
                self._nid.hIcon = self._icon()
                self._nid.szTip = self._tip
                if self._balloon:
                    self._nid.uFlags |= NIF_INFO
                    self._nid.szInfoTitle, self._nid.szInfo = self._balloon
                    self._nid.dwInfoFlags = NIIF_INFO
                    self._balloon = None
                _shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))
            return 0
        if msg == WM_TRAY_QUIT:
            u32.DestroyWindow(hwnd)
            return 0
        if msg == WM_SETTINGCHANGE:
            try:
                s = ctypes.wstring_at(lp) if lp else ""
            except (ValueError, OSError):
                s = ""
            if s == "ImmersiveColorSet":
                self.queue.put("wintheme")
            return 0
        if msg == WM_DESTROY:
            u32.PostQuitMessage(0)
            return 0
        return u32.DefWindowProcW(hwnd, msg, wp, lp)

    def _popup(self):
        menu = u32.CreatePopupMenu()
        for cid, label in self.MENU:
            if label is None:
                u32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            else:
                u32.AppendMenuW(menu, MF_STRING, cid, label)
        pt = wintypes.POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        u32.SetForegroundWindow(self._hwnd)
        cmd = u32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                 pt.x, pt.y, 0, self._hwnd, None)
        u32.PostMessageW(self._hwnd, 0, 0, 0)          # workaround MSDN
        u32.DestroyMenu(menu)
        act = self.ACTIONS.get(cmd)
        if act:
            self.queue.put(act)


APP_NAME = "TaskTracker"       # nombre para Windows (título, tray, Alt+Tab)
APP_AUMID = "Tomasjuliano.TaskTracker"   # id para los toasts (Centro de notificaciones)

# --------------------------------------------------------------------------- #
#  Persistencia
# --------------------------------------------------------------------------- #

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
DATA_FILE = os.path.join(APP_DIR, "tasks.json")

DEFAULT_STATE = {
    "window": {"x": None, "y": None, "w": 310, "h": 340, "collapsed": False,
               "sized": False, "theme": "auto", "dim_opacity": None,
               "close_to_tray": True, "tray_hint_shown": False,
               "always_on_top": False, "due_alerts": True},
    "tasks": [],
}


def load_state():
    try:
        with open(DATA_FILE, "r", encoding="utf-8-sig") as fh:   # tolera BOM de editores
            data = json.load(fh)
        state = {**DEFAULT_STATE, **data}
        state["window"] = {**DEFAULT_STATE["window"], **data.get("window", {})}
        state["tasks"] = data.get("tasks", [])
        return state
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_STATE))


def save_state(state):
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except OSError as exc:
        print("No se pudo guardar:", exc)


# --------------------------------------------------------------------------- #
#  Iniciar con Windows (clave Run del usuario actual, sin permisos de admin)
# --------------------------------------------------------------------------- #

RUN_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "TaskTrackerWidget"


def _startup_command():
    """Comando que Windows ejecuta al iniciar sesión."""
    if getattr(sys, "frozen", False):            # ejecutable de PyInstaller
        return f'"{sys.executable}"'
    # corriendo como script: preferir pythonw.exe (sin consola)
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    launcher = pyw if os.path.exists(pyw) else sys.executable
    return f'"{launcher}" "{os.path.abspath(__file__)}"'


def autostart_enabled():
    if not IS_WIN:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_autostart(enable):
    """Devuelve True si quedó en el estado pedido."""
    if not IS_WIN:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError as exc:
        print("No se pudo cambiar 'Iniciar con Windows':", exc)
        return False


# --------------------------------------------------------------------------- #
#  Temas — estética "liquid glass" (claro / oscuro)
# --------------------------------------------------------------------------- #
#
#  tkinter no tiene blur real; el efecto vidrio se logra combinando:
#   - transparencia de ventana (-alpha)
#   - acrylic blur de Windows por detrás (SetWindowCompositionAttribute)
#   - bordes finos luminosos y capas translúcidas en la paleta
#  Si la API de acrylic falla, queda el tema plano translúcido igual prolijo.

THEMES = {
    "dark": {                    # negro + amarillo
        "bg":       "#0e0e0f",   # cuerpo (casi negro)
        "header":   "#171717",   # barra superior / inferior
        "row":      "#1c1c1d",   # fila de tarea
        "row_hi":   "#292929",   # fila hover
        "input":    "#222222",
        "fg":       "#f3f1e7",   # texto (blanco cálido)
        "fg_dim":   "#8c8a7f",
        "accent":   "#ffd23f",   # amarillo
        "overdue":  "#ff5a52",
        "border":   "#343330",   # hairline
        # Con foco: panel sólido y oscuro (para usarlo). Sin foco: vidrio translúcido
        # con el blur del escritorio detrás (se funde con el fondo).
        "alpha":    0.985,       # con foco: casi opaco
        "alpha_dim": 0.82,       # sin foco: translúcido (default del slider)
        "acrylic":  True,        # blur real de Windows — sólo cuando NO tiene foco
        "tint":     0xC00E0E0F,  # 0xAABBGGRR — tinte del vidrio sin foco (negro)
    },
    "light": {                   # blanco + azul/celeste
        "bg":       "#ffffff",
        "header":   "#f1f1f4",
        "row":      "#ffffff",
        "row_hi":   "#eef1f6",
        "input":    "#ffffff",
        "fg":       "#1d1d1f",
        "fg_dim":   "#71717a",
        "accent":   "#0a84ff",
        "overdue":  "#d70015",
        "border":   "#dcdce2",
        "alpha":    0.985,       # con foco: casi opaco
        "alpha_dim": 0.88,       # sin foco: translúcido (sin acrylic, se lava en claro)
        "acrylic":  False,
        "tint":     0x00000000,
    },
}
PRIO_COLORS = {
    "dark":  {"alta": "#ff5a52", "media": "#ff9f2e", "baja": "#4ad06a"},
    "light": {"alta": "#e5342b", "media": "#d98600", "baja": "#28a745"},
}

# variables "vivas" que lee todo el resto del código; apply_theme() las reescribe
BG = BG_HEADER = BG_ROW = BG_ROW_HI = BG_INPUT = FG = FG_DIM = ACCENT = OVERDUE = BORDER = None
PRIO_COLOR = {}
WIN_ALPHA = WIN_ALPHA_DIM = 0.9
WIN_TINT = 0
WIN_ACRYLIC = False
CUR_THEME = "dark"


def resolve_theme(choice):
    if choice in ("dark", "light"):
        return choice
    return system_theme()


def system_theme():
    if not IS_WIN:
        return "dark"
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
    except OSError:
        return "dark"


def apply_theme(name):
    global BG, BG_HEADER, BG_ROW, BG_ROW_HI, BG_INPUT, FG, FG_DIM, ACCENT, OVERDUE, BORDER
    global PRIO_COLOR, WIN_ALPHA, WIN_ALPHA_DIM, WIN_TINT, WIN_ACRYLIC, CUR_THEME
    CUR_THEME = name
    t = THEMES[name]
    BG, BG_HEADER, BG_ROW, BG_ROW_HI = t["bg"], t["header"], t["row"], t["row_hi"]
    BG_INPUT, FG, FG_DIM = t["input"], t["fg"], t["fg_dim"]
    ACCENT, OVERDUE, BORDER = t["accent"], t["overdue"], t["border"]
    PRIO_COLOR = PRIO_COLORS[name]
    WIN_ALPHA, WIN_ALPHA_DIM = t["alpha"], t["alpha_dim"]
    WIN_TINT = t["tint"]
    WIN_ACRYLIC = t["acrylic"]


PRIOS = ["baja", "media", "alta"]
PRIO_RANK  = {"alta": 0, "media": 1, "baja": 2}


# --------------------------------------------------------------------------- #
#  Iconos  —  Lucide (lucide.dev, licencia ISC). SVG rasterizados a PNG y
#  embebidos en base64: variantes idle/hover para tema claro y oscuro.
#  Tamaños: 22 px (x, minus, settings), 26 px (plus), 15 px (grip).
# --------------------------------------------------------------------------- #

_ICON_B64 = {
    'dark_minus_hot': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAAbUlEQVR4AeySMQqAMAxFxT06OEgmD+D9j+IBnIKDg+YCpktoxmI7'
        'FH5p4JfyH+XRcWi0AHaxUAEVbsBD+BV6y66PnPrKVTSpY12nWghgO1fbAUwLHzTzRhOvRZM61s1fFcD5xd8MsBuEio5VfAAAAP//'
        '3XzJXgAAAAZJREFUAwBIREAtKvct0AAAAABJRU5ErkJggg=='
    ),
    'dark_minus_idle': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAAbUlEQVR4AeySQQqAIBREo0u07ABdr8RNiLQR63odoGW3yL8Z/EtJ'
        'F8KIH0ZkHvJwHBotgiGWKqgCBhDUrwhhX87oniu6t2SkI11QU1DgdK62Fdja496Mn1fjp5KRjnTzVylwfvE3EwyDVNGxig8AAP//'
        'gq/j6gAAAAZJREFUAwC/ZkAtCo+RQAAAAABJRU5ErkJggg=='
    ),
    'dark_plus': (
        'iVBORw0KGgoAAAANSUhEUgAAABoAAAAaCAYAAACpSkzOAAABmklEQVR4AeRWsUrDUBQ9L4YO0kGhkz9QQdChkwh1dOokOEj3Tg5u'
        '/oFuDk7di4Pg1MlVEKcOFgX7A04FHYpDjTzPSUXTkNcQTahguKc05957Tt59DxIPkcs+bq3Yfv3Y9rfviTfCZoR62EsNakWk8WVk'
        '+/V9jP0BYI4ArBE+kTXUw15qUCvU/FQIjSaE6ZArE3kFtUxnog14Ghdg2gAM8r+oadry8DBeOKA+3flbTJTlwdGZRjH6UVXToBGq'
        'USrt/+g1gJBWF8tXZaSTEuPdt7uHdxDcFYkZX0aJGRc5fB5DcOVdfGYjl1Aa/4+MdLJ2Wj3U9m6nMHzhHhFxXrXqcY1w/qMrL/q4'
        'atfQu9icQmWpBCHOq1Y9f3dFrif7KT//PXI9eWWZe0S48i5eKwpcyST+8nQDQlJuBhfIiK/vGSWxlE6WEKPTbgc0st20qt/nbddD'
        '6f2MQiOiqBjJwzOrN0+AbdHFEnkHNW1LHhwdYNavz2nWBJDnyqhlmxNtfH/XhUQp4GvdntDwgch0GlmvUA97qUGtUFMsgA8AAAD/'
        '/4tvAPIAAAAGSURBVAMAY624S4NDQRgAAAAASUVORK5CYII='
    ),
    'dark_settings_hot': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAD+UlEQVR4AYxVW2gcZRT+zj/bGOPM7GQL6W4qKQEvqVSLz0KJF0QQ'
        'kXorVov1ggp5CGJTKlHBYsU2tiAYUIq3qtVqq/ggiGCU2leRQsD0xdQ27m7SZDs3w7rZneM5k82CtUn6858553znnO+/zBnG4AoH'
        'MxvmnzJXmI5ViWdmZuzYL70fheUgDvoC0YeLxWLHagusStxxVWOUCU8J0SwIZTA/49jmbfFXnCsSM4+3MfCIMJxz3InrbXduo/hn'
        'kfB2PYngy87/EEdzpZsivzwch6Wh+XD6tr+jtfuksp0IY0S314k21cQ/KTvv6GhPhjVHc0O//FKlcv4WibVmizi6WHwAGZwG8evM'
        'ONDg5JToXZIZ1uoLB0Wns95YGAHYZ+Y9zZwDRPzGGivz20XlSLOAlDh920R6b/WkwTsM0bMAHSXgUD3B5lyuZxzNoXatntwsi74F'
        'yYExzxNZO2WxesbQaMoFLBJH0Y0eCNfK/f2czXV/eo2bP+xk84/Z2cKLnpf/M4pKD4VB6UMVtXO59X+5XmFIcxxn3Xu22/Uxg8aE'
        'Lx/HG3OiF4kd54wvVzBFjC1BULxHAypyXIrD8udI8BUBO1XUVkxjaA7fL96ttWBM2fa6WYWNPvTFJMxDsus2w3QiDKduUDyOyw+K'
        '3iYyAUN3pgJMiL+tGUMQnL/OIvpWa6UVB4kokThSYjWy2fVfAGavJHQYrLkPMjjBvaIEpgHHyY+pwNCAYksxizJbxW+HwV6ns/tr'
        'sdPZIk49OWdTX4Ivopd9MtUVT+qJpXpJWgTRYqu8KoFqPamdEA0y+E61fBCjUVS+Q0VtxZZiCwl/I37VGPOK70/pxySuHFKfaYto'
        'uzFqDeb7PW/DH4rbdl4XOCZ2nxD+mArQJ/6xZgydnYWzCXirvLiqBetgyiUJRgRpi0i7geiU53X/oJgKEbHt5h+V+3uYgY9U1FZM'
        'Y5qjks12f8+EkxCOtHUFTInTFiGeApL+oFJ8PIqmn4uC8mehXxrx/fIGxykcd7OFJ1XUVkw+5f2aEwWlgTiY3kFAv7asxCuQkRLL'
        '6kkjoRcAMsaiT5Ak7wK8nQi7Mga/VirnNqE5wtlin2CnmbFbcwR+h5EcEd2GBv7fbp5XOI4G3Qqml4mwO0PWFtnFISnIZaw1Q6LT'
        'adpIbVdu6U3WHMIerZHazc5y7ebk8uOOl99nu4WRq92uXy5UqsNyr7F8Vf2Tk5PtLH8Q2eldskL1wtw/r7mSI7n7tUZrBW/N9Cpa'
        '3iVGb29v1TC+BKFnba799zjsOyMpPXKioxoTe9m5IrFWzdesQdnxByJd4ncTcGS+ag2KveJclbirqyu2vcLTdnYia7sTjp0tPKEY'
        'Vhn/AgAA//9mAAqgAAAABklEQVQDADXCw74vsjvVAAAAAElFTkSuQmCC'
    ),
    'dark_settings_idle': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAADyUlEQVR4AYxUXWgUVxQ+Z7KGdHdtiw+lFGlf2mJLW+lzQUJbSqGU'
        'YlsttZXaH9qCD2IzM5uQZvfO2vzszGyK0ECLtPX//wcfBBEMor6KCAH1RVQi+CDiz64GszvH79zJRkWTONwz59xzvvPdM/eeuQ49'
        '5WOMcSCZp4TTnMSlUikfh6V/88/IzVxWbsLegAWycy0wJ3E+RyMg+YGYrjHRVdg/5bOyHnrWMSsxqm1H9nIQXq7d4ddu1+kNzC+K'
        '0ArE8rBnHI8Qx7F5sxoVe6Oo6P0Z9r2HavtB2iFEo/j8RhAE9zA/zkzZ+TnqVUxUKXrA90SReefhVaaJ40rpc0rkjAj/wcJhk5yT'
        'IHEBviXMVWg7kkmOYNyAdFsMcwj8AIucthwI6LDEqCYjTOtRWUM4WcksP4N0uwgNTzZ5seeZMQWreL1mrCn0NrCxYoD9lRxZhVgD'
        '5zCiXLDTrsjn6XmAFmKVY563bmuXV97Q5QffeIWgq6fHXIor5kt0w/9WYBcKwRXPDzzFAPuP65Y3IX+UiF7M5WgBNDn6qtVIP208'
        'EVoShuZjevBwHJodxLIHLq1qldrWR6iP0gc5H2muEI3X63RNvZYY5TckYQ+H0o692lcdMK9rEJV+QSRfwT4nzB+oqK2+NEY0PGhe'
        'ZZKDaS6tAVcCTFqxGl632SksZQCy0pZ8qj5U94lqYV6NfR5VUVt9rVgzkyzFNnRgr8tuIdhvY3jZiqHtaE3wSS3T+md7sVBD40lC'
        'bapbMk2grSLCRSGayCTOPgsQPqSaRUbQp++rqK0+mopNNp0DmsPMfdGQWW5jeFli7EvabkL3hPiztT3mAmLkFgwW4F2wF4HwqIra'
        'RLwrjRGhay4iZ6kITaDtqspFeCyxtgj2aSHO+aTvmyPwt4a4vvka1S2DY6MV4WXWhxPE3A7kHEbuceXQ1lWnJZ5qkXEEOqOhvm/x'
        'W/9SDUvborAUDQ6aV1DdXtcPvrdSMHvVh56uKKYaFlfHcXElyDoh42jd69BpV6D8BFWthcNhx9kiwn8L0Qos5M5rk1NRv3kLMTvi'
        'AbMIvjOY+IoR4r8o4c3AtpPQ4+2mVaGV3kXb/I628x1KluDEh0GwgOaJB52OjLWfxWRIMcB2pzm82J2p3dCnY/hF+z2vHP3mrztx'
        '+y73oooaSDrxVR2QjBB9CJnANRooBthKmmOm7xPCY/cY+okDRBM4lN34zJdxuZ+FnFcbst3GnpiVOmclVggu9zXQ/4nQC6j0Jcjm'
        'KR/cM485iXG519ANP9bv8nP1Ozwft9p36puZMo3cBwAA//+Rz9lYAAAABklEQVQDADpHuEQBjEnXAAAAAElFTkSuQmCC'
    ),
    'dark_x_hot': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAABQklEQVR4AezTzUrDQBAH8P821i8Kgj6OHsSTHoKI9FDowUfzYi89'
        'FAnixYMHfRwPokjaaNeZbRu2nZk0FHooNGTJZjP7y+7sbgNrurZwmViRCt9ut3zntuPvzvfLKKNSFStg7I1TON/D8PjJp+mhYYJR'
        'NP+eQ+zvyc1inIQ/R48U9AKHC7SamYaXKHBGsW8YNjJ6zt0Cdln2gyLhEai4QIvkyvX733MqvQiY2hACFbwuyoYK8wcNDzmdTd8Y'
        'KfflYsL8UeA1Ue5bCXPAtBxMn4DHCHk+Lt+NSiUc5fSU+r9TUReU2sVtwhE62VJFclm1WxZlFVbQsKVEzo19zj8RsIVyMJe6uIDD'
        'kV6y+gI/2r3mn8ZFwjsfA1r6LuUzTD8OjusB/yoI9N16R/r+NXe9wUPoGEtKnY+/FStHrACrNG0e/A8AAP//M8IokwAAAAZJREFU'
        'AwA4UbItfa9v6AAAAABJRU5ErkJggg=='
    ),
    'dark_x_idle': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAABN0lEQVR4AezTsU7DMBAG4P86QWifCCYmGFDVEYnHQGIjCSPiNWBF'
        'qEIsjPBETSLEEHOX4ij1+UyE1KFSo7h1kt+fYzueYEvHHu4nVk1FnufTh/vby6IoDvqUUUllFTw7chcAPU0z98p4BuMQdJbhDV22'
        'XSA4FFw1kxcHvHPulPFlDO9RwgkcPlY1LTm/cSqYoaaqsbBwhTY4L8uy2lD5QsF8DxKM4WNRMaKwPIjh3Zz64RtvKm2lmLA8DHGM'
        'RKVtEpbAurjD9T//Er6JqOVa8kzCfk4JdOzgPq0FjfVgwh71w69qOqsSX0uIR+EQXf0uVDjn1ncunSjYQiUsZSyu4G5L/7H6Gm/n'
        '0umwKJi39DOcu/LDH4aHdcHrhuZdduSW/rq+uXuUhkMoVpftb2XVG8eA/9zbPfgHAAD//ylGtQYAAAAGSURBVAMAVBnZLfTfSUcA'
        'AAAASUVORK5CYII='
    ),
    'light_minus_hot': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAAY0lEQVR4AeySQQrAIAwESz/RiyQP6P+f0gckeOkvGi+LOUr1IKy4'
        'sCIZZPA8Fi2CIZYqqAIGUNKvEJG7FLXIOxhrs6BGSeA4T9sJ7O5PraaRazDaZvtXJXB/8bcTDINUsbGKDwAA//9UwuYLAAAABklE'
        'QVQDAP2EQC2R9AU4AAAAAElFTkSuQmCC'
    ),
    'light_minus_idle': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAAbElEQVR4AeySwQnAIAxFS5fosQO4nDmJE4inuJwD9NgtKggfc5S2'
        'B+GLgS+SR3hk3346BEMsVVAFDCCYrRAJzvt4icR7pnpPcKC2YMDt/dk1YNVcS0mnajpmqvfkOk5lwOPH20wwDFLFwioeAAAA///3'
        'YcdEAAAABklEQVQDAED8QC0kDqqXAAAAAElFTkSuQmCC'
    ),
    'light_plus': (
        'iVBORw0KGgoAAAANSUhEUgAAABoAAAAaCAYAAACpSkzOAAABj0lEQVR4AeSVvUoDQRSFzwwqGrTUwlpIkSfwBex8ARErwUpbBduI'
        '2molWIn4Aul8AV8gKQLWFloqQUxwvF8gYbPJLjtmIYJhzmbm3nPPmb9lvRK/ymVYX6qH80o9NA1dQ4gENc2+hmklpDU0WjwLO6Gr'
        'tpNOjFAzzBliGzU1NNBCcyDQNyLgg+6NsDxITPuPFppoo+XZLhd0YwPL2bPc5tDGw9sSD82htJWk54k2Ht462+lk2WM8OKNqjPDK'
        'ggRiaoxbxYibYv1i7XFPAsXYQ9YcRsNRkc5qRQJFuElOtFGyOKb/j4y4WU/70vORRrBmbxxIx+FSk7Wds9+69y9p81bauBrF64cE'
        '0nG41PzdFWXN7Lfx2Z9R1szfOhLIymfFWVEvKzkpvnUngUm5nFgPo3YOYSzFzQJjifxA2762auRzps8GqeHdvK6tY2/H9IKTFNDG'
        'w3eO3UtwOjCSxexZbgto48EZ6fPUPXw77ZpTaStDC020mXvfiA4BW2LVCBc2bhmibqPxadS00EALTYLgBwAA//90EXCiAAAABklE'
        'QVQDAKuzohUa/I+jAAAAAElFTkSuQmCC'
    ),
    'light_settings_hot': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAADrUlEQVR4AYxUbYhUZRR+zr2z67q1FcHmMvdjBvrAlkr6HSxLRQQR'
        '0ZeRJtkHFfgjIjeMtSDJyLYEIaGQPvxavxV/CCIoov4VEWTVH8rM3DvLyor4zaDjPT7n3p1R0Rm9nGff555z3mffc95zx8GDP5ab'
        'e9B0S26b29vb+3AQFP4JgvBCEBQu+H5hVT6f7267icH7Cnd1TV/JvE8BOQtgQgSfO07HCvK21la4v7+/E5DZqqhEUfnpnp6HngVQ'
        'ovgcqwRtnjuEwzDsZ7nDLHeI/KVLl64s5d4uEd3HtT42NnYN0APk3dOmTR+2nCy3+L3v+y/Q37SmMBPeSRIcZeRnnug3VTlEvpC4'
        'SLE/uE6ZjpCcF5FFliMC5uovIu4R02AstYZwjqdaISJ1VZ1HfMHoKLH8+nWZFUXRMfLUjCdJ/Xm+/E6Mct9XxHzyugjsPtLJSYV5'
        'y48B4gPYH8eVdcQq9nQu8e3ERKnseeF7QRD+ZzBe5cPYEDG3Uqn8TazmXmtX34wZTz5OjlR4fHz8PMuN6Rjw/eLrXBsmFNvgOLIF'
        'kPkG4+YDIJh6giB4jXTANM6cOWXTkwnTWQecIbagk2Vt8zzvGfrA070LyAeqOMH+v2Iwbr4sBvDSnuLenbZXVb4GkBBNYURRaaOI'
        'LKGz23Fyb3KF4+ANW1WxoFot7zMYN18jBrhv852TI0viuLydPLW0FSm77Q8339N/W0qT8jCsFuCJ3aaTpClgo8Lgj/TVHEe3cQVL'
        '32WrCFZ6XuFlg3HzNWKuix18r4nID54XziZPrSHcGDd+AMlbvOXTFq1WK/wHukkEM1n6XoNxnm9TFuNnWCqVVMXawQPB5v3WuGUj'
        'YuOmhzine0x0ChpFlQ+TRN+n2P8G4+ZjXInU4ri0m4RfpPjZ6ALpibMRUY6bDPp++BE/1S+DoLCeGOnrKxZ4uq0U+8RgvFgsFny/'
        'uIxxy1nAFsyj8CD/cczRPUeeCZMk7Nk37LEjImtZ2l/0zSEWdnToYc7pc+Sp5fPFmTdu6FGO5Xd0WM6fjiNryDu57+5xs5Mw+UUm'
        'LFYFNyUceCznO78kGeKamuuq8Ud4iF+BZIB7FjGwmHxW3GrcIv4mRFF5KRNGyA+6rgwDellVBll+FwVyqniVay2Xc36yHF70MttD'
        '3vw9YbzZCuN3gRdeA2SzCEKWf5w9PWkcwGgWI2th6eW1iKXuWu2q9e1fvjxB5FnBmikfX1vbfYUnJycvs9TPiEeJniiqfGy+1pJZ'
        '5CYAAAD//zvjgf8AAAAGSURBVAMASh2kRO3vH3AAAAAASUVORK5CYII='
    ),
    'light_settings_idle': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAADzklEQVR4AaRVXWhbZRh+3pimo6RNtwsRGfNGRUUdXgtjqIggIpub'
        '4nRYf6iyv5zEVZqTaU/GmnSrS043O5Sh1qn1Z63ihSCCRXS3IgNBvZEpFbwYXWtyEeNZ3j3vOVnYbzrYx/ud73n/nvO+33nTxnCN'
        'y/O8GHf8GsOxLPG2bSPJbNZ9d2mpsbS42FgiPjo46PUs94JliROJ/ydV8QKgp0XwD/FLyWRj4rqIR0ZGEiR7kqR/pVLdt/X1dd1J'
        'fKrZxBbrpBP5RRXv3Jm7y3HcfCbjDjlO7v5qNRhl8goRmeP9BoVCoaEqP4igp7s7yFtMFOvm0mn3Xsa2pU3MoI3xuJwUwT56D4jI'
        'CVXdTfxvEOAgz1BY7TjBIisfthhixqIYi+Fn46AeSkjMauLU7N4CJm4V0UHq0yQuqzbXHjpU/IV6KIaDILhHVd+kYZqxrwAyACAQ'
        'wWSLCyFxtVrtF5HVrOL7iYniR+Vy6WilUnzG90uv+v7Yn6xkk+O470c7t+nw4QN/0zdkMYx9p1IZ/YC5c4DcVKvVVoErJO7t7bXW'
        '5nl/6zKZ4UdoPy9C0k/40uMiGIi2HDcbAEFrMedhy2UX88lk8rSZQ2KWHwAyxMSEamw2m83dDi4SPCEiTxH+RvuDtg2bzXzEIOmt'
        'QOwrESSop8nV5BldhQG29akq9jKgR1UeMxsgj4KLhNt9f9+cbcM0USIfSTdQ4eRgL6/nC+JQYuGz9eCXbSFcZD9vvMrJbgF+9Bsu'
        '9LcJ2NpGVbxBZ51hszwp+jUfEGlOOs6eB2wbNhsQ+VSbX1Kvs9PXOdP8MVGjhMSe54XjRuIG0Hy8Uhn7gz6wtVlV/Yz4DhJ+Z9uw'
        '2cxHzJixU8zZwNw67QdbXFHLNiLCcRPREyT91hJaW0nwNBM2M3Eq2rrZbPQrdyjM+Ya5/EXKahtdM4YVRyOi84CsT6fdZzkVL7Ot'
        'j3k9444zfAuJZny/+Hy0SzNmy2bz+6MYd7vj5LdaLqDzHN0FcIXELL/JajKm8wN+qCpvE29hF7tFYj/t2uXeTT2UHTtyvJbYSXbx'
        'Gg2MwVus9hgxRxWXj5vvl2bOnsV9qtjDICbpOiaUiVfxZUM8Q0kkxHAfIGOskDEYthzmriXHlcfN/g74fnGUMz1eqZR+XFjozgOo'
        'kWD9wIC3gp3FWelDtNXPnOkqWEy5XNxvOZZLe1vCq2hrl4CpKY9fGp/zStasXPnfr/wv8jsga0QwbT50WB2JLa/R6EqT6D1VuZH6'
        'zao4Vq93pYk7yrLER44Uamz3xf7+RCqVSvSy7efM1pEVwDkAAAD//6Qp1UwAAAAGSURBVAMAfLjNRFMj92gAAAAASUVORK5CYII='
    ),
    'light_x_hot': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAABQUlEQVR4AezTvy8EQRjG8e8QcriSRkWnUOqoVBRyUUr8e7QiF7lG'
        'SaeUKKk0lEcul6z1PtZszvzYW4VCcpN7s5ubZz6ZmZ2Z44/aDK43NtqKe9a6D6yePLLRqVOZl6ZsBM9THoE7HzG8umN9mUwTaoMH'
        'VNljgmZ9P/95Y/ESymtw+yuM+yncow72SrgpcH2CFsE7PL9b0GaQxkP0Aw63eRkGLhGsgIIpvC0qIwmrI4VbeOCXn5upxqosq0e6'
        'QrwtKq0RVqAqt1Q9wVGORyzYhGlsjbDfUxN2rW6nnRbL1L8s7FG//AIOClz2tNTi90sSDlFb99eRCvc8d85lR3AOVVjVFo9gXWm/'
        'fD9TgZOVwHuT/XqP4A7dC/vypzlUg1TC7fr3lLW9n36lN3kabfF6poECmkrXP5eNZtwE/abv/8GfAAAA//+3gUMCAAAABklEQVQD'
        'AJH5qy0Bp5ynAAAAAElFTkSuQmCC'
    ),
    'light_x_idle': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAABT0lEQVR4AezTMU8CMRgG4K8X7uJdJCHh5+jkpIMhjiYOTAysjA6e'
        'gyMrAxOLrsYQ4+KoP4cJEXt3ucobUnK0/ZpjYCChycc16duHtncNaE/tCG8O1jqKfv/hdDC4v+1205NNiun4shYcx8V1WaqXVku+'
        '93ppwpgENIryD2Tb7fzGzFnwfB6+EYlPIcRFksipC9eoEHSuFH0tl40pGc2Cx+P0V8rGagVu3ESzLLwajR5/DJcsGAEEXXhdFIYT'
        'xoALx5nq7XMrxVwUC2PQxOuimOuFEVhXGa+f+FVZUYgSPV95YX2mROKMSH2vnt6vhSqNhTWqty9ldOl6oRVrq+uETVS/KPPMue8c'
        '/2DBHIowqi5uwbjSevt6pQCrZeLNZt6pjqNvwbNZ+BoE4o5DMQkFfLEIO8jWutKTSfo3HD49YyIAX+H6c1lrxT5ol7HDg/8BAAD/'
        '/68H3FMAAAAGSURBVAMAqIXlLb+V2DMAAAAASUVORK5CYII='
    ),
}


_ICON_CACHE = {}

# Icono de las ventanas con barra de título (el diálogo de Opciones). PNG 48 px,
# variante clara / oscura sin las marcas del reloj.
_WIN_ICON_B64 = {
    "light": (
        'iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAHx0lEQVR4AeyYfWyVVx3Hv+d57tNbem+hvI1ZJq44nTBJdJESm8W/'
        '3BxWk4VZMoGZKG5kWza3isE/miUmYjRxiUbiH844XGQjEyHUpSQuU/YijTNbXQgrKJS+0FLKKN5y3+/zsu/v3N7LfSi97dNx4S5Z'
        'c3495zlvv8/3nN9zntMa+Ij/fCzgRm9g2R3wPE/Ztr3ecZw/sdxHy9IqncRHn/gU33Smyi3StAIymcxqD+g2DLNLGcZmz0MTny3m'
        'YI4K5hbnb1LK2GyYZhf9dAvLdCKuJkClc7m7LavmLZKu0wM54w3M1wlLOp27mwxTduNKAYpqV9WY5gHAi9A4RuhvuEVqaswDwkYg'
        'n4hSAaqtrc2wLOsP7ER4/q6uFDHJJozEKorwCdi9e/e9XOt1NEZPFa0/iYWJ1OuEkY8s8jdTQYBUKMsKb6pKcqGfNM0IaF7wpyCA'
        'RRiGoVqkUM02yVjkLhREkQGlbpkUWrUbIYxcYIMmzCgU5EHKITZUexJGYRVmJQUB5kOjAr8a19v4paVL7nsQ3yArQGboHUD+x1Gc'
        '5rqGzsWkh9/8HdrGWZ6tf8BReWaUCihUXZ88kXaw8XcGfn6I1mXgwWcN2LYT2HkhhAIP/DADHIJ2dBo4Nqz0x8ZzgSP9Chcm7Hw4'
        'BZjcJyBIGM61r+O42PcO8NK/TQ3vEj5NcxJxJJNZyPNMc5fq8wkobahEWV7Y42c9dBzkQULoHC1D87gjCxJ9iNSKV3kTJJ+dXUcB'
        'HmJJB4/sCSGZVhBwcvN99JAePo7t99UiZHBXZsdd7OUT4PEMqpTZtovtfzZxakxBQkZChe6QPd+Pb69No7V5AWprQ1BKsbo8RZGe'
        'BZ8AjsT0xt6yu3Mwl3H/3D+BrqMmUhIycthwHic+jtujQ3hywzIsmh8Br8x0wsS2shzsUkh+AYXaGXKJ5e7THp48oPAMz/F4Rjxe'
        'fZD07RnwsLPL0mEDh/3Y3ctmEB7/D372veW4eXE9IpEa8DLGxmApsAABGr7oYuveEP561MBvXzfx8IsGYrK0V/gmJy7GXWx7wcKl'
        'LBu5+nplXQ+ZwX/h6U1LsPrWBtRHa2GagVE4IfwfMnE4k7l0/s6gjUyO4wnER7zRZ+ChF0zEkq7mK8yRzTl4bK+J/vcVwL66kXnm'
        '7FFsuUvh3uZlaJhfB6uGL6+OfeguhfHT5fRcTIFlOySeGB2BzXPboQe+mxC4bhGxx8SEiOBBLnH/61cNvHKMcOwnfcTs/5/BFxcP'
        '4olvNWHxgghqw/kXt0gUsOAXII7oPL8MfGDipxG+Zz7c1hjGeM8hZJOJfBtXVWK7+yR34nnuRMLF6//18MzfQpfbOZebTiAaO4Kd'
        '21bhpoX1qKurYdxzd9g2xU85jhKRPgEe4fRcZXKlFG69OYoftTUi9vZBOKk4ZGU5BGJvUMR3njPx+IsWHIeeZEIt0EV24BX8dOtn'
        '8OnGBkSjYZghQ4bQxLMMn13OWYvJJ6BYW6aglEKEK/fAV1ei/X6K6PkLRVyCiMgSWL6u3adMjMYmV1bDA+mhN/Hw16L4yp2NWCBx'
        'bzG0yviZbVNgAfyTjh8cC0sZAlvWfxbtGz6JWM9LSKcugce9FiJitFGQhFZu/Dhalg/joftWYbE+70P6gzVbyHL9fAJ02HHLZ8oN'
        'w4Cc2zctqsfmr38OT7WtQPLdPfDSE3kBnEML4Oo7qQtYmngNP3mkGUsbophXZ+m4n8lHufZSQT4BpQ0zlU1TRISxjCK2tN5BEU1I'
        'v/v8ZRGE9xwbzun92PlYMz61bCEiEvfmtQmdAt+cBcgEBRGyE1ta1+CpB25D6uhu2Od7Ycf6kTyxF48zxJo/v5xxPw9W6NrCC4NP'
        'gOx8UDNMhUhdGAUR2zfdDm9gP1Lv/RFtLTV48JtrsJDnvb7n8AAIOv/V+gt4wXwC8mcxh5QLwClt4DWAIiIiYj42f2MNDu66H520'
        'HVtbsKShHvNqQ/mXdsrYoL4m+xfomfsFsGKuyeROROvDWPGJRfjSHSvQcudKrLxlCebX11LgNXMzBc83s14gdqFOflwQ2JRSCPF8'
        'D4ctXhEsXVaG3O+DzzUdA28yJLycfAJsV/+Zcbm1Cku242f0CchknNHAyz7dUlWoPpslY8nClggwvVg89XZJW1UWL2pGU5ZH8xUE'
        'sGLEGxoZ35/K2pObMLuLlfTiYI6RksR65XJhGyYjMJJ3SQkiQB5YhNfR/ovOsfHE/1z5T5PUEEtnVZC7PGGETRjJVGQWAXzWhG53'
        '98uZE72DT4xeSOZced2l21zsGo8RFmESNmEkMC8qmrn4J6W45N3xnLOh9dEjA4PnHx16P2GneD+WhhtpwiAswiRswDlyyh13qgDh'
        'ZOOQfc9d2/a919u/8cz5+NDoeBLxVA453pW5ixRf2SQ+xJf4PEvfwiAswgQM2fRORg0vvMUdYL2u5NaMsFNvbuP6H/6j/Qe/bOk/'
        'c27H8NjEW0Nj8ezp0Qn0na2siQ/xJT4H6FsYhAXo5b8RhE1f1DW8QBfeASlLJQXI9pxj58OZw4cOxu758vefXbt6U+t323Y0de57'
        '9Qsvd762tpImPsSX+BTfwgAczjB0yCRs0wu4QgS4Eyf435w3OXgs3dNzLP70j3/f39G+62RH+69OVcZ2nRQf4gsYSwPiWxiEZSq8'
        'AH8AAAD//1o3ba0AAAAGSURBVAMAupey2GIK/TkAAAAASUVORK5CYII='
    ),
    "dark": (
        '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'
    ),
}


def _get_icon(key):
    img = _ICON_CACHE.get(key)
    if img is None and key in _ICON_B64:
        img = tk.PhotoImage(data=_ICON_B64[key])
        _ICON_CACHE[key] = img
    return img


INPUT_RADIUS = 8            # mismo redondeo que la ventana (Win11)


def _round_rect(cv, x0, y0, x1, y1, r, **kw):
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    cv.create_polygon(
        x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
        x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0,
        smooth=True, **kw)


class RoundEntry(tk.Frame):
    """Entry con las esquinas redondeadas: el fondo se dibuja en un Canvas y el
    Entry va posicionado encima con place() (sin recrearlo en cada resize)."""

    def __init__(self, parent, *, small=False, **entry_kw):
        super().__init__(parent, bg=parent.cget("bg"))
        self._fill = entry_kw.pop("bg", BG_INPUT)
        self.cv = tk.Canvas(self, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.entry = tk.Entry(self.cv, relief="flat", bd=0, highlightthickness=0,
                              bg=self._fill, **entry_kw)
        self._ph = 8 if not small else 6
        # place() con relwidth/relheight: el Entry sigue solo el tamaño del canvas,
        # sin que corra código en cada evento de resize.
        self.entry.place(x=self._ph, rely=0.5, anchor="w",
                         relwidth=1.0, width=-2 * self._ph,
                         relheight=1.0, height=-6)
        self.cv.bind("<Configure>", self._redraw)
        self.cv.bind("<Button-1>", lambda e: self.entry.focus_set())

    def _redraw(self, e=None):
        w = e.width if e is not None else self.cv.winfo_width()
        h = e.height if e is not None else self.cv.winfo_height()
        if w < 6 or h < 6:
            return
        self.cv.delete("bg")
        _round_rect(self.cv, 1, 1, w - 1, h - 1, INPUT_RADIUS,
                    fill=self._fill, outline=BORDER, tags="bg")
        self.cv.tag_lower("bg")


def make_icon(parent, name, *, bg, command=None):
    """tk.Label con el PNG del icono para el tema actual; alterna en hover."""
    if name == "plus":
        idle = hot = _get_icon(CUR_THEME + "_plus")
    else:
        idle = _get_icon(f"{CUR_THEME}_{name}_idle")
        hot = _get_icon(f"{CUR_THEME}_{name}_hot")
    lbl = tk.Label(parent, image=idle, bg=bg, bd=0, highlightthickness=0,
                   cursor="hand2", takefocus=0)
    lbl._imgs = (idle, hot)                     # referencias vivas (evita el GC de Tk)
    if hot is not None and hot is not idle:
        lbl.bind("<Enter>", lambda e: lbl.configure(image=hot))
        lbl.bind("<Leave>", lambda e: lbl.configure(image=idle))
    if command:
        lbl.bind("<Button-1>", command)
    return lbl


MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]

MIN_W, MIN_H = 250, 170


def parse_due(text):
    """Acepta 'YYYY-MM-DD', 'DD/MM', 'DD/MM/YYYY'. Devuelve ISO o ''."""
    text = (text or "").strip()
    if not text:
        return ""
    hoy = date.today()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m", "%d-%m"):
        try:
            d = datetime.strptime(text, fmt).date()
            if "%Y" not in fmt:
                d = d.replace(year=hoy.year)
                if d < hoy:
                    d = d.replace(year=hoy.year + 1)
            return d.isoformat()
        except ValueError:
            continue
    return ""


def due_label(iso_str):
    if not iso_str:
        return "", FG_DIM
    try:
        d = date.fromisoformat(iso_str)
    except ValueError:
        return "", FG_DIM
    dias = (d - date.today()).days
    txt = f"{d.day} {MESES[d.month - 1]}"
    if dias < 0:
        return f"{txt}  ·  atrasada {abs(dias)}d", OVERDUE
    if dias == 0:
        return f"{txt}  ·  hoy", OVERDUE
    if dias == 1:
        return f"{txt}  ·  mañana", PRIO_COLOR["media"]
    if dias <= 7:
        return f"{txt}  ·  en {dias}d", PRIO_COLOR["media"]
    return f"{txt}  ·  en {dias}d", FG_DIM


# --------------------------------------------------------------------------- #
#  App
# --------------------------------------------------------------------------- #

class TaskWidget:

    def __init__(self):
        self.state = load_state()
        self.win = self.state["window"]
        self.tasks = self.state["tasks"]
        self._drag = (0, 0)
        self._rs = None
        self._rs_target = None
        self._rs_pending = None
        self._new_prio = "media"
        self._hwnd = None
        self._editing = False
        self._summon_flag = False
        self._glass_on = False
        self._dragging = False
        self._hidden = False
        self._hk_tid = None
        self._undo = None            # (tarea, índice) del último borrado
        self._undo_after = None
        self.tray = None
        self._due_after = None
        self._due_notified = set()   # ids de tareas ya avisadas (por día)
        self._due_day = None

        self.win.setdefault("theme", "auto")
        apply_theme(resolve_theme(self.win["theme"]))

        self.root = tk.Tk()
        self.root.title(APP_NAME)          # nombre para Windows; el encabezado dice "Tareas"
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", WIN_ALPHA)
        self.root.configure(bg=BG, highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=BORDER)
        if self.win.get("x") is None or self.win.get("y") is None:
            self.win["x"], self.win["y"] = self._default_pos()   # esquina sup. derecha
        self.root.geometry(f"{self.win['w']}x{self.win['h']}+{self.win['x']}+{self.win['y']}")
        self.root.protocol("WM_DELETE_WINDOW", self._close_click)

        self.f_title  = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_body   = tkfont.Font(family="Segoe UI", size=10)
        self.f_small  = tkfont.Font(family="Segoe UI", size=8)
        self.f_strike = tkfont.Font(family="Segoe UI", size=10, overstrike=True)

        self._win_icon = None
        self._apply_win_icon()

        self._autostart_var = tk.BooleanVar(value=autostart_enabled())
        if self._autostart_var.get():
            set_autostart(True)          # re-escribe la ruta actual por si el archivo se movió
        self._theme_var = tk.StringVar(value=self.win["theme"])

        self._build_header()
        self._build_body()
        self._build_footer()
        self._show_expanded()

        if self.win["collapsed"]:
            self._collapse(save=False)

        self.render()

        self.root.bind("<FocusOut>", lambda e: self.root.after(200, self._on_focus_evt))
        self.root.bind("<FocusIn>", lambda e: self.root.after(1, self._on_focus_evt))
        self.root.bind("<Control-z>", self._undo_delete)
        self.root.after(350, self._pin_to_desktop)
        self.root.after(500, self._snap_onscreen)   # recupera la ventana si quedó fuera de pantalla
        self.root.after(30000, self._autosave)
        self.root.after(4000, self._keep_low)

        if IS_WIN:
            threading.Thread(target=self._hotkey_loop, daemon=True).start()
            self.root.after(150, self._poll_summon)
            self._register_toast()
            self.tray = Tray()
            self.root.after(400, self._poll_tray)
            self.root.after(600, self._sync_tray)
            self.root.after(8000, self._due_watch)

    # ------------------------------------------------------------------ bandeja (tray)
    def _poll_tray(self):
        try:
            while True:
                act = self.tray.queue.get_nowait()
                if act == "show":
                    self._tray_reveal()
                elif act == "toggle":
                    if self._hidden or not self.root.winfo_viewable():
                        self._tray_reveal()
                    else:
                        self._hidden = True
                        self.root.withdraw()
                elif act == "options":
                    self._tray_reveal()
                    self._header_menu()
                elif act == "wintheme":
                    if self.win.get("theme", "auto") == "auto":
                        self._set_theme("auto")
                    self._sync_tray()
                elif act == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(180, self._poll_tray)

    def _tray_reveal(self):
        if self._hidden:
            self._hidden = False
            self.root.deiconify()
        self._summon()

    def _close_click(self, _=None):
        """La ✕: manda a la bandeja (como Discord) o cierra, según Opciones."""
        if self.win.get("close_to_tray", True) and self.tray and self.tray.ok:
            self._hidden = True
            self.root.withdraw()
            if not self.win.get("tray_hint_shown"):
                self.win["tray_hint_shown"] = True
                self.save()
                self.tray.balloon(
                    APP_NAME,
                    "Sigue corriendo en la bandeja. Clic derecho en el icono → "
                    "Salir para cerrarlo.")
        else:
            self.quit()

    def _sync_tray(self):
        if not self.tray:
            return
        pend = sum(1 for t in self.tasks if not t.get("done"))
        tip = APP_NAME if not pend else f"{APP_NAME} — {pend} pendiente{'s' if pend != 1 else ''}"
        self.tray.update(tip, CUR_THEME == "dark")   # el icono acompaña al tema del widget

    def _due_watch(self):
        """Cada 30 min: avisa (globo del tray) por tareas atrasadas o que vencen hoy."""
        ready = bool(self.tray and self.tray.ok)
        if ready:
            self._scan_due()
        # si el tray todavía no terminó de crearse, reintentar pronto
        self._due_after = self.root.after(1_800_000 if ready else 5000, self._due_watch)

    def _scan_due(self):
        if not (self.win.get("due_alerts", True) and self.tray and self.tray.ok):
            return
        today = date.today()
        if self._due_day != today:            # día nuevo: se vuelve a avisar
            self._due_day = today
            self._due_notified = set()
        venc = []
        for t in self.tasks:
            if t.get("done") or t.get("id") in self._due_notified:
                continue
            try:
                d = date.fromisoformat(t.get("due") or "")
            except ValueError:
                continue
            if d <= today:
                venc.append((d, t))
        if not venc:
            return
        for _, t in venc:
            self._due_notified.add(t.get("id"))
        if len(venc) == 1:
            d, t = venc[0]
            atraso = (today - d).days
            estado = "vence hoy" if atraso == 0 else f"atrasada {atraso}d"
            msg = f"«{t['text']}» — {estado}"
        else:
            nombres = ", ".join(t["text"] for _, t in venc[:3])
            if len(venc) > 3:
                nombres += "…"
            msg = f"{len(venc)} tareas atrasadas o para hoy: {nombres}"
        self.tray.balloon(APP_NAME, msg)

    def _apply_win_icon(self):
        """Icono de los diálogos (Opciones) según el tema; default=True lo heredan."""
        try:
            self._win_icon = tk.PhotoImage(
                data=_WIN_ICON_B64["dark" if CUR_THEME == "dark" else "light"])
            self.root.iconphoto(True, self._win_icon)
        except tk.TclError:
            pass

    def _register_toast(self):
        """(Re)registra el AUMID con el icono del tema actual, para que los
        avisos de vencimiento queden en el Centro de notificaciones."""
        if IS_WIN:
            want = "dark" if CUR_THEME == "dark" else "light"
            win_register_app_id(_tray_ico_file(want))

    # ------------------------------------------------------------------ UI
    def _build_header(self):
        h = tk.Frame(self.root, bg=BG_HEADER, height=30)
        h.pack(fill="x")
        h.pack_propagate(False)
        self.header = h

        title = tk.Label(h, text="  Tareas", bg=BG_HEADER, fg=FG, font=self.f_title)
        self.title_lbl = title
        title.pack(side="left")

        btn_close = make_icon(h, "x", bg=BG_HEADER, command=self._close_click)
        btn_close.pack(side="right", padx=(2, 6))

        btn_col = make_icon(h, "minus", bg=BG_HEADER,
                            command=lambda e: self.toggle_collapse())
        btn_col.pack(side="right", padx=2)

        btn_cfg = make_icon(h, "settings", bg=BG_HEADER, command=self._header_menu)
        btn_cfg.pack(side="right", padx=2)

        # contador discreto por prioridad (tareas pendientes)
        cnt = tk.Frame(h, bg=BG_HEADER)
        cnt.pack(side="right", padx=8)
        self.cnt_lbl = {}
        for p in ("alta", "media", "baja"):
            lbl = tk.Label(cnt, text="●0", bg=BG_HEADER, fg=PRIO_COLOR[p], font=self.f_small)
            lbl.pack(side="left", padx=2)
            self.cnt_lbl[p] = lbl
        self._tooltip(cnt, "Pendientes por prioridad: alta / media / baja")

        for w in (h, title):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)
            w.bind("<Button-3>", self._header_menu)
        title.bind("<Double-Button-1>", lambda e: self.toggle_collapse())

    def _header_menu(self, event=None):
        """Panel de Opciones: tema, iniciar con Windows, opacidad sin foco."""
        if getattr(self, "_settings", None) and self._settings.winfo_exists():
            self._settings.lift()
            self._settings.focus_force()
            return
        t = tk.Toplevel(self.root)
        self._settings = t
        t.title("Opciones")
        t.configure(bg=BG, padx=14, pady=12)
        t.resizable(False, False)
        t.transient(self.root)
        t.attributes("-topmost", True)
        t.geometry(f"+{self.root.winfo_rootx() + 24}+{self.root.winfo_rooty() + 34}")
        t.bind("<Escape>", lambda e: t.destroy())

        def sub(txt):
            tk.Label(t, text=txt, bg=BG, fg=FG_DIM, font=self.f_small,
                     anchor="w").pack(fill="x", pady=(10, 3))

        sub("Tema")
        row = tk.Frame(t, bg=BG)
        row.pack(fill="x")
        for lbl, val in (("Claro", "light"), ("Oscuro", "dark"), ("Auto", "auto")):
            tk.Radiobutton(row, text=lbl, value=val, variable=self._theme_var,
                           command=lambda v=val: (self._set_theme(v), t.destroy()),
                           bg=BG, fg=FG, selectcolor=BG_INPUT, activebackground=BG,
                           activeforeground=FG, font=self.f_small,
                           takefocus=0).pack(side="left", padx=(0, 6))

        def chk(text, var, cmd, pad):
            tk.Checkbutton(t, text=text, variable=var, command=cmd, bg=BG, fg=FG,
                           selectcolor=BG_INPUT, activebackground=BG, activeforeground=FG,
                           font=self.f_small, anchor="w",
                           takefocus=0).pack(fill="x", pady=pad)

        self._pin_var = tk.BooleanVar(value=self._pinned())
        chk("Mantener siempre visible (sobre las demás ventanas)", self._pin_var,
            self._toggle_pinned, (10, 0))
        if IS_WIN:
            chk("Iniciar con Windows", self._autostart_var, self._toggle_autostart, (2, 0))
            self._tray_var = tk.BooleanVar(value=self.win.get("close_to_tray", True))
            chk("Al cerrar, minimizar a la bandeja", self._tray_var,
                self._toggle_close_to_tray, (2, 0))
            self._due_var = tk.BooleanVar(value=self.win.get("due_alerts", True))
            chk("Avisar cuando una tarea vence", self._due_var,
                self._toggle_due_alerts, (2, 0))

        sub("Opacidad cuando no está en foco")
        cur = int(round((self.win.get("dim_opacity") or WIN_ALPHA_DIM) * 100))
        track = "#4a4a47" if CUR_THEME == "dark" else "#c9c9d2"
        sc = tk.Scale(t, from_=25, to=100, orient="horizontal", bg=BG, fg=FG_DIM,
                      troughcolor=track, activebackground=ACCENT, highlightthickness=0,
                      bd=0, sliderrelief="raised", font=self.f_small, length=220,
                      command=self._on_opacity_slide)
        sc.set(cur)
        sc.pack(fill="x")

        tk.Button(t, text="Listo", command=t.destroy, bg=BG_INPUT, fg=FG,
                  activebackground=ACCENT, relief="flat", font=self.f_small,
                  takefocus=0).pack(pady=(12, 0))
        t.focus_force()

    def _on_opacity_slide(self, val):
        v = max(0.20, int(float(val)) / 100)
        self.win["dim_opacity"] = v
        try:                       # preview en vivo (la ventana está sin foco ahora)
            self.root.attributes("-alpha", v)
        except tk.TclError:
            pass
        self.save()

    def _toggle_autostart(self):
        want = self._autostart_var.get()
        if not set_autostart(want):
            self._autostart_var.set(not want)      # falló: dejar el check como estaba

    def _toggle_close_to_tray(self):
        self.win["close_to_tray"] = self._tray_var.get()
        self.save()

    def _toggle_due_alerts(self):
        self.win["due_alerts"] = self._due_var.get()
        self.save()
        if self.win["due_alerts"]:
            self._due_notified.clear()      # re-evaluar todo y avisar ahora
            self._scan_due()

    def _build_body(self):
        self.body = tk.Frame(self.root, bg=BG)

        self.canvas = tk.Canvas(self.body, bg=BG, highlightthickness=0)
        self.scroll = tk.Scrollbar(self.body, orient="vertical", command=self.canvas.yview)
        self.list_frame = tk.Frame(self.canvas, bg=BG)
        self.list_win = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.list_frame.bind("<Configure>",
                             lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

        add = tk.Frame(self.root, bg=BG_HEADER, height=42)
        add.pack_propagate(False)          # alto fijo: la fila no salta al redimensionar
        self.add_bar = add

        # Orden de packing pensado para que al achicar la ventana se comprima SOLO
        # el campo de texto: los botones fijos se packean primero y conservan su
        # tamaño; el Entry (width=1 + expand) absorbe todo el cambio de ancho.
        self.prio_dot = tk.Label(add, text="●", bg=BG_HEADER, fg=PRIO_COLOR[self._new_prio],
                                 font=self.f_body, cursor="hand2", width=2)
        self.prio_dot.pack(side="left", padx=(6, 2), pady=6)
        self.prio_dot.bind("<Button-1>", self._cycle_new_prio)
        self._tooltip(self.prio_dot, "Prioridad de la nueva tarea (clic para cambiar)")

        btn_add = make_icon(add, "plus", bg=BG_HEADER, command=lambda e: self.add_task())
        btn_add.pack(side="right", padx=(4, 6), pady=6)

        due_wrap = RoundEntry(add, small=True, bg=BG_INPUT, fg=FG_DIM,
                              insertbackground=FG, font=self.f_small,
                              width=6, justify="center")
        due_wrap.configure(width=62, height=27)
        due_wrap.pack_propagate(False)
        due_wrap.pack(side="right", padx=2, pady=6)
        self._due_wrap = due_wrap
        self.e_due = due_wrap.entry
        self._placeholder(self.e_due, "venc.")
        self._limit_to_date(self.e_due)
        self.e_due.bind("<Return>", lambda e: self.add_task())

        text_wrap = RoundEntry(add, bg=BG_INPUT, fg=FG, insertbackground=FG,
                               font=self.f_body, width=1)
        text_wrap.configure(height=29)
        text_wrap.pack_propagate(False)
        text_wrap.pack(side="left", fill="x", expand=True, padx=(2, 2), pady=6)
        self._text_wrap = text_wrap
        self.e_text = text_wrap.entry
        self.e_text.bind("<Return>", lambda e: self.add_task())

    def _build_footer(self):
        # Franja fina abajo, sin icono: arrastrarla redimensiona la ventana.
        f = tk.Frame(self.root, bg=BG_HEADER, height=10, cursor="sizing")
        f.pack_propagate(False)
        self.footer = f
        f.bind("<Button-1>", self._resize_start)
        f.bind("<B1-Motion>", self._resize_move)
        f.bind("<ButtonRelease-1>", self._resize_end)

    def _show_expanded(self):
        self.footer.pack(fill="x", side="bottom")
        self.add_bar.pack(fill="x", side="bottom")
        self.body.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ render
    def render(self):
        self._editing = False        # cualquier edición inline en curso ya no existe
        for w in self.list_frame.winfo_children():
            w.destroy()

        wrap = max(140, self.win["w"] - 108)
        order = sorted(
            range(len(self.tasks)),
            key=lambda i: (
                self.tasks[i]["done"],
                self.tasks[i].get("due") or "9999-99-99",
                PRIO_RANK.get(self.tasks[i].get("priority", "media"), 1),
            ),
        )

        if not self.tasks:
            tk.Label(self.list_frame, text="Sin tareas. Agregá una abajo 👇",
                     bg=BG, fg=FG_DIM, font=self.f_body).pack(pady=18)
        else:
            for idx in order:
                self._row(idx, self.tasks[idx], wrap)

        done_n = sum(1 for t in self.tasks if t.get("done"))
        if self._undo:
            self._footer_action(f"Tarea borrada  ·  Deshacer", self._undo_delete)
        elif done_n:
            self._footer_action(f"Limpiar {done_n} completada{'s' if done_n != 1 else ''}",
                                self._clear_done)

        counts = {"alta": 0, "media": 0, "baja": 0}
        pend = 0
        for t in self.tasks:
            if not t["done"]:
                counts[t.get("priority", "media")] += 1
                pend += 1
        for p, lbl in self.cnt_lbl.items():
            lbl.config(text=f"●{counts[p]}")
        self.title_lbl.config(
            text=f"  Tareas · {pend}" if (self.win["collapsed"] and pend) else "  Tareas")

        self.root.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._sync_scrollbar()
        self._sync_tray()
        self.save()

    def _footer_action(self, text, cmd):
        """Enlace discreto al pie de la lista (limpiar completadas / deshacer)."""
        lbl = tk.Label(self.list_frame, text=text, bg=BG, fg=FG_DIM,
                       font=self.f_small, cursor="hand2")
        lbl.pack(pady=(6, 8))
        lbl.bind("<Button-1>", lambda e: cmd())
        lbl.bind("<Enter>", lambda e: lbl.config(fg=ACCENT))
        lbl.bind("<Leave>", lambda e: lbl.config(fg=FG_DIM))

    def _row(self, idx, task, wrap):
        row = tk.Frame(self.list_frame, bg=BG_ROW)
        row.pack(fill="x", padx=6, pady=2)

        box = tk.Label(row, text="✔" if task["done"] else "○", bg=BG_ROW,
                       fg=ACCENT if task["done"] else FG_DIM,
                       font=self.f_body, cursor="hand2", width=2)
        box.pack(side="left", padx=(4, 2), pady=4)
        box.bind("<Button-1>", lambda e, i=idx: self.toggle_done(i))

        dot = tk.Label(row, text="●", bg=BG_ROW,
                       fg=PRIO_COLOR.get(task.get("priority", "media"), FG_DIM),
                       font=self.f_small, cursor="hand2")
        dot.pack(side="left")
        dot.bind("<Button-1>", lambda e, i=idx: self.cycle_prio(i))

        mid = tk.Frame(row, bg=BG_ROW)
        mid.pack(side="left", fill="x", expand=True, padx=6)

        txt = tk.Label(mid, text=task["text"], bg=BG_ROW,
                       fg=FG_DIM if task["done"] else FG,
                       font=self.f_strike if task["done"] else self.f_body,
                       anchor="w", justify="left", wraplength=wrap)
        txt.pack(fill="x", anchor="w")
        txt.bind("<Double-Button-1>", lambda e, i=idx, m=mid: self._edit_inline(i, m, "text"))

        dl, dcolor = due_label(task.get("due", ""))
        due = tk.Label(mid, text=dl or "＋ fecha", bg=BG_ROW,
                       fg=dcolor if dl else FG_DIM, font=self.f_small,
                       anchor="w", cursor="hand2")
        due.pack(fill="x", anchor="w")
        due.bind("<Double-Button-1>", lambda e, i=idx, m=mid: self._edit_inline(i, m, "due"))
        due.bind("<Button-1>", lambda e, i=idx, m=mid: self._edit_inline(i, m, "due"))

        for w in (row, mid, txt):
            w.bind("<Button-3>", lambda e, i=idx, m=mid: self._context_menu(e, i, m))

        dele = tk.Label(row, text="✕", bg=BG_ROW, fg=BG_ROW, font=self.f_small,
                        cursor="hand2", width=2)
        dele.pack(side="right", padx=4)
        dele.bind("<Button-1>", lambda e, i=idx: self.delete_task(i))
        row.bind("<Enter>", lambda e, d=dele: d.config(fg=FG_DIM))
        row.bind("<Leave>", lambda e, d=dele: d.config(fg=BG_ROW))
        dele.bind("<Enter>", lambda e, d=dele: d.config(fg=OVERDUE))

    # ------------------------------------------------------------------ edición inline
    def _edit_inline(self, idx, mid, field):
        self._editing = True
        for child in mid.winfo_children():
            child.pack_forget()

        wrap = RoundEntry(mid, small=(field != "text"), bg=BG_INPUT, fg=FG,
                          insertbackground=FG,
                          font=self.f_body if field == "text" else self.f_small,
                          justify="left" if field == "text" else "center")
        wrap.configure(height=26)
        wrap.pack_propagate(False)
        wrap.pack(fill="x", anchor="w", pady=1)
        e = wrap.entry
        if field == "text":
            e.insert(0, self.tasks[idx]["text"])
        else:
            e.insert(0, self.tasks[idx].get("due", "") or "")
            self._limit_to_date(e)
        e.focus_set()
        e.icursor("end")
        e.select_range(0, "end")

        done = {"v": False}

        def finish(commit):
            if done["v"]:
                return
            done["v"] = True
            self._editing = False
            if commit:
                val = e.get().strip()
                if field == "text":
                    if val:
                        self.tasks[idx]["text"] = val
                else:
                    self.tasks[idx]["due"] = parse_due(val)
                    self._due_notified.discard(self.tasks[idx].get("id"))
            self.render()

        e.bind("<Return>", lambda ev: finish(True))
        e.bind("<KP_Enter>", lambda ev: finish(True))
        e.bind("<Escape>", lambda ev: finish(False))
        e.bind("<FocusOut>", lambda ev: finish(True))

    def _context_menu(self, event, idx, mid):
        m = tk.Menu(self.root, tearoff=0, bg=BG_HEADER, fg=FG,
                    activebackground=ACCENT, activeforeground="#fff", relief="flat")
        m.add_command(label="Editar texto", command=lambda: self._edit_inline(idx, mid, "text"))
        m.add_command(label="Cambiar fecha", command=lambda: self._edit_inline(idx, mid, "due"))
        prio = tk.Menu(m, tearoff=0, bg=BG_HEADER, fg=FG,
                       activebackground=ACCENT, activeforeground="#fff")
        for p in ("alta", "media", "baja"):
            prio.add_command(label=p.capitalize(), command=lambda pp=p: self._set_prio(idx, pp))
        m.add_cascade(label="Prioridad", menu=prio)
        m.add_command(
            label="Marcar como " + ("pendiente" if self.tasks[idx]["done"] else "hecha"),
            command=lambda: self.toggle_done(idx))
        m.add_separator()
        m.add_command(label="Eliminar", command=lambda: self.delete_task(idx))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    # ------------------------------------------------------------------ acciones
    def add_task(self):
        text = self.e_text.get().strip()
        if not text:
            return
        due_raw = "" if self._is_placeholder(self.e_due) else self.e_due.get()
        self.tasks.append({
            "id": uuid.uuid4().hex[:8],
            "text": text,
            "done": False,
            "priority": self._new_prio,
            "due": parse_due(due_raw),
            "created": datetime.now().isoformat(timespec="seconds"),
        })
        self.e_text.delete(0, "end")
        self.e_due.delete(0, "end")
        if self.e_due is self.root.focus_get():
            self.e_due._is_ph = False          # con foco: dejar vacío; el placeholder
            self.e_due.config(fg=FG)           # vuelve solo al perder el foco
        else:
            self._set_placeholder(self.e_due, "venc.")
        self.render()

    def toggle_done(self, i):
        self.tasks[i]["done"] = not self.tasks[i]["done"]
        self.render()

    def delete_task(self, i):
        self._undo = (self.tasks.pop(i), i)         # se puede deshacer un rato
        if self._undo_after:
            self.root.after_cancel(self._undo_after)
        self._undo_after = self.root.after(6000, self._clear_undo)
        self.render()

    def _undo_delete(self, _=None):
        if not self._undo:
            return
        task, i = self._undo
        self.tasks.insert(min(i, len(self.tasks)), task)
        self._clear_undo()

    def _clear_undo(self):
        self._undo = None
        if self._undo_after:
            self.root.after_cancel(self._undo_after)
            self._undo_after = None
        self.render()

    def _clear_done(self, _=None):
        self.tasks = [t for t in self.tasks if not t.get("done")]
        self.render()

    def cycle_prio(self, i):
        cur = self.tasks[i].get("priority", "media")
        self.tasks[i]["priority"] = PRIOS[(PRIOS.index(cur) + 1) % len(PRIOS)]
        self.render()

    def _set_prio(self, i, p):
        self.tasks[i]["priority"] = p
        self.render()

    # ------------------------------------------------------------------ colapsar
    def toggle_collapse(self):
        if self.body.winfo_ismapped():
            self._collapse()
        else:
            self._expand()

    def _collapse(self, save=True):
        self.body.pack_forget()
        self.add_bar.pack_forget()
        self.footer.pack_forget()
        self.win["collapsed"] = True
        self.root.update_idletasks()
        self.root.geometry(f"{self.win['w']}x{self.header.winfo_reqheight()}"
                           f"+{self.win['x']}+{self.win['y']}")
        try:
            self.root.attributes("-topmost", True)   # la barrita nunca se pierde
            self.root.attributes("-alpha", WIN_ALPHA)
        except tk.TclError:
            pass
        if save:
            self.save()

    def _expand(self, save=True):
        self._show_expanded()
        self.win["collapsed"] = False
        h = self.win["h"] if self.win.get("sized") else max(self.win["h"], MIN_H)
        self.root.geometry(f"{self.win['w']}x{h}+{self.win['x']}+{self.win['y']}")
        try:
            self.root.attributes("-topmost", False)
        except tk.TclError:
            pass
        self.render()
        self._on_focus_evt()
        self._send_to_bottom()
        if save:
            self.save()

    # ------------------------------------------------------------------ escritorio / z-order
    def _pinned(self):
        return self.win.get("always_on_top", False)

    def _pin_to_desktop(self):
        if not IS_WIN:
            return
        try:
            self._hwnd = u32.GetAncestor(self.root.winfo_id(), GA_ROOT) or self.root.winfo_id()
            ex = _GWLP(self._hwnd, GWL_EXSTYLE)
            _SWLP(self._hwnd, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
            self._apply_glass()
            self._send_to_bottom()
        except Exception as exc:
            print("No se pudo fijar al escritorio:", exc)

    def _toggle_pinned(self):
        self.win["always_on_top"] = self._pin_var.get()
        self._apply_glass()
        if not self._pinned():
            self._send_to_bottom()
        self.save()

    # ------------------------------------------------------------------ estética / tema
    def _has_focus(self):
        try:
            return self.root.focus_displayof() is not None
        except (KeyError, tk.TclError):
            return False

    def _apply_glass(self):
        """Translucidez + acrylic blur + marco acorde al tema."""
        dark = resolve_theme(self.win.get("theme", "auto")) == "dark"
        win_dwm_flags(self._hwnd, dark)
        self._on_focus_evt()

    def _on_focus_evt(self):
        """Con foco → panel sólido (casi opaco, sin blur), para trabajar.
        Sin foco → translúcido con el blur del escritorio detrás, se funde al fondo.
        "Siempre visible" → siempre sólido y arriba de todo."""
        if self.win["collapsed"]:
            return
        if self._pinned():
            try:
                self.root.attributes("-alpha", WIN_ALPHA)
                self.root.attributes("-topmost", True)
            except tk.TclError:
                pass
            if IS_WIN and self._hwnd:
                win_acrylic(self._hwnd, WIN_TINT, enabled=False)
                self._glass_on = False
            return
        focused = self._has_focus()
        dim_a = self.win.get("dim_opacity") or WIN_ALPHA_DIM
        try:
            self.root.attributes("-alpha", WIN_ALPHA if focused else dim_a)
        except tk.TclError:
            pass
        want_glass = (not focused) and WIN_ACRYLIC and not self._dragging
        if IS_WIN and self._hwnd:
            win_acrylic(self._hwnd, WIN_TINT, enabled=want_glass)
            self._glass_on = want_glass
        if not focused:
            self._maybe_lower()

    def _glass_suppress(self):
        """Apaga el blur mientras se arrastra/redimensiona (evita tirones en Win10)."""
        self._dragging = True
        if self._glass_on and IS_WIN and self._hwnd:
            win_acrylic(self._hwnd, WIN_TINT, enabled=False)
            self._glass_on = False

    def _glass_resume(self):
        self._dragging = False
        self._on_focus_evt()

    def _set_theme(self, choice):
        self.win["theme"] = choice
        self._theme_var.set(choice)
        apply_theme(resolve_theme(choice))
        keep = ""
        try:
            keep = self.e_text.get()
        except Exception:
            pass
        for fr in (self.header, self.body, self.add_bar, self.footer):
            fr.destroy()
        self.root.configure(bg=BG, highlightbackground=BORDER, highlightcolor=BORDER)
        self._build_header()
        self._build_body()
        self._build_footer()
        self._show_expanded()
        if self.win["collapsed"]:
            self._collapse(save=False)
        try:
            if keep:
                self._clear_placeholder(self.e_text)
                self.e_text.insert(0, keep)
        except Exception:
            pass
        self.render()
        self._apply_win_icon()
        self._register_toast()
        self._apply_glass()
        self._send_to_bottom()
        self.save()

    def _send_to_bottom(self):
        if IS_WIN and self._hwnd and not self.win["collapsed"] and not self._pinned():
            u32.SetWindowPos(self._hwnd, HWND_BOTTOM, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _maybe_lower(self):
        if self._editing or self.win["collapsed"] or self._hidden or self._pinned():
            return
        if self.root.focus_displayof() is None:
            self._send_to_bottom()

    def _keep_low(self):
        self._maybe_lower()
        self.root.after(4000, self._keep_low)

    def _summon(self):
        if self._hidden:
            self._hidden = False
            self.root.deiconify()
        if self.win["collapsed"]:
            self._expand()
        try:
            self.root.attributes("-topmost", True)
            self.root.after(700, lambda: self._drop_topmost())
        except tk.TclError:
            pass
        self.root.lift()
        self.root.focus_force()
        self.e_text.focus_set()

    def _drop_topmost(self):
        if not self.win["collapsed"] and not self._pinned():
            try:
                self.root.attributes("-topmost", False)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ atajo global (Win)
    def _hotkey_loop(self):
        self._hk_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        if not u32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_T):
            print("Ctrl+Alt+T ya está en uso por otro programa; el atajo no estará disponible.")
            return
        msg = wintypes.MSG()
        while True:
            r = u32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r in (0, -1):              # 0 = WM_QUIT (lo manda quit())
                break
            if msg.message == WM_HOTKEY:
                self._summon_flag = True      # bool: seguro entre threads (GIL)
        u32.UnregisterHotKey(None, 1)         # desde el mismo hilo que registró

    def _poll_summon(self):
        if self._summon_flag:
            self._summon_flag = False
            self._summon()
        self.root.after(150, self._poll_summon)

    # ------------------------------------------------------------------ resize
    def _resize_start(self, e):
        self._rs = (e.x_root, e.y_root, self.root.winfo_width(), self.root.winfo_height())
        self._rs_target = None
        self._rs_pending = None
        self._glass_suppress()

    def _resize_move(self, e):
        if not self._rs:
            return
        x0, y0, w0, h0 = self._rs
        self._rs_target = (max(MIN_W, w0 + (e.x_root - x0)),
                           max(MIN_H, h0 + (e.y_root - y0)))
        if self._rs_pending is None:                 # coalescer: ~1 cambio por frame
            self._rs_pending = self.root.after(16, self._apply_resize)

    def _apply_resize(self):
        self._rs_pending = None
        if not self._rs or not self._rs_target:
            return
        w, h = self._rs_target
        if (w, h) != (self.win["w"], self.win["h"]):
            self.win["w"], self.win["h"], self.win["sized"] = w, h, True
            self.root.geometry(f"{w}x{h}")

    def _resize_end(self, e):
        if self._rs_pending is not None:
            self.root.after_cancel(self._rs_pending)
            self._rs_pending = None
        self._apply_resize()
        self._rs = None
        self.render()          # recalcula el wraplength de los textos
        self._glass_resume()
        self.save()

    # ------------------------------------------------------------------ util
    def _on_canvas_configure(self, e):
        self.canvas.itemconfig(self.list_win, width=e.width)
        self._sync_scrollbar()

    def _sync_scrollbar(self):
        need = self.list_frame.winfo_reqheight() > self.canvas.winfo_height()
        if need and not self.scroll.winfo_ismapped():
            self.scroll.pack(side="right", fill="y")
        elif not need and self.scroll.winfo_ismapped():
            self.scroll.pack_forget()

    def _on_wheel(self, event):
        # bind_all es global: sólo scrollear si el puntero está sobre la lista
        try:
            w = self.root.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        while w is not None:
            if w is self.canvas or w is self.list_frame:
                break
            w = getattr(w, "master", None)
        else:
            return
        if self.list_frame.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _cycle_new_prio(self, _=None):
        self._new_prio = PRIOS[(PRIOS.index(self._new_prio) + 1) % len(PRIOS)]
        self.prio_dot.config(fg=PRIO_COLOR[self._new_prio])

    def _drag_start(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        self._glass_suppress()

    def _drag_move(self, e):
        x, y = self._clamp_pos(e.x_root - self._drag[0], e.y_root - self._drag[1])
        self.root.geometry(f"+{x}+{y}")
        self.win["x"], self.win["y"] = x, y

    def _drag_end(self, _e=None):
        self._snap_onscreen()
        self._glass_resume()
        self.save()

    # ------------------------------------------------------------------ mantener en pantalla
    def _virtual_rect(self):
        """Rectángulo que abarca TODOS los monitores (x, y, w, h)."""
        if IS_WIN:
            try:
                return (u32.GetSystemMetrics(SM_XVIRTUALSCREEN),
                        u32.GetSystemMetrics(SM_YVIRTUALSCREEN),
                        u32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
                        u32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
            except OSError:
                pass
        return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())

    def _work_area_at(self, px, py):
        """Área útil (sin barra de tareas) del monitor que contiene el punto."""
        if IS_WIN:
            try:
                mon = u32.MonitorFromPoint(_POINT(int(px), int(py)),
                                           MONITOR_DEFAULTTONEAREST)
                mi = _MONITORINFO()
                mi.cbSize = ctypes.sizeof(_MONITORINFO)
                if u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
                    r = mi.rcWork
                    return (r.left, r.top, r.right - r.left, r.bottom - r.top)
            except OSError:
                pass
        return self._virtual_rect()

    def _default_pos(self):
        """Posición inicial: esquina superior derecha del monitor primario, con margen."""
        margin = 14
        w = self.win["w"]
        sw = self.root.winfo_screenwidth()
        ax, ay, aw, ah = self._work_area_at(sw - 40, 40)
        return ax + aw - w - margin, ay + margin

    def _clamp_pos(self, x, y, keep=90):
        """Durante el arrastre: no dejar que se pierda del área de todos los monitores.
        Deja pasar el movimiento entre pantallas, pero siempre con una parte visible."""
        vx, vy, vw, vh = self._virtual_rect()
        w = self.root.winfo_width()
        hh = self.header.winfo_height() or 30
        keep = min(keep, w)
        x = max(vx - (w - keep), min(x, vx + vw - keep))     # franja horizontal visible
        y = max(vy, min(y, vy + vh - hh))                    # barra de título siempre visible
        return x, y

    def _snap_onscreen(self):
        """Al soltar (o al arrancar): meter la ventana entera dentro de un monitor."""
        w, h = self.root.winfo_width(), self.root.winfo_height()
        cx = self.root.winfo_x() + w // 2
        cy = self.root.winfo_y() + h // 2
        ax, ay, aw, ah = self._work_area_at(cx, cy)
        x = max(ax, min(self.root.winfo_x(), ax + aw - w)) if w <= aw else ax
        y = max(ay, min(self.root.winfo_y(), ay + ah - h)) if h <= ah else ay
        self.root.geometry(f"+{x}+{y}")
        self.win["x"], self.win["y"] = x, y

    def _limit_to_date(self, entry):
        vcmd = (self.root.register(self._validate_date), "%P", "%W")
        entry.config(validate="key", validatecommand=vcmd)

    def _validate_date(self, proposed, wname):
        try:
            w = self.root.nametowidget(wname)
        except KeyError:
            w = None
        if w is not None and proposed == getattr(w, "_ph", None):
            return True
        if len(proposed) > 10:
            return False
        return all(c.isdigit() or c in "/-" for c in proposed)

    def _placeholder(self, entry, text):
        entry._ph = text
        self._set_placeholder(entry, text)
        entry.bind("<FocusIn>", lambda e: self._clear_placeholder(entry))
        entry.bind("<FocusOut>", lambda e: self._restore_placeholder(entry))

    def _set_placeholder(self, entry, text):
        entry.delete(0, "end")
        entry.insert(0, text)
        entry.config(fg=FG_DIM)
        entry._is_ph = True

    def _clear_placeholder(self, entry):
        if getattr(entry, "_is_ph", False):
            entry.delete(0, "end")
            entry.config(fg=FG)
            entry._is_ph = False

    def _restore_placeholder(self, entry):
        if not entry.get().strip():
            self._set_placeholder(entry, entry._ph)

    def _is_placeholder(self, entry):
        return getattr(entry, "_is_ph", False)

    def _tooltip(self, widget, text):
        tip = {"win": None}

        def show(_):
            if tip["win"]:
                return
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height() + 2
            tw = tk.Toplevel(widget)
            tw.overrideredirect(True)
            tw.attributes("-topmost", True)
            tw.configure(bg=BORDER)
            tw.geometry(f"+{x}+{y}")
            tk.Label(tw, text=text, bg=BG_HEADER, fg=FG, font=self.f_small,
                     padx=7, pady=3).pack(padx=1, pady=1)     # borde fino con BORDER
            tip["win"] = tw

        def hide(_):
            if tip["win"]:
                tip["win"].destroy()
                tip["win"] = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    # ------------------------------------------------------------------ ciclo de vida
    def save(self):
        self.state["tasks"] = self.tasks
        save_state(self.state)

    def _autosave(self):
        self.save()
        self.root.after(30000, self._autosave)

    def quit(self):
        self.save()
        if IS_WIN:
            try:                        # despierta al hilo del atajo para que salga limpio
                if self._hk_tid:
                    u32.PostThreadMessageW(self._hk_tid, WM_QUIT, 0, 0)
                else:
                    u32.UnregisterHotKey(None, 1)
            except Exception:
                pass
            if self.tray:
                self.tray.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    single_instance_or_exit()     # una sola instancia: la 2da avisa a la 1ra y sale
    win_register_app_id()         # AUMID antes de crear ventanas (toasts que persisten)
    TaskWidget().run()
