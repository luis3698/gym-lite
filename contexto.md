# Contexto: Licenciamiento con Firebase

> Bitácora viva de esta funcionalidad. Se actualiza en cada sesión de trabajo para
> retomar el hilo sin releer todo el código. **NUNCA escribir aquí secretos**: ni el
> JSON de la cuenta de servicio, ni claves de licencia reales de clientes, ni el
> contenido de `license_key.bin`. Ese material vive fuera del repo (`.gitignore`).
>
> El plan completo (arquitectura, máquina de estados, decisiones de diseño) está en
> `C:\Users\luisg\.claude\plans\expressive-swimming-feigenbaum.md` — aprobado el
> 2026-08-12. Este archivo es el resumen operativo de "qué se hizo" y "qué falta",
> no repite el plan entero.

## Decisiones tomadas

- Firestore (no Realtime Database): las reglas distinguen `get` de `list`, encaja
  con "solo lectura de una licencia conocida, nunca listar todas".
- Autenticación del cliente: Anonymous Auth vía REST (Identity Toolkit), solo con
  el Web API key (público por diseño de Firebase, no es secreto).
- Modelo de negocio: multi-cliente. Cada gimnasio con su propia licencia.
- Niveles: `TRIAL`, `MONTHLY`, `ANNUAL`, `PERPETUAL`.
- Gracia sin conexión: 7 días desde la última sincronización exitosa.
- Las licencias de prueba SIEMPRE las emite el vendedor (`licensing_cli.py`), sin
  autoservicio dentro del programa.
- Huella del equipo: `sha256(MachineGuid + serie de disco C: + nombre de equipo)`.
  Más estricta; un reformateo legítimo se resuelve con `licensing_cli.py unbind`.
- La licencia vive **fuera** de `gym.db` (en `INSTANCE_DIR/license.dat` +
  `license_key.bin`), porque `app/backups.py` hace un backup crudo de todo el
  archivo de la base de datos y cualquier cosa dentro viajaría a equipos no
  autorizados junto con una copia de seguridad restaurada.
- Sin hilo en segundo plano para la resincronización periódica (el proyecto evita
  temporizadores persistentes a propósito). Se comprueba "¿toca sincronizar?" de
  forma perezosa en `evaluate_license()`, con un candado a nivel de módulo.
- `vendor_tools/` (la herramienta de emisión de licencias) vive en este mismo
  repositorio, en `.gitignore`, nunca se empaqueta en el instalador.
- `APP_VERSION` deja de estar duplicado en `installer/build.py` e
  `installer/installer.py`; pasa a vivir una sola vez en `app/config.py`.
- **(2026-08-13, añadida después)** Las licencias `PERPETUAL` no vuelven a
  sincronizar con Firebase después de activarse, nunca: no tienen
  `expires_at` que vigilar, así que forzar una reconexión periódica solo
  metería una dependencia de internet que ese tipo de licencia existe para
  evitar. `evaluate_license()` corta el camino normal en cuanto ve
  `tier == "PERPETUAL"` en el caché ya verificado localmente (firma y huella
  del equipo siguen aplicando igual) y nunca llega a `_effective_now()`,
  `_sync_due()` ni `_try_online_sync()`. Una revocación ya grabada en el
  caché (`status_at_sync == "REVOKED"`) se sigue respetando —leer el archivo
  local no es "conectarse a Firebase"—. `activate_license()` no cambia: la
  primera activación sigue necesitando un contacto con Firebase.
- **(2026-08-19, añadida después)** La vigencia de una licencia con
  vencimiento empieza a contar desde que el cliente la **activa**, no desde
  que el vendedor la **genera**. `do_crear()` ya no calcula `expires_at`: solo
  guarda `duration_days` (cuántos días le corresponden). `expires_at` queda
  en `None` hasta la primera activación real, momento en el que
  `app/licensing.py::activate_license()` lo calcula
  (`server_time + duration_days`) y lo escribe en la misma petición que
  reclama el equipo (`claim_device`, ahora con un parámetro `expires_at`
  opcional). Una reactivación tras `unbind` (cambio de equipo) NO recalcula
  nada: `expires_at` ya quedó fijado la primera vez y `unbind` nunca lo
  toca, solo `device_id_hash`/`activated_at`. Licencias creadas ANTES de
  este cambio (con `expires_at` ya fijado desde su creación, sin
  `duration_days`) siguen funcionando exactamente igual: la condición que
  dispara el cálculo nuevo es específicamente `expires_at is None`, que una
  licencia vieja nunca tiene.

