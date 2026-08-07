"""Migración de socios que ya existían antes del programa.

Da de alta cliente e inscripción de una vez y **sin generar recibo**: esa gente ya pagó
por otro canal, y emitir un comprobante ahora falsearía la contabilidad. Por eso las
inscripciones creadas aquí llevan `is_migrated = 1` y quedan fuera del registro de
ventas e ingresos.

Dos caminos, según cuántos sean:

* **Formulario**, para casos sueltos.
* **CSV**, para cargar el listado entero. La subida nunca escribe directamente: primero
  se analiza el archivo completo y se muestra fila a fila lo que se va a hacer y lo que
  está mal. Solo se guarda si el usuario lo confirma, y entonces en una transacción: o
  entran todas o no entra ninguna.
"""

from __future__ import annotations

import csv
import io

from flask import (
    Blueprint,
    Response,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..config import BLOOD_TYPES, MAX_MEMBERSHIP_QUANTITY, SEX_OPTIONS, VALID_DURATIONS
from ..db import query_one, query_value, transaction
from ..helpers import (
    DATE_FMT,
    InvalidNumber,
    compute_end_date,
    duration_label,
    is_valid_email,
    now_str,
    optional_string,
    parse_age,
    parse_date,
    today_str,
)
from ..security import audit, roles_required

bp = Blueprint("migration", __name__, url_prefix="/migracion")

# Columnas del CSV. El orden es el de la plantilla que se descarga.
CSV_COLUMNS = (
    ("nombre", "Nombre", True),
    ("apellido", "Apellido", True),
    ("documento", "Número de identidad", True),
    ("sexo", "Sexo (Masculino/Femenino/Otro)", False),
    ("edad", "Edad", False),
    ("telefono", "Teléfono", False),
    ("correo", "Correo electrónico", False),
    ("tipo_sangre", "Tipo de sangre", False),
    ("duracion", "Duración (DAY_1/DAY_7/DAY_15/MONTH)", True),
    ("cantidad", "Cantidad", False),
    ("inicio", "Fecha de inicio (AAAA-MM-DD)", True),
    ("vencimiento", "Vencimiento (AAAA-MM-DD, opcional)", False),
)

PREVIEW_KEY = "migracion_previa"
MAX_CSV_ROWS = 2000


# --- Alta de una fila ---------------------------------------------------------


def _validate_row(data: dict, documentos_vistos: set[str]) -> tuple[dict, list[str]]:
    """Valida una fila. Devuelve (datos limpios, lista de errores)."""
    errores: list[str] = []
    limpio: dict = {}

    for campo, etiqueta in (("nombre", "nombre"), ("apellido", "apellido"),
                            ("documento", "número de identidad")):
        valor = optional_string(data.get(campo))
        if not valor:
            errores.append(f"falta el {etiqueta}")
        limpio[campo] = valor

    documento = limpio.get("documento")
    if documento:
        if documento in documentos_vistos:
            errores.append("documento repetido dentro del archivo")
        elif query_one("SELECT 1 FROM clients WHERE document_id = ?", (documento,)):
            errores.append("ya existe un cliente con ese documento")

    correo = optional_string(data.get("correo"))
    if correo:
        if not is_valid_email(correo):
            errores.append("el correo no tiene un formato válido")
        elif query_one("SELECT 1 FROM clients WHERE email = ?", (correo,)):
            errores.append("ya existe un cliente con ese correo")
    limpio["correo"] = correo

    sexo = optional_string(data.get("sexo"))
    if sexo and sexo not in SEX_OPTIONS:
        errores.append(f"sexo inválido (use {', '.join(SEX_OPTIONS)})")
    limpio["sexo"] = sexo

    sangre = optional_string(data.get("tipo_sangre"))
    if sangre and sangre not in BLOOD_TYPES:
        errores.append("tipo de sangre inválido")
    limpio["tipo_sangre"] = sangre

    try:
        limpio["edad"] = parse_age(data.get("edad"))
    except InvalidNumber:
        errores.append("la edad debe ser un número entero")
        limpio["edad"] = None

    limpio["telefono"] = optional_string(data.get("telefono"))

    duracion = (optional_string(data.get("duracion")) or "").upper()
    if duracion not in VALID_DURATIONS:
        errores.append(f"duración inválida (use {', '.join(VALID_DURATIONS)})")
        duracion = None
    limpio["duracion"] = duracion

    bruto = (optional_string(data.get("cantidad")) or "1").strip()
    if not bruto.isdigit() or not 1 <= int(bruto) <= MAX_MEMBERSHIP_QUANTITY:
        errores.append(f"la cantidad debe ser un entero entre 1 y {MAX_MEMBERSHIP_QUANTITY}")
        limpio["cantidad"] = 1
    else:
        limpio["cantidad"] = int(bruto)

    inicio = parse_date(data.get("inicio"))
    if inicio is None:
        errores.append("la fecha de inicio no es válida (AAAA-MM-DD)")
    limpio["inicio"] = inicio

    # El vencimiento es opcional: si no viene se calcula con la duración. Se admite
    # escribirlo porque en una migración la fecha real puede no cuadrar con la tarifa
    # (medias mensualidades, cortesías, acuerdos antiguos).
    vencimiento = None
    bruto_venc = optional_string(data.get("vencimiento"))
    if bruto_venc:
        vencimiento = parse_date(bruto_venc)
        if vencimiento is None:
            errores.append("el vencimiento no es válido (AAAA-MM-DD)")
        elif inicio and vencimiento <= inicio:
            errores.append("el vencimiento debe ser posterior al inicio")
    elif inicio and duracion:
        vencimiento = compute_end_date(inicio, duracion, limpio["cantidad"])
    limpio["vencimiento"] = vencimiento

    return limpio, errores


def _insert_row(db, limpio: dict) -> int:
    """Crea cliente e inscripción migrada. Debe llamarse dentro de una transacción."""
    ahora = now_str()
    cur = db.execute(
        """INSERT INTO clients (first_name, last_name, document_id, sex, age, phone, email,
                                blood_type, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (limpio["nombre"], limpio["apellido"], limpio["documento"], limpio["sexo"],
         limpio["edad"], limpio["telefono"], limpio["correo"], limpio["tipo_sangre"],
         ahora, ahora),
    )
    client_id = int(cur.lastrowid or 0)

    # Importe cero y `is_migrated`: no hubo cobro en este programa. Si se guardara el
    # precio de la tarifa, el registro de ingresos mostraría un dinero que nunca entró
    # por caja.
    db.execute(
        """INSERT INTO memberships (client_id, sold_by_id, duration_type, quantity,
                                    start_date, end_date, base_price, services_total,
                                    total, payment_method, is_migrated, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 'EFECTIVO', 1, ?)""",
        (client_id, g.user["id"], limpio["duracion"], limpio["cantidad"],
         limpio["inicio"].strftime(DATE_FMT), limpio["vencimiento"].strftime(DATE_FMT), ahora),
    )
    return client_id


# --- Pantalla principal -------------------------------------------------------


@bp.route("/")
@roles_required("ADMIN")
def index():
    return render_template(
        "migration/index.html",
        columnas=CSV_COLUMNS,
        migrados=query_value("SELECT COUNT(*) FROM memberships WHERE is_migrated = 1", (), 0),
        hoy=today_str(),
        max_quantity=MAX_MEMBERSHIP_QUANTITY,
        max_rows=MAX_CSV_ROWS,
    )


# --- Alta manual --------------------------------------------------------------


@bp.post("/manual")
@roles_required("ADMIN")
def manual():
    limpio, errores = _validate_row(request.form, set())
    if errores:
        flash("No se pudo registrar: " + "; ".join(errores) + ".", "error")
        return redirect(url_for("migration.index"))

    with transaction() as db:
        client_id = _insert_row(db, limpio)

    audit(
        "MIGRATION_MANUAL",
        f"{limpio['documento']} - {duration_label(limpio['duracion'], limpio['cantidad'])}",
    )
    flash(
        f"{limpio['nombre']} {limpio['apellido']} migrado con su inscripción "
        f"(vence el {limpio['vencimiento'].strftime(DATE_FMT)}). No se generó recibo.",
        "success",
    )
    return redirect(url_for("clients.detail", client_id=client_id))


# --- Importación por CSV ------------------------------------------------------


@bp.get("/plantilla.csv")
@roles_required("ADMIN")
def template_csv():
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([etiqueta for _clave, etiqueta, _obl in CSV_COLUMNS])
    # Dos filas de ejemplo: se ve el formato esperado sin tener que leer la ayuda.
    writer.writerow(["Ana", "Martínez", "1012345678", "Femenino", "29", "3001234567",
                     "ana@ejemplo.com", "O+", "MONTH", "1", today_str(), ""])
    writer.writerow(["Luis", "Pérez", "1023456789", "Masculino", "35", "3009876543",
                     "", "", "MONTH", "6", today_str(), ""])

    data = "﻿" + buffer.getvalue()
    return Response(
        data,
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="plantilla-migracion.csv"'},
    )


def _read_csv(archivo) -> tuple[list[dict], str | None]:
    """Lee el archivo subido y lo devuelve como lista de diccionarios por posición.

    Se emparejan las columnas por POSICIÓN y no por el texto de la cabecera: quien
    rellena la plantilla en Excel suele reescribir los títulos, y exigir que coincidan
    al carácter convertiría la importación en una pelea con el archivo.
    """
    try:
        crudo = archivo.read()
    except Exception:  # noqa: BLE001
        return [], "No se pudo leer el archivo."

    if not crudo:
        return [], "El archivo está vacío."

    texto = None
    for codificacion in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            texto = crudo.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        return [], "No se pudo interpretar el archivo. Guárdelo como CSV UTF-8."

    # Excel en español usa «;» y en inglés «,». Se detecta en vez de imponer uno.
    muestra = texto[:2000]
    delimitador = ";" if muestra.count(";") >= muestra.count(",") else ","

    filas: list[dict] = []
    lector = csv.reader(io.StringIO(texto), delimiter=delimitador)
    for numero, campos in enumerate(lector, start=1):
        if numero == 1:
            continue  # cabecera
        if not any((c or "").strip() for c in campos):
            continue  # línea en blanco
        if len(filas) >= MAX_CSV_ROWS:
            return filas, f"El archivo supera las {MAX_CSV_ROWS} filas. Divídalo en varios."
        fila = {clave: (campos[i] if i < len(campos) else "")
                for i, (clave, _etiqueta, _obl) in enumerate(CSV_COLUMNS)}
        fila["_linea"] = numero
        filas.append(fila)

    if not filas:
        return [], "El archivo no tiene ninguna fila de datos por debajo de la cabecera."
    return filas, None


@bp.post("/analizar")
@roles_required("ADMIN")
def analyze():
    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        flash("Seleccione un archivo CSV.", "error")
        return redirect(url_for("migration.index"))

    filas, error = _read_csv(archivo)
    if error and not filas:
        flash(error, "error")
        return redirect(url_for("migration.index"))
    if error:
        flash(error, "warning")

    vistos: set[str] = set()
    previa = []
    validas = 0
    for fila in filas:
        limpio, errores = _validate_row(fila, vistos)
        if limpio.get("documento") and not errores:
            vistos.add(limpio["documento"])
        if not errores:
            validas += 1
        previa.append({
            "linea": fila["_linea"],
            "nombre": f"{limpio.get('nombre') or '—'} {limpio.get('apellido') or ''}".strip(),
            "documento": limpio.get("documento") or "—",
            "duracion": duration_label(limpio["duracion"], limpio["cantidad"]) if limpio.get("duracion") else "—",
            "inicio": limpio["inicio"].strftime(DATE_FMT) if limpio.get("inicio") else "—",
            "vencimiento": limpio["vencimiento"].strftime(DATE_FMT) if limpio.get("vencimiento") else "—",
            "errores": errores,
            # Solo las filas correctas se guardan en la sesión para el paso de confirmar.
            "datos": {
                "nombre": limpio.get("nombre"), "apellido": limpio.get("apellido"),
                "documento": limpio.get("documento"), "sexo": limpio.get("sexo"),
                "edad": limpio.get("edad"), "telefono": limpio.get("telefono"),
                "correo": limpio.get("correo"), "tipo_sangre": limpio.get("tipo_sangre"),
                "duracion": limpio.get("duracion"), "cantidad": limpio.get("cantidad"),
                "inicio": limpio["inicio"].strftime(DATE_FMT) if limpio.get("inicio") else None,
                "vencimiento": limpio["vencimiento"].strftime(DATE_FMT) if limpio.get("vencimiento") else None,
            } if not errores else None,
        })

    session[PREVIEW_KEY] = [p["datos"] for p in previa if p["datos"]]
    session.modified = True

    return render_template(
        "migration/preview.html",
        previa=previa,
        validas=validas,
        con_error=len(previa) - validas,
        columnas=CSV_COLUMNS,
    )


@bp.post("/confirmar")
@roles_required("ADMIN")
def confirm():
    pendientes = session.get(PREVIEW_KEY) or []
    if not pendientes:
        flash("No hay nada pendiente de importar. Vuelva a subir el archivo.", "warning")
        return redirect(url_for("migration.index"))

    # Se revalida contra la base antes de escribir: entre el análisis y la confirmación
    # alguien pudo dar de alta a mano uno de esos documentos desde otra pantalla.
    vistos: set[str] = set()
    listas = []
    descartadas = 0
    for fila in pendientes:
        limpio, errores = _validate_row(fila, vistos)
        if errores:
            descartadas += 1
            continue
        vistos.add(limpio["documento"])
        listas.append(limpio)

    if not listas:
        session.pop(PREVIEW_KEY, None)
        flash("Ninguna fila se pudo importar: es posible que ya existieran.", "error")
        return redirect(url_for("migration.index"))

    # Todo o nada: una importación a medias deja al gimnasio sin saber por dónde iba.
    with transaction() as db:
        for limpio in listas:
            _insert_row(db, limpio)

    session.pop(PREVIEW_KEY, None)
    audit("MIGRATION_IMPORT", f"{len(listas)} socio(s) importados")

    mensaje = f"{len(listas)} socio(s) importados con su inscripción. No se generó ningún recibo."
    if descartadas:
        mensaje += f" Se descartaron {descartadas} que ya no eran válidas."
    flash(mensaje, "success")
    return redirect(url_for("migration.index"))
