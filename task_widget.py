"""
Task Widget - un tracker de tareas para el escritorio de Windows.

- Vive pegado al escritorio: DETRAS de las ventanas normales, no se superpone.
  Al hacerle clic sube; al hacer clic afuera vuelve a bajar.
- Colapsado queda como una barrita SIEMPRE VISIBLE (arriba de todo): siempre
  se puede volver a abrir con doble clic en el título o el botón "–".
- Atajo global  Ctrl + Alt + T  para traerlo al frente desde cualquier lado.
- Ventana redimensionable (agarre "◢" abajo a la derecha).
- Editar: doble clic en el texto o en la fecha de una tarea; clic derecho = menú.
- Botón "⚙" (o clic derecho en la barra): "Iniciar con Windows".
- Todo se guarda en tasks.json, al lado de este archivo.

Requisitos: solo Python 3.8+ (tkinter viene con el instalador de Windows).
Arranque:  pythonw task_widget.py
"""

import json
import os
import sys
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


# --------------------------------------------------------------------------- #
#  Persistencia
# --------------------------------------------------------------------------- #

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
DATA_FILE = os.path.join(APP_DIR, "tasks.json")

DEFAULT_STATE = {
    "window": {"x": 120, "y": 120, "w": 310, "h": 340, "collapsed": False,
               "sized": False, "theme": "auto"},
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
    "dark": {
        "bg":       "#1f2024",   # cuerpo
        "header":   "#2b2c31",   # barra superior / inferior (capa "vidrio")
        "row":      "#303137",   # fila de tarea
        "row_hi":   "#3a3b42",   # fila hover
        "input":    "#3b3c44",
        "fg":       "#f2f2f5",
        "fg_dim":   "#9a9ba4",
        "accent":   "#4c9bff",
        "overdue":  "#ff6b60",
        "border":   "#54555f",   # hairline
        "alpha":    0.93,        # con foco
        "alpha_dim": 0.80,       # sin foco: más translúcido/oscuro
        "acrylic":  True,        # el blur real de Windows queda bien en oscuro
        "tint":     0xDC1F1F24,  # 0xAABBGGRR — con foco
        "tint_dim": 0xF00C0C10,  # sin foco: casi negro, más opaco
    },
    "light": {
        "bg":       "#f4f4f6",
        "header":   "#eaeaee",
        "row":      "#ffffff",
        "row_hi":   "#f0f0f3",
        "input":    "#ffffff",
        "fg":       "#1d1d1f",
        "fg_dim":   "#71717a",
        "accent":   "#0a84ff",
        "overdue":  "#d70015",
        "border":   "#c4c4ce",
        "alpha":    0.96,        # el acrylic claro se lava sobre fondos claros → solo translucidez
        "alpha_dim": 0.90,
        "acrylic":  False,
        "tint":     0x00000000,
        "tint_dim": 0x00000000,
    },
}
PRIO_COLORS = {
    "dark":  {"alta": "#ff6b60", "media": "#ffb340", "baja": "#4ad06a"},
    "light": {"alta": "#e5342b", "media": "#d98600", "baja": "#28a745"},
}

# variables "vivas" que lee todo el resto del código; apply_theme() las reescribe
BG = BG_HEADER = BG_ROW = BG_ROW_HI = BG_INPUT = FG = FG_DIM = ACCENT = OVERDUE = BORDER = None
PRIO_COLOR = {}
WIN_ALPHA = WIN_ALPHA_DIM = 0.9
WIN_TINT = WIN_TINT_DIM = 0
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
    global PRIO_COLOR, WIN_ALPHA, WIN_ALPHA_DIM, WIN_TINT, WIN_TINT_DIM, WIN_ACRYLIC, CUR_THEME
    CUR_THEME = name
    t = THEMES[name]
    BG, BG_HEADER, BG_ROW, BG_ROW_HI = t["bg"], t["header"], t["row"], t["row_hi"]
    BG_INPUT, FG, FG_DIM = t["input"], t["fg"], t["fg_dim"]
    ACCENT, OVERDUE, BORDER = t["accent"], t["overdue"], t["border"]
    PRIO_COLOR = PRIO_COLORS[name]
    WIN_ALPHA, WIN_ALPHA_DIM = t["alpha"], t["alpha_dim"]
    WIN_TINT, WIN_TINT_DIM = t["tint"], t["tint_dim"]
    WIN_ACRYLIC = t["acrylic"]