## Estado actual

**Fase: COMPLETO. Proyecto Firebase real creado y funcionando, verificación de
extremo a extremo hecha contra Firebase real y contra el instalador ya
compilado, instalador recompilado (45.6 MB).**

- [x] `app/device_id.py` — huella del equipo (MachineGuid + serie de disco +
      nombre de equipo). Probado: estable, cambia si cambia cualquier señal.
- [x] `app/licensing.py` — máquina de estados, caché local firmado (HMAC-SHA256 +
      pepper protegida con DPAPI cuando `pywin32` está disponible), hora de
      confianza con detección de reloj retrocedido, `license_gate()`. Probado: 17
      escenarios (los 11 estados + activación exitosa/fallida en cada variante).
- [x] `app/firebase_client.py` — envoltorio REST (Identity Toolkit + Firestore).
      Probado contra un servidor Flask simulado local (sign-in, fetch
      encontrada/inexistente/revocada, claim, error de conexión).
- [x] `app/views/licensing.py` — blueprint `/licencia` (activar, info, bloqueado).
      Verificado en el navegador: sin activar, ADMIN cae en `/licencia/activar`;
      probar activar con Firebase sin configurar da un mensaje de error limpio,
      sin traza.
- [x] `app/templates/licensing/*.html`
- [x] Entrada de menú «Información del software» en `base.html` (🪪, dentro del
      bloque ADMIN, con insignia opcional: «Prueba», «Sin conexión», «Vence
      pronto»).
- [x] `APP_VERSION` centralizado en `version.py` (raíz del repo, sin
      dependencias) — `app/config.py`, `installer/build.py` e
      `installer/installer.py` lo importan de ahí. Ya no hay literales duplicados.
- [x] `requirements.txt` con `requests` y `pywin32`. Instalados también en el
      entorno de desarrollo para poder probar de verdad (DPAPI round-trip
      confirmado con `win32crypt`).
- [x] `vendor_tools/licensing_cli.py` — CLI con `firebase-admin` + `click`:
      `create/renew/revoke/reactivate/unbind/inspect/list`. `.gitignore`
      actualizado (`vendor_tools/serviceAccountKey.json`). Probado: `--help`,
      generación de claves, error limpio sin la clave de cuenta de servicio.
      Falta la prueba real contra Firestore (necesita el proyecto).
- [x] Registrado en `app/__init__.py`: blueprint `licensing`, tercer
      `before_request` (`license_gate`, después de `verify_csrf`), insignia en
      `inject_globals()`.
- [x] Suites de prueba en el scratchpad: `test_licensing_states.py` (17
      comprobaciones, la máquina de estados completa), `test_licensing_gate.py`
      (el bloqueo HTTP real, sin el bypass — encontró y ayudó a corregir un bug
      real: la ruta `static` de Flask no pertenece a un blueprint, `"static"` en
      `_EXEMPT_BLUEPRINTS` nunca hacía nada), `test_device_fingerprint.py`.
      **Las 13 suites preexistentes del proyecto siguen pasando** gracias a
      `GYMLITE_SKIP_LICENSE=1` (interruptor solo para pruebas, ver más abajo).
- [x] Interruptor de pruebas `GYMLITE_SKIP_LICENSE=1`: ninguna suite de otra
      funcionalidad necesita activar una licencia falsa para poder probar lo suyo.
      El instalador y `gym_launcher.py` nunca lo definen, así que no existe en un
      equipo instalado de verdad.
- [x] Proyecto Firebase real creado con el usuario (cuenta
      darchencodev@gmail.com, proyecto «gestor de gym»): Firestore en modo
      producción, reglas de seguridad publicadas, Auth anónima activada (con
      limpieza automática de cuentas de más de 30 días, porque el cliente crea
      una sesión anónima nueva en cada sincronización), app web registrada para
      obtener el Web API key.
