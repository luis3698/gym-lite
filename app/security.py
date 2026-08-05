"""Sesión, permisos, protección CSRF y auditoría."""

from __future__ import annotations

import functools
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Callable

from flask import abort, flash, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .config import LOCK_MINUTES, MAX_LOGIN_ATTEMPTS, SESSION_HOURS
from .db import execute, insert, query_one
from .helpers import DATETIME_FMT, now_str, parse_datetime

# --- Contraseñas -------------------------------------------------------------
# werkzeug usa scrypt por defecto: viene con Flask y no necesita compilador,
# a diferencia de bcrypt.


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash or password is None:
        return False
    return check_password_hash(password_hash, password)


# --- Bloqueo por intentos fallidos -------------------------------------------


def lock_remaining_minutes(locked_until: str | None) -> int:
    """Minutos que faltan para que expire el bloqueo (0 si no está bloqueada)."""
    if not locked_until:
        return 0
    parsed = parse_datetime(locked_until)
    if parsed is None or parsed <= datetime.now():
        return 0
    return max(1, int((parsed - datetime.now()).total_seconds() // 60) + 1)


def register_failed_attempt(user_id: int, current_attempts: int) -> str | None:
    """Suma un intento fallido y bloquea al alcanzar el máximo.

    Devuelve el mensaje de bloqueo si la cuenta acaba de bloquearse, o None.
    """
    attempts = current_attempts + 1
    if attempts >= MAX_LOGIN_ATTEMPTS:
        locked_until = (datetime.now() + timedelta(minutes=LOCK_MINUTES)).strftime(DATETIME_FMT)
        execute(
            "UPDATE users SET failed_attempts = 0, locked_until = ? WHERE id = ?",
            (locked_until, user_id),
        )
        return (
            f"Ha superado el número de intentos permitidos. "
            f"Cuenta bloqueada por {LOCK_MINUTES} minutos."
        )
    execute("UPDATE users SET failed_attempts = ? WHERE id = ?", (attempts, user_id))
    return None


def clear_failed_attempts(user_id: int) -> None:
    execute(
        "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?",
        (user_id,),
    )


# --- Sesión ------------------------------------------------------------------


def login_user(user_id: int) -> None:
    session.clear()
    session["user_id"] = user_id
    session["expires_at"] = (datetime.now() + timedelta(hours=SESSION_HOURS)).strftime(DATETIME_FMT)
    session.permanent = False


def logout_user() -> None:
    session.clear()


def load_logged_in_user() -> None:
    """Carga g.user en cada petición a partir de la cookie de sesión.

    Se ejecuta como before_request. Si la sesión venció o el usuario ya no existe
    (lo eliminaron mientras tenía la sesión abierta), se limpia la cookie.
    """
    g.user = None
    user_id = session.get("user_id")
    if user_id is None:
        return

    expires_at = parse_datetime(session.get("expires_at"))
    if expires_at is None or expires_at <= datetime.now():
        session.clear()
        return

    row = query_one(
        """SELECT id, username, role, first_name, last_name, document_id, sex, age,
                  phone, email, blood_type, photo, password_hash
             FROM users WHERE id = ?""",
        (user_id,),
    )
    if row is None:
        session.clear()
        return
    g.user = row


def login_required(view: Callable) -> Callable:
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            # `next` permite volver a la página pedida después de iniciar sesión.
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped


def roles_required(*roles: str) -> Callable:
    """Restringe una vista a ciertos roles. Implica login_required."""

    def decorator(view: Callable) -> Callable:
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            user = g.get("user")
            if user is None:
                return redirect(url_for("auth.login", next=request.full_path))
            if user["role"] not in roles:
                flash("No tiene permisos para acceder a esa sección.", "error")
                return redirect(url_for("dashboard.index"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


# --- CSRF --------------------------------------------------------------------
# Sin esto, otra página abierta en el navegador podría enviar un POST a esta app
# aprovechando la cookie de sesión (por ejemplo, para eliminar un registro).


def get_csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def verify_csrf() -> None:
    """Valida el token en cada POST. Se registra como before_request."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    expected = session.get("csrf_token")
    received = request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, received):
        abort(400, description="Token de seguridad inválido o vencido. Recargue la página e intente de nuevo.")


# --- Auditoría ---------------------------------------------------------------


def audit(action: str, detail: str | None = None, *, success: bool = True, user_id: int | None = -1) -> None:
    """Deja constancia de una acción en el registro de actividad.

    user_id = -1 significa «el usuario de la sesión actual». Se pasa explícitamente
    None para los intentos de inicio de sesión contra cuentas inexistentes.
    Un fallo al auditar nunca debe tumbar la operación que se estaba auditando.
    """
    if user_id == -1:
        user = g.get("user")
        user_id = user["id"] if user is not None else None
    try:
        insert(
            "INSERT INTO audit_logs (user_id, action, detail, success, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, action, detail, 1 if success else 0, now_str()),
        )
    except Exception as exc:  # noqa: BLE001 - registrar nunca debe romper el flujo
        print(f"[auditoría] no se pudo registrar {action}: {exc}")
