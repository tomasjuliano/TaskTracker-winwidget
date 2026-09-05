# TaskTracker Widget

Un tracker de tareas que vive en el escritorio de Windows. Python + tkinter,
**sin dependencias externas** (tkinter viene con el instalador de Python).

- Ventana sin bordes, semitransparente y arrastrable.
- **Vive pegado al escritorio**: aparece detrás de las ventanas normales. Al
  hacerle clic sube al frente; al hacer clic afuera vuelve a bajar.
- Colapsado queda como una barrita siempre visible, así nunca se pierde.
- Atajo global **`Ctrl+Alt+T`** para traerlo al frente desde cualquier lado.
- Tareas con fecha de vencimiento y prioridad, contador por prioridad, ventana
  redimensionable.
- **Tema claro / oscuro / automático**, con estética translúcida tipo *glass*
  (blur acrylic de Windows por detrás en el tema oscuro).
- Todo se guarda en `tasks.json`, al lado del script.

---

## Descargar (sin instalar nada)

Bajá **`TaskWidget.exe`** de la [página de Releases](../../releases/latest) y hacé
doble clic. No necesita Python ni instalación. El archivo `tasks.json` se crea al
lado del `.exe` en el primer arranque.

> Windows Defender / SmartScreen puede avisar que es de un "editor desconocido"
> (pasa con todo `.exe` sin firma digital): *Más información → Ejecutar de todas formas*.
> Algunos antivirus dan falso positivo con ejecutables de PyInstaller.