- [x] Verificación de extremo a extremo contra Firebase real:
      activar/revocar/reactivar/renovar/unbind vía `licensing_cli.py` contra
      Firestore real; activación real desde `app/licensing.py` (estado VALID,
      tier y fecha correctos); las reglas de seguridad SÍ rechazan reclamar un
      equipo distinto (HTTP 403 comprobado) y SÍ permiten reafirmar el mismo
      equipo; fetch de una clave inexistente da `None` limpio, no un error.
      Todas las licencias de prueba se eliminaron de Firestore al terminar.
- [x] Bug real encontrado y corregido durante esta verificación: las fechas de
      la licencia (activación, vencimiento, última validación) se guardan en
      ISO 8601 con zona horaria, pero el filtro `fechahora` de las plantillas
      espera el formato de texto sin zona que usa el resto de la app — se
      veían todas como «—». Se agregó `licensing.format_display()` y un filtro
      Jinja aparte, `fecha_licencia`, en vez de forzarlas al formato viejo.
      Verificado en el navegador antes y después del arreglo.
- [x] Instalador recompilado (45.6 MB) con `requests` y `pywin32` integrados —
      primera vez que se usan en este proyecto, así que se verificó
      explícitamente contra el `.exe` compilado (no solo el código fuente):
      activación real contra Firebase desde el binario compilado (funcionó), y
      `license_key.bin` confirmado como un blob real de DPAPI (encabezado
      `01000000d08c9ddf0115d1118c7a00c0`, la firma estándar de
      `CryptProtectData`) — no cayó al respaldo de archivo plano.

### Detalles que quien retome esto debería saber

- La licencia vive en `INSTANCE_DIR/license.dat` + `license_key.bin`, NUNCA en
  `gym.db` (ver el porqué en el docstring de `app/licensing.py`).
- `evaluate_license()` distingue `VALID` (nada indica un problema) de
  `OFFLINE_GRACE` (el último intento de sincronizar SÍ falló por comunicación,
  pero sigue dentro de los 7 días de gracia) — no basta con "no tocaba
  sincronizar todavía" para mostrar «sin conexión»; eso sería alarmismo
  innecesario. El estado se recuerda en `_last_sync_ok` (memoria del proceso,
  se reinicia optimista en cada arranque).
- Decisión de diseño revisada durante la implementación: `PAUSED` vs `EXPIRED`
  en el kiosco de acceso (`app/views/access.py::_decide`) se dejó como estaba
  (cualquier inscripción pausada sin reanudar cuenta, sin importar si es la más
  reciente) — no es parte de licenciamiento, quedó documentado aparte en el
  código con la razón.
- `FIREBASE_PROJECT_ID` y `FIREBASE_WEB_API_KEY` siguen vacíos en
  `app/config.py`. Mientras estén vacíos, activar una licencia da un error de
  comunicación limpio (probado), y el resto del programa funciona con
  normalidad usando `GYMLITE_SKIP_LICENSE=1` en las pruebas.

## Datos de Firebase (no sensibles)

- Cuenta de Google del proyecto: darchencodev@gmail.com
- Nombre del proyecto: «gestor de gym»
- Project ID: `gestor-de-gym`
- Web API key: `AIzaSyD_09DfuWV58TTTUwzZojjLCqZfqj2_4j8` (público por diseño de
  Firebase — la protección real la dan las reglas de Firestore)
- Colección: `licenses`
- Plan: Spark (gratuito) — de sobra para el volumen esperado
- Ubicación de Firestore: nam5 (Estados Unidos) — se eligió la ubicación por
  defecto; si en el futuro conviene una más cercana a los clientes (ej. una
  región de Sudamérica) NO se puede cambiar sin recrear la base de datos
- **NUNCA anotar aquí**: el JSON de la cuenta de servicio, claves de licencia
  reales de clientes, el contenido de `license_key.bin`.

## Pendiente del usuario

Nada bloqueante. Todo lo de esta funcionalidad está terminado y verificado.
Pendientes solo para cuando haya clientes reales:

- Emitir licencias reales con `vendor_tools/licensing_cli.py create` a medida
  que se vendan (la clave de cuenta de servicio ya está en
  `vendor_tools/serviceAccountKey.json`, fuera del repositorio).
- Decidir precios y el canal de entrega de la clave al cliente (por ahora se
  asume que se la pasa el vendedor manualmente, por correo o WhatsApp, después
  del pago).
- Distribuir `dist/GymManagerLite-Setup.exe` (45.6 MB) a los clientes.

## Próximos pasos

