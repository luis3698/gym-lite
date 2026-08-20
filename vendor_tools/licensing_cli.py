"""Herramienta del vendedor para emitir y administrar licencias de GymManager Lite.

Se ejecuta en el equipo del VENDEDOR, nunca en el del cliente: usa el SDK de
administrador de Firebase (`firebase-admin`), que necesita la clave de cuenta de
servicio del proyecto —un secreto real—. Por eso esta carpeta entera queda fuera de
`installer/build.py` (nada en `app/` ni en `gym_launcher.py` la importa) y
`serviceAccountKey.json` va en `.gitignore`: si esa clave llegara al instalador,
cualquiera podría emitirse licencias propias.

La lógica de cada operación vive en funciones planas (`do_crear`, `do_renovar`,
etc.) que no saben nada de líneas de comandos ni de ventanas: las usa tanto esta
CLI como `licensing_gui.py` (la interfaz gráfica), para no mantener dos copias de
las mismas reglas de negocio.

Uso:
    py vendor_tools/licensing_cli.py create --customer "Gimnasio Ejemplo" --tier MONTHLY
    py vendor_tools/licensing_cli.py renew --key GYML-XXXX-XXXX-XXXX-XXXX --months 1
    py vendor_tools/licensing_cli.py renew --key GYML-XXXX-XXXX-XXXX-XXXX --months 1 --tier ANNUAL
    py vendor_tools/licensing_cli.py renew --key GYML-XXXX-XXXX-XXXX-XXXX --tier PERPETUAL
    py vendor_tools/licensing_cli.py revoke --key GYML-XXXX-XXXX-XXXX-XXXX
    py vendor_tools/licensing_cli.py reactivate --key GYML-XXXX-XXXX-XXXX-XXXX
    py vendor_tools/licensing_cli.py unbind --key GYML-XXXX-XXXX-XXXX-XXXX
    py vendor_tools/licensing_cli.py delete --key GYML-XXXX-XXXX-XXXX-XXXX
    py vendor_tools/licensing_cli.py inspect --key GYML-XXXX-XXXX-XXXX-XXXX
    py vendor_tools/licensing_cli.py list [--status ACTIVE|REVOKED] [--tier ...]

Requiere `serviceAccountKey.json` en esta misma carpeta (Firebase Console →
Configuración del proyecto → Cuentas de servicio → Generar nueva clave privada).

Si los comandos de terminal dan problemas (carpeta equivocada, `python` sin
configurar, etc.), use en su lugar `licensing_gui.py` — la misma herramienta con
ventanas en vez de comandos.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

HERE = Path(__file__).resolve().parent
SERVICE_ACCOUNT_PATH = HERE / "serviceAccountKey.json"

TIERS = ("TRIAL", "MONTHLY", "ANNUAL", "PERPETUAL")
TIER_LABELS = {"TRIAL": "Prueba", "MONTHLY": "Mensual", "ANNUAL": "Anual", "PERPETUAL": "Perpetua"}

# Duración por defecto al crear cada tipo, en días. Se puede ajustar con --days
# (para TRIAL) o simplemente eligiendo cuántos --months/--years renovar después.
DEFAULT_TRIAL_DAYS = 15
DEFAULT_MONTHLY_DAYS = 30
DEFAULT_ANNUAL_DAYS = 365


class LicenseAdminError(RuntimeError):
    """Una operación de administración de licencias no se pudo completar.

    Independiente de click a propósito: la usan tanto la CLI como la interfaz
    gráfica, y la GUI no tiene por qué saber nada de excepciones de click.
    """


def service_account_ready() -> bool:
    return SERVICE_ACCOUNT_PATH.exists()


def _db():
    """Conexión a Firestore con la clave de cuenta de servicio del vendedor."""
    if not service_account_ready():
        raise LicenseAdminError(
            f"Falta {SERVICE_ACCOUNT_PATH}.\n"
            "Descárguela desde Firebase Console -> Configuración del proyecto -> "
            "Cuentas de servicio -> Generar nueva clave privada, y guárdela ahí."
        )
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = credentials.Certificate(str(SERVICE_ACCOUNT_PATH))
        firebase_admin.initialize_app(cred)
    return firestore.client()


def _generate_key() -> str:
    """GYML-XXXX-XXXX-XXXX-XXXX, con caracteres al azar de sobra para no repetirse."""
    crudo = secrets.token_hex(8).upper()  # 16 caracteres hexadecimales
    grupos = [crudo[i : i + 4] for i in range(0, 16, 4)]
    return "GYML-" + "-".join(grupos)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_license(db, key: str) -> dict | None:
    doc = db.collection("licenses").document(key).get()
    return doc.to_dict() if doc.exists else None


# --- Operaciones (usadas por la CLI y por licensing_gui.py) -----------------


def do_crear(customer: str, tier: str, days: int | None, notes: str) -> dict:
    """Crea una licencia nueva. Devuelve el documento recién creado.

    `expires_at` NO se fija aquí: la vigencia empieza a contar desde que el cliente
    activa la licencia dentro del programa (`app/licensing.py::activate_license`),
    no desde que se genera la clave. Lo que se guarda es `duration_days` —cuántos
    días de vigencia le corresponden—, y el primer `activate_license()` exitoso
    calcula y fija `expires_at = ahora + duration_days`. Antes de este cambio, una
    clave que tardara una semana en llegarle al cliente ya había perdido una semana
    de una prueba de 15 días.
    """
    if not customer.strip():
        raise LicenseAdminError("Escriba el nombre del cliente.")
    if tier not in TIERS:
        raise LicenseAdminError(f"Tipo de licencia inválido: {tier}.")

    db = _db()
    key = _generate_key()
    issued_at = _now()

    if tier == "PERPETUAL":
        duration_days = None
    else:
        default_days = {"TRIAL": DEFAULT_TRIAL_DAYS, "MONTHLY": DEFAULT_MONTHLY_DAYS, "ANNUAL": DEFAULT_ANNUAL_DAYS}[tier]
        duration_days = days if days is not None else default_days

    documento = {
        "license_key": key,
        "customer_name": customer.strip(),
        "tier": tier,
        "status": "ACTIVE",
        "issued_at": issued_at,
        "duration_days": duration_days,
        "expires_at": None,
        "device_id_hash": None,
        "activated_at": None,
        "notes": notes.strip(),
        "schema_version": 2,
    }
    db.collection("licenses").document(key).set(documento)
    return documento


def vigencia_text(doc: dict) -> str:
    """Texto legible del vencimiento, para la CLI y la GUI.

    Distingue tres casos: ya activada (fecha real), perpetua (no vence nunca), y
    creada pero pendiente de que el cliente la active (sin fecha todavía a
    propósito — ver `do_crear`).
    """
    vence = doc.get("expires_at")
    if vence:
        return vence.strftime("%Y-%m-%d") if hasattr(vence, "strftime") else str(vence)
    if doc.get("tier") == "PERPETUAL":
        return "No vence"
    dias = doc.get("duration_days")
    if dias:
        return f"Sin activar ({dias} día(s) desde que se active)"
    return "No vence"


def do_renovar(key: str, months: int, years: int, tier: str | None = None) -> dict:
    """Extiende el vencimiento de una licencia y, opcionalmente, cambia su tipo.

    `tier` es opcional: sin indicarlo, se comporta como antes (solo extiende la
    vigencia del tipo actual). Indicándolo, la licencia pasa a ese tipo —incluye
    convertir una PERPETUAL en una con vencimiento, o al revés—. Nunca resta
    tiempo ya pagado: si la licencia cambia de tipo pero conserva vencimiento
    (p. ej. de MONTHLY a ANNUAL), la nueva vigencia se suma sobre el vencimiento
    que ya tenía, no desde hoy.

    Devuelve `{"tier": ..., "expires_at": ...}` con el estado ya actualizado.
    """
    db = _db()
    licencia = _get_license(db, key)
    if licencia is None:
        raise LicenseAdminError(f"No existe ninguna licencia con la clave {key}.")
    if tier is not None and tier not in TIERS:
        raise LicenseAdminError(f"Tipo de licencia inválido: {tier}.")

    # Sin `tier` explícito, una licencia PERPETUAL sigue sin tener vencimiento que
    # renovar (comportamiento de siempre). Con `tier` explícito sí se puede pasar
    # de PERPETUAL a un tipo con vencimiento: el aviso ya no aplica en ese caso.
    # Esta comprobación va ANTES de calcular `nuevo_tier`: si no, "sin --tier" en
    # una licencia ya PERPETUAL calcularía nuevo_tier="PERPETUAL" igual y caería
    # en la rama de abajo como si se hubiera pedido convertir a perpetua a
    # propósito, en vez de avisar que no había nada que renovar.
    if licencia["tier"] == "PERPETUAL" and tier is None:
        raise LicenseAdminError(
            "Esta licencia es perpetua: no tiene vencimiento que renovar. "
            "Indique también --tier si quiere cambiarla a un tipo con vencimiento."
        )

    nuevo_tier = tier or licencia["tier"]

    # Pasar a PERPETUAL no necesita meses/años: no hay vigencia que calcular, el
    # vencimiento simplemente deja de existir.
    if nuevo_tier == "PERPETUAL":
        actualizacion = {"tier": "PERPETUAL", "expires_at": None}
        db.collection("licenses").document(key).update(actualizacion)
        return actualizacion

    if months <= 0 and years <= 0:
        raise LicenseAdminError("Indique al menos un mes o un año a extender.")

    # Aproximación deliberada: un mes son 30 días y un año 365, no se calcula por
    # calendario. Es la misma simplificación que ya usa la tarifa de meses extra en
    # la aplicación (ver app/config.py), y aquí importa menos todavía: un día de
    # más o de menos en una renovación no afecta a nadie.
    dias_extra = months * 30 + years * 365
    actual = licencia.get("expires_at")

    # Todavía no se activó en ningún equipo (expires_at sigue sin fijar, tal como la
    # deja do_crear): la vigencia ni siquiera empezó a contar. Fijar ya un
    # vencimiento rompería justo lo que se buscaba al mover el cálculo a la
    # activación, así que en este caso se suman los días a la duración pendiente en
    # vez de a una fecha.
    pendiente_activacion = (
        actual is None and licencia.get("duration_days") is not None and licencia["tier"] != "PERPETUAL"
    )
    if pendiente_activacion:
        nueva_duracion = int(licencia["duration_days"]) + dias_extra
        actualizacion: dict = {"duration_days": nueva_duracion}
        if tier is not None:
            actualizacion["tier"] = tier
        db.collection("licenses").document(key).update(actualizacion)
        return {"tier": nuevo_tier, "expires_at": None, "duration_days": nueva_duracion}

    base = max(_now(), actual) if actual else _now()
    nuevo_vencimiento = base + timedelta(days=dias_extra)
    actualizacion = {"expires_at": nuevo_vencimiento}
    if tier is not None:
        actualizacion["tier"] = tier
    db.collection("licenses").document(key).update(actualizacion)
    return {"tier": nuevo_tier, "expires_at": nuevo_vencimiento}


def do_revocar(key: str) -> None:
    """Revoca una licencia: el programa deja de funcionar en cuanto vuelva a conectarse."""
    db = _db()
    if _get_license(db, key) is None:
        raise LicenseAdminError(f"No existe ninguna licencia con la clave {key}.")
    db.collection("licenses").document(key).update({"status": "REVOKED"})


def do_reactivar(key: str) -> None:
    """Deshace una revocación."""
    db = _db()
    if _get_license(db, key) is None:
        raise LicenseAdminError(f"No existe ninguna licencia con la clave {key}.")
    db.collection("licenses").document(key).update({"status": "ACTIVE"})


def do_liberar_equipo(key: str) -> None:
    """Libera el equipo asociado, para una reinstalación legítima (reformateo,
    cambio de equipo autorizado por el cliente, etc.)."""
    db = _db()
    if _get_license(db, key) is None:
        raise LicenseAdminError(f"No existe ninguna licencia con la clave {key}.")
    db.collection("licenses").document(key).update({"device_id_hash": None, "activated_at": None})


def do_eliminar(key: str) -> None:
    """Elimina permanentemente una licencia revocada del registro.

    Solo se permite sobre licencias REVOKED: así nunca se borra por accidente una
    licencia activa que un cliente todavía está usando. Para eliminar una activa
    hay que revocarla primero, a propósito.
    """
    db = _db()
    licencia = _get_license(db, key)
    if licencia is None:
        raise LicenseAdminError(f"No existe ninguna licencia con la clave {key}.")
    if licencia.get("status") != "REVOKED":
        raise LicenseAdminError("Solo se pueden eliminar licencias revocadas. Revóquela primero.")
    db.collection("licenses").document(key).delete()


def do_inspeccionar(key: str) -> dict:
    """Detalle completo de una licencia."""
    db = _db()
    licencia = _get_license(db, key)
    if licencia is None:
        raise LicenseAdminError(f"No existe ninguna licencia con la clave {key}.")
    return licencia


def do_listar(status: str | None = None, tier: str | None = None) -> list[dict]:
    """Todas las licencias que coinciden con los filtros, más recientes primero."""
    db = _db()
    query = db.collection("licenses")
    if status:
        query = query.where("status", "==", status)
    if tier:
        query = query.where("tier", "==", tier)

    filas = [doc.to_dict() for doc in query.stream()]
    filas.sort(key=lambda d: d.get("issued_at") or _now(), reverse=True)
    return filas


# --- Interfaz de línea de comandos -------------------------------------------


@click.group()
def cli() -> None:
    """Emisión y administración de licencias de GymManager Lite (Firestore)."""


@cli.command()
@click.option("--customer", required=True, help="Nombre del gimnasio o cliente.")
@click.option("--tier", required=True, type=click.Choice(TIERS), help="Tipo de licencia.")
@click.option("--days", type=int, default=None, help="Días de vigencia (por defecto según el tipo).")
@click.option("--notes", default="", help="Nota libre (referencia interna, ej. número de factura).")
def create(customer: str, tier: str, days: int | None, notes: str) -> None:
    """Crea una licencia nueva y muestra la clave para entregar al cliente."""
    try:
        documento = do_crear(customer, tier, days, notes)
    except LicenseAdminError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Licencia creada para «{customer}»:")
    click.echo(f"  Clave:   {documento['license_key']}")
    click.echo(f"  Tipo:    {tier}")
    click.echo(f"  Vence:   {vigencia_text(documento)}")
    click.echo("\nEntregue esta clave al cliente para que la active dentro del programa.")


@cli.command()
@click.option("--key", required=True, help="Clave de licencia.")
@click.option("--months", type=int, default=0, help="Meses a extender.")
@click.option("--years", type=int, default=0, help="Años a extender.")
@click.option(
    "--tier", type=click.Choice(TIERS), default=None,
    help="Cambia el tipo de licencia de paso (opcional). Sin esto, conserva el tipo actual.",
)
def renew(key: str, months: int, years: int, tier: str | None) -> None:
    """Extiende el vencimiento de una licencia y, opcionalmente, cambia su tipo."""
    try:
        resultado = do_renovar(key, months, years, tier)
    except LicenseAdminError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Licencia {key} renovada. Tipo: {resultado['tier']}. Nuevo vencimiento: {vigencia_text(resultado)}.")


@cli.command()
@click.option("--key", required=True, help="Clave de licencia.")
def revoke(key: str) -> None:
    """Revoca una licencia: el programa deja de funcionar en cuanto vuelva a conectarse."""
    try:
        do_revocar(key)
    except LicenseAdminError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Licencia {key} revocada.")


@cli.command()
@click.option("--key", required=True, help="Clave de licencia.")
def reactivate(key: str) -> None:
    """Deshace una revocación."""
    try:
        do_reactivar(key)
    except LicenseAdminError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Licencia {key} reactivada.")


@cli.command()
@click.option("--key", required=True, help="Clave de licencia.")
def unbind(key: str) -> None:
    """Libera el equipo asociado, para una reinstalación legítima (reformateo,
    cambio de equipo autorizado por el cliente, etc.)."""
    try:
        do_liberar_equipo(key)
    except LicenseAdminError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Licencia {key}: equipo liberado. Puede activarse de nuevo en cualquier equipo.")


@cli.command()
@click.option("--key", required=True, help="Clave de licencia.")
def delete(key: str) -> None:
    """Elimina permanentemente una licencia revocada del registro."""
    try:
        do_eliminar(key)
    except LicenseAdminError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Licencia {key} eliminada permanentemente.")


@cli.command()
@click.option("--key", required=True, help="Clave de licencia.")
def inspect(key: str) -> None:
    """Muestra el detalle completo de una licencia."""
    try:
        licencia = do_inspeccionar(key)
    except LicenseAdminError as exc:
        raise click.ClickException(str(exc)) from exc
    for campo, valor in licencia.items():
        click.echo(f"  {campo}: {valor}")


@cli.command(name="list")
@click.option("--status", type=click.Choice(["ACTIVE", "REVOKED"]), default=None)
@click.option("--tier", type=click.Choice(TIERS), default=None)
def list_licenses(status: str | None, tier: str | None) -> None:
    """Lista las licencias, con filtros opcionales."""
    try:
        filas = do_listar(status, tier)
    except LicenseAdminError as exc:
        raise click.ClickException(str(exc)) from exc

    if not filas:
        click.echo("No hay licencias que coincidan.")
        return

    for d in filas:
        equipo = "sí" if d.get("device_id_hash") else "no"
        click.echo(
            f"  {d['license_key']}  {d['tier']:<10}  {d['status']:<8}  "
            f"vence: {vigencia_text(d):<32}  equipo activado: {equipo:<3}  {d.get('customer_name', '')}"
        )


if __name__ == "__main__":
    cli()
