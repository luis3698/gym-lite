"""Ajustes que el administrador cambia desde la aplicación.

Tabla clave/valor: son pocos ajustes y no justifican una columna por cada uno. Todo
se lee con un valor por defecto, de modo que una base recién creada —o una clave que
todavía no existe— funciona sin necesidad de migración.
"""

from __future__ import annotations

from .config import FACE_COOLDOWN_SECONDS, MAX_FACE_COOLDOWN_SECONDS, MIN_FACE_COOLDOWN_SECONDS
from .db import execute, query_value
from .helpers import now_str

# Interruptor general del kiosco de acceso. Apagado deja el reconocimiento facial
# fuera de juego: ni cámara, ni identificación, ni captura durante la inscripción.
FACE_RECOGNITION_ENABLED = "face_recognition_enabled"

# Segundos que deben pasar para volver a registrar la entrada de la misma persona.
FACE_COOLDOWN = "face_cooldown_seconds"

DEFAULTS: dict[str, str] = {
    FACE_RECOGNITION_ENABLED: "1",
    FACE_COOLDOWN: str(FACE_COOLDOWN_SECONDS),
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
