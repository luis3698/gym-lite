# Contexto: Copias de seguridad completas y auditoría de bugs

> Bitácora viva de esta sesión de trabajo. Sigue el mismo formato que
> `contexto.md` (la de licenciamiento): qué se decidió, qué se hizo y qué
> queda pendiente, para retomar el hilo sin releer todo el código.

## Por qué existe este archivo

El usuario pidió dos cosas en la misma sesión: (1) que la copia de seguridad
abarque toda la información de caja, transacciones, usuarios y recibos, y (2)
una revisión completa del código en busca de bugs. Se separa de `contexto.md`
porque esa bitácora es específicamente de la funcionalidad de licenciamiento
("Bitácora viva de **esta funcionalidad**") y mezclar temas ahí la haría
confusa para quien la use de referencia sobre licencias.

## Punto de partida encontrado

Al empezar, `contexto.md` aparecía borrado del disco (`git status` lo mostraba
como `D contexto.md`, sin commit) pese a que `app/config.py` lo sigue
referenciando en un comentario. Se restauró con `git checkout HEAD --
contexto.md` antes de tocar nada más: contenía la bitácora completa de la
implementación de licenciamiento con Firebase y no había motivo aparente para
borrarlo.

## 1. Copias de seguridad: ahora incluyen las fotos

**Diagnóstico:** `app/backups.py` ya usaba `sqlite3.Connection.backup()` para
copiar `gym.db` de forma consistente (WAL incluido), así que caja,
transacciones, usuarios, ventas, devoluciones y auditoría YA viajaban
completos en cada copia — no hacía falta tocar eso. Los recibos tampoco son un
archivo aparte: se generan al vuelo desde esos mismos datos (ver
`app/templates/_receipt.html`), así que también quedaban cubiertos sin hacer
nada extra.