El `.exe` lo compila solo GitHub Actions en cada release — ver
[Build / CI](#build--ci) más abajo.

## Requisitos (para correrlo desde el código)

- Windows 10 / 11
- Python 3.8 o superior ([python.org](https://www.python.org/downloads/) — marcar
  *"Add Python to PATH"* en el instalador).

El atajo global y el comportamiento "pegado al escritorio" usan la API de Windows
(`ctypes`); en otros sistemas operativos la app arranca igual pero sin esas dos features.

## Uso

```bash
pythonw task_widget.py
```

`pythonw` no deja una consola abierta. Usá `python task_widget.py` si querés ver
mensajes de error o el aviso de "Ctrl+Alt+T ya está en uso".

### Para que arranque con Windows

Botón **`⚙`** en la barra (o clic derecho en la barra) → **"Iniciar con Windows"**.
Escribe una entrada en `HKCU\...\CurrentVersion\Run` apuntando al `.exe` (o a
`pythonw task_widget.py` si lo corrés desde el código). No necesita permisos de
administrador y se puede desmarcar en cualquier momento.

### Controles

| Acción | Cómo |
|---|---|
| Mover la ventana | Arrastrar desde la barra "Tareas" |
| Redimensionar | Arrastrar el agarre `◢` de abajo a la derecha |
| Colapsar / expandir | Botón `–`, doble clic en el título, o `Ctrl+Alt+T` |
| Traer al frente | `Ctrl+Alt+T` |
| Cerrar | Botón `✕` |
| Agregar tarea | Escribir abajo → Enter (o el `+`) |
| Prioridad de la nueva tarea | Clic en el `●` de la izquierda (baja → media → alta) |
| Fecha de vencimiento | Campo "venc." — acepta `11/09`, `2026-09-11`, `11/09/2026` |
| Marcar hecha | Clic en el `○` de la fila |
| Cambiar prioridad de una tarea | Clic en el `●` de la fila |
| Editar texto | Doble clic en el texto de la tarea |
| Editar / poner fecha | Clic en la fecha de la tarea (o `＋ fecha`) |
| Menú completo de una tarea | Clic derecho sobre la tarea |
| Borrar | Clic en la `✕` que aparece al pasar el mouse por la fila |
| Opciones (tema, iniciar con Windows) | Botón `⚙` o clic derecho en la barra de título |

### Estética "glass" — límites

tkinter no tiene blur nativo. El efecto se arma con transparencia de ventana +
el *blur acrylic* de Windows (`SetWindowCompositionAttribute`) por detrás. Notas:

- El acrylic sólo se usa en el **tema oscuro**; en claro se lava sobre fondos
  claros, así que el tema claro es sólo translúcido.
- Las esquinas quedan rectas: Windows no redondea ventanas sin marco.
- Si el blur da problemas (parpadeos, lentitud), arrancá con la variable de
  entorno `TW_NOACRYLIC=1` para desactivarlo y dejar sólo la translucidez.

Las tareas se ordenan solas: pendientes arriba, después por fecha más cercana y
prioridad. Las atrasadas quedan en rojo. Se guarda en cada cambio y hay autosave
cada 30 s; recuerda posición, tamaño y estado de la ventana.

## Archivos

| Archivo | Qué es |
|---|---|
| `task_widget.py` | La aplicación. Un solo archivo. |
| `tasks.json` | Tus tareas + geometría de la ventana. Local, **fuera del repo** (`.gitignore`). La app lo crea en el primer arranque. |
| `README.md` | Este archivo. |
| `.github/workflows/build.yml` | CI: compila el `.exe` en cada push y publica el Release en los tags. |

---

## Build / CI

GitHub Actions (`.github/workflows/build.yml`) compila el ejecutable con
**PyInstaller** en un runner de Windows.

- **En cada push / PR a `main`**: compila y sube `TaskWidget.exe` como *artifact*
  de la corrida (pestaña **Actions** del repo → la corrida → *Artifacts*).
  Sirve para probar; el artifact se borra a los 90 días.
- **En un tag `vX.Y.Z`**: además crea un **Release** con el `.exe` adjunto y notas
  autogeneradas. Eso es lo que baja la gente.

### Sacar una versión nueva

```bash
# 1. actualizá el Changelog del README y commiteá
git add README.md task_widget.py
git commit -m "release v4"

# 2. tag + push  →  Actions compila y publica el Release solo
git tag v4.0.0
git push --tags
```

Compilar a mano localmente (si querés probar el `.exe` sin esperar a Actions):

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name TaskWidget task_widget.py
# queda en dist/TaskWidget.exe
```

---

## Changelog

### v4 — 2026-09-05

**Nuevo**

- **Tema claro / oscuro / automático** (sigue el de Windows), en el menú `⚙`.
  Estética translúcida tipo *glass*; en oscuro además usa el blur acrylic de
  Windows por detrás. Variable `TW_NOACRYLIC=1` para desactivar el blur.
- Opción **"Iniciar con Windows"** en el menú `⚙` / clic derecho en la barra.
  Usa la clave `Run` del usuario actual (sin permisos de admin); al arrancar
  re-escribe la ruta por si moviste el archivo.
- **CI en GitHub Actions**: compila `TaskWidget.exe` con PyInstaller en cada push
  y publica un Release con el `.exe` al pushear un tag `vX.Y.Z`.
- `tasks.json` se lee tolerando BOM (por si lo editás con un editor que lo agrega).

**Arreglos**

- La ventana **ya no se puede arrastrar fuera de la pantalla**. Durante el arrastre
  siempre queda una parte visible; al soltar se acomoda entera dentro del monitor.
  Funciona con varios monitores (se puede mover entre ellos) y recupera la ventana
  al arrancar si había quedado en un monitor que ya no está.
- El botón **`+`** ya no se recorta al achicar la ventana: ahora se comprime solo
  el campo de texto y los botones fijos conservan su tamaño.

### v3 — 2026-09-04

**Arreglos**

- El atajo global **Ctrl+Alt+T** ahora funciona. No andaba porque las llamadas a la
  API de Windows se hacían sin `argtypes`: en Windows de 64 bits los handles se
  truncaban a 32 bits y `RegisterHotKey` fallaba en silencio. Además el hilo del
  atajo ya no toca tkinter directamente (no es thread-safe): prende un flag que el
  hilo principal revisa cada 150 ms.
- La **fecha de una tarea ya se puede editar**. Se sacó el pop-up (fallaba por
  problemas de foco al ser la ventana principal `overrideredirect`). Ahora se edita
  inline, igual que el texto.

**Nuevo**

- Colapsado, la barrita pasa a **always-on-top**, así nunca queda tapada y siempre
  se puede reabrir (doble clic en el título o botón `–`), aunque el atajo falle.
  Al expandir vuelve al nivel escritorio.
- **Contador por prioridad** en la barra de título: `●2 ●1 ●0` (alta / media / baja),
  cuenta solo las pendientes.
- **Ventana redimensionable**: agarre `◢` abajo a la derecha. El tamaño (`w`, `h`) se
  guarda en `tasks.json`. La lista scrollea sola y el texto re-ajusta el ancho.
- Editar la fecha: doble clic (o un clic) sobre la fecha de la tarea; si no tiene,
  muestra `＋ fecha`.

### v2 — 2026-09-04

**Cambio de modelo de ventana**

- El widget deja de estar "siempre encima" y pasa a **vivir pegado al escritorio**:
  aparece detrás de las ventanas normales (nivel escritorio, vía `SetWindowPos` +
  `HWND_BOTTOM`). Al hacerle clic sube; al hacer clic afuera vuelve a bajar.
- `WS_EX_TOOLWINDOW`: no aparece en la barra de tareas ni en Alt+Tab.

**Nuevo**

- **Atajo global Ctrl+Alt+T** para traerlo al frente / expandirlo (registrado con
  `RegisterHotKey` en un hilo aparte). — *(nota: recién quedó funcionando bien en v3)*
- Edición del **texto** de una tarea: doble clic → input inline (Enter guarda, Esc cancela).
- **Menú contextual** (clic derecho) en cada tarea: editar texto, cambiar fecha,
  prioridad, marcar hecha/pendiente, eliminar.
- El campo de fecha **limita lo que se puede tipear**: solo dígitos, `/` y `-`,
  máximo 10 caracteres.
- Colapsar/expandir separado en `_collapse()` / `_expand()`; el expand re-renderiza.

### v1 — 2026-09-03

Primera versión.

- Ventana sin bordes, siempre visible, semitransparente (`-alpha 0.94`) y **arrastrable**
  desde la barra de título.
- **Alta / baja de tareas**, marcar como hecha (tachado), eliminar (aparece la `✕` al
  pasar el mouse por la fila).
- **Fecha de vencimiento** opcional. Acepta `DD/MM`, `YYYY-MM-DD`, `DD/MM/YYYY`.
  Etiqueta con días restantes; en rojo si está atrasada o vence hoy.
- **Prioridad** Alta / Media / Baja (punto de color, clic para ciclar).
- Orden automático: pendientes primero, después por fecha más cercana y prioridad.
- **Persistencia** en `tasks.json` (guardado en cada cambio + autosave cada 30 s).
  Recuerda la posición de la ventana y si está colapsada.
- Botón `–` para colapsar a solo la barra de título; `✕` para cerrar.
