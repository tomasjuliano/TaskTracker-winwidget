# Changelog

Historial de cambios de **TaskTracker Widget**. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); los números `#N`
enlazan a los issues del repo.

## v5.0.0 — 2026-09-06

### Novedades

- **Recordatorios de vencimiento.** Cada 30 min revisa las tareas atrasadas o que
  vencen hoy y las notifica con un toast nativo de Windows (una vez por día por
  tarea). El aviso **queda guardado** en el Centro de notificaciones (`Win + N`),
  con nombre e icono propios. Se prende/apaga en Opciones. (#10)
- **Reordenar tareas arrastrando.** Al pasar el mouse por una fila aparece una
  manija a la izquierda; la arrastrás para cambiar el orden, que pasa a "manual"
  y se guarda. Toggle en Opciones y enlace al pie para volver al orden
  automático. (#11)
- **Mini calendario para el vencimiento.** Iconito de calendario al lado del
  campo "venc." y opción "Fecha en calendario…" en el menú de cada tarea. Mes
  navegable, "Hoy" y "Borrar". (#14)
- **Atajo global configurable.** En Opciones se captura la combinación que quieras
  y se guarda. Si está ocupada por otro programa, ahora se avisa en la propia UI
  (no sólo por consola). (#16)
- **Icono en la bandeja del sistema.** Clic izquierdo muestra/trae al frente el
  widget; clic derecho abre el menú (mostrar/ocultar · opciones · salir). Sigue
  el tema claro/oscuro y el tooltip muestra los pendientes. (#18)
- **La ✕ minimiza a la bandeja** en vez de cerrar, estilo Discord. Toggle en
  Opciones ("Al cerrar, minimizar a la bandeja"); "Salir" desde el tray cierra
  de verdad. La primera vez avisa. (#5)
- **"Mantener siempre visible"** en Opciones: el widget queda sobre las demás
  ventanas en lugar de a nivel escritorio. (#15)
- Colapsado, el título muestra los **pendientes** (`Tareas · 3`). (#12)
- Enlace **"Limpiar N completadas"** al pie de la lista. (#13)
- **Deshacer** al borrar una tarea: enlace al pie por unos segundos, o `Ctrl+Z`. (#21)

### Arreglos

- Tooltips ilegibles en tema claro (fondo y texto oscuros). (#1)
- Fuga de objetos `Font` al renderizar tareas completadas. (#3)
- La edición inline podía dejar el widget "pegado" al frente si no se confirmaba. (#4)
- El campo "venc." quedaba con el placeholder pegado al texto al agregar una
  tarea con Enter desde ese campo. (#6)
- La rueda del mouse scrolleaba la lista aunque el puntero no estuviera encima. (#7)
- El atajo global ahora se desregistra desde su propio hilo al cerrar. (#8)
- **Instancia única**: abrir el `.exe` de nuevo trae al frente la ventana que ya
  está corriendo en vez de arrancar una segunda que se pisaba el `tasks.json`. (#2)
- El mini calendario quedaba tapado por la ventana; ahora se fuerza al frente.
- Al arrastrar una tarea, sólo el marco cambiaba de color y los botones quedaban
  con el color viejo (parche); ahora se tiñe la fila entera.

### Bajo el capó

- La app se identifica ante Windows como **TaskTracker** (título, Alt+Tab, tray);
  el encabezado del widget sigue diciendo "Tareas". (#19)
- Icono propio del `.exe` (`assets/icon.ico`). (#17)
- Los diálogos (Opciones, calendario) usan el icono de la app según el tema, no
  la pluma de Tk. (#20)
- Los iconos de fila (manija, tacho, calendario) son PNG con anti-alias generados
  desde SVG (`assets/*.svg` + `assets/gen_row_icons.py`), no dibujos a mano en
  Canvas. La manija y el tacho sólo se ven al pasar el mouse por la fila; borrar
  pasó de una ✕ a un tacho de basura.

## v4.0.0 — 2026-09-05

### Novedades

- **Tema claro / oscuro / automático** (sigue el de Windows), en el menú `⚙`.
  Estética translúcida tipo *glass*; en oscuro además usa el blur *acrylic* de
  Windows por detrás. Variable `TW_NOACRYLIC=1` para desactivarlo.
- Opción **"Iniciar con Windows"** (clave `Run` del usuario, sin permisos de
  admin; re-escribe la ruta al arrancar por si moviste el archivo).
- **CI en GitHub Actions**: compila `TaskWidget.exe` con PyInstaller en cada push
  y publica un Release con el `.exe` al pushear un tag `vX.Y.Z`.
- `tasks.json` se lee tolerando BOM.

### Arreglos

- La ventana **ya no se puede arrastrar fuera de la pantalla**: durante el
  arrastre siempre queda una parte visible y al soltar se acomoda entera dentro
  del monitor. Multi-monitor: se puede mover entre pantallas y se recupera al
  arrancar si quedó en un monitor que ya no está.
- El botón **`+`** ya no se recorta al achicar la ventana (se comprime sólo el
  campo de texto).
- **Con foco** el widget es casi opaco; **sin foco** se vuelve translúcido y se
  funde con el fondo del escritorio.

### Estética

- **Nueva paleta**: oscuro = negro + amarillo; claro = blanco + azul/celeste.
- **Inputs con esquinas redondeadas**, igual que la ventana.
- **Slider de opacidad** para el estado sin foco, en Opciones.
- Se quitó el icono de *grip* de la franja de redimensionar.
- En el primer arranque aparece en la **esquina superior derecha**; después
  recuerda dónde lo dejaste.
- Iconos de la barra (`x`, `–`, engranaje, `+`) de [Lucide](https://lucide.dev),
  rasterizados y embebidos, con variante por tema.

## v3.0.0 — 2026-09-04

### Arreglos

- El atajo global **Ctrl+Alt+T** ahora funciona. No andaba porque las llamadas a
  la API de Windows se hacían sin `argtypes`: en 64 bits los handles se truncaban
  y `RegisterHotKey` fallaba en silencio. Además el hilo del atajo ya no toca
  tkinter directamente (prende un flag que el hilo principal revisa).
- La **fecha de una tarea ya se puede editar** (inline, igual que el texto; se
  sacó el pop-up que fallaba por foco).

### Novedades

- Colapsado, la barrita pasa a **always-on-top**, así siempre se puede reabrir
  aunque el atajo falle. Al expandir vuelve al nivel escritorio.
- **Contador por prioridad** en la barra de título (sólo pendientes).
- **Ventana redimensionable** arrastrando la franja de abajo; el tamaño se
  guarda. La lista scrollea y el texto re-ajusta el ancho.
- Editar la fecha con doble clic (o un clic) sobre ella; si no tiene, muestra
  `＋ fecha`.

## v2.0.0 — 2026-09-04

### Cambio de modelo de ventana

- El widget deja de estar "siempre encima" y pasa a **vivir pegado al
  escritorio**: aparece detrás de las ventanas normales (`SetWindowPos` +
  `HWND_BOTTOM`). Al hacerle clic sube; al hacer clic afuera vuelve a bajar.
- `WS_EX_TOOLWINDOW`: no aparece en la barra de tareas ni en Alt+Tab.

### Novedades

- **Atajo global Ctrl+Alt+T** para traerlo al frente (quedó estable en v3).
- Edición del **texto** de una tarea: doble clic → input inline.
- **Menú contextual** (clic derecho) en cada tarea: editar, fecha, prioridad,
  hecha/pendiente, eliminar.
- El campo de fecha limita lo tipeable: dígitos, `/`, `-`, máx. 10 caracteres.

## v1.0.0 — 2026-09-03

Primera versión.

- Ventana sin bordes, siempre visible, semitransparente y arrastrable desde la
  barra de título.
- Alta / baja de tareas, marcar como hecha, eliminar.
- **Fecha de vencimiento** opcional (`DD/MM`, `YYYY-MM-DD`, `DD/MM/YYYY`); etiqueta
  con días restantes, en rojo si está atrasada o vence hoy.
- **Prioridad** Alta / Media / Baja (punto de color, clic para ciclar).
- Orden automático: pendientes primero, después por fecha y prioridad.
- **Persistencia** en `tasks.json` (guardado en cada cambio + autosave cada 30 s);
  recuerda posición y estado colapsado.
- Botón `–` para colapsar; `✕` para cerrar.
