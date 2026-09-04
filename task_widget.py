"""
Task Widget - un tracker de tareas para el escritorio de Windows.

- Ventana sin bordes, siempre visible, semitransparente y arrastrable.
- Alta / baja de tareas, marcar como hecha, editar texto (doble clic).
- Fecha de vencimiento opcional y prioridad (Alta / Media / Baja).
- Todo se guarda en tasks.json, al lado de este archivo.

Requisitos: solo Python 3.8+ (tkinter viene incluido en el instalador de Windows).
Para arrancar:  python task_widget.py
"""

import json
import os
import sys
import uuid
from datetime import date, datetime
import tkinter as tk
from tkinter import font as tkfont

# --------------------------------------------------------------------------- #
#  Persistencia
# --------------------------------------------------------------------------- #

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
DATA_FILE = os.path.join(APP_DIR, "tasks.json")

DEFAULT_STATE = {
    "window": {"x": 120, "y": 120, "collapsed": False},
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
        return json.loads(json.dumps(DEFAULT_STATE))  # copia limpia


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

BG        = "#1e1f24"   # fondo de la tarjeta
BG_HEADER = "#2a2c33"   # barra superior
BG_ROW    = "#24262c"   # fila de tarea
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
                if d < hoy:                       # si ya pasó, se asume el año que viene
                    d = d.replace(year=hoy.year + 1)
            return d.isoformat()
        except ValueError:
            continue
    return ""


def due_label(iso_str):
    """Texto corto + color para una fecha de vencimiento."""
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
    WIDTH = 310
    MAX_LIST_H = 380

    def __init__(self):
        self.state = load_state()
        self.tasks = self.state["tasks"]
        self._drag = (0, 0)
        self._new_prio = "media"

        self.root = tk.Tk()
        self.root.title("Tareas")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)
        self.root.configure(bg=BG)
        wx, wy = self.state["window"]["x"], self.state["window"]["y"]
        self.root.geometry(f"{self.WIDTH}x100+{wx}+{wy}")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self.f_title = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self.f_body  = tkfont.Font(family="Segoe UI", size=10)
        self.f_small = tkfont.Font(family="Segoe UI", size=8)

        self._build_header()
        self._build_body()

        if self.state["window"]["collapsed"]:
            self.body.pack_forget()

        self.render()
        self.root.after(30000, self._autosave)      # guardado periódico
        # traer al frente sin robar foco de forma agresiva
        self.root.after(10, lambda: self.root.attributes("-topmost", True))

    # ------------------------------------------------------------------ UI
    def _build_header(self):
        h = tk.Frame(self.root, bg=BG_HEADER, height=30)
        h.pack(fill="x")
        h.pack_propagate(False)
        self.header = h

        title = tk.Label(h, text="  Tareas", bg=BG_HEADER, fg=FG, font=self.f_title)
        title.pack(side="left")

        self.count = tk.Label(h, text="", bg=BG_HEADER, fg=FG_DIM, font=self.f_small)
        self.count.pack(side="left", padx=6)

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

        # arrastrar la ventana desde la barra
        for w in (h, title):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
        title.bind("<Double-Button-1>", lambda e: self.toggle_collapse())

    def _build_body(self):
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True)

        # --- lista con scroll ---
        self.canvas = tk.Canvas(self.body, bg=BG, highlightthickness=0, height=120)
        self.scroll = tk.Scrollbar(self.body, orient="vertical", command=self.canvas.yview)
        self.list_frame = tk.Frame(self.canvas, bg=BG)
        self.list_win = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.list_frame.bind("<Configure>", self._on_list_configure)
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfig(self.list_win, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

        # --- fila para agregar ---
        add = tk.Frame(self.root, bg=BG_HEADER)
        add.pack(fill="x", side="bottom")
        self.add_bar = add

        self.prio_dot = tk.Label(add, text="●", bg=BG_HEADER, fg=PRIO_COLOR[self._new_prio],
                                 font=self.f_body, cursor="hand2")
        self.prio_dot.pack(side="left", padx=(8, 4), pady=6)
        self.prio_dot.bind("<Button-1>", self._cycle_new_prio)
        self._tooltip(self.prio_dot, "Prioridad (clic para cambiar)")

        self.e_text = tk.Entry(add, bg=BG_INPUT, fg=FG, insertbackground=FG,
                               relief="flat", font=self.f_body)
        self.e_text.pack(side="left", fill="x", expand=True, ipady=3, pady=6)
        self.e_text.bind("<Return>", lambda e: self.add_task())

        self.e_due = tk.Entry(add, bg=BG_INPUT, fg=FG_DIM, insertbackground=FG,
                              relief="flat", font=self.f_small, width=8, justify="center")
        self.e_due.pack(side="left", padx=4, ipady=4, pady=6)
        self._placeholder(self.e_due, "venc.")
        self.e_due.bind("<Return>", lambda e: self.add_task())

        btn_add = tk.Label(add, text="  +  ", bg=ACCENT, fg="#ffffff",
                           font=self.f_title, cursor="hand2")
        btn_add.pack(side="left", padx=8, pady=6)
        btn_add.bind("<Button-1>", lambda e: self.add_task())

    # ------------------------------------------------------------------ render
    def render(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

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
                self._row(idx, self.tasks[idx])

        pend = sum(1 for t in self.tasks if not t["done"])
        self.count.config(text=f"{pend} pendiente{'s' if pend != 1 else ''}")

        self.root.update_idletasks()
        list_h = min(self.list_frame.winfo_reqheight(), self.MAX_LIST_H)
        self.canvas.config(height=max(list_h, 40))
        self.scroll.pack_forget()
        if self.list_frame.winfo_reqheight() > self.MAX_LIST_H:
            self.scroll.pack(side="right", fill="y")
        self._fit_window()
        self.save()

    def _row(self, idx, task):
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
                       font=self.f_body, anchor="w", justify="left", wraplength=210)
        txt.pack(fill="x", anchor="w")
        if task["done"]:
            f = tkfont.Font(font=self.f_body); f.configure(overstrike=True)
            txt.config(font=f)
        txt.bind("<Double-Button-1>", lambda e, i=idx: self.edit_task(i))

        dl, dcolor = due_label(task.get("due", ""))
        if dl:
            tk.Label(mid, text=dl, bg=BG_ROW, fg=dcolor,
                     font=self.f_small, anchor="w").pack(fill="x", anchor="w")

        dele = tk.Label(row, text="✕", bg=BG_ROW, fg=BG_ROW, font=self.f_small,
                        cursor="hand2", width=2)
        dele.pack(side="right", padx=4)
        dele.bind("<Button-1>", lambda e, i=idx: self.delete_task(i))
        row.bind("<Enter>", lambda e, d=dele: d.config(fg=FG_DIM))
        row.bind("<Leave>", lambda e, d=dele: d.config(fg=BG_ROW))
        dele.bind("<Enter>", lambda e, d=dele: d.config(fg=OVERDUE))

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

    def edit_task(self, i):
        top = tk.Toplevel(self.root)
        top.configure(bg=BG)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        px, py = self.root.winfo_pointerxy()
        top.geometry(f"260x96+{px - 40}+{py - 20}")

        tk.Label(top, text="Editar tarea", bg=BG, fg=FG_DIM,
                 font=self.f_small).pack(anchor="w", padx=10, pady=(8, 2))
        e = tk.Entry(top, bg=BG_INPUT, fg=FG, insertbackground=FG,
                     relief="flat", font=self.f_body)
        e.pack(fill="x", padx=10, ipady=4)
        e.insert(0, self.tasks[i]["text"])
        e.focus_set()
        e.select_range(0, "end")

        d = tk.Entry(top, bg=BG_INPUT, fg=FG, insertbackground=FG,
                     relief="flat", font=self.f_small, justify="center")
        d.pack(fill="x", padx=10, pady=6, ipady=3)
        d.insert(0, self.tasks[i].get("due", "") or "")

        def commit(_=None):
            new = e.get().strip()
            if new:
                self.tasks[i]["text"] = new
            self.tasks[i]["due"] = parse_due(d.get())
            top.destroy()
            self.render()

        e.bind("<Return>", commit)
        d.bind("<Return>", commit)
        top.bind("<Escape>", lambda e: top.destroy())
        top.bind("<FocusOut>", lambda e: commit())

    def toggle_collapse(self):
        if self.body.winfo_ismapped():
            self.body.pack_forget()
            self.add_bar.pack_forget()
            self.state["window"]["collapsed"] = True
        else:
            self.body.pack(fill="both", expand=True)
            self.add_bar.pack(fill="x", side="bottom")
            self.state["window"]["collapsed"] = False
        self._fit_window()
        self.save()

    # ------------------------------------------------------------------ util
    def _cycle_new_prio(self, _=None):
        self._new_prio = PRIOS[(PRIOS.index(self._new_prio) + 1) % len(PRIOS)]
        self.prio_dot.config(fg=PRIO_COLOR[self._new_prio])

    def _fit_window(self):
        self.root.update_idletasks()
        h = self.header.winfo_reqheight()
        if self.body.winfo_ismapped():
            h += self.canvas.winfo_reqheight() + self.add_bar.winfo_reqheight()
        self.root.geometry(f"{self.WIDTH}x{h}")

    def _on_list_configure(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_wheel(self, event):
        if self.list_frame.winfo_reqheight() > self.MAX_LIST_H:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _drag_start(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        x = e.x_root - self._drag[0]
        y = e.y_root - self._drag[1]
        self.root.geometry(f"+{x}+{y}")
        self.state["window"]["x"], self.state["window"]["y"] = x, y

    # placeholders simples para Entry
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
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    TaskWidget().run()
