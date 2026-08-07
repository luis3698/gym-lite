-- Esquema de GymManager Lite (SQLite).
--
-- Diferencias respecto a la versión original, por diseño:
--   * La biometría no vive en `clients` sino en su propia tabla (`client_faces`):
--     una persona puede tener varias muestras de rostro, y borrarlas no toca su ficha.
--   * Los clientes son fichas de registro: no tienen contraseña ni acceso propio,
--     así que tampoco failed_attempts ni locked_until.
--
-- Las fechas se guardan como texto:
--   * fechas puras       -> 'YYYY-MM-DD'          (vigencias, publicaciones)
--   * fechas con hora    -> 'YYYY-MM-DD HH:MM:SS' (creación, auditoría)
-- Es el formato que SQLite ordena y compara correctamente como texto.

PRAGMA foreign_keys = ON;

-- Personal del sistema. Es el único tipo de cuenta que puede iniciar sesión.
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL,
    role            TEXT    NOT NULL CHECK (role IN ('ADMIN', 'CAJA', 'ENTRENADOR')),
    first_name      TEXT    NOT NULL,
    last_name       TEXT    NOT NULL,
    document_id     TEXT    NOT NULL UNIQUE,
    sex             TEXT,
    age             INTEGER CHECK (age IS NULL OR (age >= 0 AND age <= 120)),
    phone           TEXT,
    email           TEXT    NOT NULL UNIQUE,
    blood_type      TEXT,
    photo           TEXT,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

-- Clientes del gimnasio: ficha administrativa, sin credenciales.
-- email admite NULL y es UNIQUE: SQLite permite varios NULL en una columna UNIQUE,
-- así que varios clientes pueden quedarse sin correo sin chocar entre sí.
-- Los campos a partir de `blood_type` son la ficha deportiva: todos opcionales.
-- Un gimnasio los rellena con el tiempo, no en el mostrador el primer día, así que
-- ninguno puede bloquear el alta.
CREATE TABLE IF NOT EXISTS clients (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name              TEXT    NOT NULL,
    last_name               TEXT    NOT NULL,
    document_id             TEXT    NOT NULL UNIQUE,
    sex                     TEXT,
    age                     INTEGER CHECK (age IS NULL OR (age >= 0 AND age <= 120)),
    phone                   TEXT,
    email                   TEXT    UNIQUE,
    emergency_contact_name  TEXT,
    emergency_contact_phone TEXT,
    photo                   TEXT,
    blood_type              TEXT,
    height_cm               REAL,
    weight_kg               REAL,
    goal                    TEXT,
    activity_level          TEXT,
    medical_conditions      TEXT,
    allergies               TEXT,
    health_insurance        TEXT,
    notes                   TEXT,
    -- Perímetros corporales en centímetros. Se guardan en la ficha (no en una tabla
    -- de históricos) porque lo que se consulta a diario es la última medida; para
    -- seguir la evolución en el tiempo haría falta una tabla aparte.
    m_neck                  REAL,
    m_shoulders             REAL,
    m_chest                 REAL,
    m_biceps_relaxed        REAL,
    m_biceps_flexed         REAL,
    m_forearm               REAL,
    m_waist                 REAL,
    m_hip                   REAL,
    m_thigh_upper           REAL,
    m_thigh_mid             REAL,
    m_calf                  REAL,
    created_at              TEXT    NOT NULL,
    updated_at              TEXT    NOT NULL
);

-- Tarifas de inscripción por duración.
CREATE TABLE IF NOT EXISTS inscription_tariffs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    duration TEXT    NOT NULL UNIQUE CHECK (duration IN ('DAY_1', 'DAY_7', 'DAY_15', 'MONTH')),
    price    REAL    NOT NULL CHECK (price > 0)
);

-- Valor de cada mes adicional cuando la inscripción es de varios meses.
-- El CHECK sobre id fuerza que exista como máximo una fila.
CREATE TABLE IF NOT EXISTS extra_month_tariff (
    id    INTEGER PRIMARY KEY CHECK (id = 1),
    price REAL NOT NULL CHECK (price > 0)
);

