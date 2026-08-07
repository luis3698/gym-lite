"""Configuración y constantes de dominio compartidas por toda la aplicación."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _is_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".escritura"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        return False
    return True


def _resolve_instance_dir() -> Path:
    """Carpeta donde viven la base de datos, las fotos y la clave de sesión.

    Ejecutando el código fuente es `instance/` junto al proyecto. En la versión
    instalada (ejecutable compilado) va junto al .exe, salvo que esa carpeta sea
    de solo lectura —caso típico de «Archivos de programa»—, en cuyo caso se usa
    el perfil del usuario. GYMLITE_DATA_DIR permite forzar cualquier ruta.
    """
    override = os.environ.get("GYMLITE_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if getattr(sys, "frozen", False):
        beside_exe = Path(sys.executable).resolve().parent / "data"
        if _is_writable(beside_exe):
            return beside_exe
        fallback = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(fallback) / "GymManager Lite" / "data"

    return BASE_DIR / "instance"


INSTANCE_DIR = _resolve_instance_dir()
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

# --- Reconocimiento facial (kiosco de acceso) --------------------------------
# El navegador convierte cada rostro en 128 números («descriptor») y los manda aquí;
# el emparejamiento se hace en el servidor, así que la galería de rostros nunca sale
# de la máquina.

FACE_DESCRIPTOR_LENGTH = 128

# Distancia euclídea máxima para dar dos rostros por la misma persona.
# face-api recomienda 0,6 como punto de partida. Aquí se aprieta a 0,50 porque el
# coste de los dos errores no es simétrico: dejar entrar a quien no toca es peor que
# pedirle a un socio que se acerque otra vez a la cámara.
FACE_MATCH_THRESHOLD = 0.50

# Franja de duda: por encima del umbral pero cerca. No se identifica a nadie, se pide
# acercarse. Evita el caso feo de enseñar los datos de otra persona parecida.
FACE_UNCERTAIN_THRESHOLD = 0.58

# Muestras por cliente. Varias tomas (con gafas, sin ellas, otra luz) suben mucho el
# acierto; pasado ese punto solo engordan la comparación.
MAX_FACES_PER_CLIENT = 5

# Antirrebote: quien acaba de pasar no vuelve a registrarse durante este rato aunque
# siga delante de la cámara. Se le sigue mostrando su ficha, pero como «ya registrado».
# Este es el valor de fábrica; el administrador lo cambia desde «Control de acceso».
FACE_COOLDOWN_SECONDS = 90

# Límites del antirrebote configurable. Por debajo de 5 s la cámara registraría varias
# entradas del mismo paso; por encima de 12 h no dejaría entrar dos veces en un día.
MIN_FACE_COOLDOWN_SECONDS = 5
MAX_FACE_COOLDOWN_SECONDS = 43_200

# Nadie razonable entra más veces que esto en un día; sirve de tope defensivo por si
# la cámara se queda mirando una foto pegada en la pared.
MAX_ACCESS_LOGS_PER_DAY = 50

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

# --- Ficha deportiva del cliente ---------------------------------------------
# Todo esto es opcional: se rellena con el tiempo, no en el mostrador el primer día.

CLIENT_GOALS = (
    "Bajar de peso",
    "Ganar masa muscular",
    "Tonificar",
    "Mantenerse en forma",
    "Rendimiento deportivo",
    "Rehabilitación",
)
ACTIVITY_LEVELS = ("Principiante", "Intermedio", "Avanzado")

# Topes para que un dedazo (1.75 en vez de 175) no pase inadvertido.
MAX_HEIGHT_CM = 260
MAX_WEIGHT_KG = 400

# Topes defensivos: evitan que un formulario manipulado genere fechas de vencimiento
# absurdas o cantidades imposibles de cobrar.
# Cuántas veces se puede comprar de golpe la misma duración (60 días, 60 meses…).
MAX_MEMBERSHIP_QUANTITY = 60
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
    "FACE_ENROLLED": "Rostro registrado para el acceso",
    "FACE_REMOVED": "Rostro eliminado del acceso",
    "FACE_TOGGLED": "Reconocimiento facial activado o desactivado",
    "FACE_COOLDOWN_CHANGED": "Antirrebote del kiosco modificado",
}

# Motivos del kiosco: el código que se guarda en access_logs.reason y el texto que se
# muestra en pantalla.
ACCESS_REASONS = {
    "ACTIVE": "Inscripción vigente",
    "EXPIRED": "Inscripción vencida",
    "NO_MEMBERSHIP": "Sin inscripción registrada",
    "UNKNOWN": "Rostro no reconocido",
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
