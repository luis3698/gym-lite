"""Licenciamiento del programa: valida contra Firebase, funciona sin conexión.

El programa se vende a distintos gimnasios, cada uno con su propia licencia.
Firebase es la fuente de verdad remota, pero un gimnasio no puede depender de que
internet funcione en todo momento para poder cobrar una inscripción, así que la
validación real ocurre contra una copia local, firmada y atada a este equipo, que
se sincroniza con Firebase cuando hay conexión.

## Por qué la licencia no vive en `gym.db`

`app/backups.py` hace una copia cruda de TODO el archivo de la base de datos.
Cualquier cosa guardada ahí —incluida la tabla `settings`— viaja dentro de cada
copia de seguridad y podría restaurarse en un equipo sin autorización. Por eso el
estado de la licencia vive en archivos aparte, junto a `secret_key` en
`INSTANCE_DIR` (ver `get_secret_key()` en `app/config.py`, mismo patrón).

## Qué protege esto y qué no

Este equipo lo controla por completo quien lo usa: no hay TPM ni enclave seguro, así
que ningún mecanismo puramente local es infalible ante alguien suficientemente
decidido. Lo que se hace aquí es defensa en profundidad —validación remota, huella
del equipo, almacenamiento firmado, comprobación del reloj— para que manipular la
licencia cueste mucho más que pagarla, no para prometer que es imposible. El límite
concreto de cada mecanismo se explica donde corresponde más abajo.

## Los estados posibles

`VALID`, `OFFLINE_GRACE` (sin conexión pero dentro del margen), `EXPIRED`,
`REVOKED`, `NOT_FOUND` (solo al activar), `TAMPERED` (el archivo local no pasa su
propia firma), `UNAUTHORIZED_DEVICE` (la huella no coincide con la registrada),
`CLOCK_TAMPER_SUSPECTED` (el reloj del equipo retrocedió más de lo tolerable),
`OFFLINE_GRACE_EXCEEDED` y `NOT_ACTIVATED`. `COMMUNICATION_ERROR` no es un estado
que devuelva `evaluate_license()` —un fallo de red con caché existente cae al
cálculo sin conexión, nunca bloquea por sí solo—; solo aparece como mensaje de
`LicenseError` cuando se intenta activar por primera vez sin poder llegar a
Firebase, que es el único caso donde no hay caché al que recurrir.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Response, g, redirect, request, url_for

from . import firebase_client
from .config import (
    CLOCK_TOLERANCE_MINUTES,
    INSTANCE_DIR,
    LICENSE_SYNC_INTERVAL_HOURS,
    OFFLINE_GRACE_DAYS,
)
from .device_id import device_fingerprint_hash

CACHE_PATH = INSTANCE_DIR / "license.dat"
PEPPER_PATH = INSTANCE_DIR / "license_key.bin"
SCHEMA_VERSION = 1

# --- Estados -------------------------------------------------------------

VALID = "VALID"
OFFLINE_GRACE = "OFFLINE_GRACE"
EXPIRED = "EXPIRED"
REVOKED = "REVOKED"
NOT_FOUND = "NOT_FOUND"
TAMPERED = "TAMPERED"
UNAUTHORIZED_DEVICE = "UNAUTHORIZED_DEVICE"
CLOCK_TAMPER_SUSPECTED = "CLOCK_TAMPER_SUSPECTED"
OFFLINE_GRACE_EXCEEDED = "OFFLINE_GRACE_EXCEEDED"
NOT_ACTIVATED = "NOT_ACTIVATED"
COMMUNICATION_ERROR = "COMMUNICATION_ERROR"

# Con la licencia en cualquiera de estos dos estados el programa se usa con
# normalidad; el resto bloquea (ver license_gate()).
USABLE_STATES = (VALID, OFFLINE_GRACE)

STATE_LABELS = {
    VALID: "Activa",
    OFFLINE_GRACE: "Activa (sin conexión)",
    EXPIRED: "Vencida",
    REVOKED: "Revocada",
    NOT_FOUND: "Clave no encontrada",
    TAMPERED: "Datos de licencia alterados",
    UNAUTHORIZED_DEVICE: "Equipo no autorizado",
    CLOCK_TAMPER_SUSPECTED: "Reloj del sistema sospechoso",
    OFFLINE_GRACE_EXCEEDED: "Sin conexión por demasiado tiempo",
    NOT_ACTIVATED: "Sin activar",
    COMMUNICATION_ERROR: "Error de comunicación con Firebase",
}

TIER_LABELS = {
    "TRIAL": "Prueba",
    "MONTHLY": "Mensual",
    "ANNUAL": "Anual",
    "PERPETUAL": "Perpetua",
}


class LicenseError(ValueError):
    """La licencia no se puede activar. El mensaje es para mostrarlo tal cual."""


class LicenseStatus:
    """Resultado de evaluar la licencia: el estado y lo que se sabe de ella."""

    def __init__(
        self,
        state: str,
        *,
        tier: str | None = None,
        expires_at: str | None = None,
        activated_at: str | None = None,
        license_key: str | None = None,
        last_online_check: str | None = None,
        grace_remaining_days: int | None = None,
        device_fingerprint: str | None = None,
    ) -> None:
        self.state = state
        self.tier = tier
        self.expires_at = expires_at
        self.activated_at = activated_at
        self.license_key = license_key
        self.last_online_check = last_online_check
        self.grace_remaining_days = grace_remaining_days
        self.device_fingerprint = device_fingerprint

    @property
    def usable(self) -> bool:
        return self.state in USABLE_STATES

    @property
    def label(self) -> str:
        return STATE_LABELS.get(self.state, self.state)

    @property
    def tier_label(self) -> str:
        return TIER_LABELS.get(self.tier or "", self.tier or "—")

    @property
    def days_until_expiry(self) -> int | None:
        """Para avisos («vence pronto») en el menú. None si no vence o no se sabe."""
        expires = _parse_iso(self.expires_at)
        if expires is None:
            return None
        return (expires - _now_utc()).days


# --- Fechas ----------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def format_display(value: str | None) -> str:
    """Fecha/hora en ISO 8601 (lo que guarda este módulo) a texto legible.

    El resto de la aplicación guarda las fechas como texto sin zona horaria
    ('YYYY-MM-DD HH:MM:SS', ver app/helpers.py) y el filtro `fechahora` de las
    plantillas espera justo ese formato. Las fechas de la licencia, en cambio,
    vienen de Firebase con zona horaria y microsegundos (ISO 8601 real), así que
    necesitan su propio formateador en vez de pasar por ese filtro sin más —
    de lo contrario `parse_datetime()` no las reconoce y todo se ve vacío.
    """
    parsed = _parse_iso(value)
    if parsed is None:
        return "—"
    return parsed.astimezone().strftime("%d/%m/%Y %H:%M")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


# --- Pepper: clave local de firma, protegida con DPAPI cuando se puede -----


def _read_pepper() -> bytes | None:
    """Lee la pepper del disco. Solo para VERIFICAR: nunca crea una nueva aquí,
    para no enmascarar un archivo dañado o cifrado por otra cuenta de Windows
    generando una pepper distinta en silencio."""
    if not PEPPER_PATH.exists():
        return None
    raw = PEPPER_PATH.read_bytes()
    try:
        import win32crypt  # type: ignore

        return win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1]
    except ImportError:
        return raw
    except Exception:
        return None


def _write_pepper(pepper: bytes) -> None:
    PEPPER_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        import win32crypt  # type: ignore

        blob = win32crypt.CryptProtectData(pepper, "GymManager Lite license", None, None, None, 0)
    except ImportError:
        blob = pepper
    tmp = PEPPER_PATH.with_name(PEPPER_PATH.name + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, PEPPER_PATH)


def _get_or_create_pepper() -> bytes:
    """Solo se usa al ESCRIBIR (activar o resincronizar), nunca al verificar."""
    pepper = _read_pepper()
    if pepper is not None and len(pepper) == 32:
        return pepper
    pepper = os.urandom(32)
    _write_pepper(pepper)
    return pepper


# --- Caché local firmado -----------------------------------------------------


def _sign(body: dict[str, Any], key: bytes) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def save_cache(license_data: dict[str, Any], *, server_time: datetime) -> None:
    """Guarda el estado verificado contra Firebase.

    `server_time` es la hora de confianza capturada en la propia sincronización (la
    cabecera Date de la respuesta HTTPS), no `datetime.now()`: es la base sobre la
    que se detecta después si el reloj del equipo se manipula.
    """
    pepper = _get_or_create_pepper()
    now_local = _now_utc()
    device_hash = device_fingerprint_hash()
    body = {
        "schema_version": SCHEMA_VERSION,
        "license_key": license_data["license_key"],
        "tier": license_data["tier"],
        "status_at_sync": license_data.get("status", "ACTIVE"),
        "expires_at": license_data.get("expires_at"),
        "device_fingerprint_hash": device_hash,
        "activated_at": license_data.get("activated_at") or _iso(now_local),
        "server_time_at_sync": _iso(server_time),
        "local_time_at_sync": _iso(now_local),
        "grace_period_days": OFFLINE_GRACE_DAYS,
    }
    key = hmac.new(pepper, device_hash.encode("utf-8"), hashlib.sha256).digest()
    payload = dict(body, _sig=_sign(body, key))

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_name(CACHE_PATH.name + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, CACHE_PATH)


class _CacheResult:
    """`state` viene relleno cuando la lectura falla (NOT_ACTIVATED / TAMPERED /
    UNAUTHORIZED_DEVICE); si es None, `data` trae el payload ya verificado."""

    __slots__ = ("state", "data")

    def __init__(self, state: str | None, data: dict[str, Any] | None) -> None:
        self.state = state
        self.data = data


def load_cache() -> _CacheResult:
    if not CACHE_PATH.exists():
        return _CacheResult(NOT_ACTIVATED, None)

    pepper = _read_pepper()
    if pepper is None:
        return _CacheResult(TAMPERED, None)

    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _CacheResult(TAMPERED, None)

    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        return _CacheResult(TAMPERED, None)

    sig = payload.get("_sig")
    if not isinstance(sig, str) or not sig:
        return _CacheResult(TAMPERED, None)
    body = {k: v for k, v in payload.items() if k != "_sig"}

    device_hash = body.get("device_fingerprint_hash")
    if not device_hash:
        return _CacheResult(TAMPERED, None)

    key = hmac.new(pepper, str(device_hash).encode("utf-8"), hashlib.sha256).digest()
    if not hmac.compare_digest(_sign(body, key), sig):
        return _CacheResult(TAMPERED, None)

    if device_hash != device_fingerprint_hash():
        return _CacheResult(UNAUTHORIZED_DEVICE, None)

    return _CacheResult(None, payload)


# --- Hora de confianza -------------------------------------------------------


def _effective_now(payload: dict[str, Any]) -> tuple[datetime | None, bool]:
    """Hora de confianza actual, y si se sospecha manipulación del reloj.

    No se confía en la hora absoluta del equipo, solo en cuánto ha avanzado desde
    la última sincronización honesta. Retroceder el reloj produce un avance
    negativo, que se recorta a cero: no compra tiempo. Adelantarlo solo acerca el
    vencimiento, nunca lo aleja, así que no hay incentivo a manipularlo en esa
    dirección.
    """
    server_time = _parse_iso(payload.get("server_time_at_sync"))
    local_time = _parse_iso(payload.get("local_time_at_sync"))
    if server_time is None or local_time is None:
        return None, True

    drift = _now_utc() - local_time
    if drift < -timedelta(minutes=CLOCK_TOLERANCE_MINUTES):
        return None, True
    return server_time + max(timedelta(0), drift), False


# --- Sincronización con Firebase (perezosa, sin hilo en segundo plano) -----

_sync_lock = threading.Lock()
_last_sync_attempt: datetime | None = None
# Si el último intento de sincronizar (cuando tocaba) falló por comunicación, se
# recuerda aquí: así una petición que llega DESPUÉS de ese fallo, pero ANTES de que
# vuelva a tocar reintentar (cada LICENSE_SYNC_INTERVAL_HOURS), sigue reflejando
# «sin conexión» en vez de volver a decir VALID sin haber confirmado nada nuevo.
# Al arrancar el proceso se asume que no hay motivo para dudar todavía: la primera
# comprobación real llega de inmediato, porque _sync_due() empieza en True.
_last_sync_ok = True


def _sync_due() -> bool:
    return _last_sync_attempt is None or _now_utc() - _last_sync_attempt >= timedelta(
        hours=LICENSE_SYNC_INTERVAL_HOURS
    )


def _try_online_sync(license_key: str) -> str:
    """Intenta refrescar contra Firebase sin bloquear al resto de peticiones.

    `threaded=True` en el servidor (ver gym_launcher.py) significa que dos
    peticiones pueden llegar casi a la vez; el candado evita que ambas disparen la
    sincronización por duplicado. Si no se consigue el candado, esta petición
    simplemente sigue con lo que ya había en caché ("skipped") — la siguiente
    petición que sí consiga el candado es la que actualiza el estado conocido.
    """
    global _last_sync_attempt
    if not _sync_lock.acquire(blocking=False):
        return "skipped"
    try:
        _last_sync_attempt = _now_utc()
        id_token, _ = firebase_client.sign_in_anonymously()
        data, server_time = firebase_client.fetch_license(license_key, id_token)
        if data is None:
            return "not_found"
        firebase_client.claim_device(license_key, id_token, device_fingerprint_hash())
        save_cache(data, server_time=server_time)
        return "ok"
    except firebase_client.FirebaseError:
        return "failed"
    finally:
        _sync_lock.release()


# --- Evaluación --------------------------------------------------------------


def _status_from_cache(
    payload: dict[str, Any], effective_now: datetime, *, online_ok: bool
) -> LicenseStatus:
    tier = payload.get("tier")
    license_key = payload.get("license_key")
    device_fp = payload.get("device_fingerprint_hash")
    expires_raw = payload.get("expires_at")
    expires_at = _parse_iso(expires_raw) if expires_raw else None

    if payload.get("status_at_sync") == "REVOKED":
        return LicenseStatus(REVOKED, tier=tier, license_key=license_key, device_fingerprint=device_fp)

    if expires_at is not None and effective_now > expires_at:
        return LicenseStatus(
            EXPIRED, tier=tier, expires_at=expires_raw, license_key=license_key, device_fingerprint=device_fp
        )

    last_sync = _parse_iso(payload.get("server_time_at_sync"))
    grace_deadline = last_sync + timedelta(days=OFFLINE_GRACE_DAYS) if last_sync else None
    if grace_deadline is not None and effective_now > grace_deadline:
        return LicenseStatus(
            OFFLINE_GRACE_EXCEEDED, tier=tier, expires_at=expires_raw, license_key=license_key,
            device_fingerprint=device_fp,
        )

    remaining = None
    state = VALID if online_ok else OFFLINE_GRACE
    if state == OFFLINE_GRACE and grace_deadline is not None:
        remaining = max(0, (grace_deadline - effective_now).days)

    return LicenseStatus(
        state, tier=tier, expires_at=expires_raw, activated_at=payload.get("activated_at"),
        license_key=license_key, last_online_check=payload.get("server_time_at_sync"),
        grace_remaining_days=remaining, device_fingerprint=device_fp,
    )


def evaluate_license() -> LicenseStatus:
    """Punto de entrada único: qué puede hacer el programa ahora mismo."""
    global _last_sync_ok

    result = load_cache()
    if result.state is not None:
        return LicenseStatus(result.state)

    payload = result.data
    assert payload is not None  # result.state es None solo cuando data está presente

    effective_now, clock_suspect = _effective_now(payload)
    if clock_suspect:
        return LicenseStatus(CLOCK_TAMPER_SUSPECTED, tier=payload.get("tier"), license_key=payload.get("license_key"))

    online_ok = _last_sync_ok
    if _sync_due():
        outcome = _try_online_sync(payload["license_key"])
        if outcome == "not_found":
            # Estaba en el caché pero ya no existe en Firebase: se trata como
            # revocada, no como un fallo de comunicación.
            _last_sync_ok = True  # se pudo hablar con Firebase; lo que dijo es REVOKED, no un fallo de red
            return LicenseStatus(REVOKED, tier=payload.get("tier"), license_key=payload.get("license_key"))
        if outcome == "ok":
            online_ok = True
            result = load_cache()
            if result.state is not None:
                return LicenseStatus(result.state)
            payload = result.data
            assert payload is not None
            effective_now, clock_suspect = _effective_now(payload)
            if clock_suspect:
                return LicenseStatus(
                    CLOCK_TAMPER_SUSPECTED, tier=payload.get("tier"), license_key=payload.get("license_key")
                )
        elif outcome == "failed":
            online_ok = False
        # "skipped" (otro hilo ya está sincronizando): se mantiene lo que ya se sabía.

    _last_sync_ok = online_ok
    assert effective_now is not None
    return _status_from_cache(payload, effective_now, online_ok=online_ok)


def activate_license(license_key: str) -> LicenseStatus:
    """Primera activación (o reactivación tras TAMPERED/UNAUTHORIZED_DEVICE).

    Consulta Firebase, valida lo que responde, y solo si todo encaja escribe el
    caché local. No hay red al margen de esto: si Firebase no responde, no hay
    forma de activar por primera vez (COMMUNICATION_ERROR es el único caso donde
    esto es realmente bloqueante — sin caché previo no hay a qué recurrir).
    """
    global _last_sync_attempt, _last_sync_ok
    license_key = (license_key or "").strip().upper()
    if not license_key:
        raise LicenseError("Escriba la clave de licencia.")

    try:
        id_token, _ = firebase_client.sign_in_anonymously()
        data, server_time = firebase_client.fetch_license(license_key, id_token)
    except firebase_client.FirebaseError as exc:
        raise LicenseError(
            "No se pudo contactar a Firebase para activar la licencia. "
            "Compruebe la conexión a internet e intente de nuevo."
        ) from exc

    if data is None:
        raise LicenseError(f"No existe ninguna licencia con la clave «{license_key}».")
    if data.get("status") == "REVOKED":
        raise LicenseError("Esta licencia fue revocada. Contacte al proveedor.")

    my_device = device_fingerprint_hash()
    existing_device = data.get("device_id_hash")
    if existing_device and existing_device != my_device:
        raise LicenseError(
            "Esta licencia ya está activada en otro equipo. Contacte al proveedor "
            "para transferirla si corresponde."
        )

    expires_raw = data.get("expires_at")
    if expires_raw:
        expires_at = _parse_iso(expires_raw)
        if expires_at and server_time.astimezone(timezone.utc) > expires_at:
            raise LicenseError("Esta licencia ya venció. Contacte al proveedor para renovarla.")

    try:
        firebase_client.claim_device(license_key, id_token, my_device)
    except firebase_client.FirebaseError as exc:
        raise LicenseError(
            "La licencia es válida, pero no se pudo confirmar el equipo en Firebase. Intente de nuevo."
        ) from exc

    data.setdefault("activated_at", _iso(server_time))
    save_cache(data, server_time=server_time)
    _last_sync_attempt = _now_utc()
    _last_sync_ok = True
    return evaluate_license()


# --- Puerta de acceso (before_request) ---------------------------------------

# Estas rutas se dejan siempre alcanzables: iniciar/cerrar sesión, activar la
# licencia y los archivos estáticos. Sin esto, una licencia bloqueada dejaría a
# quien administra sin forma de llegar a la pantalla que arregla el problema.
#
# El archivo estático de Flask (`static`) se registra directamente en la app, no
# dentro de un blueprint: su `request.blueprint` es None, no "static". Por eso va
# en _EXEMPT_ENDPOINTS (que compara el endpoint) y no en _EXEMPT_BLUEPRINTS.
_EXEMPT_BLUEPRINTS = {"auth", "licensing"}
_EXEMPT_ENDPOINTS = {"static", "uploaded_file"}


def license_gate() -> Response | None:
    # Interruptor SOLO para las suites de prueba de este proyecto (siguen el mismo
    # patrón que GYMLITE_DATA_DIR para aislar la base de datos de las pruebas): así
    # las pruebas de otras funcionalidades no tienen que activar una licencia falsa
    # para poder llegar a la ruta que de verdad quieren probar. El instalador y
    # gym_launcher.py nunca ponen esta variable, así que no existe en un equipo
    # instalado de verdad.
    if os.environ.get("GYMLITE_SKIP_LICENSE") == "1":
        return None

    if request.blueprint in _EXEMPT_BLUEPRINTS or request.endpoint in _EXEMPT_ENDPOINTS:
        return None
    if g.get("user") is None:
        return None  # login_required ya se encarga de esto en cada vista

    status = evaluate_license()
    g.license_status = status
    if status.usable:
        return None

    if g.user["role"] == "ADMIN":
        if request.endpoint == "licensing.activate":
            return None
        return redirect(url_for("licensing.activate"))

    if request.endpoint == "licensing.blocked":
        return None
    return redirect(url_for("licensing.blocked"))
