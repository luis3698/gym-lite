"""Personal del sistema: perfil propio, contraseña y administración de usuarios."""

from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..config import PASSWORD_POLICY_TEXT, STAFF_ROLES
from ..db import execute, insert, query_all, query_one, query_value
from ..helpers import (
    InvalidNumber,
    is_strong_password,
    is_valid_email,
    now_str,
    optional_string,
    parse_age,
)
from ..security import audit, hash_password, login_required, roles_required, verify_password
from ..uploads import UploadError, delete_image, resolve_captured_photo

bp = Blueprint("users", __name__, url_prefix="/usuarios")


def _read_profile(form) -> dict:
    first_name = optional_string(form.get("first_name"))
    last_name = optional_string(form.get("last_name"))
    document_id = optional_string(form.get("document_id"))
    email = optional_string(form.get("email"))

    if not first_name or not last_name or not document_id or not email:
        raise ValueError("Nombre, apellido, documento y correo son obligatorios.")
    if not is_valid_email(email):
        raise ValueError("El correo electrónico no tiene un formato válido.")

    try:
        age = parse_age(form.get("age"))
    except InvalidNumber as exc:
        raise ValueError(str(exc)) from None

    return {
        "first_name": first_name,
        "last_name": last_name,
        "document_id": document_id,
        "email": email,
        "sex": optional_string(form.get("sex")),
        "age": age,
        "phone": optional_string(form.get("phone")),
        "blood_type": optional_string(form.get("blood_type")),
    }


def _check_unique(email: str, document_id: str, exclude_id: int | None = None) -> None:
    for column, value, label in (("email", email, "correo"), ("document_id", document_id, "documento")):
        sql = f"SELECT 1 FROM users WHERE {column} = ?"
        params: list = [value]
        if exclude_id:
            sql += " AND id != ?"
            params.append(exclude_id)
        if query_one(sql, params):
            raise ValueError(f"El {label} ya está en uso por otro usuario.")


# --- Perfil propio -----------------------------------------------------------


@bp.route("/perfil", methods=("GET", "POST"))
@login_required
def profile():
    user = query_one("SELECT * FROM users WHERE id = ?", (g.user["id"],))

    if request.method == "POST":
        try:
            data = _read_profile(request.form)
            _check_unique(data["email"], data["document_id"], exclude_id=user["id"])
            photo, to_delete = resolve_captured_photo(
                user["photo"], request.form.get("photo_data")
            )
            execute(
                """UPDATE users SET first_name = ?, last_name = ?, document_id = ?, sex = ?,
                                    age = ?, phone = ?, email = ?, blood_type = ?, photo = ?,
                                    updated_at = ?
                    WHERE id = ?""",
                (
                    data["first_name"], data["last_name"], data["document_id"], data["sex"],
                    data["age"], data["phone"], data["email"], data["blood_type"], photo,
                    now_str(), user["id"],
                ),
            )
            delete_image(to_delete)
            audit("PROFILE_UPDATED")
            flash("Perfil actualizado correctamente.", "success")
            return redirect(url_for("users.profile"))
        except (ValueError, UploadError) as exc:
            flash(str(exc), "error")
            merged = dict(user)
            merged.update(request.form)
            return render_template("users/profile.html", user=merged), 400

    return render_template("users/profile.html", user=user)


@bp.route("/contrasena", methods=("GET", "POST"))
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password") or ""
        current_confirm = request.form.get("current_password_confirm") or ""
        new = request.form.get("new_password") or ""
        new_confirm = request.form.get("new_password_confirm") or ""

        error = None
        if not all((current, current_confirm, new, new_confirm)):
            error = "Todos los campos son obligatorios."
        elif current != current_confirm:
            error = "La contraseña actual no coincide en ambos campos."
        elif new != new_confirm:
            error = "La nueva contraseña no coincide en ambos campos."
        elif not verify_password(g.user["password_hash"], current):
            # Es un fallo de reconfirmación, no de sesión: la sesión sigue abierta y el
            # usuario se queda en esta misma pantalla con el mensaje.
            error = "La contraseña actual es incorrecta."
        elif not is_strong_password(new):
            error = PASSWORD_POLICY_TEXT
        elif verify_password(g.user["password_hash"], new):
            error = "No puede reutilizar la contraseña actual."

        if error:
            flash(error, "error")
            return render_template("users/password.html"), 400

        execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (hash_password(new), now_str(), g.user["id"]),
        )
        audit("PASSWORD_CHANGED")
        flash("Contraseña actualizada correctamente.", "success")
        return redirect(url_for("users.profile"))

    return render_template("users/password.html")


# --- Administración de personal ---------------------------------------------


@bp.route("/")
@roles_required("ADMIN")
def index():
    return render_template(
        "users/index.html",
        users=query_all("SELECT * FROM users ORDER BY created_at DESC, id DESC"),
    )


