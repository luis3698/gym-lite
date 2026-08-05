"""Inicio y cierre de sesión del personal.

Los clientes no tienen cuenta en esta versión: son fichas de registro, así que la
única tabla contra la que se autentica es `users`.
"""

from __future__ import annotations

from urllib.parse import urlparse

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..db import query_one
from ..security import (
    audit,
    clear_failed_attempts,
    lock_remaining_minutes,
    login_user,
    logout_user,
    register_failed_attempt,
    verify_password,
)

bp = Blueprint("auth", __name__)


def _safe_next(target: str | None) -> str:
    """Solo admite redirecciones internas.

    Sin esta comprobación, ?next=https://otro-sitio convierte el login en un salto
    a una página externa que puede imitar la aplicación para robar credenciales.
    """
    if not target:
        return url_for("dashboard.index")
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return url_for("dashboard.index")
    return target


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.get("user") is not None:
        return redirect(url_for("dashboard.index"))

    username = ""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("Usuario y contraseña son obligatorios.", "error")
            return render_template("login.html", username=username), 400

        user = query_one(
            "SELECT id, username, password_hash, failed_attempts, locked_until FROM users WHERE username = ?",
            (username,),
        )

        if user is None:
            audit("LOGIN_FAILED", f"cuenta inexistente: {username}", success=False, user_id=None)
            flash("Usuario o contraseña incorrectos.", "error")
            return render_template("login.html", username=username), 401

        remaining = lock_remaining_minutes(user["locked_until"])
        if remaining:
            flash(
                f"Cuenta bloqueada temporalmente por intentos fallidos. "
                f"Intente de nuevo en {remaining} minuto(s).",
                "error",
            )
            return render_template("login.html", username=username), 423

        if not verify_password(user["password_hash"], password):
            lock_message = register_failed_attempt(user["id"], user["failed_attempts"])
            audit("LOGIN_FAILED", "contraseña incorrecta", success=False, user_id=user["id"])
            flash(lock_message or "Usuario o contraseña incorrectos.", "error")
            return render_template("login.html", username=username), 401

        clear_failed_attempts(user["id"])
        login_user(user["id"])
        audit("LOGIN_SUCCESS", user_id=user["id"])
        return redirect(_safe_next(request.args.get("next")))

    return render_template("login.html", username=username)


@bp.post("/logout")
def logout():
    user = g.get("user")
    if user is not None:
        audit("LOGOUT", user_id=user["id"])
    logout_user()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("auth.login"))
