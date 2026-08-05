# 🏋️ GymManager Lite

Sistema de gestión de gimnasio para uso interno del personal: registro de clientes,
inscripciones y mensualidades, venta de productos con control de stock, tarifas
configurables, panel de indicadores y registro de actividad.

Hecho **100 % en Python y SQL**, para correr localmente en un PC:
**Flask + SQLite con consultas SQL directas** y plantillas Jinja2. No usa ORM, ni
frameworks de JavaScript, ni servicios externos.

## Diferencias con GymManager Pro

Esta versión es deliberadamente más reducida:

| | GymManager Pro | GymManager Lite |
|---|---|---|
| Stack | Node/Express + React | Python/Flask + SQLite |
| Reconocimiento facial (FaceID) | Sí | **No incluido** |
| Portal del cliente (cuenta propia) | Sí | **No incluido** |
| Asistencias y rachas | Sí | No (dependían del FaceID) |
| Blog y cronograma | Sí | No (solo existían para el portal del cliente) |
| Clientes | Ficha + cuenta de acceso | **Solo ficha administrativa** |
| Cuentas del sistema | Personal + clientes | **Solo personal** |

Los clientes no inician sesión ni tienen perfil propio: son registros que administra
el personal. Por eso tampoco existen pantallas de contenido para clientes.

## Requisitos

- **Python 3.10 o superior** (probado con 3.14). Incluye `pip`.
- Un navegador moderno.
- No hace falta instalar ningún motor de base de datos: SQLite es un archivo local que
  se crea solo.

## Instalación

**En Windows**, doble clic en **`instalar.bat`**. Crea el entorno, instala las
dependencias, prepara la base de datos y deja un acceso directo en el escritorio.
Después se abre con **`iniciar.bat`** o desde ese acceso directo.

Guía detallada, copias de seguridad y solución de problemas: **[INSTALACION.md](INSTALACION.md)**.

**A mano** (o en macOS / Linux):

```bash
cd "gym lite"
python -m pip install -r requirements.txt
python run.py
```

En el primer arranque se crea la base de datos, se cargan los datos iniciales y se
abre el navegador en <http://localhost:5000>. Para detener el servidor: `Ctrl+C`.

### Archivos de instalación

| Archivo | Para qué sirve |
|---|---|
| `instalar.bat` | Instala el programa (comprueba Python, crea `.venv`, instala Flask, prepara la base y crea el acceso directo). |
| `iniciar.bat` | Arranca el programa. Admite las mismas opciones que `run.py`, por ejemplo `iniciar.bat --port 5001`. |
| `crear-paquete.bat` | Genera un `.zip` para instalarlo en otro PC, **sin incluir los datos** de este equipo. |
| `desinstalar.bat` | Quita el entorno y el acceso directo. Pregunta aparte si borrar también los datos. |

### Opciones de `run.py`

| Opción | Para qué sirve |
|---|---|
| `--port 5001` | Usar otro puerto si el 5000 está ocupado. |
| `--no-browser` | No abrir el navegador automáticamente. |
| `--debug` | Recarga automática al editar el código (solo para desarrollo). |

## Acceso por defecto

| Campo | Valor |
|---|---|
| Usuario | `Admin` |
| Contraseña | `Admin.123` |

> ⚠️ Cambie esta contraseña antes de usar el sistema de verdad, desde
> **Mi cuenta → Cambiar contraseña**. La política exige mínimo 8 caracteres, una
> mayúscula, una minúscula, un número y un carácter especial.

Los datos iniciales incluyen además un cliente de ejemplo con una inscripción vigente,
las tarifas base, cuatro servicios complementarios y ocho productos, para poder
recorrer la aplicación de inmediato.

## Roles

| Rol | Acceso |
|---|---|
| **Administrador** | Todo: clientes, inscripciones, ventas, catálogo, tarifas, usuarios y registro de actividad. |
| **Caja** | Inicio, registro de clientes, inscripciones y ventas. |
| **Entrenador** | Inicio y su propio perfil. |

> El rol **Entrenador** quedó con muy poco alcance: en la versión original su trabajo
> era administrar el blog y el cronograma, módulos que aquí no existen. Se conserva
> por si le asigna nuevas funciones; si no lo necesita, puede no crear usuarios con
> ese rol.

## Módulos

| Módulo | Qué hace |
|---|---|
| Inicio | Indicadores, **perfiles de los clientes con inscripción vencida**, los que vencen en 7 días, gráficas de 12 meses, desglose de ingresos del mes, productos más vendidos y stock bajo. |
| Registro de usuarios | Alta, búsqueda, filtros, edición y baja de clientes, con **foto tomada desde la cámara**. |
| Inscripción de gym | Tablero con **filtro por estado** (todos / vigentes / vencidas / sin inscripción), alta de mensualidades con servicios complementarios y recibo imprimible. |
| Venta de productos | Catálogo, carrito, liquidación con autocompletado del comprador, control de stock, recibo imprimible e historial. |
| Catálogo de productos | Alta, edición, imágenes y baja lógica de productos. |
| Crear tarifas | Precios de inscripción por duración, valor de mes adicional y servicios complementarios. |
| Administrar usuarios | Alta, edición y baja del personal del sistema. |
| Registro de actividad | Historial de acciones con filtros por rol, usuario y fechas, y exportación a CSV. |

