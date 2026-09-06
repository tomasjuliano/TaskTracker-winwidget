# TaskTracker

Un widget de tareas para el escritorio de Windows. Liviano, sin instalación y
**sin dependencias** — es un solo archivo de Python (tkinter).

---

## Qué hace

- **Vive en el escritorio.** Aparece *detrás* de las ventanas normales, como un
  widget de verdad: le hacés clic y sube, hacés clic afuera y vuelve a bajar.
  No te tapa lo que estás haciendo.
- **Siempre a mano.** Atajo global (`Ctrl+Alt+T`, configurable) para traerlo al
  frente desde cualquier lado. Colapsalo a una barrita y queda fija arriba de todo.
- **Tareas con lo justo.** Prioridad (alta / media / baja), fecha de vencimiento
  con mini calendario, marcar como hecha, editar en el lugar, reordenar
  arrastrando. Contador de pendientes por prioridad en la barra.
- **Te avisa.** Cuando una tarea vence o está atrasada salta un toast de Windows
  que **queda guardado** en el Centro de notificaciones (`Win + N`).
- **Se adapta.** Tema claro / oscuro / automático (sigue el de Windows), con una
  estética translúcida tipo *glass*. Ventana redimensionable y con opacidad
  ajustable.
- **En la bandeja del sistema.** Clic izquierdo lo muestra, clic derecho abre el
  menú. La ✕ lo manda a la bandeja en vez de cerrarlo (configurable, como Discord).
- **Arranca con Windows** si querés — un toggle, sin permisos de administrador.
- Todo se guarda solo en `tasks.json`, al lado del programa.

## Descargar

Bajá **`TaskWidget.exe`** de la [última Release](../../releases/latest) y hacé
doble clic. No necesita Python ni instalación; `tasks.json` se crea solo al lado
del `.exe` en el primer arranque.

> SmartScreen puede avisar "editor desconocido" (pasa con todo `.exe` sin firma
> digital): *Más información → Ejecutar de todas formas*. Algunos antivirus dan
> falso positivo con ejecutables de PyInstaller.

## Controles

| Acción | Cómo |
|---|---|
| Agregar tarea | Escribir abajo → Enter (o el `+`) |
| Prioridad de la nueva tarea | Clic en el `●` de la izquierda (baja → media → alta) |
| Fecha de vencimiento | Campo "venc." (`11/09`, `2026-09-11`, `11/09/2026`) o el iconito de calendario |
| Marcar hecha | Clic en el `○` de la fila |
| Editar texto / fecha | Doble clic en el texto; clic en la fecha (o `＋ fecha`) |
| Cambiar prioridad | Clic en el `●` de la fila |
| Reordenar | Pasar el mouse por la fila y arrastrar desde la manija de la izquierda |
| Borrar | Pasar el mouse por la fila → tacho de la derecha (`Ctrl+Z` para deshacer) |
| Limpiar completadas | Enlace al pie de la lista |
| Menú de una tarea | Clic derecho sobre ella |
| Mover la ventana | Arrastrar desde la barra "Tareas" |
| Redimensionar | Arrastrar la franja fina de abajo |
| Colapsar / expandir | Botón `–`, doble clic en el título, o el atajo global |
| Traer al frente | Atajo global (`Ctrl+Alt+T` por defecto) |
| Minimizar a la bandeja | Botón `✕` |
| Opciones | Botón `⚙` o clic derecho en la barra |
| Bandeja del sistema | Clic izq. = mostrar · clic der. = menú |

## Opciones (botón `⚙` o clic derecho en la barra)

- **Tema**: claro / oscuro / automático.
- **Mantener siempre visible**: el widget sube por encima de las demás ventanas.
- **Orden manual**: reordenás arrastrando; si está apagado, la lista se ordena
  sola (pendientes arriba, después por fecha más cercana y prioridad; atrasadas
  en rojo).
- **Iniciar con Windows**.
- **Al cerrar, minimizar a la bandeja**.
- **Avisar cuando una tarea vence**.
- **Atajo global**: "Cambiar…" y presionás la combinación que quieras.
- **Opacidad cuando no está en foco**: un slider.

## Notas

- El "vivir pegado al escritorio", el atajo global y los toasts usan API de
  Windows. En otros sistemas la app abre igual, pero sin esas tres features.
- El blur *acrylic* sólo se usa en el tema oscuro (en claro se lava sobre fondos
  claros). Si da problemas, arrancá con `TW_NOACRYLIC=1`. Las esquinas quedan
  rectas: Windows no redondea las ventanas sin marco.
- Cambios guardados en cada acción + autosave cada 30 s. Recuerda posición,
  tamaño y estado de la ventana.

## Correrlo desde el código

Requisitos: **Windows 10 / 11** y **Python 3.8+**
([python.org](https://www.python.org/downloads/), marcando *"Add Python to PATH"*).
tkinter viene incluido.

```bash
pythonw task_widget.py
```

`pythonw` no deja una consola abierta; usá `python task_widget.py` para ver los
mensajes por consola.

## Desarrollo

- **Un solo archivo**: [`task_widget.py`](task_widget.py).
- **CI** (`.github/workflows/build.yml`): compila `TaskWidget.exe` con PyInstaller
  en cada push a `main` (queda como *artifact* de la corrida) y publica un
  **Release** con el `.exe` al pushear un tag `vX.Y.Z`.
- **Sacar una versión**: actualizar [`CHANGELOG.md`](CHANGELOG.md), commitear,
  `git tag vX.Y.Z && git push --tags`.
- **Compilar local**:
  ```bash
  pip install pyinstaller
  pyinstaller --onefile --windowed --name TaskWidget --icon assets/icon.ico task_widget.py
  ```
- **Iconos**: fuentes SVG en `assets/`. El de la app (`icon.ico`) se arma con
  Pillow desde `assets/icon-light.svg`; los de fila (`grip` / `trash` / `calendar`)
  con `python assets/gen_row_icons.py`.

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md).

## Créditos

Iconos: [Lucide](https://lucide.dev) — licencia ISC (© Lucide Contributors).
