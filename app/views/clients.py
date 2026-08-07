"""Registro de usuarios (clientes del gimnasio).

En esta versión el cliente es únicamente una ficha administrativa: no tiene correo
de acceso, contraseña ni portal propio.
"""

from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..config import (
    ACTIVITY_LEVELS,
    BLOOD_TYPES,
    CLIENT_GOALS,
    MAX_AGE,
    MAX_HEIGHT_CM,
    MAX_WEIGHT_KG,
)
from ..db import execute, insert, query_all, query_one, query_value, transaction
from ..helpers import (
    InvalidNumber,
    bmi_category,
    body_mass_index,
    is_valid_email,
    now_str,
    optional_string,
    parse_age,
    parse_optional_decimal,
)
from ..security import audit, roles_required, verify_password
from ..uploads import UploadError, delete_image, resolve_captured_photo

bp = Blueprint("clients", __name__, url_prefix="/clientes")


def _read_form(form) -> dict:
    """Lee y valida el formulario. Lanza ValueError con un mensaje para el usuario."""
    first_name = optional_string(form.get("first_name"))
    last_name = optional_string(form.get("last_name"))
    document_id = optional_string(form.get("document_id"))
    email = optional_string(form.get("email"))

    if not first_name or not last_name or not document_id:
        raise ValueError("Nombre, apellido y número de identidad son obligatorios.")
    if email and not is_valid_email(email):
        raise ValueError("El correo electrónico no tiene un formato válido.")

    try:
        age = parse_age(form.get("age"))
        height = parse_optional_decimal(
            form.get("height_cm"), field="La altura", maximum=MAX_HEIGHT_CM)
        weight = parse_optional_decimal(
            form.get("weight_kg"), field="El peso", maximum=MAX_WEIGHT_KG)
    except InvalidNumber as exc:
        raise ValueError(str(exc)) from None

    # Las listas cerradas se validan contra su catálogo: un <select> manipulado no debe
    # meter valores que después no encajen en los filtros ni en los informes.
    blood_type = optional_string(form.get("blood_type"))
    if blood_type and blood_type not in BLOOD_TYPES:
        raise ValueError("Tipo de sangre inválido.")
    goal = optional_string(form.get("goal"))
    if goal and goal not in CLIENT_GOALS:
        raise ValueError("Objetivo inválido.")
    activity_level = optional_string(form.get("activity_level"))
    if activity_level and activity_level not in ACTIVITY_LEVELS:
        raise ValueError("Nivel de actividad inválido.")

    return {
        "first_name": first_name,
        "last_name": last_name,
        "document_id": document_id,
        "sex": optional_string(form.get("sex")),
        "age": age,
        "phone": optional_string(form.get("phone")),
        "email": email,
        "emergency_contact_name": optional_string(form.get("emergency_contact_name")),
        "emergency_contact_phone": optional_string(form.get("emergency_contact_phone")),
        # Ficha deportiva: toda opcional.
        "blood_type": blood_type,
        "height_cm": height,
        "weight_kg": weight,
        "goal": goal,
        "activity_level": activity_level,
        "medical_conditions": optional_string(form.get("medical_conditions")),
        "allergies": optional_string(form.get("allergies")),
        "health_insurance": optional_string(form.get("health_insurance")),
        "notes": optional_string(form.get("notes")),
    }


# Columnas que se escriben desde el formulario, en el orden en que viajan a la base.
# Tenerlas en un solo sitio evita que un campo nuevo se añada al INSERT y se olvide en
# el UPDATE, que es como los datos acaban guardándose solo al crear.
CLIENT_FIELDS = (
    "first_name", "last_name", "document_id", "sex", "age", "phone", "email",
    "emergency_contact_name", "emergency_contact_phone",
    "blood_type", "height_cm", "weight_kg", "goal", "activity_level",
    "medical_conditions", "allergies", "health_insurance", "notes",
)


def _check_duplicates(document_id: str, email: str | None, exclude_id: int | None = None) -> None:
    params: list = [document_id]
    sql = "SELECT 1 FROM clients WHERE document_id = ?"
    if exclude_id:
        sql += " AND id != ?"
        params.append(exclude_id)
    if query_one(sql, params):
        raise ValueError("Ya existe un cliente con ese número de identidad.")

    if email:
        params = [email]
        sql = "SELECT 1 FROM clients WHERE email = ?"
        if exclude_id:
            sql += " AND id != ?"
            params.append(exclude_id)
        if query_one(sql, params):
            raise ValueError("Ya existe un cliente con ese correo electrónico.")


@bp.route("/")
@roles_required("ADMIN", "CAJA")
def index():
    search = optional_string(request.args.get("q")) or ""
    sex = optional_string(request.args.get("sex")) or ""
    min_age = optional_string(request.args.get("min_age")) or ""
    max_age = optional_string(request.args.get("max_age")) or ""

    sql = "SELECT * FROM clients WHERE 1 = 1"
    params: list = []
    if search:
        # LIKE con parámetros ligados: el término nunca se concatena al SQL.
        sql += " AND (document_id LIKE ? OR first_name LIKE ? OR last_name LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    if sex:
        sql += " AND sex = ?"
        params.append(sex)
    # Las edades del filtro se descartan en silencio si no son números: es un filtro,
    # no vale la pena bloquear el listado por ello.
    for value, operator in ((min_age, ">="), (max_age, "<=")):
        if value and value.isdigit():
            sql += f" AND age {operator} ?"
            params.append(int(value))
    sql += " ORDER BY created_at DESC, id DESC"

    return render_template(
        "clients/index.html",
        clients=query_all(sql, params),
        filters={"q": search, "sex": sex, "min_age": min_age, "max_age": max_age},
        max_age=MAX_AGE,
    )


