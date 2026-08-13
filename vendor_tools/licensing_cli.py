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
    """Crea una licencia nueva. Devuelve el documento recién creado."""
    if not customer.strip():
        raise LicenseAdminError("Escriba el nombre del cliente.")
    if tier not in TIERS:
        raise LicenseAdminError(f"Tipo de licencia inválido: {tier}.")

    db = _db()
    key = _generate_key()
    issued_at = _now()

    if tier == "PERPETUAL":
        expires_at = None
    else:
        default_days = {"TRIAL": DEFAULT_TRIAL_DAYS, "MONTHLY": DEFAULT_MONTHLY_DAYS, "ANNUAL": DEFAULT_ANNUAL_DAYS}[tier]
        expires_at = issued_at + timedelta(days=days if days is not None else default_days)

    documento = {
        "license_key": key,
        "customer_name": customer.strip(),
        "tier": tier,
        "status": "ACTIVE",
        "issued_at": issued_at,
        "expires_at": expires_at,
        "device_id_hash": None,
        "activated_at": None,
        "notes": notes.strip(),
        "schema_version": 1,
    }
    db.collection("licenses").document(key).set(documento)
    return documento


def do_renovar(key: str, months: int, years: int) -> datetime:
    """Extiende el vencimiento de una licencia. Nunca resta tiempo ya pagado."""
    if months <= 0 and years <= 0:
        raise LicenseAdminError("Indique al menos un mes o un año a extender.")

    db = _db()
    licencia = _get_license(db, key)
    if licencia is None:
        raise LicenseAdminError(f"No existe ninguna licencia con la clave {key}.")
    if licencia["tier"] == "PERPETUAL":
        raise LicenseAdminError("Esta licencia es perpetua: no tiene vencimiento que renovar.")

    actual = licencia.get("expires_at")
    base = max(_now(), actual) if actual else _now()
    # Aproximación deliberada: un mes son 30 días y un año 365, no se calcula por
    # calendario. Es la misma simplificación que ya usa la tarifa de meses extra en
    # la aplicación (ver app/config.py), y aquí importa menos todavía: un día de
    # más o de menos en una renovación no afecta a nadie.
    nuevo_vencimiento = base + timedelta(days=months * 30 + years * 365)
    db.collection("licenses").document(key).update({"expires_at": nuevo_vencimiento})
    return nuevo_vencimiento


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

    expires_at = documento["expires_at"]
    click.echo(f"Licencia creada para «{customer}»:")
    click.echo(f"  Clave:   {documento['license_key']}")
    click.echo(f"  Tipo:    {tier}")
    click.echo(f"  Vence:   {expires_at.strftime('%Y-%m-%d') if expires_at else 'No vence'}")
    click.echo("\nEntregue esta clave al cliente para que la active dentro del programa.")


@cli.command()
@click.option("--key", required=True, help="Clave de licencia.")
@click.option("--months", type=int, default=0, help="Meses a extender.")
@click.option("--years", type=int, default=0, help="Años a extender.")
def renew(key: str, months: int, years: int) -> None:
    """Extiende el vencimiento de una licencia. Nunca resta tiempo ya pagado."""
    try:
        nuevo_vencimiento = do_renovar(key, months, years)
    except LicenseAdminError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Licencia {key} renovada. Nuevo vencimiento: {nuevo_vencimiento.strftime('%Y-%m-%d')}.")


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
        vence = d.get("expires_at")
        vence_txt = vence.strftime("%Y-%m-%d") if vence else "No vence"
        equipo = "sí" if d.get("device_id_hash") else "no"
        click.echo(
            f"  {d['license_key']}  {d['tier']:<10}  {d['status']:<8}  "
            f"vence: {vence_txt:<12}  equipo activado: {equipo:<3}  {d.get('customer_name', '')}"
        )


if __name__ == "__main__":
    cli()
