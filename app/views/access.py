"""Kiosco de acceso por reconocimiento facial.

Dos mundos distintos conviven en este módulo:

* **El kiosco** (`/acceso/`) funciona sin sesión iniciada, porque tiene que quedarse
  encendido en la entrada sin que nadie lo atienda. A cambio solo se sirve a peticiones
  que salgan de la propia máquina: el servidor escucha en 127.0.0.1 y además se
  comprueba aquí, por si alguien arranca `run.py --host 0.0.0.0`.
* **El alta de rostros** ocurre durante la inscripción y exige sesión de ADMIN o CAJA,
  igual que el resto del módulo de inscripciones.

Lo que viaja por la red es siempre el descriptor (128 números), nunca una imagen: la
foto del rostro no se guarda ni se transmite.
"""

from __future__ import annotations

import json

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from ..config import (
    ACCESS_REASONS,
    STAFF_ROLES,
    FACE_MATCH_THRESHOLD,
    MAX_ACCESS_LOGS_PER_DAY,
    MAX_FACE_COOLDOWN_SECONDS,
    MAX_FACES_PER_CLIENT,
    MIN_FACE_COOLDOWN_SECONDS,
)
from ..db import execute, query_all, query_one, query_value, transaction
from ..faces import (
    InvalidDescriptor,
    best_match,
    classify,
    client_face_count,
    duplicate_owner,
    invalidate_gallery,
    parse_descriptor,
    serialize_descriptor,
)
from ..helpers import (
    active_membership_sql,
    duration_label,
    format_date,
    format_datetime,
    membership_status,
    now_str,
    today_str,
)
from ..security import audit, roles_required
from ..settings import (
    FACE_COOLDOWN,
    FACE_RECOGNITION_ENABLED,
    face_cooldown_seconds,
    face_recognition_enabled,
    set_flag,
    set_setting,
)

bp = Blueprint("access", __name__, url_prefix="/acceso")

LOCAL_ADDRESSES = {"127.0.0.1", "::1", "localhost"}


@bp.before_request
def only_from_this_computer():
    """El kiosco enseña datos personales sin pedir contraseña: que no salga del equipo."""
    if request.remote_addr not in LOCAL_ADDRESSES:
        abort(403)


# --- Pantalla del kiosco ------------------------------------------------------


@bp.route("/")
def kiosk():
    enrolled = query_value("SELECT COUNT(DISTINCT client_id) FROM client_faces", (), 0)
    return render_template(
        "access/kiosk.html",
        enabled=face_recognition_enabled(),
        enrolled_clients=enrolled,
    )


# --- Configuración (solo administradores) -------------------------------------


@bp.route("/configuracion", methods=("GET", "POST"))
@roles_required("ADMIN")
def config():
    if request.method == "POST":
        # Dos formularios distintos apuntan aquí: el interruptor y el antirrebote.
        # `accion` los distingue para no pisar un ajuste al guardar el otro.
        accion = request.form.get("accion")

        if accion == "cooldown":
            raw = (request.form.get("cooldown_seconds") or "").strip()
            if not raw.isdigit():
                flash("El antirrebote debe ser un número entero de segundos.", "error")
            else:
                seconds = int(raw)
                if not MIN_FACE_COOLDOWN_SECONDS <= seconds <= MAX_FACE_COOLDOWN_SECONDS:
                    flash(
                        f"El antirrebote debe estar entre {MIN_FACE_COOLDOWN_SECONDS} y "
                        f"{MAX_FACE_COOLDOWN_SECONDS} segundos.",
                        "error",
                    )
                else:
                    set_setting(FACE_COOLDOWN, str(seconds))
                    audit("FACE_COOLDOWN_CHANGED", f"{seconds} segundos")
                    flash(f"Antirrebote fijado en {seconds} segundos.", "success")
            return redirect(url_for("access.config"))

        enable = request.form.get("enabled") == "1"
        set_flag(FACE_RECOGNITION_ENABLED, enable)
        audit("FACE_TOGGLED", "activado" if enable else "desactivado")
        flash(
            "Reconocimiento facial activado. La pestaña del kiosco ya funciona."
            if enable else
            "Reconocimiento facial desactivado. El kiosco no abrirá la cámara y no se "
            "pedirá el rostro al inscribir.",
            "success",
        )
        return redirect(url_for("access.config"))

    recent = query_all(
        """SELECT a.created_at, a.allowed, a.reason, a.distance,
                  c.first_name, c.last_name, c.document_id
             FROM access_logs a
             LEFT JOIN clients c ON c.id = a.client_id
            ORDER BY a.created_at DESC, a.id DESC LIMIT 50""",
    )
    return render_template(
        "access/config.html",
        enabled=face_recognition_enabled(),
        enrolled_clients=query_value("SELECT COUNT(DISTINCT client_id) FROM client_faces", (), 0),
        total_faces=query_value("SELECT COUNT(*) FROM client_faces", (), 0),
        total_clients=query_value("SELECT COUNT(*) FROM clients", (), 0),
        entries_today=query_value(
            "SELECT COUNT(*) FROM access_logs WHERE created_at >= ?",
            (f"{today_str()} 00:00:00",), 0),
        recent=recent,
        cooldown_seconds=face_cooldown_seconds(),
        min_cooldown=MIN_FACE_COOLDOWN_SECONDS,
        max_cooldown=MAX_FACE_COOLDOWN_SECONDS,
        max_faces=MAX_FACES_PER_CLIENT,
        match_threshold=FACE_MATCH_THRESHOLD,
    )


