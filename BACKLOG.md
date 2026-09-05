# Backlog de issues

_Generado a partir de una revisión del código. Cada uno tiene un link para crearlo como issue en GitHub._


## 🐛 Tooltip ilegible en tema claro (fondo negro + texto oscuro)

**Tema:** claro

Los tooltips (el del `●` de prioridad, el del contador, etc.) se dibujan con **fondo negro** y **texto oscuro**, no se leen.

**Causa:** `task_widget.py` `_tooltip()` crea el `tk.Label` con `bg="#000000"` hardcodeado y `fg=FG`. En claro `FG` = `#1d1d1f`.

**Fix:** usar colores del tema (`bg=BG_HEADER`/inverso + `fg` con contraste + borde `BORDER`).

Prioridad: baja / cosmético.

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=Tooltip+ilegible+en+tema+claro+%28fondo+negro+%2B+texto+oscuro%29&body=%2A%2ATema%3A%2A%2A+claro%0A%0ALos+tooltips+%28el+del+%60%E2%97%8F%60+de+prioridad%2C+el+del+contador%2C+etc.%29+se+dibujan+con+%2A%2Afondo+negro%2A%2A+y+%2A%2Atexto+oscuro%2A%2A%2C+no+se+leen.%0A%0A%2A%2ACausa%3A%2A%2A+%60task_widget.py%60+%60_tooltip%28%29%60+crea+el+%60tk.Label%60+con+%60bg%3D%22%23000000%22%60+hardcodeado+y+%60fg%3DFG%60.+En+claro+%60FG%60+%3D+%60%231d1d1f%60.%0A%0A%2A%2AFix%3A%2A%2A+usar+colores+del+tema+%28%60bg%3DBG_HEADER%60%2Finverso+%2B+%60fg%60+con+contraste+%2B+borde+%60BORDER%60%29.%0A%0APrioridad%3A+baja+%2F+cosm%C3%A9tico.%0A&labels=bug)


## 🐛 Varias instancias comparten tasks.json y se pisan los datos

Si se abre el widget dos veces (pasa fácil al probar el `.exe`), **ambas instancias leen y escriben el mismo `tasks.json`** sin coordinación: la última que guarda pisa lo de la otra, y se pueden perder tareas.

**Fix propuesto:** lock de instancia única — al arrancar, si ya hay otra corriendo, traer esa al frente (via el atajo / un mutex con nombre en Windows) y salir. El fallo de `RegisterHotKey` ("Ctrl+Alt+T ya está en uso") ya es una pista de que hay otra instancia.

Severidad: media (posible pérdida de datos).

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=Varias+instancias+comparten+tasks.json+y+se+pisan+los+datos&body=Si+se+abre+el+widget+dos+veces+%28pasa+f%C3%A1cil+al+probar+el+%60.exe%60%29%2C+%2A%2Aambas+instancias+leen+y+escriben+el+mismo+%60tasks.json%60%2A%2A+sin+coordinaci%C3%B3n%3A+la+%C3%BAltima+que+guarda+pisa+lo+de+la+otra%2C+y+se+pueden+perder+tareas.%0A%0A%2A%2AFix+propuesto%3A%2A%2A+lock+de+instancia+%C3%BAnica+%E2%80%94+al+arrancar%2C+si+ya+hay+otra+corriendo%2C+traer+esa+al+frente+%28via+el+atajo+%2F+un+mutex+con+nombre+en+Windows%29+y+salir.+El+fallo+de+%60RegisterHotKey%60+%28%22Ctrl%2BAlt%2BT+ya+est%C3%A1+en+uso%22%29+ya+es+una+pista+de+que+hay+otra+instancia.%0A%0ASeveridad%3A+media+%28posible+p%C3%A9rdida+de+datos%29.%0A&labels=bug)


## 🐛 Fuga de objetos Font al renderizar tareas completadas

En `_row()`, para cada tarea hecha se crea un `tkfont.Font` nuevo en cada `render()`:

```python
f = tkfont.Font(font=self.f_body); f.configure(overstrike=True)
txt.config(font=f)
```

