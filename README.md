# 🏋️ GymManager Lite

Sistema de gestión de gimnasio para uso interno del personal: registro de clientes,
inscripciones y mensualidades, venta de productos con control de stock, tarifas
configurables, panel de indicadores y registro de actividad.

Hecho **100 % en Python y SQL**, para correr localmente en un PC:
**Flask + SQLite con consultas SQL directas** y plantillas Jinja2. No usa ORM, ni
frameworks de JavaScript, ni servicios externos.

Se distribuye como un **instalador gráfico compilado** (`GymManagerLite-Setup.exe`) que
no exige tener Python en el equipo de destino.

## Contenido

- [Diferencias con GymManager Pro](#diferencias-con-gymmanager-pro)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Acceso por defecto](#acceso-por-defecto)
- [Roles](#roles) · [Módulos](#módulos)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Ejecutar desde el código (desarrollo)](#ejecutar-desde-el-código-desarrollo)
- **[Compilar el instalador](#compilar-el-instalador)**
  - [Qué hace el script, paso a paso](#qué-hace-el-script-paso-a-paso)
  - [Actualizar el programa y generar un instalador nuevo](#actualizar-el-programa-y-generar-un-instalador-nuevo)
  - [Personalizar el instalador](#personalizar-el-instalador)
  - [Problemas al compilar](#problemas-al-compilar)
- [Comandos de mantenimiento](#comandos-de-mantenimiento)
- [Seguridad](#seguridad) · [Solución de problemas](#solución-de-problemas)

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

**Para usar el programa instalado:** Windows 10 u 11 y un navegador moderno. Nada más:
el instalador lleva todo dentro, no hace falta Python ni internet.

**Para trabajar sobre el código:** Python 3.10 o superior (probado con 3.14) con `pip`.
No hace falta instalar ningún motor de base de datos: SQLite es un archivo local que se
crea solo.

## Instalación

Doble clic en **`dist\GymManagerLite-Setup.exe`**. Es el único archivo que se
distribuye: lleva el programa ya compilado dentro, así que **no requiere Python, ni
internet, ni permisos de administrador**.

El asistente pide aceptar la licencia, deja elegir la carpeta de destino, copia los
archivos mostrando el progreso y crea una **base de datos limpia con un único usuario
administrador**. Al terminar deja accesos directos y una entrada en «Agregar o quitar
programas».

Guía paso a paso, copias de seguridad, desinstalación y solución de problemas:
**[INSTALACION.md](INSTALACION.md)**.

> ¿Necesita generar un instalador nuevo con sus cambios?
> Vea **[Compilar el instalador](#compilar-el-instalador)**.

## Acceso por defecto

| Campo | Valor |
|---|---|
| Usuario | `Admin` |
| Contraseña | `Admin.123` |

> ⚠️ Cambie esta contraseña antes de usar el sistema de verdad, desde
> **Mi cuenta → Cambiar contraseña**. La política exige mínimo 8 caracteres, una
> mayúscula, una minúscula, un número y un carácter especial.

La base de datos arranca **vacía**: ese administrador es lo único que existe. No hay
clientes, productos, servicios ni tarifas de ejemplo. Lo primero que conviene hacer es
entrar en **Crear tarifas** y fijar los precios de inscripción, porque sin ellos no se
pueden registrar mensualidades.

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
├── run.py                  # arranque del servidor (desarrollo, con consola)
├── gym_launcher.py         # arranque de la versión instalada (ventana de control)
├── requirements.txt        # única dependencia: Flask
├── app/
│   ├── __init__.py         # fábrica de la aplicación y manejo de errores
│   ├── config.py           # configuración, rutas de datos y vocabulario del dominio
│   ├── schema.sql          # esquema completo de la base de datos
│   ├── db.py               # conexión SQLite y ayudas de consulta
│   ├── seed.py             # usuario administrador inicial (idempotente)
│   ├── security.py         # sesión, roles, CSRF, contraseñas y auditoría
│   ├── helpers.py          # validaciones, fechas y formato
│   ├── uploads.py          # guardado de imágenes
│   ├── charts.py           # gráficas SVG generadas en Python
│   ├── views/              # un archivo por módulo
│   ├── templates/          # plantillas Jinja2
│   └── static/styles.css   # hoja de estilos única
├── installer/              # todo lo relativo a empaquetar y distribuir
│   ├── build.py            # compila la aplicación y produce el instalador
│   ├── installer.py        # el asistente gráfico de instalación
│   ├── uninstall.py        # el desinstalador gráfico
│   ├── license.txt         # acuerdo de licencia que muestra el asistente
│   ├── make_icon.py        # generador del icono, sin dependencias externas
│   └── assets/             # icono generado (se recrea al compilar)
├── instance/               # datos en desarrollo (NO subir a git)
│   ├── gym.db              # base de datos
│   ├── secret_key          # clave de firma de la sesión
│   └── uploads/            # fotos subidas
├── build/                  # intermedios de compilación (temporal, se puede borrar)
└── dist/                   # instalador compilado (NO subir a git)
    └── GymManagerLite-Setup.exe
```

`build/`, `dist/`, `instance/`, `.venv/` e `installer/assets/` están en `.gitignore`:
se generan solos y no forman parte del código.

En la versión instalada los datos no van a `instance/`, sino a la subcarpeta `data` de
la carpeta de instalación.

## Ejecutar desde el código (desarrollo)

```bash
cd "gym lite"
python -m pip install -r requirements.txt
python run.py
```

En el primer arranque se crea la base de datos con el usuario administrador y se abre
el navegador en <http://localhost:5000>. Para detener el servidor: `Ctrl+C`.

En este modo los datos van a `instance/`, no a la carpeta de una instalación.

### Opciones de `run.py`

| Opción | Para qué sirve |
|---|---|
| `--port 5001` | Usar otro puerto si el 5000 está ocupado. |
| `--no-browser` | No abrir el navegador automáticamente. |
| `--debug` | Recarga automática al editar el código (solo para desarrollo). |
| `--host 0.0.0.0` | Escuchar en toda la red en lugar de solo en este equipo. |

### Opciones de `gym_launcher.py`

Es el punto de entrada de la **versión instalada**: en lugar de una consola abre una
ventana de control con la dirección del programa, la ruta de los datos y los botones
«Abrir en el navegador» y «Detener y salir».

| Opción | Para qué sirve |
|---|---|
| `--init-db` | Crea la base de datos limpia y termina. Lo usa el instalador. |
| `--no-browser` | Abre la ventana de control sin lanzar el navegador. |

Busca automáticamente un puerto libre entre el 5000 y el 5010.

### Dónde busca los datos la aplicación

`app/config.py` decide la carpeta de datos en este orden:

1. La variable de entorno **`GYMLITE_DATA_DIR`**, si está definida (útil para pruebas).
2. Si el programa está **compilado**: la subcarpeta `data` junto al `.exe`; y si esa
   carpeta es de solo lectura (por ejemplo «Archivos de programa»), entonces
   `%LOCALAPPDATA%\GymManager Lite\data`.
3. Si se ejecuta **desde el código**: la carpeta `instance/` del proyecto.

---

## Compilar el instalador

Todo el empaquetado se hace con un solo comando:

```bash
py -3 installer/build.py
```

Al terminar imprime la ruta y el tamaño del resultado:

```
==============================================================
  COMPILACIÓN COMPLETADA
==============================================================
  Instalador: F:\claude code\gym lite\dist\GymManagerLite-Setup.exe
  Tamaño:     39.8 MB
==============================================================
```

Tarda entre uno y dos minutos la primera vez (crea el entorno y descarga PyInstaller) y
alrededor de un minuto las siguientes.

### Qué hace el script, paso a paso

| Paso | Qué produce |
|---|---|
| 1. Entorno de compilación | Crea `.venv` si no existe e instala Flask + PyInstaller. |
| 2. Icono | Ejecuta `make_icon.py` y genera `installer/assets/gymlite.ico` y `gymlite-96.png`. |
| 3. Aplicación | Compila `gym_launcher.py` en `build/app-dist/GymManager Lite/` (carpeta con `GymManager Lite.exe` y sus dependencias). |
| 4. Desinstalador | Compila `installer/uninstall.py` en un `.exe` único y **lo copia dentro de la carpeta anterior**, para que viaje con el programa. |
| 5. Instalador | Compila `installer/installer.py` incrustando esa carpeta como carga útil, y deja `dist/GymManagerLite-Setup.exe`. |

Antes del paso 5 borra cualquier carpeta `data` que hubiera quedado en la carga útil:
así **nunca** se distribuye una base de datos con información dentro.

### Requisitos para compilar

- **Windows** (el instalador usa el registro y los accesos directos de Windows).
- **Python 3.10 o superior** con `pip` y `tkinter` (viene incluido en el instalador
  oficial de python.org).
- **Conexión a internet la primera vez**, para descargar Flask y PyInstaller. Después
  ya no hace falta: el entorno queda en `.venv`.

### Actualizar el programa y generar un instalador nuevo

Cuando haga cambios y quiera distribuirlos:

**1. Edite lo que corresponda.**

| Si quiere cambiar… | Toque… |
|---|---|
| Funcionalidad, pantallas o consultas | `app/` (vistas, plantillas, `styles.css`) |
| Esquema de la base de datos | `app/schema.sql` |
| Datos iniciales (el usuario administrador) | `app/seed.py` |
| Texto de la licencia | `installer/license.txt` |
| Textos, pantallas o comportamiento del asistente | `installer/installer.py` |
| El desinstalador | `installer/uninstall.py` |
| El icono | `installer/make_icon.py` |
| Ventana de control del programa instalado | `gym_launcher.py` |

**2. Suba el número de versión.** Está en dos sitios y conviene que coincidan:

```python
# installer/build.py
APP_VERSION = "1.0.0"

# installer/installer.py
APP_VERSION = "1.0.0"
```

La versión se ve en la portada del asistente, en las propiedades del `.exe` (pestaña
«Detalles» de Windows) y en «Agregar o quitar programas».

**3. Pruebe con el código antes de compilar** — es mucho más rápido que esperar a que
compile:

```bash
python run.py
```

**4. Compile:**

```bash
py -3 installer/build.py
```

**5. Distribuya** el archivo `dist\GymManagerLite-Setup.exe`. Es autónomo: basta con
copiarlo al otro equipo.

Quien ya tenga una versión anterior solo tiene que ejecutar el instalador nuevo sobre
la misma carpeta. El asistente detecta la instalación previa, avisa de que la va a
reemplazar y —si encuentra datos— **pregunta si conservarlos o empezar con una base
limpia**. Las actualizaciones normales se hacen conservando los datos.

> Si cambió `app/schema.sql`, tenga en cuenta que el esquema se aplica con
> `CREATE TABLE IF NOT EXISTS`: sobre una base existente **no** añade columnas nuevas a
> tablas que ya existían. Para cambios de esquema sobre instalaciones en producción hay
> que escribir la migración a mano o reinstalar con base limpia.

### Personalizar el instalador

Las constantes del principio de `installer/installer.py` controlan la identidad del
producto:

```python
APP_NAME = "GymManager Lite"          # título, carpeta y accesos directos
APP_VERSION = "1.0.0"
PUBLISHER = "GymManager"              # «Publicador» en Agregar o quitar programas
EXE_NAME = "GymManager Lite.exe"
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\GymManagerLite"
```

Si cambia `APP_NAME` o `EXE_NAME`, cámbielos **también** en `installer/build.py` y en
`installer/uninstall.py`: los tres archivos tienen que hablar del mismo nombre.

La paleta de colores del asistente (`INDIGO`, `SLATE_*`) es la misma de la aplicación,
tomada de `app/static/styles.css`.

### Limpiar los archivos de compilación

`build/` son intermedios de PyInstaller y se pueden borrar sin miedo: el siguiente
`build.py` los regenera.

```bash
rm -rf build
```

Borrar `.venv` también es seguro, pero entonces la próxima compilación volverá a
descargar Flask y PyInstaller (necesita internet).

### Problemas al compilar

| Síntoma | Solución |
|---|---|
| `No module named PyInstaller` | Ejecute `installer/build.py`, que lo instala solo. No llame a PyInstaller a mano. |
| `El instalador está incompleto` al ejecutar el setup | Se compiló sin carga útil. Borre `build/` y vuelva a compilar. |
| El antivirus bloquea el `.exe` recién creado | Es habitual con ejecutables de PyInstaller sin firmar. Añada una excepción o firme el binario. |
| El `.exe` compilado no arranca | Ejecútelo desde la consola para ver el error, o consulte `data\error.log` junto al ejecutable. |
| Los cambios no aparecen en el instalador | Se compiló antes de guardar. Vuelva a ejecutar `build.py`. |

---

## Comandos de mantenimiento

Desde la carpeta del proyecto, con la variable `FLASK_APP` apuntando a la aplicación:

```bash
python -m flask --app app init-db
```

| Comando | Qué hace |
|---|---|
| `init-db` | Reaplica el esquema (no borra datos). |
| `seed` | Recrea el usuario administrador si falta. |
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
- **«No hay tarifa configurada para esta duración»**: es lo esperado en una instalación
  nueva. Entre en «Crear tarifas» y fije los precios.
- **Olvidé la contraseña de administrador**: no hay recuperación por correo. Pida a otro
  administrador que cree un usuario nuevo o borre la base de datos para empezar de cero
  (se pierden todos los datos).
- **Empezar de cero**: borre la carpeta de datos completa y vuelva a abrir el programa
  — `instance/` si ejecuta el código, `data\` si usa la versión instalada.

Los problemas de la versión instalada (SmartScreen, accesos directos, desinstalación)
están en **[INSTALACION.md](INSTALACION.md)**; los de compilación, en
[Problemas al compilar](#problemas-al-compilar).

## Licencia

© 2026 Luis Mancilla. Todos los derechos reservados.