### Foto del cliente

Al registrar o editar un cliente, la foto se **toma con la cámara del equipo** y
después se abre un editor para centrar el rostro: se arrastra la imagen y se ajusta el
acercamiento dentro de una guía circular. También se puede subir una imagen existente,
que pasa por el mismo editor.

> Esta es la única parte de la aplicación con JavaScript real
> (`app/static/photo-capture.js`, sin librerías): acceder a la cámara y recortar de
> forma interactiva son capacidades del navegador que no tienen equivalente en el
> servidor. El recorte final viaja al servidor y **Python lo decodifica, valida que sea
> realmente una imagen y lo guarda** en `instance/uploads/`.
>
> La cámara solo funciona en `localhost` o con HTTPS: es una restricción de los
> navegadores, no de la aplicación. Si el equipo no tiene cámara, use «Subir imagen».

### Recibos y exportaciones

Los recibos de venta e inscripción se abren como página imprimible: el botón
**«Imprimir / Guardar PDF»** usa el diálogo del navegador, que permite tanto imprimir
como guardar el comprobante en PDF. El registro de actividad se exporta a **CSV**
(se abre directamente en Excel).

## Estructura del proyecto

```
gym lite/
├── run.py                  # arranque del servidor
├── requirements.txt        # única dependencia: Flask
├── app/
│   ├── __init__.py         # fábrica de la aplicación y manejo de errores
│   ├── config.py           # configuración y vocabulario del dominio
│   ├── schema.sql          # esquema completo de la base de datos
│   ├── db.py               # conexión SQLite y ayudas de consulta
│   ├── seed.py             # datos iniciales (idempotente)
│   ├── security.py         # sesión, roles, CSRF, contraseñas y auditoría
│   ├── helpers.py          # validaciones, fechas y formato
│   ├── uploads.py          # guardado de imágenes
│   ├── charts.py           # gráficas SVG generadas en Python
│   ├── views/              # un archivo por módulo
│   ├── templates/          # plantillas Jinja2
│   └── static/styles.css   # hoja de estilos única
└── instance/               # se crea al ejecutar (NO subir a git)
    ├── gym.db              # base de datos
    ├── secret_key          # clave de firma de la sesión
    └── uploads/            # fotos subidas
```

## Comandos de mantenimiento

Desde la carpeta del proyecto, con la variable `FLASK_APP` apuntando a la aplicación:

```bash
python -m flask --app app init-db
```

| Comando | Qué hace |
|---|---|
| `init-db` | Reaplica el esquema (no borra datos). |
| `seed` | Vuelve a cargar los datos iniciales que falten. |
| `reset-db` | **Borra todo** y deja la base recién creada (pide confirmación). |

## Seguridad

- Contraseñas guardadas con hash **scrypt** (nunca en texto plano).
- **Bloqueo de cuenta** durante 5 minutos tras 3 intentos fallidos.
- Sesión en cookie firmada, `HttpOnly`, con caducidad de 8 horas.
- **Protección CSRF** en todos los formularios.
- Todas las consultas usan **parámetros ligados**, nunca concatenación de cadenas:
  no hay superficie de inyección de SQL.
- Eliminar un cliente o un usuario exige **volver a escribir la contraseña** de quien
  tiene la sesión abierta.
- Las imágenes se guardan con nombre aleatorio y extensión validada.

> El servidor incluido es el de desarrollo de Flask, pensado para uso local en una
> máquina de confianza. Para exponerlo en una red debería ponerse detrás de un
> servidor WSGI (waitress, gunicorn) y HTTPS.

## Solución de problemas

- **«El puerto 5000 ya está en uso»**: arranque con `python run.py --port 5001`.
  En macOS el 5000 lo ocupa AirPlay.
- **No puedo eliminar un cliente**: tiene inscripciones o ventas asociadas. Cancele
  primero la inscripción desde «Inscripción de gym»; las ventas no se borran porque
  forman parte del histórico contable.
- **No puedo eliminar un usuario**: tiene ventas o inscripciones registradas a su
  nombre. Cámbiele el rol en lugar de borrarlo.
- **«Token de seguridad inválido»**: la pestaña estuvo abierta demasiado tiempo.
  Recargue la página e intente de nuevo.
- **Olvidé la contraseña de administrador**: no hay recuperación por correo. Elimine
  `instance/gym.db` y vuelva a ejecutar `python run.py` para empezar de cero, o pida a
  otro administrador que cree un usuario nuevo.
- **Empezar de cero**: borre la carpeta `instance/` completa y ejecute `python run.py`.

## Licencia

© 2026 Luis Mancilla. Todos los derechos reservados.
