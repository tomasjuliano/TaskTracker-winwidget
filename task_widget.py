"""
Task Widget - un tracker de tareas para el escritorio de Windows.

- Vive pegado al escritorio: DETRAS de las ventanas normales, no se superpone.
  Al hacerle clic sube; al hacer clic afuera vuelve a bajar.
- Colapsado queda como una barrita SIEMPRE VISIBLE (arriba de todo): siempre
  se puede volver a abrir con doble clic en el título o el botón "–".
- Atajo global  Ctrl + Alt + T  para traerlo al frente desde cualquier lado.
- Ventana redimensionable (agarre "◢" abajo a la derecha).
- Editar: doble clic en el texto o en la fecha de una tarea; clic derecho = menú.
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

# --------------------------------------------------------------------------- #
#  Persistencia
# --------------------------------------------------------------------------- #

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
DATA_FILE = os.path.join(APP_DIR, "tasks.json")

DEFAULT_STATE = {
    "window": {"x": 120, "y": 120, "w": 310, "h": 340, "collapsed": False, "sized": False},
    "tasks": [],
}


def load_state():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as fh:
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
#  Paleta y helpers
# --------------------------------------------------------------------------- #

BG        = "#1e1f24"
BG_HEADER = "#2a2c33"
BG_ROW    = "#24262c"
BG_INPUT  = "#2f323a"
FG        = "#e8e8ea"
FG_DIM    = "#8a8d96"
ACCENT    = "#5a9cff"
OVERDUE   = "#e5534b"

PRIOS = ["baja", "media", "alta"]
PRIO_COLOR = {"alta": "#e5534b", "media": "#e3b341", "baja": "#3fb950"}
PRIO_RANK  = {"alta": 0, "media": 1, "baja": 2}

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
        return f"{txt}  ·  mañana", "#e3b341"
    if dias <= 7:
        return f"{txt}  ·  en {dias}d", "#e3b341"
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

        self.root = tk.Tk()
        self.root.title("Tareas")
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", 0.94)
        self.root.configure(bg=BG)
        self.root.geometry(f"{self.win['w']}x{self.win['h']}+{self.win['x']}+{self.win['y']}")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self.f_title = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_body  = tkfont.Font(family="Segoe UI", size=10)
        self.f_small = tkfont.Font(family="Segoe UI", size=8)

        self._build_header()
        self._build_body()
        self._build_footer()
        self._show_expanded()

        if self.win["collapsed"]:
            self._collapse(save=False)

        self.render()

        self.root.bind("<FocusOut>", lambda e: self.root.after(250, self._maybe_lower))
        self.root.after(350, self._pin_to_desktop)
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

        btn_close = tk.Label(h, text="✕  ", bg=BG_HEADER, fg=FG_DIM, font=self.f_title,
                             cursor="hand2")
        btn_close.pack(side="right")
        btn_close.bind("<Button-1>", lambda e: self.quit())
        btn_close.bind("<Enter>", lambda e: btn_close.config(fg=OVERDUE))
        btn_close.bind("<Leave>", lambda e: btn_close.config(fg=FG_DIM))

        btn_col = tk.Label(h, text="–", bg=BG_HEADER, fg=FG_DIM, font=self.f_title,
                           cursor="hand2")
        btn_col.pack(side="right", padx=4)
        btn_col.bind("<Button-1>", lambda e: self.toggle_collapse())
        self._tooltip(btn_col, "Colapsar / expandir  ·  atajo global: Ctrl+Alt+T")

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
        title.bind("<Double-Button-1>", lambda e: self.toggle_collapse())

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

        self.prio_dot = tk.Label(add, text="●", bg=BG_HEADER, fg=PRIO_COLOR[self._new_prio],
                                 font=self.f_body, cursor="hand2")
        self.prio_dot.pack(side="left", padx=(8, 4), pady=6)
        self.prio_dot.bind("<Button-1>", self._cycle_new_prio)
        self._tooltip(self.prio_dot, "Prioridad de la nueva tarea (clic para cambiar)")

        self.e_text = tk.Entry(add, bg=BG_INPUT, fg=FG, insertbackground=FG,
                               relief="flat", font=self.f_body)
        self.e_text.pack(side="left", fill="x", expand=True, ipady=3, pady=6)
        self.e_text.bind("<Return>", lambda e: self.add_task())

        self.e_due = tk.Entry(add, bg=BG_INPUT, fg=FG_DIM, insertbackground=FG,
                              relief="flat", font=self.f_small, width=8, justify="center")
        self.e_due.pack(side="left", padx=4, ipady=4, pady=6)
        self._placeholder(self.e_due, "venc.")
        self._limit_to_date(self.e_due)
        self.e_due.bind("<Return>", lambda e: self.add_task())

        btn_add = tk.Label(add, text="  +  ", bg=ACCENT, fg="#ffffff",
                           font=self.f_title, cursor="hand2")
        btn_add.pack(side="left", padx=8, pady=6)
        btn_add.bind("<Button-1>", lambda e: self.add_task())

    def _build_footer(self):
        f = tk.Frame(self.root, bg=BG_HEADER, height=13)
        f.pack_propagate(False)
        self.footer = f
        grip = tk.Label(f, text="◢", bg=BG_HEADER, fg=FG_DIM, font=self.f_small, cursor="sizing")
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
            self._send_to_bottom()
        except Exception as exc:
            print("No se pudo fijar al escritorio:", exc)

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

    def _drag_move(self, e):
        x = e.x_root - self._drag[0]
        y = e.y_root - self._drag[1]
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
