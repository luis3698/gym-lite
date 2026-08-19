"""Índices corporales: qué se calcula en la ficha y cómo se interpreta.

La fórmula de cada índice está en `app/indexes.py` y no se toca desde aquí. Lo que se
edita en esta pantalla es la **matriz de interpretación**: qué etiqueta le corresponde
a cada valor, pudiendo distinguir por sexo y por franja de edad.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..config import SEX_OPTIONS
from ..db import execute, insert, query_all, query_one
from ..helpers import InvalidNumber, optional_string, parse_optional_decimal, parse_optional_int
from ..indexes import INDEX_BY_CODE, restore_defaults
from ..security import audit, roles_required

bp = Blueprint("body", __name__, url_prefix="/indices")

SEVERITIES = {
    "ok": "Correcto (verde)",
    "warn": "Atención (ámbar)",
    "bad": "Riesgo (rojo)",
}


@bp.route("/")
@roles_required("ADMIN")
def index():
    indices = []
    for row in query_all("SELECT * FROM body_indexes ORDER BY sort_order, code"):
        definition = INDEX_BY_CODE.get(row["code"])
        indices.append({
            "row": row,
            "definition": definition,
            "ranges": query_all(
                "SELECT * FROM index_ranges WHERE index_code = ? ORDER BY sort_order, id",
                (row["code"],),
            ),
        })
    return render_template("body/index.html", indices=indices, severities=SEVERITIES)


@bp.post("/<code>/activar")
@roles_required("ADMIN")
def toggle(code: str):
    row = query_one("SELECT * FROM body_indexes WHERE code = ?", (code,))
    if row is None:
        flash("Índice no encontrado.", "error")
        return redirect(url_for("body.index"))

    enabled = 0 if row["enabled"] else 1
    execute("UPDATE body_indexes SET enabled = ? WHERE code = ?", (enabled, code))
    audit("INDEX_TOGGLED", f"{code} {'activado' if enabled else 'desactivado'}")
    flash(
        f"«{row['name']}» {'se mostrará' if enabled else 'ya no se mostrará'} en la ficha del cliente.",
        "success",
    )
    return redirect(url_for("body.index"))


def _read_range(form) -> dict:
    """Valida una fila de la matriz. Lanza ValueError con un mensaje para el usuario."""
    label = optional_string(form.get("label"))
    if not label:
        raise ValueError("La etiqueta es obligatoria: es lo que se le muestra al cliente.")

    severity = optional_string(form.get("severity")) or "ok"
    if severity not in SEVERITIES:
        raise ValueError("Nivel inválido.")

    sex = optional_string(form.get("sex"))
    if sex and sex not in SEX_OPTIONS:
        raise ValueError("Sexo inválido.")

    try:
        age_min = parse_optional_int(form.get("age_min"), minimum=0, maximum=120)
        age_max = parse_optional_int(form.get("age_max"), minimum=0, maximum=120)
        min_value = parse_optional_decimal(form.get("min_value"), field="El valor mínimo", minimum=-1e6)
        max_value = parse_optional_decimal(form.get("max_value"), field="El valor máximo", minimum=-1e6)
    except InvalidNumber as exc:
        raise ValueError(str(exc)) from None

    if age_min is not None and age_max is not None and age_min > age_max:
        raise ValueError("La edad mínima no puede ser mayor que la máxima.")
    if min_value is not None and max_value is not None and min_value >= max_value:
        raise ValueError(
            "El valor mínimo debe ser menor que el máximo. Recuerde que el intervalo "
            "incluye el mínimo y excluye el máximo."
        )
    if min_value is None and max_value is None:
        raise ValueError(
            "Indique al menos un límite. Una fila sin mínimo ni máximo se aplicaría a "
            "cualquier valor y taparía a todas las demás."
        )

    return {
        "sex": sex, "age_min": age_min, "age_max": age_max,
        "min_value": min_value, "max_value": max_value,
        "label": label, "severity": severity,
    }


@bp.post("/<code>/rango")
@roles_required("ADMIN")
def add_range(code: str):
    if code not in INDEX_BY_CODE:
        flash("Índice no encontrado.", "error")
        return redirect(url_for("body.index"))

    try:
        data = _read_range(request.form)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("body.index", _anchor=code))

    siguiente = query_one(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM index_ranges WHERE index_code = ?",
        (code,),
    )["n"]
    insert(
        """INSERT INTO index_ranges (index_code, sex, age_min, age_max, min_value,
                                     max_value, label, severity, sort_order)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (code, data["sex"], data["age_min"], data["age_max"], data["min_value"],
         data["max_value"], data["label"], data["severity"], siguiente),
    )
    audit("INDEX_RANGE_ADDED", f"{code}: {data['label']}")
    flash(f"Rango «{data['label']}» añadido.", "success")
    return redirect(url_for("body.index", _anchor=code))


@bp.post("/rango/<int:range_id>/editar")
@roles_required("ADMIN")
def edit_range(range_id: int):
    row = query_one("SELECT * FROM index_ranges WHERE id = ?", (range_id,))
    if row is None:
        flash("Rango no encontrado.", "error")
        return redirect(url_for("body.index"))

    try:
        data = _read_range(request.form)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("body.index", _anchor=row["index_code"]))

    # `index_code` y `sort_order` no se tocan: editar no debe cambiar de índice ni
    # reordenar la tabla, solo actualizar los datos de esta fila.
    execute(
        """UPDATE index_ranges SET sex = ?, age_min = ?, age_max = ?, min_value = ?,
                                    max_value = ?, label = ?, severity = ?
            WHERE id = ?""",
        (data["sex"], data["age_min"], data["age_max"], data["min_value"],
         data["max_value"], data["label"], data["severity"], range_id),
    )
    audit("INDEX_RANGE_EDITED", f"{row['index_code']}: {row['label']} -> {data['label']}")
    flash(f"Rango «{data['label']}» actualizado.", "success")
    return redirect(url_for("body.index", _anchor=row["index_code"]))


@bp.post("/rango/<int:range_id>/eliminar")
@roles_required("ADMIN")
def delete_range(range_id: int):
    row = query_one("SELECT * FROM index_ranges WHERE id = ?", (range_id,))
    if row is None:
        flash("Rango no encontrado.", "error")
        return redirect(url_for("body.index"))

    execute("DELETE FROM index_ranges WHERE id = ?", (range_id,))
    audit("INDEX_RANGE_DELETED", f"{row['index_code']}: {row['label']}")
    flash(f"Rango «{row['label']}» eliminado.", "success")
    return redirect(url_for("body.index", _anchor=row["index_code"]))


@bp.post("/<code>/restaurar")
@roles_required("ADMIN")
def restore(code: str):
    if code not in INDEX_BY_CODE:
        flash("Índice no encontrado.", "error")
        return redirect(url_for("body.index"))

    restore_defaults(code)
    audit("INDEX_RANGES_RESTORED", code)
    flash("Rangos restaurados a los valores de fábrica.", "success")
    return redirect(url_for("body.index", _anchor=code))