Todos los pasos de construcción se completaron. Ideas para más adelante, no
urgentes:

- Suite de prueba automatizada para el flujo de renovación cerca del
  vencimiento (recordatorio dentro de la app, no solo la insignia del menú).
- Si `vendor_tools/licensing_cli.py` se usa mucho, agregar un comando
  `licensing_cli.py stats` con totales por tipo/estado.
- Revisar si conviene mover la ubicación de Firestore a una región más cercana
  a los clientes reales una vez se sepa dónde están concentrados (implica
  recrear la base de datos, así que mejor decidirlo temprano si se va a hacer).

## Registro

- 2026-08-12: plan aprobado (ver ruta arriba). Creado este archivo de contexto.
  Iniciando implementación de las partes que no dependen de un proyecto Firebase
  real todavía.
- 2026-08-12: implementadas y probadas todas las piezas que no requieren un
  proyecto Firebase real (ver «Estado actual»): huella del equipo, máquina de
  estados con caché local firmado, cliente REST de Firebase, blueprint y
  pantallas, entrada de menú, centralización de `APP_VERSION`, dependencias,
  registro en `app/__init__.py`, herramienta del vendedor, y las 16 suites de
  prueba (13 preexistentes siguen pasando + 3 nuevas). Verificado también en el
  navegador: el bloqueo redirige correctamente y el mensaje de error de Firebase
  sin configurar es limpio.
- 2026-08-12: creado el proyecto Firebase real con el usuario (Firestore,
  reglas de seguridad, Auth anónima con limpieza automática, app web para el
  Web API key). Rellenados `FIREBASE_PROJECT_ID`/`FIREBASE_WEB_API_KEY` en
  `app/config.py`. Descargada la clave de cuenta de servicio a
  `vendor_tools/serviceAccountKey.json` (con permiso explícito del usuario,
  dado que es un secreto real). Verificación de extremo a extremo completa
  contra Firebase real: emisión/revocación/renovación/unbind de licencias,
  activación real (VALID con datos correctos), reglas de seguridad
  confirmadas rechazando un equipo distinto y aceptando reafirmar el mismo.
  Encontrado y corregido un bug real en el camino: las fechas de la licencia
  no se mostraban (formato ISO 8601 vs. el formato de fecha del resto de la
  app) — arreglado con un filtro Jinja dedicado, verificado en el navegador.
  Instalador recompilado (45.6 MB) y verificado contra el binario compilado:
  activación real desde el `.exe` funcionó, y se confirmó que `pywin32`/DPAPI
  quedó realmente activo (no cayó al respaldo de archivo plano) inspeccionando
  la firma del blob cifrado. Todas las licencias de prueba se eliminaron de
  Firestore al terminar. **Funcionalidad completa.**
- 2026-08-13: pedido explícito del usuario: una licencia `PERPETUAL`, una vez
  activada, no debe volver a necesitar conexión a internet ni a Firebase para
  seguir validándose. Se agregó `_status_from_cache_perpetual()` en
  `app/licensing.py` y un atajo temprano en `evaluate_license()` (justo
  después de cargar y verificar el caché local, antes de cualquier cómputo de
  reloj de confianza o intento de sincronización) que, para `tier ==
  "PERPETUAL"`, devuelve `VALID` directamente sin pasar por
  `_effective_now()`, `_sync_due()` ni `_try_online_sync()` — código de red
  literalmente inalcanzable para ese tier, no una bandera que se salta. Se
  conserva el respeto a una revocación ya grabada en el caché local
  (`status_at_sync == "REVOKED"`) y las comprobaciones de manipulación/huella
  del equipo de `load_cache()`, que no dependen de la red. TRIAL/MONTHLY/
  ANNUAL no cambian. Se ajustó `app/templates/licensing/info.html` para que la
  fila "Última validación en línea" muestre "No aplica (licencia perpetua)" en
  vez de una fecha congelada para siempre. Verificado con scripts de humo
  (sin suite persistida en el repo, mismo patrón de sesiones anteriores):
  activación PERPETUAL simulada, sync forzado a "debido" sin que se llame a
  Firebase, caché envejecido 37+ días sin caer en `OFFLINE_GRACE_EXCEEDED`,
  revocación local respetada sin red, y comprobación de regresión de que
  MONTHLY sigue sincronizando con normalidad. Además, una prueba de
  integración HTTP completa (sin `GYMLITE_SKIP_LICENSE`) activando la
  licencia vía la vista real y navegando varias páginas con Firebase
  mockeado para fallar la prueba si se le llegaba a llamar.