PRIOS = ["baja", "media", "alta"]
PRIO_RANK  = {"alta": 0, "media": 1, "baja": 2}


# --------------------------------------------------------------------------- #
#  Iconos  —  Lucide (lucide.dev, licencia ISC). SVG rasterizados a PNG y
#  embebidos en base64: variantes idle/hover para tema claro y oscuro.
#  Tamaños: 22 px (x, minus, settings), 26 px (plus), 15 px (grip).
# --------------------------------------------------------------------------- #

_ICON_B64 = {
    'dark_grip_hot': (
        'iVBORw0KGgoAAAANSUhEUgAAAA8AAAAPCAYAAAA71pVKAAABLklEQVR4AaySMU7DMBSGY6dKIoJeEzgASGyIEyAGuAF0hImFQ7Ew'
        'wUg5AWLqCRAbgguUOC5BqdXEvJ8McTFSBxr5+ff3/P+JI1kG/3jWG9babmtdPWitD3Eo1iPmcVnaLbBb3pejaJ6x4dhaucsasO6w'
        'nsTxPGddGnKJGJIkeSVKs+Fw844xYL0Fow92ywu7m6vWXthaOygKfaaU+jkmFIz+75d54aqqDsIwvJcyuuzMgysw9/c77mcvnKbp'
        'c9M0o7Y1N51tcQ3m/kvH/eyFhRCLPKdxlmUFbFAw+mC3vDA2+f/+7GPPLc9U1/XebPb1UZafFzCynvMlUeiD3fLCxhjFhkch5Btr'
        'IET7zvpkTIw+L/vhhYloypdiRLQxgY15QpSeEokp2C0v7G6uWn8DAAD///vilOEAAAAGSURBVAMA5mZzH4A25dgAAAAASUVORK5C'
        'YII='
    ),
    'dark_grip_idle': (
        'iVBORw0KGgoAAAANSUhEUgAAAA8AAAAPCAYAAAA71pVKAAABQklEQVR4AaySv07CYBTF29pERtRJHDSxLMYnMA72DZSJCNo42EbC'
        'Q/QpMP0kMVUwxkF8AuvkExgXIDrphDJi6B/vwcEbrwmDNj293+/ec9oO19D+cP1vOAzDBXXSulHqfAM/FQRnm3TuNJtX82Au8eXR'
        'aDZPhq0sy1aoarquL9PDTpJ0Dswlwp5X7ruH1bzn7V/A6Lp77S8u98FcIsyH084iHEWReaxaO41Ge/KbqGD0f75MhLvdl/UZXbs2'
        'zfQAZsNMXXCv97oG5hLhYrHwkGRaKY6NUxjT2FBgy1p8BHOJsG3b8ZFb7dRqlXcYUcHog7lEGEPf93/tY8YlTEFwuVpYst5oMSow'
        '0pLs0tIM0QdzifB4/DEkwy3piUT7oT9TvcvlJn06ft8iXK87A1qKEi3HPWyoxNuO4wzAXCLMh9POnwAAAP//ziao0QAAAAZJREFU'
        'AwDtzXAfqTeDmwAAAABJRU5ErkJggg=='
    ),
    'dark_minus_hot': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAAaklEQVR4AeySMQrAIBAEQ1o5LVPmAfn/U/KAlCn1sI/XLF4pSQph'
        'xYMV2UEG1+WnRTDEUgVVwACC+xWqeuRcr1LqPTLWsS6oLThwO3+2HVhEzpTCHmPYRsY61u1f5cD9xdtMMAxSxcQqHgAAAP//QNmh'
        'CQAAAAZJREFUAwDedEAtlrd2OAAAAABJRU5ErkJggg=='
    ),
    'dark_minus_idle': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAAaUlEQVR4AeySsQnAIBBFQ5ZI6QDZKKTNDXVpQzbKAJbZwrP5eKWo'
        'hfDFD1/kHvJwXQYtgiGWKqgCBlDcr1B9d72faPkrE/MsqFYc2M7dtgOLHJ9cZ7BslQl5tnyVA5cXrZ1gGKSKiVUkAAAA//+4d5bV'
        'AAAABklEQVQDAMH7QC10pG1MAAAAAElFTkSuQmCC'
    ),
    'dark_plus': (
        'iVBORw0KGgoAAAANSUhEUgAAABoAAAAaCAYAAACpSkzOAAABgElEQVR4AeRWsUoDQRScW2IRONDaH0jhr1wE2yBYWKTS1vxBYqvV'
        'IRaCpBVMPkWL/IC1wkGKhFtnEjyyIZvc6oUIOd4ct7PvzdzbXbgzWLhOH+1x8mC7xBsxIWwgVKParrQWpFEYJalt5TlGnOwQJ0SN'
        'CA3VqLYjLWn+CMyMRFiDZ5IxUVXE0pS2BM2sRYM0Ahio9KJgxDVL5WHY4hWAKjuhnBOxPLR0TYfezqApo0aIdv0AEEJqmNuQUY0P'
        'peM2AYTSBfPEmozmjyXvh3VAKJlepAUbFZWBD3tkpJN1dwY8tVwccY+EZV65qvGt6O6XbjwBrl+Ai76LzzEgLPPKVc3/7cj3Zr/l'
        'd79Hvjf/4h4Jvnkfr46mvslV/M0QEFbNreGmMtLne02OO6WTJbjsxtFIRoONaX9PGBhjcE+djNhWZPIwr5fRB3K0LcCo1ouCVtry'
        '0NJh2I76UY5z2lTZWSZNaVOX/yi6EyLYoj7rPQ7fiaDTyHyFalTbk5Y0RQrfAAAA///6Xld7AAAABklEQVQDAP/koQkITCDvAAAA'
        'AElFTkSuQmCC'
    ),
    'dark_settings_hot': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAADtklEQVR4AYxTWWgUWRS9t6qm6aWqutNCGIagCDODM8yMzLcgYWYY'
        'BgYRd9xwRQU/RDSiuICiokYFwYAi7vsSxQ9BBIOovyKCoP64EYOE2FZXVXeapPs9z63udFDsxOKevufd5VS9924b9I2P1toArG8s'
        'p1GFe3t7bd8vHPf9Yr6KwrGenp7kaC8YVTgeT3VAZCkz9QHvwZfbdvoQ/Ig2ojC2HkP3bK3preMkfwJ+wfo11vNkJ+AN7TPhIAh+'
        'DYL+zdhyW7FYnAS+C51xfGkXM5eBAazvM1MyHrelbpLU+n7/plwu/AO5utWFP34MpuN+nmitdhLpfeWyfgi/HvDLZXVgqAO8HdxD'
        'fCMgNfuI1G7L4seigVxkkbDW2jJNQ86tDL4QmRXMfIGID1YqgxOzWecp1R7hg4P8OxHvlxpmWmUYxmIiKkOjA/0WeHUqcAQZLFqA'
        'e+m0fc51U8dwnvNdN7kuk8m8CYLizHw+PCkQns0m3iHXJjWOkzpq24nT6O0Cvg/DMAtfFXYcB1ujblzKZDT/JwkB3s5hWLgIf5WZ'
        'FwuE12IsNQLPC/+VXvBu27b74KvCaMARqDZmwhRwp+/7P0syDPtnaM1ziPRzZuNvgXCJSU5q8vn8j4bBNxm9lYpaw8xK4ob8CNJp'
        '5xIz7QAw/NYUiSml/hfPbK52nESXQLjEhnPfTcNaJmdHU5NzHTyyunC0Gv5pFB+uqDGtqSwULzLFD6EuIKOCom1IlJQa6IQn3PYt'
        '8VpXOoKg/y+BcIkN5ZTiG1iXmI2tnhfMBo8sEsaFROMG4QGl9FRMwkvJ4rY7mfVlIp6gtborEC4xyRGepqYE/ol6GnpLeNkBjdFF'
        'mCLhsDoiLYZBDzMZ+44kBAwF207NhZ+FhlMC4bWYlhpBOm3fZqb74C210aVIuDYiMm6tGLcFQVBYGQTF875fbPc8b5zjJK+heYlA'
        'uOeVxiG3V2pQuxoTIn+qVgh3Y3Rz8FVhZlZ41iJggJ/Fto7g6+ZhtNabZuxRLhf8hlxkfX3+BNOsPEFug9Sg9jB6zyAZ++q4ZTLO'
        'Nej/iUvYQsQbiIzJ8AeJKGtZRht8ZLGYCc4uEe+p1WyUHvRObDhu2MZTzOou/F3bXTfx4MOHxGZ8UQi0vnql4/hCi5n+IaISctul'
        'BrV7pUd6Ea9bdMb11Rdk/HjGGNEViI0dM6b4DGf6Ai8Zi7ILkoNvaCMKS1epVFgDfwKCzfA/AGdqMdDGNqpwc3Nz6LqpZa6bTGMi'
        'HNdNLZJYY8lq5hMAAAD//51bUBAAAAAGSURBVAMAYcvZPjmZ4VQAAAAASUVORK5CYII='
    ),
    'dark_settings_idle': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAD+ElEQVR4AaRUW2hcZRD+5pzdJZR6oQ/WXKygsVRRi89CCSoiiIi3'
        'FJPd2Njdk03zUMSmVKI2ESu2sYWCMbt7VrfJbqKNjeKDIIJBtK8ihYIXaqmySSwUaaUP6V7+32/O7gZbmqTQwz9n5p/L98+Zmf84'
        'uMFneHjYIYVu0B1rAo+NzazPZAsft7S2X2ppvfeS70/56XR63VoHrAkcjlwZg8Wr1uKChfxtYeOOs/7oTQHv3z8TAaQTwF+LC2fu'
        'WyhG7ucB5yxMl34J9SuuqzJOpQoPpP3CkO/nB7PZwqOtd5UPMLIJgjnWtzIy0lkSkR8AWReJlIbUR31Zqjc+8icexv+eZeBUavJ5'
        'cXBKgHf5yYeMxUlYu4cZ/luFOdyIqVaqo5QvWmCf+ljIIZbqvRDcnxWDtmAFwMwm5LjOURFUDBBjSz0eMA2RI6Za3tof7zkdePPV'
        '399zmraHIPYD8mkrTtIR7ABQEVfGFIsyIfhubt58O1mbBb5PJqIFb2fUTySi3V68+/X+/t4/fb/wYiZTyCmpTNu8F48Nknf3xbvS'
        '8Xh0grFzArlz48Z7NhCrBry4+PtFbooCuy2Vyj9FubGENf+UQZ9DsyKprDo6CClY6fSxJzWWm+L582cvkNeAmX4F1gxaKxHHxWwm'
        'M7FZjczuBUZvZw1/FTiPK9VkbFcb+GSz+XZxQl9prKma3cRiNVEDph2e1/OZI/IO2HER9xnwsRZPk0HEGUgkuuaUVFZdw0b+HPdN'
        'GptM9nxBOVhB8wKJr+AocsBepQ9UK7yMOBU1GWNc5Q1aBkhx3GDt2zQslcvOLDk4JV8rt9aM+f70Y0oqq65hM+XSl9wviSNvZTJ5'
        'vUzc1kvButTHzZasqTy7a1f3WbWy67Ns1nEItvC2fadUk3FcberDqTlnqpblsEsQOaxYqg8yro9IG6yc7Ovb8a0a6mT7EtGXBXgJ'
        'FseUVFYdWC9SsJLJ2DcWwhuJtvro1ppXH5EiBB281tF0drqPXZ/KZPOj4+O5u5ndCc+L9iqprDrO9EH1IQ1ks1MxHtjBU4oc3X/I'
        'a8BM35gqXmOHHcdFXqxJWaALVva4ofBP4+OTD6qzUjqd2+K44VNMYq/6kD401k7SFjHXG7dkMnqChkfo+KbA7iVtg8gRBmxwQ+4g'
        'ebBEwoNs3K3M8P3Ax8o+jalWzNYVx03/A6zfgUQiNkr6MeyWhoh2GTAduVyuiV8WguAJ6pZCofKI+nhe90GN0Vjql1fQvOXdNUJv'
        'by87jRlANpXK4V+aW9t/A7CJ4NOBjZuV1qrAGlS+EtlNoE9E7B38/BbATgY6Na5CawIPDHRe9uLRnQvzf9y2MH/mFi8Re0V1q2AG'
        'pv8AAAD//xfyB40AAAAGSURBVAMAtzjCRJTCmSAAAAAASUVORK5CYII='
    ),
    'dark_x_hot': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAABO0lEQVR4AezTv04CQRAG8G80BEUsfB6trLQwhMLCxAIbCh6IggoL'
        'bSyMIcbGUp9IvOipjDujHH9mZ7mQUJBAbo+9229/t7e3u4UV/TZwMbFmKrhzXufO1QW3WjtFyqmksgbGdv0MxLfYwyO32zXHhKCg'
        '2pNm96k5n7PwZ+UhhJ9D8BiVfBDDCxR0BPALfoaDkJ85DEy9XoZR1vRwg3J2St274YwaLgwc7kGDEbwsKkYUloYYDpnT8es7I5W+'
        'UlxYGg1eEpW+SVgCWph29V9PlOP7YKTVxCkJT+YUh8F49T5oaDOHC0/Q/yXF7yep1TIvR2GL/i0pM+fOOpeHGNhDJSylLG5g3dIL'
        'vr7Bq18Neeh0sfAb34P5EgvWqeJ5taHZUlu63/+g7vWNdpweQqQu29/L2hFHgGVurR/8CwAA//+mRbdHAAAABklEQVQDAHzO1C2s'
        'MZNuAAAAAElFTkSuQmCC'
    ),
    'dark_x_idle': (
        'iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAABR0lEQVR4AezTP0vEMBgG8DclrXroJ9LJSQc5XATRpQh2uM9zQ7mh'
        'kze4iBzi4qifx8E/aFNS80BajrxJrg43HFy4lyvNk1/TNEloTW0L9wvLlmI6vd+fzeaXVVXt9qnARSzL4CxrzlrSc9XIp7IsRwGT'
        'gKapeka2aXbO3RyDtf54NKEXInEsktHCh3coifaIWvFa13JBTmNwURTfqs4wAy/uokqlp5PJxafjEoMRQNCHD0VheGF0+HCsaff6'
        'oZliLCoIo9PFh6IYG4URsLVn/4mErqV817SiReF+TYkOjfNmyvtBzX32C8I9areU+ZgnpoK7xZW9MEPtlnLXPLTP8RAGh1CEUUNx'
        'BuNIU/f6dqYAl8vFk+RgvNyPawZL+ftAibhetU+Bt/prjGw95Ejnef5ze3N1h4F4cqxw/ENZNuMY9J++zYP/AAAA//9LtcHoAAAA'
        'BklEQVQDADVo2i0JW4iFAAAAAElFTkSuQmCC'
    ),
    'light_grip_hot': (
        'iVBORw0KGgoAAAANSUhEUgAAAA8AAAAPCAYAAAA71pVKAAABJUlEQVR4AaxSMU4DMRDctfKAAF3ufBeJDvECRAE/gJRQ0fAoGioo'
        'CS9AVLwA0SFy53M6IA+IbGYQinxyUAqwPJqd3Z07e2Ujf1j/ay6KYsfa6n40qg94qKqqDq2tp2VZblOnyP5sjBmK6JExMhasELQG'
        'HavqFri3TU9BOOdenWuGXdfcQgr4hpp56hSZOS1uiteZB2VZn+Ku38ckU+NDA6C3M3NRjPdV5S5GvWBnCHKp0BjYHnWKzOz97DlG'
        'majGazZicFcRuuu6F+oUmRnFJYY0bdv2E7GQqREvgd5eZ2bDb3nWVsiarLW7eBQfGNI5u8Bn0AvmqVNk5hDCAg0PGNQbWMAzkfj4'
        'k2dqhczsvX/Ho5jM580Tu8jOtSfMU6fIzGlxU/wFAAD//8idNP8AAAAGSURBVAMADaVqH4mhouAAAAAASUVORK5CYII='
    ),
    'light_grip_idle': (
        'iVBORw0KGgoAAAANSUhEUgAAAA8AAAAPCAYAAAA71pVKAAABRklEQVR4AaySsUrDUBSGb5KSrok+gEI38QnEQd9AO+rkInRoyR2K'
        'SemQoZpIh5SUUnBx0tH6BOLUJxC3oi9Qk44NSfT8Ll48Qgcb8nPOd87/J3e4uvjHs96w53mbUnYeW62LPRyK6r7jeBMp/Q2wKvbn'
        'PDcsMhwYhrFNVei6tqVp2mGe5zZYFQv3+71ZFF1ZpHsYB4PwjnprOOzNwKpYWF2u6lnY9/2KlO5xo+F+HxMVjPnvj7Fwmma7QugP'
        '1ap2BrNpinNwkmQ7YFUsbFnmixBlfbn8vIUxy8QN2LbNV7AqFqbj5VEUTsbjMIERFYw5WBULY0nGP+fYqWKmZrNbWyyyD8dxT2GU'
        'snNCStvtbg2sioXLskjJ8FSWxhtVURTFO9XnSqXAnNqfl4VHo2BOl6Iex5dT2OL4ekp8FATBHKyKhdXlqv4LAAD//3OFf2UAAAAG'
        'SURBVAMA8BpyH7G0Te4AAAAASUVORK5CYII='
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


def _get_icon(key):
    img = _ICON_CACHE.get(key)
    if img is None and key in _ICON_B64:
        img = tk.PhotoImage(data=_ICON_B64[key])
        _ICON_CACHE[key] = img
    return img


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
        self._new_prio = "media"
        self._hwnd = None
        self._editing = False
        self._summon_flag = False
        self._glass_on = False
        self._dragging = False

        self.win.setdefault("theme", "auto")
        apply_theme(resolve_theme(self.win["theme"]))

        self.root = tk.Tk()
        self.root.title("Tareas")
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", WIN_ALPHA)
        self.root.configure(bg=BG, highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=BORDER)
        self.root.geometry(f"{self.win['w']}x{self.win['h']}+{self.win['x']}+{self.win['y']}")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self.f_title = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_body  = tkfont.Font(family="Segoe UI", size=10)
        self.f_small = tkfont.Font(family="Segoe UI", size=8)

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
        self.root.after(350, self._pin_to_desktop)
        self.root.after(500, self._snap_onscreen)   # recupera la ventana si quedó fuera de pantalla
        self.root.after(30000, self._autosave)
        self.root.after(4000, self._keep_low)

        if IS_WIN:
            threading.Thread(target=self._hotkey_loop, daemon=True).start()
            self.root.after(150, self._poll_summon)

    # ------------------------------------------------------------------ UI
    def _build_header(self):
        h = tk.Frame(self.root, bg=BG_HEADER, height=30)
        h.pack(fill="x")
        h.pack_propagate(False)
        self.header = h

        title = tk.Label(h, text="  Tareas", bg=BG_HEADER, fg=FG, font=self.f_title)
        title.pack(side="left")

        btn_close = make_icon(h, "x", bg=BG_HEADER, command=lambda e: self.quit())
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
        m = tk.Menu(self.root, tearoff=0, bg=BG_HEADER, fg=FG,
                    activebackground=ACCENT, activeforeground="#fff", relief="flat")

        tema = tk.Menu(m, tearoff=0, bg=BG_HEADER, fg=FG,
                       activebackground=ACCENT, activeforeground="#fff")
        for lbl, val in (("Claro", "light"), ("Oscuro", "dark"), ("Automático", "auto")):
            tema.add_radiobutton(label=lbl, value=val, variable=self._theme_var,
                                 command=lambda v=val: self._set_theme(v))
        m.add_cascade(label="Tema", menu=tema)

        if IS_WIN:
            m.add_checkbutton(label="Iniciar con Windows", variable=self._autostart_var,
                              command=self._toggle_autostart)
        m.add_separator()
        m.add_command(label="Cerrar", command=self.quit)
        x = event.x_root if event is not None else self.root.winfo_pointerx()
        y = event.y_root if event is not None else self.root.winfo_pointery()
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _toggle_autostart(self):
        want = self._autostart_var.get()
        if not set_autostart(want):
            self._autostart_var.set(not want)      # falló: dejar el check como estaba

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

        add = tk.Frame(self.root, bg=BG_HEADER)
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

        self.e_due = tk.Entry(add, bg=BG_INPUT, fg=FG_DIM, insertbackground=FG,
                              relief="flat", font=self.f_small, width=7, justify="center")
        self.e_due.pack(side="right", padx=2, ipady=4, pady=6)
        self._placeholder(self.e_due, "venc.")
        self._limit_to_date(self.e_due)
        self.e_due.bind("<Return>", lambda e: self.add_task())

        self.e_text = tk.Entry(add, bg=BG_INPUT, fg=FG, insertbackground=FG,
                               relief="flat", font=self.f_body, width=1)
        self.e_text.pack(side="left", fill="x", expand=True, padx=(0, 2), ipady=3, pady=6)
        self.e_text.bind("<Return>", lambda e: self.add_task())

    def _build_footer(self):
        f = tk.Frame(self.root, bg=BG_HEADER, height=13)
        f.pack_propagate(False)
        self.footer = f
        grip = make_icon(f, "grip", bg=BG_HEADER)
        grip.configure(cursor="sizing")
        grip.pack(side="right", padx=3)
        grip.bind("<Button-1>", self._resize_start)
        grip.bind("<B1-Motion>", self._resize_move)
        grip.bind("<ButtonRelease-1>", self._resize_end)

    def _show_expanded(self):
        self.footer.pack(fill="x", side="bottom")
        self.add_bar.pack(fill="x", side="bottom")
        self.body.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ render
    def render(self):
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

        counts = {"alta": 0, "media": 0, "baja": 0}
        for t in self.tasks:
            if not t["done"]:
                counts[t.get("priority", "media")] += 1
        for p, lbl in self.cnt_lbl.items():
            lbl.config(text=f"●{counts[p]}")

        self.root.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._sync_scrollbar()
        self.save()

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
                       font=self.f_body, anchor="w", justify="left", wraplength=wrap)
        txt.pack(fill="x", anchor="w")
        if task["done"]:
            f = tkfont.Font(font=self.f_body); f.configure(overstrike=True)
            txt.config(font=f)
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

        e = tk.Entry(mid, bg=BG_INPUT, fg=FG, insertbackground=FG,
                     relief="flat", font=self.f_body if field == "text" else self.f_small,
                     justify="left" if field == "text" else "center")
        if field == "text":
            e.insert(0, self.tasks[idx]["text"])
        else:
            e.insert(0, self.tasks[idx].get("due", "") or "")
            self._limit_to_date(e)
        e.pack(fill="x", anchor="w", ipady=2)
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
        self._set_placeholder(self.e_due, "venc.")
        self.render()

    def toggle_done(self, i):
        self.tasks[i]["done"] = not self.tasks[i]["done"]
        self.render()

    def delete_task(self, i):
        del self.tasks[i]
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
        """Ajusta translucidez y tinte según si la ventana tiene foco o no.
        Sin foco → más translúcida y (en oscuro) más oscura."""
        if self.win["collapsed"]:
            return
        focused = self._has_focus()
        alpha = WIN_ALPHA if focused else WIN_ALPHA_DIM
        tint = WIN_TINT if focused else WIN_TINT_DIM
        try:
            self.root.attributes("-alpha", alpha)
        except tk.TclError:
            pass
        if WIN_ACRYLIC and IS_WIN and self._hwnd and not self._dragging:
            win_acrylic(self._hwnd, tint, enabled=True)
            self._glass_on = True
        elif not WIN_ACRYLIC and IS_WIN and self._hwnd:
            win_acrylic(self._hwnd, 0, enabled=False)
            self._glass_on = False
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
        self._apply_glass()
        self._send_to_bottom()
        self.save()

    def _send_to_bottom(self):
        if IS_WIN and self._hwnd and not self.win["collapsed"]:
            u32.SetWindowPos(self._hwnd, HWND_BOTTOM, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def _maybe_lower(self):
        if self._editing or self.win["collapsed"]:
            return
        if self.root.focus_displayof() is None:
            self._send_to_bottom()

    def _keep_low(self):
        self._maybe_lower()
        self.root.after(4000, self._keep_low)

    def _summon(self):
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
        if not self.win["collapsed"]:
            try:
                self.root.attributes("-topmost", False)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ atajo global (Win)
    def _hotkey_loop(self):
        if not u32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_T):
            print("Ctrl+Alt+T ya está en uso por otro programa; el atajo no estará disponible.")
            return
        msg = wintypes.MSG()
        while True:
            r = u32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r in (0, -1):
                break
            if msg.message == WM_HOTKEY:
                self._summon_flag = True      # bool: seguro entre threads (GIL)

    def _poll_summon(self):
        if self._summon_flag:
            self._summon_flag = False
            self._summon()
        self.root.after(150, self._poll_summon)

    # ------------------------------------------------------------------ resize
    def _resize_start(self, e):
        self._rs = (e.x_root, e.y_root, self.root.winfo_width(), self.root.winfo_height())
        self._glass_suppress()

    def _resize_move(self, e):
        if not self._rs:
            return
        x0, y0, w0, h0 = self._rs
        w = max(MIN_W, w0 + (e.x_root - x0))
        h = max(MIN_H, h0 + (e.y_root - y0))
        self.win["w"], self.win["h"], self.win["sized"] = w, h, True
        self.root.geometry(f"{w}x{h}")

    def _resize_end(self, e):
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
            tw.geometry(f"+{x}+{y}")
            tk.Label(tw, text=text, bg="#000000", fg=FG, font=self.f_small,
                     padx=6, pady=2).pack()
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
            try:
                u32.UnregisterHotKey(None, 1)
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    TaskWidget().run()