@bp.route("/nuevo", methods=("GET", "POST"))
@roles_required("ADMIN")
def create():
    if request.method == "POST":
        try:
            username = optional_string(request.form.get("username"))
            password = request.form.get("password") or ""
            role = optional_string(request.form.get("role"))

            if not username:
                raise ValueError("El nombre de usuario es obligatorio.")
            if role not in STAFF_ROLES:
                raise ValueError("Rol inválido.")
            if not is_strong_password(password):
                raise ValueError(PASSWORD_POLICY_TEXT)

            data = _read_profile(request.form)
            if query_one("SELECT 1 FROM users WHERE username = ?", (username,)):
                raise ValueError("El nombre de usuario ya existe.")
            _check_unique(data["email"], data["document_id"])

            photo, _ = resolve_captured_photo(None, request.form.get("photo_data"))
            now = now_str()
            insert(
                """INSERT INTO users (username, password_hash, role, first_name, last_name,
                                      document_id, sex, age, phone, email, blood_type, photo,
                                      created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    username, hash_password(password), role, data["first_name"], data["last_name"],
                    data["document_id"], data["sex"], data["age"], data["phone"], data["email"],
                    data["blood_type"], photo, now, now,
                ),
            )
            audit("USER_CREATED", f"usuario creado: {username}")
            flash(f"Usuario «{username}» creado correctamente.", "success")
            return redirect(url_for("users.index"))
        except (ValueError, UploadError) as exc:
            flash(str(exc), "error")
            return render_template("users/form.html", user=request.form, is_new=True), 400

    return render_template("users/form.html", user={}, is_new=True)


@bp.route("/<int:user_id>/editar", methods=("GET", "POST"))
@roles_required("ADMIN")
def edit(user_id: int):
    target = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    if target is None:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for("users.index"))

    if request.method == "POST":
        try:
            role = optional_string(request.form.get("role")) or target["role"]
            if role not in STAFF_ROLES:
                raise ValueError("Rol inválido.")
            # Sin administradores no se podrían crear usuarios, editar tarifas ni
            # consultar la auditoría: el sistema quedaría bloqueado sin recuperación.
            if target["role"] == "ADMIN" and role != "ADMIN":
                admins = query_value("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'", (), 0)
                if admins <= 1:
                    raise ValueError("No puede cambiar el rol del último administrador del sistema.")

            data = _read_profile(request.form)
            _check_unique(data["email"], data["document_id"], exclude_id=user_id)
            photo, to_delete = resolve_captured_photo(
                target["photo"], request.form.get("photo_data")
            )

            execute(
                """UPDATE users SET role = ?, first_name = ?, last_name = ?, document_id = ?,
                                    sex = ?, age = ?, phone = ?, email = ?, blood_type = ?,
                                    photo = ?, updated_at = ?
                    WHERE id = ?""",
                (
                    role, data["first_name"], data["last_name"], data["document_id"], data["sex"],
                    data["age"], data["phone"], data["email"], data["blood_type"], photo,
                    now_str(), user_id,
                ),
            )
            delete_image(to_delete)
            audit("USER_UPDATED", f"usuario editado: {target['username']}")
            flash("Usuario actualizado correctamente.", "success")
            return redirect(url_for("users.index"))
        except (ValueError, UploadError) as exc:
            flash(str(exc), "error")
            merged = dict(target)
            merged.update(request.form)
            return render_template("users/form.html", user=merged, is_new=False), 400

    return render_template("users/form.html", user=target, is_new=False)


@bp.post("/<int:user_id>/eliminar")
@roles_required("ADMIN")
def delete(user_id: int):
    if user_id == g.user["id"]:
        flash("No puede eliminar su propio usuario mientras tiene la sesión activa.", "error")
        return redirect(url_for("users.index"))

    target = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    if target is None:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for("users.index"))

    password = request.form.get("password") or ""
    if not password:
        flash("Debe ingresar su contraseña para confirmar.", "error")
        return redirect(url_for("users.index"))

    if not verify_password(g.user["password_hash"], password):
        audit("USER_DELETE_FAILED", f"intento de eliminar id={user_id}", success=False)
        flash("Contraseña de administrador incorrecta. No se eliminó el usuario.", "error")
        return redirect(url_for("users.index"))

    if target["role"] == "ADMIN":
        admins = query_value("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'", (), 0)
        if admins <= 1:
            flash("No puede eliminar al último administrador del sistema.", "error")
            return redirect(url_for("users.index"))

    # Ventas e inscripciones guardan quién las registró: borrar al usuario dejaría el
    # histórico sin responsable, así que se bloquea igual que con los clientes.
    referencias = query_value(
        """SELECT (SELECT COUNT(*) FROM sales       WHERE seller_id  = ?)
                + (SELECT COUNT(*) FROM memberships WHERE sold_by_id = ?)""",
        (user_id, user_id),
        0,
    )
    if referencias:
        flash(
            "No se puede eliminar: el usuario tiene ventas o inscripciones registradas "
            "a su nombre. Cambie su rol si ya no debe tener acceso.",
            "error",
        )
        return redirect(url_for("users.index"))

    execute("DELETE FROM users WHERE id = ?", (user_id,))
    delete_image(target["photo"])
    audit("USER_DELETED", f"usuario eliminado: {target['username']}")
    flash(f"Usuario «{target['username']}» eliminado.", "success")
    return redirect(url_for("users.index"))