-- Servicios complementarios (casillero, clases grupales, etc.).
CREATE TABLE IF NOT EXISTS services (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT    NOT NULL UNIQUE,
    price  REAL    NOT NULL CHECK (price > 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

-- Inscripción de gimnasio (mensualidad).
-- `quantity` es cuántas veces se compró la duración elegida: 3 días, 2 semanas,
-- 6 meses. Se llamaba `months` cuando solo las mensualidades admitían cantidad.
--
-- Pausa: al pausar se guarda el día (`paused_at`) y los días que le quedaban
-- (`paused_days`). Al reanudar, el vencimiento se recalcula desde ese día con los
-- días guardados. No se toca `end_date` mientras está pausada, así que si alguien
-- deshace la pausa el mismo día todo queda exactamente como estaba.
--
-- `is_migrated` marca las inscripciones cargadas desde «Migración de datos»: existían
-- antes del programa y no representan un cobro, así que no cuentan como ingreso.
CREATE TABLE IF NOT EXISTS memberships (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id      INTEGER NOT NULL REFERENCES clients(id),
    sold_by_id     INTEGER NOT NULL REFERENCES users(id),
    duration_type  TEXT    NOT NULL CHECK (duration_type IN ('DAY_1', 'DAY_7', 'DAY_15', 'MONTH')),
    quantity       INTEGER,
    start_date     TEXT    NOT NULL,
    end_date       TEXT    NOT NULL,
    base_price     REAL    NOT NULL,
    services_total REAL    NOT NULL DEFAULT 0,
    total          REAL    NOT NULL,
    payment_method TEXT    NOT NULL DEFAULT 'EFECTIVO',
    paused_at      TEXT,
    paused_days    INTEGER,
    is_migrated    INTEGER NOT NULL DEFAULT 0 CHECK (is_migrated IN (0, 1)),
    created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS membership_services (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    membership_id INTEGER NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
    service_id    INTEGER NOT NULL REFERENCES services(id),
    price         REAL    NOT NULL
);

-- Catálogo de productos. Eliminar un producto lo marca inactivo (active = 0) para no
-- romper el histórico de ventas que lo referencia.
CREATE TABLE IF NOT EXISTS products (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    price      REAL    NOT NULL CHECK (price > 0),
    stock      INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    category   TEXT,
    image      TEXT,
    active     INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id      INTEGER NOT NULL REFERENCES users(id),
    client_id      INTEGER REFERENCES clients(id),
    buyer_document TEXT    NOT NULL,
    buyer_name     TEXT    NOT NULL,
    buyer_phone    TEXT,
    total          REAL    NOT NULL,
    payment_method TEXT    NOT NULL DEFAULT 'EFECTIVO',
    created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sale_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id    INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price REAL    NOT NULL
);

-- Registro de actividad. user_id admite NULL para los intentos de inicio de sesión
-- contra una cuenta que no existe.
CREATE TABLE IF NOT EXISTS audit_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action     TEXT    NOT NULL,
    detail     TEXT,
    success    INTEGER NOT NULL DEFAULT 1 CHECK (success IN (0, 1)),
    created_at TEXT    NOT NULL
);

-- Ajustes que el administrador puede cambiar desde la aplicación, en formato
-- clave/valor: son pocos y no merecen una columna cada uno. Los valores se guardan
-- como texto ('1'/'0' para los interruptores) y siempre se leen con un valor por
-- defecto, así que una clave que falte nunca rompe nada.
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Índices corporales que se calculan en la ficha del cliente (IMC, % de grasa…).
-- La fórmula de cada uno vive en el código, no aquí: una fórmula escrita a mano en la
-- base daría datos de salud erróneos sin que nada avisara. Lo configurable es cuáles
-- se muestran y, sobre todo, cómo se interpretan (tabla `index_ranges`).
CREATE TABLE IF NOT EXISTS body_indexes (
    code       TEXT    PRIMARY KEY,
    name       TEXT    NOT NULL,
    enabled    INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0
);

-- La matriz de interpretación: qué etiqueta le corresponde a cada valor.
--
-- `sex` y las edades permiten filas distintas para hombres y mujeres o por franja de
-- edad; en NULL, la fila vale para cualquiera. Al clasificar gana la fila más
-- específica, de modo que se puede tener un rango general y excepciones encima sin
-- tener que repetir toda la tabla.
--
-- `min_value` en NULL significa «sin límite por abajo» y `max_value` en NULL, «sin
-- límite por arriba». El intervalo es [min, max): así dos filas consecutivas encajan
-- sin dejar huecos ni solaparse en el punto de corte.
CREATE TABLE IF NOT EXISTS index_ranges (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    index_code TEXT    NOT NULL REFERENCES body_indexes(code) ON DELETE CASCADE,
    sex        TEXT,
    age_min    INTEGER,
    age_max    INTEGER,
    min_value  REAL,
    max_value  REAL,
    label      TEXT    NOT NULL,
    severity   TEXT    NOT NULL DEFAULT 'ok' CHECK (severity IN ('ok', 'warn', 'bad')),
    sort_order INTEGER NOT NULL DEFAULT 0
);

-- Rostros registrados para el kiosco de acceso.
--
-- Se admiten VARIAS muestras por cliente (con gafas y sin ellas, otra luz, otro
-- peinado) y el emparejamiento se queda con la más parecida: es la forma barata de
-- bajar los falsos negativos sin tocar el umbral, que si se afloja empieza a
-- confundir a hermanos entre sí.
--
-- `descriptor` es el vector de 128 números en coma flotante que produce face-api,
-- serializado como un array JSON. No es una foto ni permite reconstruir el rostro.
CREATE TABLE IF NOT EXISTS client_faces (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id  INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    descriptor TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

-- Paso por el kiosco de acceso: es a la vez el histórico de asistencia y lo que
-- permite no volver a saludar a la misma persona mientras sigue delante de la cámara.
--
-- Se registran también los intentos denegados (inscripción vencida, sin inscripción)
-- porque son justo los que el gimnasio necesita revisar después.
-- client_id admite NULL: un rostro no reconocido no corresponde a ningún cliente.
CREATE TABLE IF NOT EXISTS access_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id  INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    allowed    INTEGER NOT NULL CHECK (allowed IN (0, 1)),
    reason     TEXT    NOT NULL CHECK (reason IN ('ACTIVE', 'EXPIRED', 'PAUSED', 'NO_MEMBERSHIP', 'UNKNOWN')),
    -- Distancia euclídea con la muestra que ganó (0 = idéntico). Guardarla permite
    -- afinar el umbral con datos reales en vez de a ojo.
    distance   REAL,
    created_at TEXT    NOT NULL
);

-- Índices para las consultas que más se repiten (tableros y listados con filtro).
CREATE INDEX IF NOT EXISTS idx_memberships_client   ON memberships(client_id);
CREATE INDEX IF NOT EXISTS idx_memberships_end      ON memberships(end_date);
CREATE INDEX IF NOT EXISTS idx_memberships_created  ON memberships(created_at);
CREATE INDEX IF NOT EXISTS idx_sale_items_sale      ON sale_items(sale_id);
CREATE INDEX IF NOT EXISTS idx_sales_created        ON sales(created_at);
CREATE INDEX IF NOT EXISTS idx_clients_document     ON clients(document_id);
CREATE INDEX IF NOT EXISTS idx_clients_created      ON clients(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_created        ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_user           ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_client_faces_client  ON client_faces(client_id);
CREATE INDEX IF NOT EXISTS idx_index_ranges_code    ON index_ranges(index_code, sort_order);
CREATE INDEX IF NOT EXISTS idx_access_logs_created  ON access_logs(created_at);
-- El antirrebote busca «último paso de este cliente», así que ordena por fecha
-- dentro de un cliente concreto: el índice compuesto lo resuelve sin recorrer nada.
CREATE INDEX IF NOT EXISTS idx_access_logs_client   ON access_logs(client_id, created_at);