Nunca se libera. `render()` se llama en cada toggle/edición/resize, así que en una sesión larga se acumulan handles de fuente.

**Fix:** crear **una sola** `Font` con `overstrike=True` a nivel de instancia (como `self.f_body`) y reusarla.

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=Fuga+de+objetos+Font+al+renderizar+tareas+completadas&body=En+%60_row%28%29%60%2C+para+cada+tarea+hecha+se+crea+un+%60tkfont.Font%60+nuevo+en+cada+%60render%28%29%60%3A%0A%0A%60%60%60python%0Af+%3D+tkfont.Font%28font%3Dself.f_body%29%3B+f.configure%28overstrike%3DTrue%29%0Atxt.config%28font%3Df%29%0A%60%60%60%0A%0ANunca+se+libera.+%60render%28%29%60+se+llama+en+cada+toggle%2Fedici%C3%B3n%2Fresize%2C+as%C3%AD+que+en+una+sesi%C3%B3n+larga+se+acumulan+handles+de+fuente.%0A%0A%2A%2AFix%3A%2A%2A+crear+%2A%2Auna+sola%2A%2A+%60Font%60+con+%60overstrike%3DTrue%60+a+nivel+de+instancia+%28como+%60self.f_body%60%29+y+reusarla.%0A&labels=bug)


## 🐛 _editing puede quedar en True para siempre y la ventana no vuelve a bajar

`_edit_inline()` hace `self._editing = True` y sólo lo vuelve a `False` dentro de `finish()`. Si `finish()` no llega a ejecutarse (excepción, el widget se destruye por un cambio de tema, etc.), `_editing` queda en `True` y `_maybe_lower()` deja de mandar la ventana al escritorio — se queda "pegada" al frente.

**Fix:** resetear `self._editing = False` también en `render()` / `_set_theme()`, o envolver la edición en `try/finally`.

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=_editing+puede+quedar+en+True+para+siempre+y+la+ventana+no+vuelve+a+bajar&body=%60_edit_inline%28%29%60+hace+%60self._editing+%3D+True%60+y+s%C3%B3lo+lo+vuelve+a+%60False%60+dentro+de+%60finish%28%29%60.+Si+%60finish%28%29%60+no+llega+a+ejecutarse+%28excepci%C3%B3n%2C+el+widget+se+destruye+por+un+cambio+de+tema%2C+etc.%29%2C+%60_editing%60+queda+en+%60True%60+y+%60_maybe_lower%28%29%60+deja+de+mandar+la+ventana+al+escritorio+%E2%80%94+se+queda+%22pegada%22+al+frente.%0A%0A%2A%2AFix%3A%2A%2A+resetear+%60self._editing+%3D+False%60+tambi%C3%A9n+en+%60render%28%29%60+%2F+%60_set_theme%28%29%60%2C+o+envolver+la+edici%C3%B3n+en+%60try%2Ffinally%60.%0A&labels=bug)


## 🐛 Borrar tarea y cerrar la ventana no piden confirmación ni tienen undo

Un clic accidental en la `✕` de una fila borra la tarea al instante, sin deshacer. Lo mismo con la `✕` del header (cierra todo).

**Fix propuesto:**
- Deshacer el último borrado (Ctrl+Z, o un "deshacer" que aparece 3-4 s).
- O una papelera simple (tareas borradas recuperables desde el menú).
- Confirmación al cerrar sólo si hay pendientes (opcional).

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=Borrar+tarea+y+cerrar+la+ventana+no+piden+confirmaci%C3%B3n+ni+tienen+undo&body=Un+clic+accidental+en+la+%60%E2%9C%95%60+de+una+fila+borra+la+tarea+al+instante%2C+sin+deshacer.+Lo+mismo+con+la+%60%E2%9C%95%60+del+header+%28cierra+todo%29.%0A%0A%2A%2AFix+propuesto%3A%2A%2A%0A-+Deshacer+el+%C3%BAltimo+borrado+%28Ctrl%2BZ%2C+o+un+%22deshacer%22+que+aparece+3-4+s%29.%0A-+O+una+papelera+simple+%28tareas+borradas+recuperables+desde+el+men%C3%BA%29.%0A-+Confirmaci%C3%B3n+al+cerrar+s%C3%B3lo+si+hay+pendientes+%28opcional%29.%0A&labels=bug)


