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
    "window": {"x": None, "y": None, "w": 310, "h": 340, "collapsed": False,
               "sized": False, "theme": "auto", "dim_opacity": None},
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
        self.entry.place(x=self._ph, rely=0.5, anchor="w")
        self.cv.bind("<Configure>", self._redraw)
        self.cv.bind("<Button-1>", lambda e: self.entry.focus_set())

    def _redraw(self, e=None):
        w = e.width if e is not None else self.cv.winfo_width()
        h = e.height if e is not None else self.cv.winfo_height()
        if w < 4 or h < 4:
            return
        self.cv.delete("bg")
        _round_rect(self.cv, 1, 1, w - 1, h - 1, INPUT_RADIUS,
                    fill=self._fill, outline=BORDER, tags="bg")
        self.cv.tag_lower("bg")
        self.entry.place_configure(width=w - 2 * self._ph, height=max(1, h - 6))


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
        if self.win.get("x") is None or self.win.get("y") is None:
            self.win["x"], self.win["y"] = self._default_pos()   # esquina sup. derecha
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

        if IS_WIN:
            tk.Checkbutton(t, text="Iniciar con Windows", variable=self._autostart_var,
                           command=self._toggle_autostart, bg=BG, fg=FG,
                           selectcolor=BG_INPUT, activebackground=BG, activeforeground=FG,
                           font=self.f_small, anchor="w",
                           takefocus=0).pack(fill="x", pady=(10, 0))

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

        due_wrap = RoundEntry(add, small=True, bg=BG_INPUT, fg=FG_DIM,
                              insertbackground=FG, font=self.f_small,
                              width=6, justify="center")
        due_wrap.configure(width=62, height=27)
        due_wrap.pack_propagate(False)
        due_wrap.pack(side="right", padx=2, pady=6)
        self.e_due = due_wrap.entry
        self._placeholder(self.e_due, "venc.")
        self._limit_to_date(self.e_due)
        self.e_due.bind("<Return>", lambda e: self.add_task())

        text_wrap = RoundEntry(add, bg=BG_INPUT, fg=FG, insertbackground=FG,
                               font=self.f_body, width=1)
        text_wrap.configure(height=29)
        text_wrap.pack_propagate(False)
        text_wrap.pack(side="left", fill="x", expand=True, padx=(2, 2), pady=6)
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
        """Con foco → panel sólido (casi opaco, sin blur), para trabajar.
        Sin foco → translúcido con el blur del escritorio detrás, se funde al fondo."""
        if self.win["collapsed"]:
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
