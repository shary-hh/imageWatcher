# imageWatcher (Linux Mint)

Clon **libre y clean-room** de la funcionalidad de [PicPick](https://picpick.app/es/),
reimplementado desde cero para **Linux** (probado en Linux Mint 22.3 con
Cinnamon/X11, y compatible con GNOME, KDE Plasma, Sway y Hyprland en Wayland)
con Python + GTK3 + Pillow + Xlib.

> Aviso legal: este proyecto es una reimplementacion independiente basada en las
> funciones descritas publicamente en la web de PicPick. No contiene ni usa codigo
> del binario original, no esta afiliado a NGWIN y no se ha realizado ingenieria
> inversa sobre el software propietario.

## Funciones

### Captura de pantalla
- Pantalla completa (todos los monitores).
- Ventana activa (con decoraciones).
- Region seleccionable con el raton, con resaltado de ventana al pasar el cursor.
  Tiene **imanes** que acoplan los bordes a ventanas, pantalla y lineas de
  texto/UI (se activan/desactivan en **Preferencias > General** o con **M**),
  y se puede cambiar a **lazo** con la tecla **L**. La seleccion se
  puede **mover** (arrastrando desde dentro) y **redimensionar** (tiradores de
  esquinas/bordes) antes de confirmar con **Enter** o doble clic (**Esc** cancela).
  Muestra el tamano en px.
- Repetir la ultima captura.
- Captura con retardo configurable.
- Copia automatica al portapapeles y autoguardado opcional.
- Opcion de incluir el cursor del raton.
- Opcion de incluir el panel (barra de menu) del escritorio en las capturas de
  pantalla completa y monitor (`Preferencias > General`).
- En **Ventana con desplazamiento**, opcion de recortar la barra fija superior
  (pestanas y barra de direcciones del navegador) del resultado
  (`Preferencias > General`).

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
  muestra y copia cada color en el **formato de color seleccionado**. El tamano
  de zoom de la lupa se ajusta en **Preferencias > General**.
- **Lupa** que sigue al cursor.
- **Punto de mira**: arrastra desde cualquier punto o haz clic en dos esquinas
  para medir el rectangulo; muestra **Ancho x Alto (px)** y copia las medidas al
  cerrar. Tiene **imanes** que acoplan la seleccion a bordes de ventanas,
  bordes de pantalla y lineas de texto/UI (tecla **M** o Preferencias).
- **Regla de pixeles**: clic en el origen y clic en el destino para medir la
  distancia (linea con marcas, en **px/cm** y `dx`/`dy`). Se copia y cierra.
- **Transportador**: clic en el vertice y clic en el primer brazo, y el angulo sigue
  al cursor; un tercer clic **copia los grados** y cierra.
- **Pizarra** para dibujar y guardar.

### Grabacion de pantalla
- X11: pantalla completa o region seleccionada, con `ffmpeg` (x11grab). La
  region se puede mover y redimensionar antes de grabar, y se conserva al
  volver a pulsar **Ajustar region...**.
- Wayland/wlroots: pantalla completa o region con `wf-recorder` (y `slurp`
  para elegir la region).
- Wayland/GNOME: grabacion de pantalla completa con la API de GNOME Shell.
- Cuenta regresiva configurable antes de empezar (0-30 s), que se muestra a
  pantalla completa.
- Salida en **MP4** o **GIF animado**. El GIF no incluye audio y se limita a
  15 FPS, ideal para compartir una region corta.
- Atajo global `Ctrl+Alt+R` para iniciar o detener la grabacion sin abrir la
  ventana del grabador.
- FPS ajustable y audio del sistema opcional (segun el backend).

### Integracion
- Barra de captura flotante (se puede ocultar desde Preferencias, la bandeja
  o un atajo global).
- Seccion de **herramientas favoritas** en la barra (boton de estrella e iconos),
  al inicio de los menus de bandeja/herramientas y con **atajo global**
  configurable. Se eligen en **Preferencias > Favoritos** e incluyen tambien
  **Historial de colores** y **Formato de color**.
- Menus organizados por categorias: **Favoritos**, **Capturar** y
  **Herramientas**.
- Icono en la bandeja del sistema.
- Atajos de teclado globales configurables para capturas, editor,
  grabador, herramientas de diseno y acciones de la aplicacion. En X11 se usa
  `XGrabKey`; en Wayland se usa el portal `GlobalShortcuts` cuando el escritorio
  lo ofrece (si no, la app funciona sin atajos globales).
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
| Grabacion | Cuenta regresiva configurable antes de grabar | ✅ |
| Grabacion | Exportar a GIF animado | ✅ |
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
- **GdkPixbuf / Gdk** — captura del framebuffer en X11 y conversion rapida a/desde PIL.
- **Xlib + XTest + XFixes** — ventana activa, atajos globales, cursor real y scroll simulado en X11.
- **xdg-desktop-portal** — captura de pantalla, region nativa y atajos globales en Wayland.
- **grim / slurp / wf-recorder** — captura y grabacion nativas en compositores wlroots.
- **ffmpeg** — grabacion de video (`x11grab`, audio por `pulse`).

## Requisitos

Funciona en **X11** (Linux Mint / Cinnamon) y en **Wayland** (GNOME, KDE
Plasma, Sway, Hyprland y otros compositores wlroots). En X11 usa Xlib/XTest;
en Wayland usa el portal de escritorio y, cuando hace falta, herramientas
nativas del compositor.

Dependencias base:

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
                 python3-pil python3-xlib ffmpeg libnotify-bin
```

Para Wayland se recomienda ademas:

```bash
# Portal de escritorio (GNOME/KDE/wlroots segun tu escritorio)
sudo apt install xdg-desktop-portal
# GNOME
sudo apt install xdg-desktop-portal-gnome
# KDE Plasma
sudo apt install xdg-desktop-portal-kde
# wlroots (Sway, Hyprland, etc.)
sudo apt install xdg-desktop-portal-wlr grim slurp wf-recorder
# Opcional: simulacion de rueda/scroll en Wayland
sudo apt install ydotool wlrctl
```

`wf-recorder` y `slurp` son opcionales: habilitan grabacion y seleccion de
region nativas en wlroots. En GNOME la grabacion usa la API de GNOME Shell y
en KDE la app puede usar el portal para capturas.

### Limitaciones en Wayland

Wayland no permite a las aplicaciones leer la pantalla ni controlar el teclado
global directamente. imageWatcher usa los mecanismos estandar disponibles:

- La captura de pantalla y el selector de region pasan por
  `xdg-desktop-portal` (puede aparecer un dialogo del sistema). Repetir una
  captura de region vuelve a abrir el selector del portal.
- La ventana activa y la lista de ventanas solo se pueden consultar en
  compositores que exponen esa informacion (Sway, Hyprland o KDE con
  `kdotool`). Si no esta disponible, la captura de ventana pide seleccionar la
  region manualmente.
- Los atajos globales requieren el portal `GlobalShortcuts`. Si el escritorio
  no lo implementa (por ejemplo algunas versiones de GNOME), configura los
  atajos desde el propio escritorio o usa la barra/menu de imageWatcher.
- Las herramientas que siguen el puntero global (lupa, regla, punto de mira)
  funcionan mejor en Hyprland/KDE, donde se puede consultar la posicion del
  cursor; en otros compositores pueden quedar limitadas.
- Con monitores de distinta escala (HiDPI mixto), el recorte de una region puede
  ser aproximado porque el compositor entrega la captura en pixeles fisicos.
- Las superposiciones no interactivas (por ejemplo la lupa) pueden no recibir
  `Esc` en Wayland; usa *Ocultar superposiciones* o el menu para cerrarlas.
- La grabacion de region esta disponible en wlroots con `wf-recorder`; en
  GNOME se graba la pantalla completa. En KDE Plasma Wayland la grabacion
  integrada no esta disponible actualmente.
- En GNOME Wayland el icono de bandeja necesita la extension AppIndicator.

## Instalacion

```bash
./install.sh        # instala dependencias, lanzador y entrada de menu
```

Si prefieres el paquete `.deb` del sistema, puedes compilarlo e instalarlo con
un solo comando (pide tu contrasena para `sudo` y reinicia la aplicacion):

```bash
./install_deb.sh            # compila si hace falta, instala y reinicia
./install_deb.sh --test     # ademas ejecuta la arena de pruebas (si hay pytest)
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
| Iniciar/detener grabacion | `Ctrl+Alt+R` |

Los atajos se cambian en **Preferencias > Atajos** con el formato
`modificadores+tecla`, por ejemplo `Print`, `Ctrl+Alt+1` o `Shift+Alt+P`.
La tecla Impr Pant se puede escribir como `ImpPm`, `Impr Pant`, `PrintScreen`
o `Print`. Los botones **Usar Impr Pant para toda la pantalla** y **Usar Impr
Pant para la ventana activa** asignan `Print` a la captura completa (incluye el
panel y todos los monitores) o a la ventana activa (recorta la ventana, sin
panel). Al guardar, imageWatcher ofrece quitar el atajo que Cinnamon usa para
sus propias capturas, para que la tecla quede libre.
Ademas de las capturas se pueden asignar atajos al editor, grabador,
herramientas de diseno (color, lupa, regla, punto de mira, transportador,
pizarra), ocultar superposiciones, mostrar/ocultar la barra, preferencias,
guia de uso y salir. Deja el campo vacio para desactivar un atajo.

> Si `Print`/`ImpPm` no funciona, comprueba que ninguna otra aplicacion o el
> propio Cinnamon lo esten usando. Tambien puedes desactivarlo en
> *Preferencias del sistema > Teclado > Atajos* o usar las combinaciones por
> defecto.

## Atajos del editor
Como el visor de imagenes: `Ctrl+O` abrir, `Ctrl+S` guardar, `Ctrl+Shift+S`
guardar como, `Ctrl+P` imprimir, `Ctrl+W` cerrar, `Ctrl+Z` deshacer,
`Ctrl+Shift+Z`/`Ctrl+Y` rehacer.

### Memoria y rendimiento
- El historial de deshacer se limita por numero de pasos y por memoria
  (192 MB por pila), de modo que editar capturas 4K no dispara el consumo.
- Al cerrar el editor o una herramienta se liberan las imagenes y se devuelve
  la memoria retenida al sistema cuando es posible.
- Los atajos globales esperan eventos de X11 en lugar de consultar el teclado
  periodicamente: en reposo el consumo de CPU es practicamente nulo.
- La conversion de imagen a `GdkPixbuf` evita copias intermedias.

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

### Categorias de la arena

| Categoria | Marcador | Contenido |
| --- | --- | --- |
| Funcionamiento | `func` | captura, editor, herramientas, config, atajos, instancia unica y flujos completos |
| Estabilidad | `stability` | ciclos de apertura/cierre, presupuesto del historial, memoria, hilos, sockets, servidor HTTP y config corrupta |
| Seguridad | `security` | aislamiento del servidor de compartir, path traversal, permisos, ejecucion sin shell, secretos y autostart |

```bash
./arena/run_suites.sh                  # todas las categorias
./arena/run_suites.sh funcionamiento
./arena/run_suites.sh estabilidad
./arena/run_suites.sh seguridad
./arena/run_arena.sh -m security       # equivalente con pytest directo
```

O en contenedor:

```bash
docker build -f arena/Dockerfile -t imagewatcher-arena .
docker run --rm imagewatcher-arena
```

Incluye pruebas de captura y su rendimiento, editor, efectos, render,
herramientas y overlays, ventana de herramientas, config, atajos, la capa
de compatibilidad con Wayland, estabilidad de recursos y seguridad.

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
  capture.py       captura X11/Wayland (pantalla, ventana, region, cursor)
  session.py       deteccion de sesion, portal y herramientas Wayland
  region.py        overlay de seleccion de region
  editor.py        editor de imagenes con anotaciones y efectos
  recorder.py      grabador de pantalla (ffmpeg/wf-recorder/GNOME)
  hotkeys.py       atajos globales (XGrabKey o portal GlobalShortcuts)
  config.py        preferencias persistentes
  gtk_util.py      utilidades GTK/PIL
  tools/           selector de color, lupa, regla, punto de mira, transportador, pizarra
arena/             arena de pruebas (tests + Xvfb + Docker)
packaging/         scripts .deb / AppImage / .exe + assets
run.sh             lanzador
install.sh         instalador
```

## Seguridad

- No subas tokens, claves ni credenciales al repositorio. `.gitignore` bloquea
  `.env`, claves privadas, configuracion y capturas locales.
- El workflow `.github/workflows/secrets.yml` ejecuta **gitleaks** en cada push
  y pull request.
- Si alguna credencial llego a commitearse, rota la credencial y purga el
  historial; borrar el archivo en un commit nuevo no la elimina del historial.

## Desinstalar

```bash
rm ~/.local/bin/imagewatcher \
   ~/.local/share/applications/imagewatcher.desktop \
   ~/.config/autostart/imagewatcher.desktop
rm -rf ~/.config/imagewatcher
```