@bp.route("/nuevo", methods=("GET", "POST"))
@roles_required("ADMIN", "CAJA")
def create():
    if request.method == "POST":
        try:
            data = _read_form(request.form)
            _check_duplicates(data["document_id"], data["email"])
            # La foto llega del editor del navegador como data URL, no como archivo.
            photo, _ = resolve_captured_photo(None, request.form.get("photo_data"))

            now = now_str()
            columnas = ", ".join(CLIENT_FIELDS)
            marcadores = ", ".join("?" for _ in CLIENT_FIELDS)
            client_id = insert(
                f"""INSERT INTO clients ({columnas}, photo, created_at, updated_at)
                    VALUES ({marcadores}, ?, ?, ?)""",
                [data[c] for c in CLIENT_FIELDS] + [photo, now, now],
            )
            audit("CLIENT_CREATED", data["document_id"])
            flash(f"Cliente {data['first_name']} {data['last_name']} registrado correctamente.", "success")
            return redirect(url_for("clients.detail", client_id=client_id))
        except (ValueError, UploadError) as exc:
            flash(str(exc), "error")
            return render_template("clients/form.html", client=request.form, is_new=True), 400

    return render_template("clients/form.html", client={}, is_new=True)


@bp.route("/<int:client_id>")
@roles_required("ADMIN", "CAJA")
def detail(client_id: int):
    client = query_one("SELECT * FROM clients WHERE id = ?", (client_id,))
    if client is None:
        flash("Registro no encontrado.", "error")
        return redirect(url_for("clients.index"))

    memberships = query_all(
        """SELECT m.*, u.first_name AS seller_first, u.last_name AS seller_last
             FROM memberships m JOIN users u ON u.id = m.sold_by_id
            WHERE m.client_id = ? ORDER BY m.created_at DESC""",
        (client_id,),
    )
    sales = query_all(
        "SELECT * FROM sales WHERE client_id = ? ORDER BY created_at DESC LIMIT 20",
        (client_id,),
    )
    imc = body_mass_index(client["height_cm"], client["weight_kg"])
    return render_template(
        "clients/detail.html",
        client=client,
        memberships=memberships,
        sales=sales,
        imc=imc,
        imc_categoria=bmi_category(imc),
    )


@bp.route("/<int:client_id>/editar", methods=("GET", "POST"))
@roles_required("ADMIN", "CAJA")
def edit(client_id: int):
    client = query_one("SELECT * FROM clients WHERE id = ?", (client_id,))
    if client is None:
        flash("Registro no encontrado.", "error")
        return redirect(url_for("clients.index"))

    if request.method == "POST":
        try:
            data = _read_form(request.form)
            _check_duplicates(data["document_id"], data["email"], exclude_id=client_id)
            photo, to_delete = resolve_captured_photo(client["photo"], request.form.get("photo_data"))
            asignaciones = ", ".join(f"{c} = ?" for c in CLIENT_FIELDS)
            execute(
                f"UPDATE clients SET {asignaciones}, photo = ?, updated_at = ? WHERE id = ?",
                [data[c] for c in CLIENT_FIELDS] + [photo, now_str(), client_id],
            )
            # La foto anterior se borra solo después de que la fila se guardó bien.
            delete_image(to_delete)
            audit("CLIENT_UPDATED", data["document_id"])
            flash("Datos del cliente actualizados.", "success")
            return redirect(url_for("clients.detail", client_id=client_id))
        except (ValueError, UploadError) as exc:
            flash(str(exc), "error")
            merged = dict(client)
            merged.update(request.form)
            return render_template("clients/form.html", client=merged, is_new=False), 400

    return render_template("clients/form.html", client=client, is_new=False)


@bp.post("/<int:client_id>/eliminar")
@roles_required("ADMIN", "CAJA")
def delete(client_id: int):
    """Eliminar exige reconfirmar la contraseña del usuario que tiene la sesión."""
    client = query_one("SELECT * FROM clients WHERE id = ?", (client_id,))
    if client is None:
        flash("Registro no encontrado.", "error")
        return redirect(url_for("clients.index"))

    password = request.form.get("password") or ""
    if not password:
        flash("Debe ingresar su contraseña para confirmar.", "error")
        return redirect(url_for("clients.detail", client_id=client_id))

    if not verify_password(g.user["password_hash"], password):
        audit("CLIENT_DELETE_FAILED", f"intento de eliminar id={client_id}", success=False)
        flash("Contraseña incorrecta. No se eliminó el registro.", "error")
        return redirect(url_for("clients.detail", client_id=client_id))

    # Inscripciones y ventas representan pagos reales: bloquean el borrado a
    # propósito y deben resolverse antes, de forma explícita.
    memberships = query_value("SELECT COUNT(*) FROM memberships WHERE client_id = ?", (client_id,), 0)
    if memberships:
        flash(
            "No se puede eliminar: el cliente tiene inscripciones registradas. "
            "Cancélelas primero desde «Inscripción de gym».",
            "error",
        )
        return redirect(url_for("clients.detail", client_id=client_id))

    sales = query_value("SELECT COUNT(*) FROM sales WHERE client_id = ?", (client_id,), 0)
    if sales:
        flash(
            "No se puede eliminar: el cliente tiene ventas asociadas, que forman parte "
            "del histórico contable y no se borran.",
            "error",
        )
        return redirect(url_for("clients.detail", client_id=client_id))

    with transaction() as db:
        db.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    delete_image(client["photo"])
    audit("CLIENT_DELETED", client["document_id"])
    flash(f"Cliente {client['first_name']} {client['last_name']} eliminado.", "success")
    return redirect(url_for("clients.index"))
