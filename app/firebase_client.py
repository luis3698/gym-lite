"""Llamadas a Firebase para el licenciamiento: solo lo mínimo, siempre por REST.

No se usa el SDK de administrador (`firebase-admin`) aquí: ese requiere una clave
de cuenta de servicio, que es un secreto y jamás debe viajar dentro de un programa
que se instala en el equipo de un cliente. Este módulo se autentica solo con el Web
API key —que Firebase diseña para ir embebido en el cliente; la protección real la
dan las reglas de seguridad de Firestore, no ocultar esta clave—.

El flujo es: iniciar sesión anónima (Identity Toolkit) para obtener un token, y con
ese token leer o actualizar el documento de la licencia en Firestore. Las reglas de
seguridad (ver contexto.md) son las que de verdad impiden leer licencias ajenas o
escribir cualquier campo que no sea «reclamar este equipo».

La hora de confianza que usa `app/licensing.py` para detectar manipulación del
reloj sale de la cabecera HTTP `Date` de estas mismas respuestas: no hace falta
ninguna llamada aparte.
"""

from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import requests

from .config import FIREBASE_PROJECT_ID, FIREBASE_TIMEOUT_SECONDS, FIREBASE_WEB_API_KEY

IDENTITY_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
FIRESTORE_BASE = "https://firestore.googleapis.com/v1"


class FirebaseError(RuntimeError):
    """No se pudo completar la operación contra Firebase (red, configuración o
    respuesta inesperada). Quien llama decide qué hacer: en el uso normal esto cae
    al cálculo de licencia sin conexión, no es necesariamente un error fatal."""


def _server_time(response: requests.Response) -> datetime:
    """Hora del servidor a partir de la cabecera `Date` de la respuesta HTTPS.

    No es falsificable sin falsificar también el certificado TLS de Firebase, que
    es justo el límite que este mecanismo no pretende cubrir (ver app/licensing.py).
    Si por lo que sea faltara la cabecera, se usa la hora local como reserva: es
    peor que la hora del servidor, pero sigue siendo mejor que no tener ninguna.
    """
    raw = response.headers.get("Date")
    if raw:
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed is not None:
                return parsed
        except (TypeError, ValueError):
            pass
    return datetime.now().astimezone()


def _require_config() -> None:
    if not FIREBASE_PROJECT_ID or not FIREBASE_WEB_API_KEY:
        raise FirebaseError(
            "El programa todavía no tiene configurado el proyecto de Firebase "
            "(FIREBASE_PROJECT_ID / FIREBASE_WEB_API_KEY en app/config.py)."
        )


def sign_in_anonymously() -> tuple[str, datetime]:
    """Token de sesión anónima y la hora del servidor en ese mismo instante."""
    _require_config()
    try:
        response = requests.post(
            IDENTITY_URL,
            params={"key": FIREBASE_WEB_API_KEY},
            json={"returnSecureToken": True},
            timeout=FIREBASE_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise FirebaseError(f"No se pudo conectar con Firebase: {exc}") from exc

    server_time = _server_time(response)
    if response.status_code != 200:
        raise FirebaseError(f"Firebase rechazó el inicio de sesión anónimo (HTTP {response.status_code}).")

    try:
        token = response.json()["idToken"]
    except (ValueError, KeyError) as exc:
        raise FirebaseError("Respuesta inesperada de Firebase al iniciar sesión.") from exc
    return token, server_time


def _document_url(license_key: str) -> str:
    return (
        f"{FIRESTORE_BASE}/projects/{FIREBASE_PROJECT_ID}/databases/(default)"
        f"/documents/licenses/{quote(license_key, safe='')}"
    )


def _decode_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Traduce el formato de valores tipados de Firestore a un dict normal.

    Firestore REST envuelve cada valor como {"stringValue": "..."} / {"nullValue":
    null} / etc. en vez de JSON plano; esto deshace ese envoltorio para el resto
    del módulo de licenciamiento, que solo quiere trabajar con datos normales.
    """
    salida: dict[str, Any] = {}
    for clave, valor in fields.items():
        if "stringValue" in valor:
            salida[clave] = valor["stringValue"]
        elif "nullValue" in valor:
            salida[clave] = None
        elif "timestampValue" in valor:
            salida[clave] = valor["timestampValue"]
        elif "integerValue" in valor:
            salida[clave] = int(valor["integerValue"])
        elif "booleanValue" in valor:
            salida[clave] = bool(valor["booleanValue"])
        else:
            salida[clave] = None
    return salida


def fetch_license(license_key: str, id_token: str) -> tuple[dict[str, Any] | None, datetime]:
    """Documento de la licencia, o None si no existe. Con la hora del servidor.

    Un 404 no es un error de comunicación: es una respuesta válida que significa
    «esta clave no existe», y quien llama la trata así (NOT_FOUND / REVOKED según
    el contexto), no como un fallo de red.
    """
    _require_config()
    try:
        response = requests.get(
            _document_url(license_key),
            headers={"Authorization": f"Bearer {id_token}"},
            timeout=FIREBASE_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise FirebaseError(f"No se pudo conectar con Firebase: {exc}") from exc

    server_time = _server_time(response)
    if response.status_code == 404:
        return None, server_time
    if response.status_code != 200:
        raise FirebaseError(f"Firebase respondió con un error al leer la licencia (HTTP {response.status_code}).")

    try:
        document = response.json()
        data = _decode_fields(document.get("fields", {}))
    except ValueError as exc:
        raise FirebaseError("Respuesta inesperada de Firebase al leer la licencia.") from exc
    data.setdefault("license_key", license_key)
    return data, server_time


def claim_device(license_key: str, id_token: str, device_hash: str) -> None:
    """Registra este equipo como el autorizado para la licencia (una sola vez).

    Las reglas de seguridad de Firestore son las que de verdad impiden reclamar un
    equipo distinto del ya guardado: esta llamada solo hace la petición, no decide
    si tiene permiso.
    """
    _require_config()
    body = {
        "fields": {
            "device_id_hash": {"stringValue": device_hash},
            "activated_at": {"stringValue": datetime.now().astimezone().isoformat()},
        }
    }
    try:
        response = requests.patch(
            _document_url(license_key),
            params={
                "updateMask.fieldPaths": ["device_id_hash", "activated_at"],
                "key": FIREBASE_WEB_API_KEY,
            },
            headers={"Authorization": f"Bearer {id_token}"},
            json=body,
            timeout=FIREBASE_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise FirebaseError(f"No se pudo conectar con Firebase: {exc}") from exc

    if response.status_code != 200:
        raise FirebaseError(
            f"Firebase no permitió confirmar este equipo para la licencia (HTTP {response.status_code})."
        )