## 🐛 El campo "venc." queda con el placeholder pegado al texto

Si agregás una tarea con **Enter desde el campo "venc."**, después de `add_task()` se restaura el placeholder (`_set_placeholder`) mientras el campo **todavía tiene el foco**. Como `_clear_placeholder` sólo corre en `<FocusIn>` (que no se vuelve a disparar), lo próximo que tipees se agrega a `"venc."` → queda `venc.05/09`.

**Fix:** al limpiar los campos en `add_task()`, si `e_due` tiene el foco no poner el placeholder (o forzar `_clear_placeholder` en el próximo keypress).

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=El+campo+%22venc.%22+queda+con+el+placeholder+pegado+al+texto&body=Si+agreg%C3%A1s+una+tarea+con+%2A%2AEnter+desde+el+campo+%22venc.%22%2A%2A%2C+despu%C3%A9s+de+%60add_task%28%29%60+se+restaura+el+placeholder+%28%60_set_placeholder%60%29+mientras+el+campo+%2A%2Atodav%C3%ADa+tiene+el+foco%2A%2A.+Como+%60_clear_placeholder%60+s%C3%B3lo+corre+en+%60%3CFocusIn%3E%60+%28que+no+se+vuelve+a+disparar%29%2C+lo+pr%C3%B3ximo+que+tipees+se+agrega+a+%60%22venc.%22%60+%E2%86%92+queda+%60venc.05%2F09%60.%0A%0A%2A%2AFix%3A%2A%2A+al+limpiar+los+campos+en+%60add_task%28%29%60%2C+si+%60e_due%60+tiene+el+foco+no+poner+el+placeholder+%28o+forzar+%60_clear_placeholder%60+en+el+pr%C3%B3ximo+keypress%29.%0A&labels=bug)


## 🐛 bind_all("<MouseWheel>") es global: la rueda scrollea la lista desde cualquier lado

`_build_body()` hace `self.canvas.bind_all("<MouseWheel>", self._on_wheel)`. `bind_all` es **a nivel de aplicación**: girar la rueda sobre el panel de Opciones (u otra ventana de la app) scrollea la lista de tareas de atrás.

**Fix:** bindear `<MouseWheel>` sólo al `canvas` / `list_frame` (con `<Enter>`/`<Leave>` para activar/desactivar), no `bind_all`.

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=bind_all%28%22%3CMouseWheel%3E%22%29+es+global%3A+la+rueda+scrollea+la+lista+desde+cualquier+lado&body=%60_build_body%28%29%60+hace+%60self.canvas.bind_all%28%22%3CMouseWheel%3E%22%2C+self._on_wheel%29%60.+%60bind_all%60+es+%2A%2Aa+nivel+de+aplicaci%C3%B3n%2A%2A%3A+girar+la+rueda+sobre+el+panel+de+Opciones+%28u+otra+ventana+de+la+app%29+scrollea+la+lista+de+tareas+de+atr%C3%A1s.%0A%0A%2A%2AFix%3A%2A%2A+bindear+%60%3CMouseWheel%3E%60+s%C3%B3lo+al+%60canvas%60+%2F+%60list_frame%60+%28con+%60%3CEnter%3E%60%2F%60%3CLeave%3E%60+para+activar%2Fdesactivar%29%2C+no+%60bind_all%60.%0A&labels=bug)


## 🐛 UnregisterHotKey se llama desde el hilo equivocado

`RegisterHotKey` se hace en el hilo `_hotkey_loop` (daemon), pero `quit()` llama `UnregisterHotKey(None, 1)` desde el hilo principal. En Win32 los hotkeys son **por hilo**, así que ese `UnregisterHotKey` no hace nada. En la práctica no molesta (el proceso muere y Windows limpia), pero es incorrecto y el hilo del hotkey nunca sale limpio de `GetMessageW`.