El hueco real, y el que la propia pantalla de copias documentaba
explícitamente ("las fotos... no están dentro de la base... conviene copiar
también esa carpeta"): las fotos de clientes, personal y productos viven como
archivos en `instance/uploads/` y no viajaban con la copia.

**Decisión de diseño importante — qué se excluye a propósito:**
La licencia (`INSTANCE_DIR/license.dat` + `license_key.bin`) NO se incluye en
la copia. Esto ya estaba documentado en `contexto.md`: la licencia es de este
equipo, y si viajara dentro de una copia de seguridad, restaurarla en otro
equipo le regalaría la licencia a quien no la compró. Se mantuvo ese criterio
al ampliar el formato.

**Qué se cambió (`app/backups.py`, `app/views/backup.py`,
`app/templates/backup/index.html`):**
- Las copias pasan de ser un `.db` suelto a un `.zip` con `gym.db` +
  `uploads/`. `create_backup()` sigue usando `_copy_database()` (la API
  `backup()` de SQLite) para la foto consistente de la base, y luego empaqueta
  esa foto junto con `UPLOAD_DIR` completo.
- **Compatibilidad con copias antiguas:** `verify_backup()` y
  `restore_backup()` detectan el formato por contenido
  (`zipfile.is_zipfile()`), no por extensión, así que las copias `.db` sueltas
  de antes siguen funcionando (verse, descargarse, borrarse, restaurarse) —
  solo que restaurarlas no trae fotos. Se marcan con la insignia "Sin fotos"
  en la pantalla.
- `resolve_backup()` tenía un bug de paso: `BACKUP_PATTERN` (la regex pensada
  para validar el nombre) estaba definida pero **nunca se usaba** — la
  validación real era más laxa (solo "termina en .db, sin barras"). Se
  corrigió para que `resolve_backup()` sí valide contra el patrón completo
  (ahora también acepta `.zip` y el sufijo numérico `-2`, `-3`... que
  `create_backup()` genera para dos copias en el mismo minuto).
- Restaurar un `.zip` copia las fotos del paquete a `uploads/` de forma
  aditiva (sobrescribe las que coincidan en nombre, no borra las que no estén
  en la copia) — evita perder fotos por una copia parcial.

**Verificado:** script de prueba directo sobre `app/backups.py` (crear,
verificar, restaurar con fotos, listar, `resolve_backup` rechazando path
traversal y nombres inválidos) y prueba de humo a través del blueprint HTTP
completo (`/copias/`, crear, listar como `.zip`, descargar y comprobar la
firma `PK` del zip). Además compatibilidad con una copia `.db` antigua
simulada (verificar/listar/resolver/restaurar).

## 2. Auditoría de bugs

Se lanzaron 4 agentes en paralelo, cada uno sobre un área distinta del código
(dinero/transacciones, seguridad/licenciamiento, kiosco facial,
clientes/migración/vistas restantes), con instrucciones de solo investigar y
reportar bugs reales y confirmados leyendo el código, no estilo ni
suposiciones. De los hallazgos, se corrigieron los siguientes (todos
verificados con pruebas de humo después del cambio, no solo por lectura):

### Dinero y transacciones
- **`app/views/memberships.py::cancel()`** — cancelar una inscripción que ya
  tenía una devolución registrada la borraba (`DELETE FROM memberships`)
  dejando la devolución huérfana: el reporte de ingresos (`income.py`) perdía
  el cobro original pero seguía restando la devolución, descuadrando la caja
  para siempre sin rastro de por qué. Ahora se bloquea igual que una venta con
  ventas asociadas: si hay una devolución contra esa inscripción, no se puede
  cancelar.
- **`app/views/sales.py::history()`** — el total y el conteo del historial de
  ventas se calculaban sumando solo las 300 filas mostradas (`LIMIT 300`), no
  con una consulta de agregación sobre todas las ventas. En cuanto hubiera más
  de 300 ventas, el total mostrado quedaba por debajo del real sin ningún
  aviso — exactamente el error que `income.py` documenta evitar a propósito.
  Se separó en una consulta de agregación aparte, y la plantilla avisa cuando
  se están mostrando menos filas de las que existen.
- **`app/views/memberships.py::_create_membership()`** — el precio de la
  inscripción se calculaba con las tarifas leídas al pintar la pantalla, antes
  de abrir la transacción de escritura (a diferencia de `sales.py`, que sí
  relee el precio del producto dentro de la transacción). Se movió la
  recarga de tarifas dentro de `with transaction()`.

### Seguridad y licenciamiento
- **`app/licensing.py`** — cuando Firebase respondía que una licencia ya no
  existe (404, revocada/eliminada), `evaluate_license()` devolvía `REVOKED`
  en esa respuesta pero **nunca lo guardaba en el caché firmado en disco**. La
  siguiente petición (hasta 12 horas después, `LICENSE_SYNC_INTERVAL_HOURS`),
  al no tocar volver a sincronizar, releía el caché viejo con
  `status_at_sync="ACTIVE"` y volvía a reportar la licencia como `VALID`.
  Ahora `_try_online_sync()` persiste el estado `REVOKED` en el caché en el
  mismo momento en que lo detecta.
- **`app/security.py::register_failed_attempt()`** — el conteo de intentos
  fallidos se leía en Python y se escribía como número absoluto
  (`current_attempts + 1`), un "lost update" clásico: dos intentos fallidos
  casi simultáneos (el servidor corre con `threaded=True`) podían leer el
  mismo valor de partida y solo uno de los incrementos sobrevivía, permitiendo
  más intentos de los que `MAX_LOGIN_ATTEMPTS` debería permitir. Se cambió a
  un `UPDATE failed_attempts = failed_attempts + 1` atómico en SQL.
- **`app/security.py`** — cambiar la contraseña no invalidaba otras sesiones
  ya abiertas (por ejemplo, una cookie de sesión robada seguía sirviendo hasta
  su vencimiento natural de `SESSION_HOURS`). Se añadió una huella corta del
  hash de contraseña (`pw_tag`) a la sesión; si no coincide con el hash actual
  del usuario, la sesión se cierra en `load_logged_in_user()`.

### Kiosco de acceso facial
- **`app/views/access.py::enroll()`** — el hueco disponible
  (`MAX_FACES_PER_CLIENT - client_face_count(...)`) se comprobaba fuera de
  cualquier transacción; dos envíos casi simultáneos del mismo formulario
  podían leer ambos "quedan huecos" antes de que ninguno insertara, dejando
  más de 5 muestras guardadas. Se movió la comprobación y la inserción dentro
  de `with transaction()`, recontando con el bloqueo de escritura ya tomado
  (mismo patrón que ya usaba `identify()` para el antirrebote).
- **`app/views/access.py::identify()`** — al llegar al tope diario
  (`MAX_ACCESS_LOGS_PER_DAY`), dejaba de insertar filas pero no marcaba nada
  más: el antirrebote seguía comparando contra el último registro real (cada
  vez más viejo), así que cada fotograma siguiente reabría una transacción de
  escritura sin insertar nada y el aviso de "ya registrado" dejaba de
  mostrarse. Ahora, al llegar al tope, se trata como si estuviera en
  antirrebote el resto del día.
- **`app/views/access.py::identify()`** — si el motivo de acceso cambiaba
  (p. ej. EXPIRED → ACTIVE porque el socio pagó en mostrador) mientras seguía
  dentro del antirrebote, no se registraba nada nuevo: el histórico y el aviso
  al personal se quedaban con el estado viejo. Ahora un cambio de motivo
  respecto al último registro fuerza el registro aunque siga en antirrebote.
- **`app/views/access.py::_client_card()`** — la ficha que se muestra junto a
  la cámara elegía la membresía por "vencimiento más lejano", que podía ser
  una distinta de la que realmente decidió el acceso (p. ej. una pausada de
  vencimiento lejano vs. una corta vigente). Ahora recibe el motivo que ya
  decidió `_decide()` y elige la membresía coherente con ese motivo.

### Clientes, migración y datos
- **`app/views/migration.py`** — la previsualización de una importación CSV
  (hasta 2000 filas) se guardaba entera en la cookie de sesión, que Flask no
  particiona: por encima de ~15-20 filas, el navegador la truncaba o
  descartaba y `confirm()` recibía la sesión vacía, perdiendo la importación
  completa en silencio — justo el caso de uso que el módulo anuncia soportar.
  Se cambió a guardar la previsualización en un archivo temporal
  (`instance/tmp/migracion/<token>.json`, fuera del repo por el `.gitignore`
  de `instance/`) y solo un token corto en la cookie. Incluye limpieza de
  previsualizaciones abandonadas (más de 6 horas sin confirmar).
- **`app/views/clients.py` y `app/views/users.py`** — el campo `sex` no se
  validaba contra `SEX_OPTIONS` (a diferencia de `blood_type`, `goal` y
  `activity_level`, que sí), pese a que el propio comentario del código dice
  que un `<select>` manipulado no debe colar valores fuera del catálogo. Se
  agregó la validación en ambos formularios (y `blood_type` en `users.py`,
  que tampoco la tenía). De paso se encontró que `app/seed.py` sembraba el
  administrador con `sex = 'No especifica'`, un valor que tampoco está en
  `SEX_OPTIONS` — se cambió a `NULL` (el resto del sistema representa "sin
  especificar" con NULL, no con un texto).
- **`app/views/clients.py` y `app/views/users.py`** — la comprobación de
  duplicados (documento/correo/usuario) era un `SELECT` antes del
  `INSERT`/`UPDATE`, sin protección de carrera: dos altas casi simultáneas con
  el mismo documento podían pasar ambas la comprobación y la segunda escritura
  lanzaba `sqlite3.IntegrityError` sin capturar → error 500, y si la petición
  traía una foto nueva, quedaba huérfana en disco (ya guardada, pero
  referenciada por ninguna fila). Se capturó `sqlite3.IntegrityError`
  alrededor de la escritura en los cuatro puntos (crear/editar cliente,
  crear/editar usuario), con un mensaje normal y borrando la foto huérfana si
  la hubo.
- **`app/views/clients.py::delete()`** — entre contar las membresías/ventas
  del cliente y el `DELETE`, otra sesión podía registrar una inscripción o
  venta nueva; sin `ON DELETE` en la clave foránea, el `DELETE` violaba la FK
  y lanzaba una excepción sin capturar → error 500. Se capturó
  `sqlite3.IntegrityError` con un mensaje pidiendo reintentar.
- **`app/charts.py`** — el adelgazado de etiquetas del eje X
  (`label_step = count // 7`) no actuaba con `count=12` (división entera:
  `12 // 7 == 1`), que es exactamente el tamaño de los gráficos de 12 meses
  del dashboard — el propio comentario decía que a los 12 meses no cabían
  todas las etiquetas, pero con esa fórmula sí se mostraban todas. Cambiado a
  división hacia arriba.

### Encontrados pero NO corregidos (documentados como aceptados)
- **Enumeración de usuarios / canal de tiempo en `/login`** — una cuenta
  inexistente responde más rápido que una que sí existe (no se llama a
  `check_password_hash`, que es costoso), y una cuenta bloqueada responde 423
  con un mensaje distinto al de credenciales inválidas. Corregirlo del todo
  implicaría ocultarle a un socio legítimo bloqueado por qué no puede entrar,
  a cambio de una mitigación de enumeración de bajo impacto en un programa de
  un solo gimnasio con acceso ya restringido a la red local. Se deja como
  está.
- **Falta `SESSION_COOKIE_SECURE`** — mitigado porque el host por defecto es
  `127.0.0.1`; solo importa si alguien arranca `run.py --host 0.0.0.0` para
  acceso en red local. No se fuerza a `True` porque el programa no sirve HTTPS
  y eso rompería la cookie por completo en el caso normal.
- **Huella del equipo (`device_id.py`) puede coincidir en equipos clonados**
  — no es un bug de código: en despliegues por imagen de disco sin
  `sysprep`/`NewSID` (frecuente en cadenas que preparan varios equipos a la
  vez), MachineGuid y número de serie de volumen pueden ser idénticos entre
  máquinas. Queda como nota para quien venda a una cadena, no como algo para
  arreglar en este código.

## Verificación

Todo lo corregido se probó con scripts de humo contra el cliente de pruebas de
Flask (base de datos temporal, `GYMLITE_SKIP_LICENSE=1`), no solo por lectura:
login y bloqueo por intentos fallidos, alta de cliente con validación de sexo,
creación y cancelación bloqueada de inscripción con devolución, historial de
ventas, importación CSV completa por el nuevo mecanismo de token, cambio de
contraseña invalidando otra sesión, alta de rostros respetando el tope de 5
bajo condición de carrera simulada, identificación del kiosco con antirrebote
y con el tope diario, y el flujo completo de copias de seguridad (crear,
listar como `.zip`, descargar) a través de la pantalla HTTP real.

## Pendiente

Nada bloqueante. Ideas para más adelante, no urgentes:

- Sería razonable trasladar `PREVIEW_MAX_AGE_HOURS` (limpieza de
  previsualizaciones de migración abandonadas) a una constante en
  `app/config.py` si en el futuro se quiere hacer configurable, igual que
  `BACKUP_FREQUENCY_DAYS`.
- El aviso "Sin fotos" en la pantalla de copias es permanente para las copias
  `.db` antiguas; con el tiempo, cuando ya no queden copias en ese formato
  (se van purgando solas con `prune_backups`), esa rama de compatibilidad deja
  de usarse pero no hace daño dejarla.

## Registro

- 2026-08-13: restaurado `contexto.md` (aparecía borrado sin commit). Copias
  de seguridad ampliadas para incluir `uploads/` (fotos) en un `.zip`, con
  compatibilidad hacia atrás con copias `.db` sueltas y exclusión deliberada
  de la licencia del equipo. Auditoría de bugs con 4 agentes en paralelo sobre
  dinero/transacciones, seguridad/licenciamiento, kiosco facial y
  clientes/migración/vistas. Corregidos: cancelación de inscripción con
  devolución huérfana, total truncado del historial de ventas, precio de
  inscripción no releído en transacción, licencia revocada revirtiendo a
  VALID hasta 12h, condición de carrera en el bloqueo por intentos fallidos,
  contraseña cambiada sin invalidar otras sesiones, condición de carrera en
  el tope de rostros por cliente, antirrebote roto por el tope diario del
  kiosco, cambios de estado no registrados en antirrebote, ficha del kiosco
  mostrando la membresía equivocada, pérdida silenciosa de importaciones CSV
  grandes por el límite de la cookie de sesión, falta de validación de sexo/
  tipo de sangre contra su catálogo, carreras de unicidad sin capturar (500 +
  fotos huérfanas) en clientes y usuarios, borrado de cliente sin capturar la
  violación de FK, y adelgazado de etiquetas del eje X inactivo en gráficos de
  12 meses. Todo verificado con pruebas de humo funcionales, no solo por
  lectura del código.
