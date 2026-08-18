# 🏋️ GymManager Lite

Sistema de gestión de gimnasio para uso interno del personal: registro de clientes,
inscripciones y mensualidades, venta de productos con control de stock, devoluciones,
control de acceso por reconocimiento facial, copias de seguridad, migración de datos,
tarifas configurables, panel de indicadores y registro de actividad.

Hecho **en Python y SQL**, para correr localmente en un PC: **Flask + SQLite con
consultas SQL directas** y plantillas Jinja2. No usa ORM ni frameworks de JavaScript de
por medio. La única llamada a un servicio externo es la validación de la licencia contra
**Firebase** (ver [Licenciamiento](#licenciamiento)) — y ni siquiera esa se repite para
siempre: una licencia **perpetua**, una vez activada, no vuelve a necesitar internet.

Se distribuye como un **instalador gráfico compilado** (`GymManagerLite-Setup.exe`) que
no exige tener Python en el equipo de destino.

## Contenido

- [Diferencias con GymManager Pro](#diferencias-con-gymmanager-pro)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Acceso por defecto](#acceso-por-defecto)
- [Roles](#roles) · [Módulos](#módulos)
- [Control de acceso (reconocimiento facial)](#control-de-acceso-reconocimiento-facial)
- [Licenciamiento](#licenciamiento)
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

Esta versión nació deliberadamente más reducida, aunque con el tiempo recuperó algunas
funciones que al principio eran exclusivas de Pro (como el reconocimiento facial):

| | GymManager Pro | GymManager Lite |
|---|---|---|
| Stack | Node/Express + React | Python/Flask + SQLite |
| Reconocimiento facial (control de acceso) | Sí | **Sí** (kiosco propio, ver más abajo) |
| Portal del cliente (cuenta propia) | Sí | **No incluido** |
| Asistencias y rachas | Sí | No (dependían del portal del cliente) |
| Blog y cronograma | Sí | No (solo existían para el portal del cliente) |
| Clientes | Ficha + cuenta de acceso | **Solo ficha administrativa** |
| Cuentas del sistema | Personal + clientes | **Solo personal** |
| Licenciamiento | — | **Firebase, con modo perpetuo sin conexión** |

Los clientes no inician sesión ni tienen perfil propio: son registros que administra
el personal. Por eso tampoco existen pantallas de contenido para clientes.

## Requisitos

**Para usar el programa instalado:** Windows 10 u 11 y un navegador moderno. El
instalador lleva todo dentro, no hace falta Python. Internet solo hace falta para
**activar la licencia la primera vez** (un único contacto con Firebase); después, una
licencia con vencimiento reconecta cuando puede y tolera hasta 7 días sin conexión, y
una licencia **perpetua** no vuelve a necesitar internet nunca más. El control de acceso
por reconocimiento facial es opcional y necesita una cámara en el equipo del kiosco.

**Para trabajar sobre el código:** Python 3.10 o superior (probado con 3.14) con `pip`.
No hace falta instalar ningún motor de base de datos: SQLite es un archivo local que se
crea solo.

## Instalación

Doble clic en **`dist\GymManagerLite-Setup.exe`**. Es el único archivo que se
distribuye: lleva el programa ya compilado dentro, así que **no requiere Python ni
permisos de administrador** (sí necesita internet una vez, para activar la licencia).

El asistente pide aceptar la licencia, deja elegir la carpeta de destino, copia los
archivos mostrando el progreso y crea una **base de datos limpia con un único usuario
administrador**. Al terminar deja accesos directos y una entrada en «Agregar o quitar
programas». La primera vez que se abre el programa, un administrador debe activar la
licencia con la clave que le entregó el vendedor (ver [Licenciamiento](#licenciamiento)).

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
> mayúscula, una minúscula, un número y un carácter especial. Cambiarla cierra
> automáticamente cualquier otra sesión que hubiera quedado abierta con la contraseña
> anterior.

La base de datos arranca **vacía**: ese administrador es lo único que existe. No hay
clientes, productos, servicios ni tarifas de ejemplo. Lo primero que conviene hacer es
entrar en **Crear tarifas** y fijar los precios de inscripción, porque sin ellos no se
pueden registrar mensualidades.

## Roles

| Rol | Acceso |
|---|---|
| **Administrador** | Todo: clientes, inscripciones, ventas, devoluciones, catálogo, tarifas, usuarios, copias de seguridad, migración de datos, índices corporales, control de acceso, licenciamiento y registro de actividad. |
| **Caja** | Inicio, registro de clientes, inscripciones, ventas y devoluciones. |
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
| Inscripción de gym | Tablero con **filtro por estado** (todos / vigentes / pausadas / vencidas / sin inscripción), alta de mensualidades con servicios complementarios, pausar/reanudar y recibo imprimible. |
| Venta de productos | Catálogo, carrito, liquidación con autocompletado del comprador, control de stock, recibo imprimible e historial. |
| Devoluciones | Se busca el recibo por código de barras o número, se ve el saldo devolvible y se registra una devolución total o parcial, sin tocar el recibo original. |
| Ventas e ingresos *(admin)* | Histórico combinado de ventas e inscripciones con filtros y exportación a CSV. |
| Catálogo de productos *(admin)* | Alta, edición, imágenes y baja lógica de productos. |
| Crear tarifas *(admin)* | Precios de inscripción por duración, valor de mes adicional y servicios complementarios. |
| Administrar usuarios *(admin)* | Alta, edición y baja del personal del sistema. |
| Datos del negocio *(admin)* | Nombre, NIT, contacto y pie de página que se imprimen en los recibos; interruptor del código de barras. |
| Copias de seguridad *(admin)* | Copia y restauración de **toda** la base de datos (caja, transacciones, clientes, usuarios) **y las fotos**, en un solo archivo `.zip`; frecuencia automática configurable. |
| Migración de datos *(admin)* | Alta manual o por CSV de socios que ya existían antes del programa, sin generar recibo (no representan un cobro). |
| Índices corporales *(admin)* | Qué índices se calculan en la ficha del cliente (IMC, % de grasa, etc.) y cómo se interpretan según sexo y edad. |
| Control de acceso *(admin)* | Configura y monitorea el kiosco de reconocimiento facial — ver [más abajo](#control-de-acceso-reconocimiento-facial). |
| Registro de actividad *(admin)* | Historial de acciones con filtros por rol, usuario y fechas, y exportación a CSV. |
| Información del software *(admin)* | Estado de la licencia y datos de la instalación — ver [Licenciamiento](#licenciamiento). |

### Foto del cliente

Al registrar o editar un cliente, la foto se **toma con la cámara del equipo** y
después se abre un editor para centrar el rostro: se arrastra la imagen y se ajusta el
acercamiento dentro de una guía circular. También se puede subir una imagen existente,
que pasa por el mismo editor.

> Esta es una de las pocas partes de la aplicación con JavaScript real
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
como guardar el comprobante en PDF. Si el código de barras está activado (**Datos del
negocio**), el recibo lo incluye para poder leerlo después desde **Devoluciones**. El
registro de actividad y el histórico de ventas e ingresos se exportan a **CSV** (se
abren directamente en Excel).

## Control de acceso (reconocimiento facial)

Un kiosco (`/acceso/`) pensado para quedar encendido, sin atender, en la entrada del
gimnasio: reconoce al socio por la cámara y muestra si su inscripción está vigente,
vencida, pausada o si no tiene ninguna.

- **El reconocimiento ocurre en el navegador**, con [face-api.js](app/static/vendor/faceapi)
  (modelos incluidos, sin llamadas externas): la cámara nunca sale del equipo. Lo único
  que viaja al servidor es un **descriptor de 128 números**, no una imagen ni un video.
  El emparejamiento contra los rostros registrados se hace en el servidor.
- Cada cliente admite **hasta 5 muestras** de rostro (con gafas, sin ellas, otra luz),
  registradas desde su ficha en **Inscripción de gym**.
- El kiosco solo responde a peticiones del **propio equipo** (`127.0.0.1`), aunque el
  servidor esté escuchando en la red.
- Un **antirrebote configurable** (5 segundos a 12 horas) evita registrar entradas
  repetidas de quien sigue delante de la cámara.
- Se activa o desactiva por completo desde **Control de acceso**; apagado, el kiosco no
  abre la cámara y la inscripción tampoco pide rostro.

## Licenciamiento

El programa se vende con una licencia por instalación, validada contra **Firebase**
(`app/licensing.py`) y guardada localmente en un archivo firmado —no dentro de
`gym.db`, así que restaurar una copia de seguridad en otro equipo nunca «regala» la
licencia de quien la hizo—.

| Tipo | Vencimiento |
|---|---|
| Prueba (`TRIAL`) | Sí, corto (la emite siempre el vendedor). |
| Mensual (`MONTHLY`) | Sí. |
| Anual (`ANNUAL`) | Sí. |
| Perpetua (`PERPETUAL`) | **No vence.** Tras activarse, no vuelve a validar contra Firebase nunca más. |

Con conexión intermitente, una licencia con vencimiento sigue funcionando hasta 7 días
sin poder reconectar; pasado ese margen, exige volver a tener internet. Una licencia
**perpetua** no tiene ese límite porque simplemente deja de intentar conectarse tras la
activación — no hay vencimiento que vigilar.

Un administrador activa la licencia desde **Información del software**, con la clave
que le entrega el vendedor. La emisión, renovación (que también permite **cambiar el
tipo de licencia**, incluida la conversión hacia o desde perpetua), revocación y demás
administración se hacen con `vendor_tools/licensing_cli.py` (línea de comandos) o
`vendor_tools/licensing_gui.py` (misma herramienta con ventanas) — se ejecutan en el
equipo del **vendedor**, nunca en el del cliente, y esa carpeta entera queda fuera de lo
que empaqueta `installer/build.py`.

## Estructura del proyecto

```
gym lite/
├── run.py                  # arranque del servidor (desarrollo, con consola)
├── gym_launcher.py         # arranque de la versión instalada (ventana de control)
├── version.py              # único lugar donde vive el número de versión
├── requirements.txt        # Flask + requests y pywin32 (licenciamiento)
├── app/
│   ├── __init__.py         # fábrica de la aplicación y manejo de errores
│   ├── config.py           # configuración, rutas de datos y vocabulario del dominio
│   ├── schema.sql          # esquema completo de la base de datos
│   ├── db.py               # conexión SQLite y ayudas de consulta
│   ├── seed.py              # usuario administrador inicial (idempotente)
│   ├── security.py         # sesión, roles, CSRF, contraseñas y auditoría
│   ├── licensing.py        # máquina de estados de la licencia, caché local firmado
│   ├── firebase_client.py  # envoltorio REST mínimo para hablar con Firebase
│   ├── device_id.py        # huella del equipo para atar la licencia
│   ├── backups.py          # copia y restauración (base de datos + fotos) en .zip
│   ├── faces.py            # emparejamiento de descriptores para el kiosco
│   ├── indexes.py          # fórmulas de los índices corporales
│   ├── refunds.py          # cálculo y validación del saldo devolvible
│   ├── receipts.py / barcode.py  # código de barras de los recibos
│   ├── helpers.py          # validaciones, fechas y formato
│   ├── uploads.py          # guardado de imágenes
│   ├── charts.py           # gráficas SVG generadas en Python
│   ├── views/              # un archivo por módulo
│   ├── templates/          # plantillas Jinja2
│   └── static/             # styles.css, JS puntual y los modelos de face-api.js
├── installer/               # todo lo relativo a empaquetar y distribuir
│   ├── build.py            # compila la aplicación y produce el instalador
│   ├── installer.py        # el asistente gráfico de instalación
│   ├── uninstall.py        # el desinstalador gráfico
│   ├── license.txt         # acuerdo de licencia que muestra el asistente
│   ├── make_icon.py        # generador del icono, sin dependencias externas
│   └── assets/             # icono generado (se recrea al compilar)
├── vendor_tools/            # herramienta del VENDEDOR para emitir licencias (Firestore)
│   ├── licensing_cli.py    # línea de comandos
│   ├── licensing_gui.py    # misma herramienta con ventanas
│   └── serviceAccountKey.json  # secreto real del vendedor, NO se sube ni se empaqueta
├── instance/               # datos en desarrollo (NO subir a git)
│   ├── gym.db              # base de datos
│   ├── secret_key          # clave de firma de la sesión
│   ├── license.dat / license_key.bin  # licencia de este equipo (fuera de gym.db)
│   ├── backups/            # copias de seguridad (.zip)
│   └── uploads/            # fotos subidas
├── build/                  # intermedios de compilación (temporal, se puede borrar)
└── dist/                   # instalador compilado (NO subir a git)
    └── GymManagerLite-Setup.exe
```

`build/`, `dist/`, `instance/`, `.venv/`, `installer/assets/` y
`vendor_tools/serviceAccountKey.json` están en `.gitignore`: se generan solos, son datos
de una instalación concreta, o son secretos que nunca deben viajar con el código.

En la versión instalada los datos no van a `instance/`, sino a la subcarpeta `data` de
la carpeta de instalación.

## Ejecutar desde el código (desarrollo)

```bash
cd "gym lite"
python -m pip install -r requirements.txt
python run.py
```

En el primer arranque se crea la base de datos con el usuario administrador y se abre
el navegador en <http://localhost:5000>. La primera vez que un administrador entra,
el programa pide activar una licencia (ver [Licenciamiento](#licenciamiento)) — para
desarrollo o pruebas sin licencia real, la variable de entorno
`GYMLITE_SKIP_LICENSE=1` la salta por completo (nunca la use en un equipo instalado
de verdad). Para detener el servidor: `Ctrl+C`.

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
  Instalador: gym lite\dist\GymManagerLite-Setup.exe
  Tamaño:     45.6 MB
==============================================================
```

Tarda entre uno y dos minutos la primera vez (crea el entorno y descarga las
dependencias de compilación) y alrededor de un minuto las siguientes.

### Qué hace el script, paso a paso

| Paso | Qué produce |
|---|---|
| 1. Entorno de compilación | Crea `.venv` si no existe e instala las dependencias de `requirements.txt` más PyInstaller. |
| 2. Icono | Ejecuta `make_icon.py` y genera `installer/assets/gymlite.ico` y `gymlite-96.png`. |
| 3. Aplicación | Compila `gym_launcher.py` en `build/app-dist/GymManager Lite/` (carpeta con `GymManager Lite.exe` y sus dependencias). |
| 4. Desinstalador | Compila `installer/uninstall.py` en un `.exe` único y **lo copia dentro de la carpeta anterior**, para que viaje con el programa. |
| 5. Instalador | Compila `installer/installer.py` incrustando esa carpeta como carga útil, y deja `dist/GymManagerLite-Setup.exe`. |

Antes del paso 5 borra cualquier carpeta `data` que hubiera quedado en la carga útil:
así **nunca** se distribuye una base de datos con información dentro (ni, por lo mismo,
una licencia activada de prueba).

### Requisitos para compilar

- **Windows** (el instalador usa el registro y los accesos directos de Windows).
- **Python 3.10 o superior** con `pip` y `tkinter` (viene incluido en el instalador
  oficial de python.org).
- **Conexión a internet la primera vez**, para descargar las dependencias de
  compilación. Después ya no hace falta: el entorno queda en `.venv`.

### Actualizar el programa y generar un instalador nuevo

Cuando haga cambios y quiera distribuirlos:

**1. Edite lo que corresponda.**

| Si quiere cambiar… | Toque… |
|---|---|
| Funcionalidad, pantallas o consultas | `app/` (vistas, plantillas, `styles.css`) |
| Esquema de la base de datos | `app/schema.sql` |
| Datos iniciales (el usuario administrador) | `app/seed.py` |
| Texto de la licencia del instalador | `installer/license.txt` |
| Textos, pantallas o comportamiento del asistente | `installer/installer.py` |
| El desinstalador | `installer/uninstall.py` |
| El icono | `installer/make_icon.py` |
| Ventana de control del programa instalado | `gym_launcher.py` |
| Emisión/renovación de licencias de cliente | `vendor_tools/licensing_cli.py` o `licensing_gui.py` |

**2. Suba el número de versión.** Vive en un único archivo, `version.py`, en la raíz del
proyecto — tanto `installer/build.py` como `installer/installer.py` lo importan de ahí,
así que no hay que tocar nada más:

```python
# version.py
APP_VERSION = "1.0.2"
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
limpia**. Las actualizaciones normales se hacen conservando los datos (y la licencia
activada, que vive fuera de `gym.db`).

> Si cambió `app/schema.sql`, tenga en cuenta que el esquema se aplica con
> `CREATE TABLE IF NOT EXISTS`: sobre una base existente **no** añade columnas nuevas a
> tablas que ya existían. `app/db.py::migrate()` ya cubre las migraciones de columnas
> conocidas; para cambios de esquema nuevos hay que ampliar esa función o reinstalar
> con base limpia.

### Personalizar el instalador

Las constantes del principio de `installer/installer.py` controlan la identidad del
producto (la versión se importa de `version.py`, no se repite aquí):

```python
APP_NAME = "GymManager Lite"          # título, carpeta y accesos directos
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
descargar las dependencias (necesita internet).

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
- **Bloqueo de cuenta** durante 5 minutos tras 3 intentos fallidos (conteo atómico:
  no se puede evadir enviando intentos en paralelo).
- Sesión en cookie firmada, `HttpOnly`, con caducidad de 8 horas; **cambiar la
  contraseña invalida cualquier otra sesión** abierta con la anterior.
- **Protección CSRF** en todos los formularios.
- Todas las consultas usan **parámetros ligados**, nunca concatenación de cadenas:
  no hay superficie de inyección de SQL.
- Eliminar un cliente o un usuario exige **volver a escribir la contraseña** de quien
  tiene la sesión abierta.
- Las imágenes se guardan con nombre aleatorio y extensión validada.
- La licencia queda atada a una **huella del equipo** y se revalida contra Firebase
  periódicamente (salvo las perpetuas, que dejan de necesitarlo tras activarse); vive
  fuera de `gym.db` a propósito, para que restaurar una copia de seguridad en otro
  equipo nunca transfiera la licencia con ella.
- Las copias de seguridad incluyen la base de datos **y las fotos**, pero nunca la
  licencia de este equipo ni la clave de firma de la sesión.

> El servidor incluido es el de desarrollo de Flask, pensado para uso local en una
> máquina de confianza. Para exponerlo en una red debería ponerse detrás de un
> servidor WSGI (waitress, gunicorn) y HTTPS.

## Solución de problemas

- **«El puerto 5000 ya está en uso»**: arranque con `python run.py --port 5001`.
  En macOS el 5000 lo ocupa AirPlay.
- **No puedo eliminar un cliente**: tiene inscripciones o ventas asociadas. Cancele
  primero la inscripción desde «Inscripción de gym»; las ventas no se borran porque
  forman parte del histórico contable. Tampoco se puede cancelar una inscripción que
  ya tiene una devolución registrada, por el mismo motivo.
- **No puedo eliminar un usuario**: tiene ventas o inscripciones registradas a su
  nombre. Cámbiele el rol en lugar de borrarlo.
- **«Token de seguridad inválido»**: la pestaña estuvo abierta demasiado tiempo.
  Recargue la página e intente de nuevo.
- **«No hay tarifa configurada para esta duración»**: es lo esperado en una instalación
  nueva. Entre en «Crear tarifas» y fije los precios.
- **No se pudo activar la licencia / «Error de comunicación con Firebase»**: revise la
  conexión a internet del equipo. La activación inicial sí necesita red; una vez
  activada, una licencia con vencimiento tolera hasta 7 días sin conexión y una
  perpetua no vuelve a necesitarla.
- **El kiosco de reconocimiento facial no abre la cámara**: revise que esté activado en
  «Control de acceso» y que el navegador tenga permiso de cámara para `localhost`; fuera
  de `localhost` hace falta HTTPS, restricción del navegador y no de la aplicación.
- **Olvidé la contraseña de administrador**: no hay recuperación por correo. Pida a otro
  administrador que cree un usuario nuevo o borre la base de datos para empezar de cero
  (se pierden todos los datos, aunque la licencia activada del equipo no se ve afectada,
  vive fuera de `gym.db`).
- **Empezar de cero**: borre la carpeta de datos completa y vuelva a abrir el programa
  — `instance/` si ejecuta el código, `data\` si usa la versión instalada. Esto también
  borra la licencia activada de ese equipo.

Los problemas de la versión instalada (SmartScreen, accesos directos, desinstalación)
están en **[INSTALACION.md](INSTALACION.md)**; los de compilación, en
[Problemas al compilar](#problemas-al-compilar).

## Licencia

© 2026 Luis Mancilla. Todos los derechos reservados.