**Fix:** postear `WM_QUIT` al hilo del hotkey (`PostThreadMessage`) en `quit()`, y desregistrar ahí.

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=UnregisterHotKey+se+llama+desde+el+hilo+equivocado&body=%60RegisterHotKey%60+se+hace+en+el+hilo+%60_hotkey_loop%60+%28daemon%29%2C+pero+%60quit%28%29%60+llama+%60UnregisterHotKey%28None%2C+1%29%60+desde+el+hilo+principal.+En+Win32+los+hotkeys+son+%2A%2Apor+hilo%2A%2A%2C+as%C3%AD+que+ese+%60UnregisterHotKey%60+no+hace+nada.+En+la+pr%C3%A1ctica+no+molesta+%28el+proceso+muere+y+Windows+limpia%29%2C+pero+es+incorrecto+y+el+hilo+del+hotkey+nunca+sale+limpio+de+%60GetMessageW%60.%0A%0A%2A%2AFix%3A%2A%2A+postear+%60WM_QUIT%60+al+hilo+del+hotkey+%28%60PostThreadMessage%60%29+en+%60quit%28%29%60%2C+y+desregistrar+ah%C3%AD.%0A&labels=bug)


## ✨ Recordatorio / notificación cuando una tarea vence

Hoy la fecha de vencimiento sólo cambia el color del texto. Estaría bueno una **notificación del sistema** (toast de Windows) cuando una tarea llega a su fecha (o el día anterior).

Ideas:
- Chequear cada X minutos las tareas con `due` <= hoy y no hechas.
- Notificación nativa (`ctypes` + Shell_NotifyIcon, o `winrt` si se acepta una dependencia opcional).
- Opción en el panel de Opciones para prender/apagar.

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=Recordatorio+%2F+notificaci%C3%B3n+cuando+una+tarea+vence&body=Hoy+la+fecha+de+vencimiento+s%C3%B3lo+cambia+el+color+del+texto.+Estar%C3%ADa+bueno+una+%2A%2Anotificaci%C3%B3n+del+sistema%2A%2A+%28toast+de+Windows%29+cuando+una+tarea+llega+a+su+fecha+%28o+el+d%C3%ADa+anterior%29.%0A%0AIdeas%3A%0A-+Chequear+cada+X+minutos+las+tareas+con+%60due%60+%3C%3D+hoy+y+no+hechas.%0A-+Notificaci%C3%B3n+nativa+%28%60ctypes%60+%2B+Shell_NotifyIcon%2C+o+%60winrt%60+si+se+acepta+una+dependencia+opcional%29.%0A-+Opci%C3%B3n+en+el+panel+de+Opciones+para+prender%2Fapagar.%0A&labels=enhancement)


## ✨ Reordenar tareas arrastrando

Ahora el orden es fijo (hechas al final, después por fecha y prioridad). Permitir **arrastrar una fila para reordenar manualmente** y guardar ese orden en `tasks.json` (un campo `order` o el índice de la lista).

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=Reordenar+tareas+arrastrando&body=Ahora+el+orden+es+fijo+%28hechas+al+final%2C+despu%C3%A9s+por+fecha+y+prioridad%29.+Permitir+%2A%2Aarrastrar+una+fila+para+reordenar+manualmente%2A%2A+y+guardar+ese+orden+en+%60tasks.json%60+%28un+campo+%60order%60+o+el+%C3%ADndice+de+la+lista%29.%0A&labels=enhancement)


## ✨ Ver la cantidad de pendientes cuando está colapsado

Colapsado, la barrita sólo dice "Tareas". No se puede saber si hay pendientes sin expandir.

**Propuesta:** mostrar en la barrita colapsada el total de pendientes (o los `●N` por prioridad, como en el header expandido).

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=Ver+la+cantidad+de+pendientes+cuando+est%C3%A1+colapsado&body=Colapsado%2C+la+barrita+s%C3%B3lo+dice+%22Tareas%22.+No+se+puede+saber+si+hay+pendientes+sin+expandir.%0A%0A%2A%2APropuesta%3A%2A%2A+mostrar+en+la+barrita+colapsada+el+total+de+pendientes+%28o+los+%60%E2%97%8FN%60+por+prioridad%2C+como+en+el+header+expandido%29.%0A&labels=enhancement)