- 2026-08-18: pedido del usuario: al renovar una licencia desde
  `vendor_tools/licensing_cli.py` / `licensing_gui.py`, también poder cambiar
  su tipo (tier) de paso. `do_renovar(key, months, years, tier=None)` ahora
  acepta un `tier` opcional: sin indicarlo, se comporta exactamente igual que
  antes (compatibilidad hacia atrás). Indicándolo, cambia el tipo — incluye
  convertir una PERPETUAL en una con vencimiento (usa "ahora" como base, ya
  que no tenía `expires_at` del que partir) y al revés (pasar cualquier tipo a
  PERPETUAL no pide meses/años, porque no hay vigencia que calcular). Cuando
  se cambia de un tipo con vencimiento a otro (p. ej. MONTHLY → ANNUAL), la
  nueva vigencia se sigue sumando sobre el vencimiento que ya tenía, no desde
  hoy — nunca se resta tiempo ya pagado. Renovar una PERPETUAL SIN indicar
  `tier` sigue bloqueado con el mismo aviso de siempre (nada que renovar).
  Encontré y corregí un bug propio durante la verificación: el orden de las
  comprobaciones hacía que "renovar sin --tier" en una licencia YA perpetua
  calculara igual `nuevo_tier="PERPETUAL"` y cayera en la rama de éxito en vez
  de avisar — se movió la comprobación de bloqueo antes de calcular
  `nuevo_tier`. CLI: nueva opción `--tier` en `renew`. GUI: el botón
  "Renovar…" ya no se deshabilita para licencias PERPETUAL, y el diálogo
  suma un combo de tipo que deshabilita los campos de meses/años cuando se
  elige "Perpetua". Verificado con Firestore simulado en memoria (7
  escenarios: comportamiento previo intacto, cambio de tipo conservando
  tiempo pagado, conversión a PERPETUAL sin duración, bloqueo de PERPETUAL
  sin --tier, conversión desde PERPETUAL, tier inválido, clave inexistente) y
  con la CLI real (`click.testing.CliRunner`) y la ventana de Tkinter
  instanciada de verdad (incluida la interacción con el combo del diálogo).
- 2026-08-19: pedido del usuario: la licencia debe empezar a regir desde que
  se **activa**, no desde que se **genera** (antes, una clave que tardara
  en llegarle al cliente ya perdía días de una prueba/mensualidad corta).
  Cambiado `do_crear()` (`vendor_tools/licensing_cli.py`) para guardar
  `duration_days` en vez de un `expires_at` fijo; `activate_license()`
  (`app/licensing.py`) calcula y fija `expires_at` en la primera activación
  real; `claim_device()` (`app/firebase_client.py`) gana un parámetro
  `expires_at` opcional para escribirlo en la misma petición que reclama el
  equipo (nunca una segunda escritura aparte, para no dejar una ventana con
  el equipo ya reclamado pero sin vencimiento). `do_renovar()`: renovar una
  licencia YA activada sigue extendiendo una fecha real, sin cambios;
  renovar una que TODAVÍA no se activó ahora suma los días a
  `duration_days` en vez de fijar una fecha antes de tiempo (rompería el
  cambio si no). Nueva función compartida `vigencia_text()` en
  `licensing_cli.py`, usada por la CLI y por `licensing_gui.py`, para
  mostrar correctamente los tres casos ("vence el...", "No vence"
  perpetua, "Sin activar (N día(s) desde que se active)"). Verificado con
  Firestore simulado en memoria: creación sin `expires_at`, primera
  activación calculándolo correctamente (diferencia de 0.00s contra lo
  esperado), reactivación tras `unbind` sin recalcularlo, renovación antes y
  después de activar, PERPETUAL sin tocar, y **compatibilidad hacia atrás
  con licencias creadas antes de este cambio** (con `expires_at` ya fijado
  y sin `duration_days`) — se activan exactamente igual que siempre, sin
  recalcular nada. También se re-verificaron las pruebas de humo anteriores
  de esta sesión (PERPETUAL, renovar+cambiar tipo) para confirmar que
  siguen pasando sin regresión.
