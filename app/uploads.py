"""Guardado y borrado de las imágenes que sube el personal.

Todas las imágenes del programa —clientes, usuarios y productos— pasan antes por el
editor del navegador (`static/photo-capture.js`), así que llegan aquí ya recortadas y
como data URL. No hay ninguna subida de archivo directa: por eso este módulo solo sabe
de data URLs y no acepta un `FileStorage`.

Se guardan como archivos en instance/uploads y en la base solo queda el nombre del
archivo. Guardarlas dentro de la propia base (como hacía la versión original con
base64) hincha cada consulta que lea esa fila.
"""

from __future__ import annotations

import base64
import binascii
import re
import secrets
from pathlib import Path

from .config import MAX_UPLOAD_BYTES, UPLOAD_DIR

# Marca que envía el editor de fotos cuando el usuario pulsa "Quitar foto".
REMOVE_TOKEN = "__REMOVE__"


class UploadError(ValueError):
    """La imagen no se pudo aceptar (formato o tamaño)."""


def delete_image(filename: str | None) -> None:
    """Borra una foto del disco. Silencioso si ya no está."""
    if not filename:
        return
    # Solo el nombre: descarta cualquier intento de salir del directorio.
    safe = Path(filename).name
    try:
        (UPLOAD_DIR / safe).unlink(missing_ok=True)
    except OSError:
        pass


# El editor del navegador siempre entrega un JPEG generado con canvas.toDataURL.
DATA_URL_RE = re.compile(r"^data:image/(jpeg|png|webp);base64,(?P<payload>[A-Za-z0-9+/=\s]+)$")

# Firmas de archivo de los formatos aceptados. Se comprueba el contenido y no solo la
# cabecera del data URL, que la escribe quien envía el formulario y puede mentir.
MAGIC_NUMBERS = (
    b"\xff\xd8\xff",       # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"RIFF",               # WEBP (RIFF....WEBP)
)


def save_data_url(data_url: str) -> str:
    """Decodifica la foto tomada con la cámara y la guarda como archivo JPEG."""
    match = DATA_URL_RE.match(data_url.strip())
    if not match:
        raise UploadError("La foto capturada no tiene un formato válido.")

    try:
        raw = base64.b64decode(match.group("payload"), validate=True)
    except (binascii.Error, ValueError):
        raise UploadError("No fue posible decodificar la foto capturada.") from None

    if not raw:
        raise UploadError("La foto capturada llegó vacía.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise UploadError(f"La foto supera el máximo de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not any(raw.startswith(magic) for magic in MAGIC_NUMBERS):
        raise UploadError("El contenido recibido no es una imagen.")

    name = f"{secrets.token_hex(16)}.jpg"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / name).write_bytes(raw)
    return name


def resolve_captured_photo(current: str | None, photo_data: str | None) -> tuple[str | None, str | None]:
    """Resuelve el campo del editor de fotos.

    Devuelve (nombre_a_guardar, nombre_a_borrar_del_disco):
      * vacío           -> no se tocó la foto
      * REMOVE_TOKEN    -> se quita la actual
      * data URL        -> se guarda la nueva y se borra la anterior
    """
    value = (photo_data or "").strip()
    if not value:
        return current, None
    if value == REMOVE_TOKEN:
        return None, current
    return save_data_url(value), current
