"""Configuración y constantes de dominio compartidas por toda la aplicación."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = INSTANCE_DIR / "uploads"
DATABASE_PATH = INSTANCE_DIR / "gym.db"
SECRET_KEY_PATH = INSTANCE_DIR / "secret_key"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000

# Sesión: 8 horas, igual que el JWT de la versión original.
SESSION_HOURS = 8

# Bloqueo de cuenta tras intentos fallidos de inicio de sesión.
MAX_LOGIN_ATTEMPTS = 3
LOCK_MINUTES = 5

# Subida de fotos: se guardan como archivo en instance/uploads.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB por imagen
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# --- Vocabulario del dominio -------------------------------------------------

ROLES = {
    "ADMIN": "Administrador",
    "CAJA": "Caja",
    "ENTRENADOR": "Entrenador",
}
STAFF_ROLES = tuple(ROLES)

DURATIONS = {
    "DAY_1": "1 día",
    "DAY_7": "7 días",
    "DAY_15": "15 días",
    "MONTH": "Por mes",
}
VALID_DURATIONS = tuple(DURATIONS)

PAYMENT_METHODS = {
    "EFECTIVO": "Efectivo",
    "TARJETA": "Tarjeta",
    "TRANSFERENCIA": "Transferencia",
}
VALID_PAYMENT_METHODS = tuple(PAYMENT_METHODS)

SEX_OPTIONS = ("Masculino", "Femenino", "Otro")
BLOOD_TYPES = ("O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-")

# Topes defensivos: evitan que un formulario manipulado genere fechas de vencimiento
# absurdas o cantidades imposibles de cobrar.
MAX_MEMBERSHIP_MONTHS = 60
MAX_ITEM_QUANTITY = 10_000
MAX_STOCK = 1_000_000
MAX_AGE = 120

PASSWORD_POLICY_TEXT = (
    "La contraseña debe tener mínimo 8 caracteres, una mayúscula, "
    "una minúscula, un número y un carácter especial."
)

ACTION_LABELS = {
    "LOGIN_SUCCESS": "Inicio de sesión exitoso",
    "LOGIN_FAILED": "Intento de inicio de sesión fallido",
    "LOGOUT": "Cierre de sesión",
    "PROFILE_UPDATED": "Perfil actualizado",
    "PASSWORD_CHANGED": "Contraseña cambiada",
    "USER_CREATED": "Usuario creado",
    "USER_UPDATED": "Usuario editado",
    "USER_DELETED": "Usuario eliminado",
    "USER_DELETE_FAILED": "Intento fallido de eliminar usuario",
    "TARIFFS_UPDATED": "Tarifas de inscripción actualizadas",
    "SERVICE_CREATED": "Servicio complementario creado",
    "SERVICE_UPDATED": "Servicio complementario editado",
    "SERVICE_DELETED": "Servicio complementario eliminado",
    "CLIENT_CREATED": "Cliente registrado",
    "CLIENT_UPDATED": "Cliente editado",
    "CLIENT_DELETED": "Cliente eliminado",
    "CLIENT_DELETE_FAILED": "Intento fallido de eliminar cliente",
    "MEMBERSHIP_CREATED": "Inscripción de gimnasio registrada",
    "MEMBERSHIP_CANCELLED": "Inscripción de gimnasio cancelada",
    "PRODUCT_CREATED": "Producto creado",
    "PRODUCT_UPDATED": "Producto editado",
    "PRODUCT_DELETED": "Producto eliminado",
    "SALE_CREATED": "Venta registrada",
}


def get_secret_key() -> bytes:
    """Clave para firmar la cookie de sesión.

    Se genera una vez y se guarda en instance/secret_key. Si se generase en cada
    arranque, todas las sesiones abiertas se invalidarían al reiniciar el servidor.
    """
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_KEY_PATH.exists():
        key = SECRET_KEY_PATH.read_bytes()
        if len(key) >= 32:
            return key
    key = os.urandom(48)
    SECRET_KEY_PATH.write_bytes(key)
    try:  # en Windows es un no-op, en Unix restringe la lectura al propietario
        SECRET_KEY_PATH.chmod(0o600)
    except OSError:
        pass
    return key
