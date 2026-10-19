"""Acciones de la aplicacion que se pueden asociar a un atajo global.

Cada entrada es ``(accion, etiqueta, grupo, atajo_por_defecto)``. Los atajos
nuevos quedan vacios por defecto para no chocar con los del escritorio.
"""

HOTKEY_ACTIONS = [
    # Captura
    ("fullscreen", "Pantalla completa", "Captura", "Ctrl+Alt+1"),
    ("window", "Ventana activa", "Captura", "Ctrl+Alt+3"),
    ("region", "Region", "Captura", "Ctrl+Alt+2"),
    ("fixed", "Region fija", "Captura", "Ctrl+Alt+5"),
    ("freehand", "Freehand", "Captura", "Ctrl+Alt+6"),
    ("scrolling", "Ventana con desplazamiento", "Captura", ""),
    ("delayed", "Captura con retardo", "Captura", ""),
    ("monitor", "Monitor principal", "Captura", ""),
    ("repeat", "Repetir ultima captura", "Captura", "Ctrl+Alt+4"),
    # Editor y herramientas
    ("editor", "Editor de imagenes", "Editor y herramientas", ""),
    ("recorder", "Grabador de pantalla", "Editor y herramientas", ""),
    ("color", "Selector de color", "Editor y herramientas", ""),
    ("magnifier", "Lupa", "Editor y herramientas", ""),
    ("ruler", "Regla de pixeles", "Editor y herramientas", ""),
    ("crosshair", "Punto de mira", "Editor y herramientas", ""),
    ("protractor", "Transportador", "Editor y herramientas", ""),
    ("whiteboard", "Pizarra", "Editor y herramientas", ""),
    ("hide_overlays", "Ocultar superposiciones", "Editor y herramientas", ""),
    # Aplicacion
    ("preferences", "Preferencias", "Aplicacion", ""),
    ("welcome", "Guia de uso", "Aplicacion", ""),
    ("show_bar", "Mostrar barra de captura", "Aplicacion", ""),
    ("hide_bar", "Ocultar barra de captura", "Aplicacion", ""),
    ("quit", "Salir de imageWatcher", "Aplicacion", ""),
]

HOTKEY_DEFAULTS = {
    action: default for action, _label, _group, default in HOTKEY_ACTIONS
}