## ✨ "Limpiar completadas" / archivar en el menú

Las tareas hechas se acumulan tachadas al final. Agregar en el panel de Opciones (o clic derecho) un **"Limpiar completadas"** que las borre (o las mande a un archivo `tasks-archive.json`).

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=%22Limpiar+completadas%22+%2F+archivar+en+el+men%C3%BA&body=Las+tareas+hechas+se+acumulan+tachadas+al+final.+Agregar+en+el+panel+de+Opciones+%28o+clic+derecho%29+un+%2A%2A%22Limpiar+completadas%22%2A%2A+que+las+borre+%28o+las+mande+a+un+archivo+%60tasks-archive.json%60%29.%0A&labels=enhancement)


## ✨ Selector de fecha (mini calendario) para el vencimiento

Hoy el vencimiento es sólo texto (`DD/MM`, `YYYY-MM-DD`). Agregar un **date picker** chiquito (un calendario dibujado con tkinter, sin dependencias) que se abra al hacer clic en un iconito al lado del campo "venc." / de la fecha de la tarea.

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=Selector+de+fecha+%28mini+calendario%29+para+el+vencimiento&body=Hoy+el+vencimiento+es+s%C3%B3lo+texto+%28%60DD%2FMM%60%2C+%60YYYY-MM-DD%60%29.+Agregar+un+%2A%2Adate+picker%2A%2A+chiquito+%28un+calendario+dibujado+con+tkinter%2C+sin+dependencias%29+que+se+abra+al+hacer+clic+en+un+iconito+al+lado+del+campo+%22venc.%22+%2F+de+la+fecha+de+la+tarea.%0A&labels=enhancement)


## ✨ Opción "siempre visible" (always on top) como alternativa al modo escritorio

El widget vive a nivel escritorio (atrás de todo salvo cuando tiene foco). Algunas personas lo quieren **siempre encima de todas las ventanas**.

**Propuesta:** un toggle en Opciones — "Modo": *Escritorio* (actual) / *Siempre visible* (`-topmost` permanente).

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=Opci%C3%B3n+%22siempre+visible%22+%28always+on+top%29+como+alternativa+al+modo+escritorio&body=El+widget+vive+a+nivel+escritorio+%28atr%C3%A1s+de+todo+salvo+cuando+tiene+foco%29.+Algunas+personas+lo+quieren+%2A%2Asiempre+encima+de+todas+las+ventanas%2A%2A.%0A%0A%2A%2APropuesta%3A%2A%2A+un+toggle+en+Opciones+%E2%80%94+%22Modo%22%3A+%2AEscritorio%2A+%28actual%29+%2F+%2ASiempre+visible%2A+%28%60-topmost%60+permanente%29.%0A&labels=enhancement)


## ✨ Atajo global configurable

El atajo es fijo `Ctrl+Alt+T` y si ya está tomado por otro programa, el widget se queda sin atajo (sólo avisa por consola).

**Propuesta:** dejar elegir la combinación en el panel de Opciones (capturar la tecla) y guardarla en `tasks.json`. Si falla el registro, avisar en la UI, no sólo en consola.

[→ crear este issue](https://github.com/tomasjuliano/TaskTracker-winwidget/issues/new?title=Atajo+global+configurable&body=El+atajo+es+fijo+%60Ctrl%2BAlt%2BT%60+y+si+ya+est%C3%A1+tomado+por+otro+programa%2C+el+widget+se+queda+sin+atajo+%28s%C3%B3lo+avisa+por+consola%29.%0A%0A%2A%2APropuesta%3A%2A%2A+dejar+elegir+la+combinaci%C3%B3n+en+el+panel+de+Opciones+%28capturar+la+tecla%29+y+guardarla+en+%60tasks.json%60.+Si+falla+el+registro%2C+avisar+en+la+UI%2C+no+s%C3%B3lo+en+consola.%0A&labels=enhancement)
