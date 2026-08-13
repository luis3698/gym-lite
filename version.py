"""Versión de GymManager Lite: único lugar donde vive el número.

Vive fuera del paquete `app/` a propósito: los scripts de `installer/` la
necesitan sin arrastrar el `import` de Flask y el resto de `app/__init__.py`
—que sí ocurriría si importaran algo de dentro del paquete `app`, porque Python
ejecuta `app/__init__.py` antes que cualquier submódulo suyo—. Este archivo,
en cambio, no tiene ninguna dependencia: lo puede importar cualquiera.
"""

from __future__ import annotations

APP_VERSION = "1.0.2"
