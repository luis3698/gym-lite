"""Ajustes que el administrador cambia desde la aplicación.

Tabla clave/valor: son pocos ajustes y no justifican una columna por cada uno. Todo
se lee con un valor por defecto, de modo que una base recién creada —o una clave que
todavía no existe— funciona sin necesidad de migración.
"""

from __future__ import annotations

from .config import (
    DEFAULT_BACKUP_KEEP,
    FACE_COOLDOWN_SECONDS,
    MAX_BACKUP_KEEP,
    MAX_FACE_COOLDOWN_SECONDS,
    MIN_BACKUP_KEEP,
    MIN_FACE_COOLDOWN_SECONDS,
)
from .db import execute, query_value
from .helpers import now_str

# Interruptor general del kiosco de acceso. Apagado deja el reconocimiento facial
# fuera de juego: ni cámara, ni identificación, ni captura durante la inscripción.
FACE_RECOGNITION_ENABLED = "face_recognition_enabled"

# Segundos que deben pasar para volver a registrar la entrada de la misma persona.
FACE_COOLDOWN = "face_cooldown_seconds"

# Imprimir el código de barras en los recibos. Es lo que permite leer un recibo para
# devolverlo; apagarlo no borra nada, solo deja de imprimirlo.
BARCODE_ENABLED = "barcode_enabled"

# Copias de seguridad: cada cuánto y cuántas conservar.
BACKUP_FREQUENCY = "backup_frequency"
BACKUP_KEEP = "backup_keep"

# Datos del establecimiento que se imprimen en los recibos.
BUSINESS_KEYS = (
    "business_name", "business_nit", "business_address", "business_city",
    "business_phone", "business_email", "business_extra", "business_tax_note",
    "business_footer", "receipt_width",
)

DEFAULTS: dict[str, str] = {
    FACE_RECOGNITION_ENABLED: "1",
    FACE_COOLDOWN: str(FACE_COOLDOWN_SECONDS),
    BARCODE_ENABLED: "1",
    BACKUP_FREQUENCY: "DAILY",
    BACKUP_KEEP: str(DEFAULT_BACKUP_KEEP),
    # Ejemplo listo para editar: así el primer recibo ya sale con la forma correcta y
    # se ve qué va en cada sitio, en vez de imprimirse con huecos vacíos.
    "business_name": "GIMNASIO EJEMPLO S.A.S.",
    "business_nit": "901.234.567-8",
    "business_address": "Calle 12 # 34-56, Local 3",
    "business_city": "Bogotá D.C., Colombia",
    "business_phone": "(601) 234 5678 · Cel. 300 123 4567",
    "business_email": "contacto@gimnasioejemplo.com",
    "business_extra": "www.gimnasioejemplo.com · @gimnasioejemplo",
    "business_tax_note": "No responsable de IVA · Régimen simplificado",
    "business_footer": (
        "Documento equivalente. No es una factura electrónica.\n"
        "Cambios y devoluciones dentro de los 5 días siguientes presentando este recibo.\n"
        "¡Gracias por entrenar con nosotros!"
    ),
    "receipt_width": "80",
}


def get_setting(key: str) -> str:
    value = query_value("SELECT value FROM settings WHERE key = ?", (key,))
    if value is None:
        return DEFAULTS.get(key, "")
    return str(value)


def set_setting(key: str, value: str) -> None:
    execute(
        """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
        (key, value, now_str()),
    )


def get_flag(key: str) -> bool:
    return get_setting(key) == "1"


def set_flag(key: str, enabled: bool) -> None:
    set_setting(key, "1" if enabled else "0")


def face_recognition_enabled() -> bool:
    """Atajo del interruptor que más se consulta (lo mira cada vista del kiosco)."""
    return get_flag(FACE_RECOGNITION_ENABLED)


def barcode_enabled() -> bool:
    """¿Se imprime el código de barras en los recibos?"""
    return get_flag(BARCODE_ENABLED)


def backup_keep() -> int:
    """Cuántas copias conservar, recortado a los límites admitidos."""
    try:
        value = int(get_setting(BACKUP_KEEP))
    except ValueError:
        return DEFAULT_BACKUP_KEEP
    return max(MIN_BACKUP_KEEP, min(MAX_BACKUP_KEEP, value))


def business_info() -> dict:
    """Datos del establecimiento para la cabecera de los recibos.

    Se devuelven sin el prefijo `business_` para que la plantilla quede legible:
    `negocio.nit` en vez de `negocio.business_nit`.
    """
    datos = {
        clave.replace("business_", "", 1): get_setting(clave)
        for clave in BUSINESS_KEYS if clave != "receipt_width"
    }
    ancho = get_setting("receipt_width")
    datos["width"] = ancho if ancho in ("58", "80") else "80"
    return datos


def face_cooldown_seconds() -> int:
    """Antirrebote en segundos, siempre dentro de los límites admitidos.

    Se recorta al leer y no solo al guardar: si el valor quedara fuera de rango por
    una edición manual de la base, el kiosco seguiría comportándose de forma sensata.
    """
    try:
        value = int(get_setting(FACE_COOLDOWN))
    except ValueError:
        return FACE_COOLDOWN_SECONDS
    return max(MIN_FACE_COOLDOWN_SECONDS, min(MAX_FACE_COOLDOWN_SECONDS, value))
