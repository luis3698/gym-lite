"""Fábrica de la aplicación GymManager Lite."""

from __future__ import annotations

from datetime import timedelta

from flask import Flask, g, render_template, send_from_directory

from . import config as cfg
from . import db as database
from .helpers import register_filters
from .security import get_csrf_token, load_logged_in_user, verify_csrf


def _run_scheduled_backup(app: Flask) -> None:
    """Hace la copia automática si toca. Nunca impide que el programa arranque.

    Si algo falla —disco lleno, carpeta sin permisos— se avisa por consola y se sigue:
    quedarse sin poder abrir el gimnasio porque falló una copia sería peor que la
    propia falta de copia.
    """
    from .backups import BackupError, create_backup, due, prune_backups
    from .settings import BACKUP_FREQUENCY, backup_keep, get_setting

    try:
        frecuencia = get_setting(BACKUP_FREQUENCY)
        if not due(frecuencia):
            return
        ruta = create_backup(app.config["DATABASE"], suffix="auto")
        borradas = prune_backups(backup_keep())
        extra = f", {borradas} antigua(s) eliminada(s)" if borradas else ""
        print(f"[GymManager Lite] Copia de seguridad automática: {ruta.name}{extra}")
    except (BackupError, OSError) as exc:
        print(f"[GymManager Lite] AVISO: no se pudo hacer la copia automática: {exc}")


def create_app(*, database_path: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)

    app.config.update(
        SECRET_KEY=cfg.get_secret_key(),
        DATABASE=str(database_path or cfg.DATABASE_PATH),
        # Manda el envío más grande que admite el programa, que es restaurar una copia
        # de seguridad. El tamaño de las fotos se sigue limitando aparte, al guardarlas.
        MAX_CONTENT_LENGTH=cfg.MAX_BACKUP_UPLOAD_BYTES + (1024 * 1024),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=cfg.SESSION_HOURS),
        # Sin esto, editar una plantilla obliga a reiniciar el servidor.
        TEMPLATES_AUTO_RELOAD=True,
    )

    cfg.INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    cfg.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    database.register(app)
    register_filters(app)

    # Global de Jinja, no valor del context processor: las macros ({% macro %}) no ven
    # el contexto de la plantilla que las llama, y sin esto `csrf_token()` queda
    # indefinido dentro de los formularios de confirmación de _macros.html.
    app.jinja_env.globals["csrf_token"] = get_csrf_token

    # Crea el esquema y, si la base está recién hecha, carga los datos iniciales.
    with app.app_context():
        is_new = database.init_db(app)
        if is_new:
            from .seed import seed_database

            for line in seed_database(app):
                print(f"[GymManager Lite] {line}")

        # La matriz de índices corporales se siembra siempre que falte, no solo en una
        # base nueva: así una instalación que viene de una versión anterior arranca ya
        # con los rangos cargados y utilizables.
        from .indexes import ensure_defaults

        ensure_defaults()

        # Copia de seguridad automática. Se hace al arrancar y no con un temporizador
        # porque el equipo de un gimnasio se enciende por la mañana y se apaga por la
        # noche: un temporizador de 24 h no llegaría a dispararse nunca.
        #
        # Una base recién creada no se copia: estaría vacía y solo gastaría un hueco de
        # los que se conservan.
        if not is_new:
            _run_scheduled_backup(app)

    app.before_request(load_logged_in_user)
    app.before_request(verify_csrf)

    from .views import (
        access, audit, auth, backup, body, business, clients, dashboard, income,
        memberships, migration, products, refunds, sales, tariffs, users,
    )

    app.register_blueprint(auth.bp)
    app.register_blueprint(access.bp)
    app.register_blueprint(income.bp)
    app.register_blueprint(body.bp)
    app.register_blueprint(migration.bp)
    app.register_blueprint(backup.bp)
    app.register_blueprint(business.bp)
    app.register_blueprint(refunds.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(clients.bp)
    app.register_blueprint(memberships.bp)
    app.register_blueprint(sales.bp)
    app.register_blueprint(products.bp)
    app.register_blueprint(tariffs.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(audit.bp)

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename: str):
        """Sirve las fotos subidas.

        send_from_directory rechaza por sí mismo las rutas que intentan salir del
        directorio (../), así que no hace falta sanear el nombre aquí.
        """
        return send_from_directory(cfg.UPLOAD_DIR, filename)

    @app.context_processor
    def inject_globals() -> dict:
        """Valores disponibles en todas las plantillas sin pasarlos en cada render."""
        from .settings import face_recognition_enabled

        return {
            "current_user": g.get("user"),
            # La barra lateral y la ficha de inscripción cambian según esté activado
            # el reconocimiento facial, así que el interruptor va en el contexto común.
            "FACE_ENABLED": face_recognition_enabled() if g.get("user") else False,
            "ROLES": cfg.ROLES,
            "DURATIONS": cfg.DURATIONS,
            "PAYMENT_METHODS": cfg.PAYMENT_METHODS,
            "SEX_OPTIONS": cfg.SEX_OPTIONS,
            "BLOOD_TYPES": cfg.BLOOD_TYPES,
            "CLIENT_GOALS": cfg.CLIENT_GOALS,
            "ACTIVITY_LEVELS": cfg.ACTIVITY_LEVELS,
            "BODY_MEASUREMENTS": cfg.BODY_MEASUREMENTS,
            "MAX_MEASUREMENT_CM": cfg.MAX_MEASUREMENT_CM,
            "MAX_HEIGHT_CM": cfg.MAX_HEIGHT_CM,
            "MAX_WEIGHT_KG": cfg.MAX_WEIGHT_KG,
            "ACTION_LABELS": cfg.ACTION_LABELS,
            "ACCESS_REASONS": cfg.ACCESS_REASONS,
            "PASSWORD_POLICY_TEXT": cfg.PASSWORD_POLICY_TEXT,
        }

    @app.errorhandler(400)
    def bad_request(err):
        return render_template("error.html", code=400, title="Solicitud inválida",
                               message=getattr(err, "description", "")), 400

    @app.errorhandler(403)
    def forbidden(err):
        return render_template("error.html", code=403, title="Sin permisos",
                               message="No tiene permisos para ver esta página."), 403

    @app.errorhandler(404)
    def not_found(err):
        return render_template("error.html", code=404, title="Página no encontrada",
                               message="La dirección solicitada no existe."), 404

    @app.errorhandler(413)
    def too_large(err):
        return render_template("error.html", code=413, title="Archivo demasiado grande",
                               message=f"El archivo enviado supera el máximo de "
                                       f"{cfg.MAX_BACKUP_UPLOAD_BYTES // (1024 * 1024)} MB."), 413

    @app.errorhandler(500)
    def server_error(err):
        # El detalle va a la consola; al navegador solo un mensaje genérico, para no
        # filtrar rutas ni SQL.
        app.logger.exception("Error interno")
        return render_template("error.html", code=500, title="Error interno",
                               message="Ocurrió un error inesperado. Revise la consola del servidor."), 500

    return app