# --- Aviso en vivo para el personal -------------------------------------------


# Tope de entradas por consulta. En hora punta pueden pasar varias personas entre dos
# consultas; más de diez avisos encolados no se llegan a leer, así que se descartan las
# más viejas quedándose con las últimas.
MAX_PENDING_ENTRIES = 10


def _entry_payload(row) -> dict:
    return {
        "id": row["id"],
        "client_id": row["client_id"],
        "name": f"{row['first_name']} {row['last_name']}" if row["first_name"] else "Desconocido",
        "document_id": row["document_id"],
        "photo_url": url_for("uploaded_file", filename=row["photo"]) if row["photo"] else None,
        "initial": (row["first_name"] or "?")[0].upper(),
        "allowed": bool(row["allowed"]),
        "reason_label": ACCESS_REASONS.get(row["reason"], row["reason"]),
        "at": format_datetime(row["created_at"]),
        "ago": max(0, int(row["ago"] or 0)),
        "url": url_for("memberships.manage", client_id=row["client_id"]) if row["client_id"] else None,
    }


ENTRY_SELECT = """
    SELECT a.id, a.allowed, a.reason, a.created_at,
           c.id AS client_id, c.first_name, c.last_name, c.document_id, c.photo,
           CAST((julianday('now', 'localtime') - julianday(a.created_at)) * 86400 AS INTEGER) AS ago
      FROM access_logs a
      LEFT JOIN clients c ON c.id = a.client_id
"""


@bp.get("/ultimo")
@roles_required(*STAFF_ROLES)
def last_entry():
    """Entradas del kiosco que el navegador todavía no ha anunciado.

    Con `desde` devuelve TODAS las posteriores a ese id, no solo la última: en hora
    punta entran varias personas entre dos consultas y, devolviendo solo la última, las
    anteriores no se anunciarían nunca. Sin `desde` devuelve únicamente la más reciente,
    para que una pantalla recién abierta fije su punto de partida sin arrastrar el
    histórico entero.

    Lo consulta cada pocos segundos cualquier pantalla del programa, así que devuelve lo
    mínimo y se apoya en el índice de access_logs.
    """
    if not face_recognition_enabled():
        return jsonify({"ok": True, "enabled": False, "events": []})

    since = request.args.get("desde")
    if since and since.isdigit():
        rows = query_all(
            ENTRY_SELECT + " WHERE a.id > ? ORDER BY a.id ASC LIMIT ?",
            (int(since), MAX_PENDING_ENTRIES),
        )
    else:
        rows = query_all(ENTRY_SELECT + " ORDER BY a.id DESC LIMIT 1")

    return jsonify({
        "ok": True,
        "enabled": True,
        "events": [_entry_payload(row) for row in rows],
    })


# --- Identificación -----------------------------------------------------------


