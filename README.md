# imageWatcher (Linux Mint)

Clon **libre y clean-room** de la funcionalidad de [PicPick](https://picpick.app/es/),
reimplementado desde cero para **Linux Mint 22.3 (Cinnamon / X11)** con
Python + GTK3 + Pillow + Xlib.

> Aviso legal: este proyecto es una reimplementacion independiente basada en las
> funciones descritas publicamente en la web de PicPick. No contiene ni usa codigo
> del binario original, no esta afiliado a NGWIN y no se ha realizado ingenieria
> inversa sobre el software propietario.

## Funciones

### Captura de pantalla
- Pantalla completa (todos los monitores).
- Ventana activa (con decoraciones).
- Region seleccionable con el raton, con resaltado de ventana al pasar el cursor.
  La seleccion se puede **mover** (arrastrando desde dentro) y **redimensionar**
  (tiradores de esquinas/bordes) antes de confirmar con **Enter** o doble clic
  (**Esc** cancela). Muestra el tamano en px.
- Repetir la ultima captura.
- Captura con retardo configurable.
- Copia automatica al portapapeles y autoguardado opcional.
- Opcion de incluir el cursor del raton.

### Editor de imagenes
- Anotaciones: lapiz, rotulador, resaltador, linea, flecha, rectangulo, elipse.
- Texto, sellos numerados, borrador (restaura la imagen base), relleno (bote de pintura).
- Desenfoque y mosaico/pixelado por region.
- Efectos: escala de grises, invertir, desenfoque, enfoque, pixelado.
- Ajustes: brillo/contraste, color/saturacion.
- Transformaciones: rotar 90/180, voltear; recortar a seleccion; redimensionar.
- Borde/marco, marca de agua.
- Deshacer/rehacer, zoom, ajustar a ventana.
- Desplazar la imagen con la herramienta **Mover** (arrastrando con el boton
  izquierdo), con el boton central, `Shift+rueda` o las barras de scroll.
- Guardar en PNG, JPG, BMP, GIF, PDF y copiar al portapapeles.

### Herramientas de diseno (menu en el mouse)
No hay ventana de herramientas aparte. Con **clic derecho en la barra** (o *Mas >
Herramientas de diseno*) aparece un **menu en la posicion del raton** con las
herramientas. Las de medicion se proyectan **sobre el escritorio** en un overlay
*click-through* (se ven a pantalla completa y **no bloquean** el raton); se quitan
con la tecla **Esc**, volviendo a elegirlas o con *Ocultar superposiciones*
(al pulsar Esc se captura solo esa tecla, el resto del teclado no se bloquea).

- **Selector de color** con lupa/cuentagotas que sigue al cursor y muestra el color
  seleccionado. El **formato de salida** se elige con la **rueda del raton** sobre la
  lupa o en el menu (*Formato de color*): HEX, RGB, HSL, HSV, HTML, C++ o Delphi.
  Al cambiar el formato, **el color copiado se actualiza** en vivo. Se guarda un
  **historial de colores** (16) que aparece en la lupa y en el menu
  (*Historial de colores*, clic para recopiar; opcion de limpiarlo). El historial
  muestra y copia cada color en el **formato de color seleccionado**.
- **Lupa** que sigue al cursor.
- **Punto de mira**: arrastra desde cualquier punto o haz clic en dos esquinas
  para medir el rectangulo; muestra **Ancho x Alto (px)** y copia las medidas al
  cerrar. Tiene **imanes** que acoplan la seleccion a bordes de ventanas,
  bordes de pantalla y lineas de texto/UI.
- **Regla de pixeles**: clic en el origen y clic en el destino para medir la
  distancia (linea con marcas, en **px/cm** y `dx`/`dy`). Se copia y cierra.
- **Transportador**: clic en el vertice y clic en el primer brazo, y el angulo sigue
  al cursor; un tercer clic **copia los grados** y cierra.
- **Pizarra** para dibujar y guardar.

### Grabacion de pantalla
- Pantalla completa o region seleccionada, con `ffmpeg` (x11grab).
- FPS ajustable y audio del sistema opcional.

### Integracion
- Barra de captura flotante (se puede ocultar desde Preferencias, la bandeja
  o un atajo global).
- Icono en la bandeja del sistema.
- Atajos de teclado globales (X11) configurables para capturas, editor,
  grabador, herramientas de diseno y acciones de la aplicacion.
- Preferencias persistentes en `~/.config/imagewatcher/config.json`.
- Inicio automatico al entrar en sesion (opcional).

## Cobertura de caracteristicas (picpick.app/features)

Leyenda: ✅ implementado · ◐ parcial · ✗ requiere servicio externo/cuenta.

| Area | Caracteristica | Estado |
| --- | --- | --- |
| Captura | Pantalla completa / ventana activa / region | ✅ |
| Captura | Ventana con desplazamiento (scroll + stitch) | ✅ |
| Captura | Repetir ultima / region fija | ✅ |
| Captura | Captura con cursor / retrasada / autoguardado | ✅ |
| Captura | Multiples monitores | ✅ |
| Grabacion | Pantalla completa / region + audio del sistema | ✅ |
| Grabacion | Ventana / microfono | ◐ |
| Editor | Lapiz, pincel, rotulador, resaltador | ✅ |
| Editor | Aerografo, caligrafia | ✅ |
| Editor | Texto, etiquetas, flechas, lineas | ✅ |
| Editor | Formas y globos de texto (callouts) | ✅ |
| Editor | Sellos de numero y de cursor | ✅ |
| Editor | Seleccion rectangular y a mano alzada (lazo) | ✅ |
| Editor | Recortar, redimensionar, rotar, voltear | ✅ |
| Editor | Relleno, borrador, retoque (desenfoque de pincel) | ✅ |
| Efectos | Desenfoque, enfoque, mosaico, grises, invertir | ✅ |
| Efectos | Marco, marca de agua, sombra paralela | ✅ |
| Efectos | Brillo/contraste, color/saturacion, balance de color | ✅ |
| Guardar | Portapapeles, PNG/JPG/BMP/GIF, PDF | ✅ |
| Guardar | Impresora | ✅ |
| Guardar | URL (servidor HTTP local), programa externo | ✅ |
| Guardar | Nube (Drive/Dropbox/OneDrive/Box), FTP, redes sociales | ✗ |
| Diseno | Color (HEX/RGB/HTML/C++/Delphi) + paleta HSV + lupa | ✅ |
| Diseno | Regla, lupa, punto de mira, transportador, pizarra | ✅ |

### Librerias graficas usadas (las mas apropiadas por tarea)

- **GTK3 + PyGObject** — interfaz, `HeaderBar`, `DrawingArea`, portapapeles, impresion (`Gtk.PrintOperation`).
- **Cairo** — dibujo vectorial y previews (mira, regla, transportador, retocar, resaltados).
- **Pillow (PIL)** — operaciones raster: efectos, stitch de scroll, sombras, balance de color, sellos, lazo.
- **GdkPixbuf / Gdk** — captura del framebuffer y conversion rapida a/desde PIL.
- **Xlib + XTest + XFixes** — ventana activa, atajos globales, cursor real y scroll simulado.
- **ffmpeg** — grabacion de video (`x11grab`, audio por `pulse`).

## Requisitos

Linux Mint / Ubuntu sobre **X11** (Cinnamon por defecto). No funciona en Wayland
porque usa `XGrabKey` y `x11grab`.

Dependencias del sistema (ya presentes en la mayoria de instalaciones de Mint):

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
                 python3-pil python3-xlib ffmpeg libnotify-bin
```

## Instalacion

```bash
./install.sh        # instala dependencias, lanzador y entrada de menu
```

O ejecutar directamente sin instalar:

```bash
./run.sh
# o
python3 -m imagewatcher
```

## Uso

Al arrancar aparece la **barra de captura** flotante y un icono en la bandeja.
Tambien se muestra una **pantalla de bienvenida** con las instrucciones basicas;
puedes desactivarla con la casilla inferior o reabrirla desde *Mas > Guia de uso*.
Puedes mover la barra arrastrandola.

| Accion | Atajo por defecto |
| --- | --- |
| Pantalla completa | `Ctrl+Alt+1` |
| Region | `Ctrl+Alt+2` |
| Ventana activa | `Ctrl+Alt+3` |
| Repetir ultima | `Ctrl+Alt+4` |

Los atajos se cambian en **Preferencias > Atajos** con el formato
`modificadores+tecla`, por ejemplo `Print`, `Ctrl+Alt+1` o `Shift+Alt+P`.
Ademas de las capturas se pueden asignar atajos al editor, grabador,
herramientas de diseno (color, lupa, regla, punto de mira, transportador,
pizarra), ocultar superposiciones, mostrar/ocultar la barra, preferencias,
guia de uso y salir. Deja el campo vacio para desactivar un atajo.

> Si usas `Print`/`Shift+Print` y no funcionan, es porque Cinnamon ya los tiene
> asignados: desactivalos en *Preferencias del sistema > Teclado > Atajos* o usa
> las combinaciones por defecto.

## Atajos del editor
Como el visor de imagenes: `Ctrl+O` abrir, `Ctrl+S` guardar, `Ctrl+Shift+S`
guardar como, `Ctrl+P` imprimir, `Ctrl+W` cerrar, `Ctrl+Z` deshacer,
`Ctrl+Shift+Z`/`Ctrl+Y` rehacer.

`rueda`, `+` o `-`: zoom; `F`: ajustar a ventana; `Ctrl+0`: tamano real (100%);
`1`: alternar 100%/ajustar; `F11`: pantalla completa; `Alt+flechas`: desplazar;
`Ctrl+R`/`Ctrl+Shift+R`: rotar. La herramienta **Mover** esta activa al abrir:
arrastra con el boton izquierdo o usa el boton central, `Shift+rueda` o las
barras de scroll.

## Arena de pruebas (sandbox)

La suite usa **pytest** (`conftest.py` + configuracion en `pyproject.toml`). Si no hay
sesion grafica, `run_arena.sh` levanta un servidor **Xvfb** automaticamente:

```bash
python3 -m pytest          # directamente
./arena/run_arena.sh       # con Xvfb si hace falta (instala pytest si falta)
```

Dependencias de test: `pip install -r requirements-dev.txt`.

O en contenedor:

```bash
docker build -f arena/Dockerfile -t imagewatcher-arena .
docker run --rm imagewatcher-arena
```

Incluye 52 pruebas (captura y su rendimiento, editor, efectos, render,
herramientas y overlays, ventana de herramientas, config y atajos).

## Empaquetado

En `packaging/` hay scripts que toman la version desde `imagewatcher/__init__.py`:

```bash
./packaging/build_deb.sh        # dist/imagewatcher_<version>_all.deb
./packaging/build_appimage.sh   # dist/imageWatcher-<version>-x86_64.AppImage
# .exe (en Windows):  powershell -File packaging\windows\build_exe.ps1
```

Detalles y limitaciones del `.exe` en `packaging/README.md` y
`packaging/windows/README.md`.

## Estructura

```
imagewatcher/
  app.py           aplicacion, barra, bandeja y preferencias
  capture.py       captura X11 (pantalla, ventana, region, cursor)
  region.py        overlay de seleccion de region
  editor.py        editor de imagenes con anotaciones y efectos
  recorder.py      grabador de pantalla con ffmpeg
  hotkeys.py       atajos globales con XGrabKey
  config.py        preferencias persistentes
  gtk_util.py      utilidades GTK/PIL
  tools/           selector de color, lupa, regla, punto de mira, transportador, pizarra
arena/             arena de pruebas (tests + Xvfb + Docker)
packaging/         scripts .deb / AppImage / .exe + assets
run.sh             lanzador
install.sh         instalador
```

## Desinstalar

```bash
rm ~/.local/bin/imagewatcher \
   ~/.local/share/applications/imagewatcher.desktop \
   ~/.config/autostart/imagewatcher.desktop
rm -rf ~/.config/imagewatcher
```