def _client_card(client_id: int, reason: str | None = None) -> dict:
    """Ficha que se pinta a la derecha de la cámara.

    `reason` es el motivo que ya decidió `_decide()`: la membresía que se muestra debe
    ser la que explica ese motivo, no simplemente "la de vencimiento más lejano". Un
    cliente puede tener a la vez una inscripción larga en pausa (vencimiento lejano) y
    otra corta vigente; sin distinguir el motivo, el panel podía mostrar "vence el
    [fecha lejana de la pausada]" mientras el acceso se concedía por la vigente.
    """
    client = query_one("SELECT * FROM clients WHERE id = ?", (client_id,))
    if client is None:
        return {}

    if reason == "ACTIVE":
        membership = query_one(
            f"""SELECT duration_type, quantity, start_date, end_date, paused_at
                 FROM memberships WHERE client_id = ? AND {active_membership_sql()}
                ORDER BY end_date DESC, id DESC LIMIT 1""",
            (client_id, today_str()),
        )
    elif reason == "PAUSED":
        membership = query_one(
            """SELECT duration_type, quantity, start_date, end_date, paused_at
                 FROM memberships WHERE client_id = ? AND paused_at IS NOT NULL
                ORDER BY end_date DESC, id DESC LIMIT 1""",
            (client_id,),
        )
    else:
        membership = query_one(
            """SELECT duration_type, quantity, start_date, end_date, paused_at
                 FROM memberships WHERE client_id = ?
                ORDER BY end_date DESC, id DESC LIMIT 1""",
            (client_id,),
        )
    status, days_left = membership_status(
        membership["end_date"] if membership else None,
        membership["paused_at"] if membership else None,
    )

    card = {
        "id": client["id"],
        "name": f"{client['first_name']} {client['last_name']}",
        "document_id": client["document_id"],
        "phone": client["phone"],
        "email": client["email"],
        "sex": client["sex"],
        "age": client["age"],
        "emergency_name": client["emergency_contact_name"],
        "emergency_phone": client["emergency_contact_phone"],
        "photo_url": url_for("uploaded_file", filename=client["photo"]) if client["photo"] else None,
        "initial": (client["first_name"] or "?")[0].upper(),
        "status": status,
        "membership": None,
    }
    if membership:
        card["membership"] = {
            "duration": duration_label(membership["duration_type"], membership["quantity"]),
            "start_label": format_date(membership["start_date"]),
            "end_label": format_date(membership["end_date"]),
            "days_left": days_left,
        }
    return card


def _decide(client_id: int) -> tuple[bool, str]:
    """¿Puede entrar? Misma regla de vigencia que usa todo el sistema."""
    has_any = query_value(
        "SELECT COUNT(*) FROM memberships WHERE client_id = ?", (client_id,), 0
    )
    if not has_any:
        return False, "NO_MEMBERSHIP"

    is_active = query_value(
        f"SELECT COUNT(*) FROM memberships WHERE client_id = ? AND {active_membership_sql()}",
        (client_id, today_str()),
        0,
    )
    if is_active:
        return True, "ACTIVE"

    # Se distingue la pausa del vencimiento: al socio hay que decirle cosas distintas
    # («reanude su inscripción» no es lo mismo que «renuévela»). Se mira si hay
    # CUALQUIER inscripción todavía en pausa (sin reanudar): reanudarla es una acción
    # concreta que el mostrador puede ofrecer, sin importar si después se compró otra
    # inscripción aparte que ya venció por su cuenta.
    is_paused = query_value(
        "SELECT COUNT(*) FROM memberships WHERE client_id = ? AND paused_at IS NOT NULL",
        (client_id,),
        0,
    )
    return (False, "PAUSED") if is_paused else (False, "EXPIRED")


def _seconds_since_last(client_id: int) -> int | None:
    """Segundos desde el último paso por el kiosco, o None si nunca pasó."""
    seconds = query_value(
        """SELECT CAST((julianday('now', 'localtime') - julianday(created_at)) * 86400 AS INTEGER)
             FROM access_logs WHERE client_id = ?
            ORDER BY created_at DESC, id DESC LIMIT 1""",
        (client_id,),
    )
    return None if seconds is None else max(0, int(seconds))


def _visits_today(client_id: int) -> int:
    return query_value(
        "SELECT COUNT(*) FROM access_logs WHERE client_id = ? AND created_at >= ?",
        (client_id, f"{today_str()} 00:00:00"),
        0,
    )


def _last_reason(client_id: int) -> str | None:
    """Motivo del último paso registrado de este cliente, o None si nunca pasó."""
    return query_value(
        """SELECT reason FROM access_logs WHERE client_id = ?
            ORDER BY created_at DESC, id DESC LIMIT 1""",
        (client_id,),
    )


@bp.post("/identificar")
def identify():
    """Recibe un descriptor y responde con la ficha y la decisión de acceso.

    Responde siempre 200 con un JSON describiendo lo ocurrido, salvo que el descriptor
    esté mal formado. El kiosco llama a esto varias veces por segundo: no conviene que
    un caso normal («no reconocido») se comunique como un error HTTP.
    """
    # El interruptor se comprueba aquí y no solo al pintar la página: si un
    # administrador lo apaga con el kiosco abierto, la pestaña deja de identificar
    # sin que nadie tenga que ir a cerrarla.
    if not face_recognition_enabled():
        return jsonify({"ok": True, "status": "disabled"})

    try:
        descriptor = parse_descriptor(request.form.get("descriptor"))
    except InvalidDescriptor as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    client_id, distance = best_match(descriptor)
    verdict = classify(distance)

    if verdict != "match" or client_id is None:
        # Un desconocido delante de la cámara genera un fotograma tras otro; guardar
        # cada uno llenaría la tabla de ruido. Los no reconocidos no se registran.
        return jsonify({
            "ok": True,
            "status": verdict,          # 'uncertain' o 'unknown'
            "allowed": False,
            "reason": "UNKNOWN",
            "reason_label": ACCESS_REASONS["UNKNOWN"],
            "distance": round(distance, 4) if distance is not None else None,
        })

    allowed, reason = _decide(client_id)
    elapsed = _seconds_since_last(client_id)
    within_cooldown = elapsed is not None and elapsed < face_cooldown_seconds()

    # El motivo cambió respecto al último registro (p. ej. pagó en mostrador mientras
    # seguía delante de la cámara: EXPIRED pasa a ACTIVE) — se registra igual, aunque
    # siga dentro del antirrebote, para que el panel del personal y el histórico
    # reflejen el cambio real y no sigan mostrando el estado viejo el resto del rato.
    if within_cooldown and _last_reason(client_id) != reason:
        within_cooldown = False

    # Antirrebote: quien sigue plantado delante de la cámara no genera una entrada
    # nueva cada segundo. Se le sigue enseñando su ficha, marcada como ya registrada.
    #
    # El kiosco llama a esto varias veces por segundo y el servidor corre con varios
    # hilos, así que dos peticiones casi simultáneas para el mismo cliente podrían leer
    # las dos «no está en antirrebote» antes de que ninguna escriba. La comprobación se
    # repite dentro de la transacción, con el bloqueo de escritura ya tomado, para que la
    # segunda vea ya el registro de la primera. Si la lectura de fuera ya dice que está
    # en antirrebote no hace falta abrir una transacción para confirmarlo: solo hay
    # riesgo de colarse cuando se va a escribir.
    if not within_cooldown:
        with transaction() as db:
            elapsed = _seconds_since_last(client_id)
            within_cooldown = elapsed is not None and elapsed < face_cooldown_seconds()
            if within_cooldown and _last_reason(client_id) != reason:
                within_cooldown = False
            if not within_cooldown:
                if _visits_today(client_id) < MAX_ACCESS_LOGS_PER_DAY:
                    db.execute(
                        """INSERT INTO access_logs (client_id, allowed, reason, distance, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (client_id, 1 if allowed else 0, reason, round(distance, 4), now_str()),
                    )
                    elapsed = 0
                else:
                    # Tope diario alcanzado: no se inserta más, pero se trata como si
                    # ya estuviera en antirrebote el resto del día. Si no, el último
                    # registro real (el del tope, de hace rato) hacía que cada
                    # fotograma siguiente volviera a ver "no está en antirrebote",
                    # reabriendo una transacción de escritura sin insertar nada — y
                    # el aviso de "ya registrado" dejaba de mostrarse justo cuando
                    # más hacía falta (alguien insistiendo delante de la cámara).
                    within_cooldown = True
                    elapsed = 0

    return jsonify({
        "ok": True,
        "status": "match",
        "allowed": allowed,
        "reason": reason,
        "reason_label": ACCESS_REASONS[reason],
        "distance": round(distance, 4),
        "repeat": within_cooldown,
        "seconds_since": elapsed,
        "visits_today": _visits_today(client_id),
        "client": _client_card(client_id, reason),
    })


# --- Alta y baja de rostros (durante la inscripción) --------------------------


@bp.post("/registrar/<int:client_id>")
@roles_required("ADMIN", "CAJA")
def enroll(client_id: int):
    client = query_one("SELECT id, first_name, last_name, document_id FROM clients WHERE id = ?", (client_id,))
    if client is None:
        flash("Cliente no encontrado.", "error")
        return redirect(url_for("memberships.index"))

    back = redirect(url_for("memberships.manage", client_id=client_id))

    if not face_recognition_enabled():
        flash("El reconocimiento facial está desactivado. Actívelo en «Control de acceso».", "warning")
        return back

    # El navegador toma varias muestras seguidas y las envía juntas: una sola vuelta
    # al servidor por sesión de captura, en vez de una por muestra.
    raw = request.form.get("descriptors") or ""
    try:
        batch = json.loads(raw)
    except ValueError:
        flash("No se pudo registrar el rostro: los datos de la captura no son válidos.", "error")
        return back
    if not isinstance(batch, list) or not batch:
        flash("No se recibió ninguna muestra de rostro.", "error")
        return back

    if client_face_count(client_id) >= MAX_FACES_PER_CLIENT:
        flash(
            f"Este cliente ya tiene {MAX_FACES_PER_CLIENT} muestras de rostro, el máximo. "
            "Elimine las actuales para volver a capturarlas.",
            "warning",
        )
        return back

    try:
        descriptors = [parse_descriptor(item) for item in batch]
    except InvalidDescriptor as exc:
        flash(f"No se pudo registrar el rostro: {exc}", "error")
        return back

    # Basta comprobar una: todas las muestras son de la misma persona.
    other = duplicate_owner(descriptors[0], exclude_client_id=client_id)
    if other is not None:
        owner = query_one("SELECT first_name, last_name, document_id FROM clients WHERE id = ?", (other,))
        nombre = f"{owner['first_name']} {owner['last_name']} ({owner['document_id']})" if owner else "otro cliente"
        flash(
            f"Ese rostro ya está registrado a nombre de {nombre}. "
            "Verifique que está en la ficha correcta antes de continuar.",
            "error",
        )
        return back

    now = now_str()
    with transaction() as db:
        # El hueco disponible se recuenta aquí dentro, con el bloqueo de escritura ya
        # tomado: dos envíos casi simultáneos del mismo formulario (doble clic,
        # reintento tras un timeout de red) podían leer los dos "quedan huecos libres"
        # antes de que ninguno insertara, y el cliente terminaba con más de
        # MAX_FACES_PER_CLIENT muestras guardadas.
        current = db.execute(
            "SELECT COUNT(*) FROM client_faces WHERE client_id = ?", (client_id,)
        ).fetchone()[0]
        free_slots = max(0, MAX_FACES_PER_CLIENT - current)
        guardados = descriptors[:free_slots]
        for descriptor in guardados:
            db.execute(
                "INSERT INTO client_faces (client_id, descriptor, created_at) VALUES (?, ?, ?)",
                (client_id, serialize_descriptor(descriptor), now),
            )
    invalidate_gallery()

    if not guardados:
        flash(
            f"Este cliente ya tiene {MAX_FACES_PER_CLIENT} muestras de rostro, el máximo. "
            "Elimine las actuales para volver a capturarlas.",
            "warning",
        )
        return back

    total = client_face_count(client_id)
    audit("FACE_ENROLLED", f"cliente {client['document_id']} - {len(guardados)} muestra(s)")
    flash(
        f"{len(guardados)} muestra(s) registrada(s). "
        f"El cliente tiene {total} de {MAX_FACES_PER_CLIENT}.",
        "success",
    )
    return back


@bp.post("/eliminar/<int:client_id>")
@roles_required("ADMIN", "CAJA")
def remove_faces(client_id: int):
    client = query_one("SELECT document_id FROM clients WHERE id = ?", (client_id,))
    if client is None:
        flash("Cliente no encontrado.", "error")
        return redirect(url_for("memberships.index"))

    removed = execute("DELETE FROM client_faces WHERE client_id = ?", (client_id,)).rowcount
    invalidate_gallery()

    audit("FACE_REMOVED", f"cliente {client['document_id']} - {removed} muestra(s)")
    flash("Se eliminaron los rostros registrados de este cliente.", "success")
    return redirect(url_for("memberships.manage", client_id=client_id))
