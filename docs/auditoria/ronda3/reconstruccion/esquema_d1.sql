-- =====================================================================
-- Esquema D1 (SQLite) MÍNIMO para una reconstrucción nativa de D'CASA
-- Autor: r3-reconstruccion (auditoría ronda 3) · 2026-10-01
-- ESTADO: DISEÑO DE REFERENCIA. No es la app; no se ha desplegado nada.
-- Validado en SQLite (python3 + sqlite3, base en memoria) con
-- docs/auditoria/ronda3/reconstruccion/validar_esquema.py
--
-- Principios
--  * Dinero en CENTAVOS ENTEROS (INTEGER). Nunca REAL para importes.
--  * Cantidades de inventario en milésimas (INTEGER, qty_mil = 1000 = 1 und).
--  * Fechas ISO-8601 en TEXT; 'fecha' contable = día de Panamá (UTC-5).
--  * Libros (contable, puntos, stock) son SOLO-ANEXAR: triggers impiden
--    UPDATE/DELETE de lo publicado. Correcciones = asiento contrario.
--  * Sin columnas de saldo: saldo = SUM(lineas) (regla 2 de socios, y la
--    misma idea para cuentas contables y existencias).
--  * Idempotencia: toda escritura que viene de fuera (web, Brian, cola,
--    reintento) lleva 'clave_idem' UNIQUE.
--  * D1 no tiene transacciones interactivas: cada operación de negocio se
--    manda como UN batch() (atómico) o se serializa en un Durable Object
--    "Libro". Los triggers son la última defensa si el código se equivoca.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 0. Configuración, usuarios e idempotencia
-- ---------------------------------------------------------------------
CREATE TABLE config (
  clave TEXT PRIMARY KEY,
  valor TEXT NOT NULL
);
-- Claves usadas: 'fecha_bloqueo' (YYYY-MM-DD; nada con fecha <= se publica),
-- 'moneda'='USD', 'ruc', 'dv', 'whatsapp', 'puntos_version'.

CREATE TABLE usuario (
  id         INTEGER PRIMARY KEY,
  nombre     TEXT NOT NULL,
  correo     TEXT UNIQUE,
  rol        TEXT NOT NULL CHECK (rol IN ('admin','gerencia','contador','vendedora','bodega')),
  activo     INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1)),
  creado_en  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE idempotencia (
  clave_idem  TEXT PRIMARY KEY,
  operacion   TEXT NOT NULL,
  resultado   TEXT,               -- JSON con ids creados
  creado_en   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE auditoria (            -- quién hizo qué (incluye Brian)
  id          INTEGER PRIMARY KEY,
  usuario_id  INTEGER REFERENCES usuario(id),
  canal       TEXT NOT NULL CHECK (canal IN ('panel','web','brian','telegram','cola','sistema')),
  accion      TEXT NOT NULL,
  entidad     TEXT NOT NULL,
  entidad_id  INTEGER,
  detalle     TEXT,               -- JSON
  creado_en   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TRIGGER auditoria_sin_update BEFORE UPDATE ON auditoria
BEGIN SELECT RAISE(ABORT, 'auditoria es solo-anexar'); END;
CREATE TRIGGER auditoria_sin_delete BEFORE DELETE ON auditoria
BEGIN SELECT RAISE(ABORT, 'auditoria es solo-anexar'); END;

-- ---------------------------------------------------------------------
-- 1. Terceros (cliente = socio = proveedor: una sola ficha, llave celular)
-- ---------------------------------------------------------------------
CREATE TABLE tercero (
  id              INTEGER PRIMARY KEY,
  nombre          TEXT NOT NULL,
  tipo_persona    TEXT NOT NULL DEFAULT 'natural' CHECK (tipo_persona IN ('natural','juridica')),
  ruc             TEXT,
  dv              TEXT,
  celular_digitos TEXT UNIQUE,      -- llave del socio (regla 5), solo dígitos con 507
  correo          TEXT,
  direccion       TEXT,
  es_cliente      INTEGER NOT NULL DEFAULT 1 CHECK (es_cliente IN (0,1)),
  es_proveedor    INTEGER NOT NULL DEFAULT 0 CHECK (es_proveedor IN (0,1)),
  -- Socios
  socio_codigo    TEXT UNIQUE,      -- DCA...
  padrino_id      INTEGER REFERENCES tercero(id),
  socio_estado    TEXT CHECK (socio_estado IN ('activo','suspendido')),
  pin_hash        TEXT,             -- hash(PIN + DCASA_PIN_PEPPER); la pimienta NO vive aquí
  pin_fallos      INTEGER NOT NULL DEFAULT 0,
  pin_bloqueo_hasta TEXT,
  cumple_mmdd     TEXT,
  creado_en       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  CHECK (padrino_id IS NULL OR padrino_id <> id)
);
-- Regla 4: el padrino se escribe UNA vez.
CREATE TRIGGER tercero_padrino_una_vez BEFORE UPDATE OF padrino_id ON tercero
WHEN OLD.padrino_id IS NOT NULL AND (NEW.padrino_id IS NULL OR NEW.padrino_id <> OLD.padrino_id)
BEGIN SELECT RAISE(ABORT, 'el padrino ya fue asignado y no se cambia'); END;

-- ---------------------------------------------------------------------
-- 2. Núcleo contable (doble partida)
-- ---------------------------------------------------------------------
CREATE TABLE cuenta (
  id          INTEGER PRIMARY KEY,
  codigo      TEXT NOT NULL UNIQUE,        -- plan l10n_pa (se importa del de Odoo)
  nombre      TEXT NOT NULL,
  tipo        TEXT NOT NULL CHECK (tipo IN (
                'activo_corriente','banco','por_cobrar','inventario','activo_fijo',
                'pasivo_corriente','por_pagar','impuesto_por_pagar','patrimonio',
                'ingreso','costo_venta','gasto','otro_ingreso','otro_gasto')),
  conciliable INTEGER NOT NULL DEFAULT 0 CHECK (conciliable IN (0,1)),
  activa      INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0,1))
);

CREATE TABLE diario (
  id            INTEGER PRIMARY KEY,
  codigo        TEXT NOT NULL UNIQUE,     -- VEN, COM, BNK1, CAJA, YAPPY, MISC
  nombre        TEXT NOT NULL,
  tipo          TEXT NOT NULL CHECK (tipo IN ('venta','compra','banco','efectivo','general')),
  cuenta_defecto_id INTEGER REFERENCES cuenta(id),
  prefijo       TEXT NOT NULL,            -- 'INV/2026/'
  siguiente_num INTEGER NOT NULL DEFAULT 1 -- se consume dentro del batch de publicación
);

CREATE TABLE impuesto (
  id           INTEGER PRIMARY KEY,
  nombre       TEXT NOT NULL UNIQUE,      -- 'ITBMS 7%', 'ITBMS 0%', 'Exento'
  tasa_pb      INTEGER NOT NULL CHECK (tasa_pb >= 0),   -- puntos básicos: 700 = 7 %
  uso          TEXT NOT NULL CHECK (uso IN ('venta','compra')),
  precio_incluye INTEGER NOT NULL DEFAULT 0 CHECK (precio_incluye IN (0,1)), -- decisión E-01 pendiente
  cuenta_id    INTEGER NOT NULL REFERENCES cuenta(id),  -- ITBMS por pagar / por acreditar
  codigo_dgi   TEXT                                       -- código de tasa para la FE (por confirmar con PAC)
);

CREATE TABLE asiento (
  id           INTEGER PRIMARY KEY,
  diario_id    INTEGER NOT NULL REFERENCES diario(id),
  numero       TEXT,                       -- se asigna al publicar
  fecha        TEXT NOT NULL,              -- YYYY-MM-DD
  referencia   TEXT,
  estado       TEXT NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador','publicado')),
  reversa_de   INTEGER REFERENCES asiento(id),
  motivo       TEXT,                       -- obligatorio en reversas
  origen       TEXT,                       -- 'documento','pago','stock','ajuste','apertura'
  origen_id    INTEGER,
  clave_idem   TEXT UNIQUE,
  creado_por   INTEGER REFERENCES usuario(id),
  publicado_en TEXT,
  UNIQUE (diario_id, numero),
  CHECK (reversa_de IS NULL OR motivo IS NOT NULL)
);
CREATE INDEX asiento_fecha ON asiento(fecha, estado);

CREATE TABLE linea_asiento (
  id           INTEGER PRIMARY KEY,
  asiento_id   INTEGER NOT NULL REFERENCES asiento(id),
  cuenta_id    INTEGER NOT NULL REFERENCES cuenta(id),
  tercero_id   INTEGER REFERENCES tercero(id),
  descripcion  TEXT,
  debe_c       INTEGER NOT NULL DEFAULT 0 CHECK (debe_c >= 0),
  haber_c      INTEGER NOT NULL DEFAULT 0 CHECK (haber_c >= 0),
  impuesto_id  INTEGER REFERENCES impuesto(id),   -- línea de impuesto
  base_c       INTEGER,                           -- base imponible (para el resumen de ITBMS)
  analitica    TEXT,                              -- 'tienda' | 'web'
  vence        TEXT,                              -- para por cobrar / por pagar
  CHECK ((debe_c = 0) <> (haber_c = 0))           -- exactamente uno de los dos > 0
);
CREATE INDEX linea_cuenta ON linea_asiento(cuenta_id);
CREATE INDEX linea_tercero ON linea_asiento(tercero_id, cuenta_id);
CREATE INDEX linea_asiento_idx ON linea_asiento(asiento_id);

-- Inmutabilidad de lo publicado
CREATE TRIGGER linea_no_insert_publicado BEFORE INSERT ON linea_asiento
WHEN (SELECT estado FROM asiento WHERE id = NEW.asiento_id) = 'publicado'
BEGIN SELECT RAISE(ABORT, 'asiento publicado: no se agregan lineas'); END;
CREATE TRIGGER linea_no_update_publicado BEFORE UPDATE ON linea_asiento
WHEN (SELECT estado FROM asiento WHERE id = OLD.asiento_id) = 'publicado'
BEGIN SELECT RAISE(ABORT, 'asiento publicado: lineas inmutables'); END;
CREATE TRIGGER linea_no_delete_publicado BEFORE DELETE ON linea_asiento
WHEN (SELECT estado FROM asiento WHERE id = OLD.asiento_id) = 'publicado'
BEGIN SELECT RAISE(ABORT, 'asiento publicado: lineas inmutables'); END;
CREATE TRIGGER asiento_no_delete_publicado BEFORE DELETE ON asiento
WHEN OLD.estado = 'publicado'
BEGIN SELECT RAISE(ABORT, 'asiento publicado: se corrige con asiento contrario'); END;
CREATE TRIGGER asiento_no_despublicar BEFORE UPDATE ON asiento
WHEN OLD.estado = 'publicado'
BEGIN SELECT RAISE(ABORT, 'asiento publicado: inmutable'); END;

-- Publicar = cuadrar + no estar en periodo bloqueado + tener al menos 2 líneas
CREATE TRIGGER asiento_publicar_valida BEFORE UPDATE OF estado ON asiento
WHEN OLD.estado = 'borrador' AND NEW.estado = 'publicado'
BEGIN
  SELECT RAISE(ABORT, 'asiento descuadrado')
   WHERE (SELECT COALESCE(SUM(debe_c),0) - COALESCE(SUM(haber_c),0)
            FROM linea_asiento WHERE asiento_id = NEW.id) <> 0;
  SELECT RAISE(ABORT, 'asiento sin lineas suficientes')
   WHERE (SELECT COUNT(*) FROM linea_asiento WHERE asiento_id = NEW.id) < 2;
  SELECT RAISE(ABORT, 'periodo bloqueado')
   WHERE NEW.fecha <= COALESCE((SELECT valor FROM config WHERE clave = 'fecha_bloqueo'), '0000-00-00');
  SELECT RAISE(ABORT, 'falta numero')
   WHERE NEW.numero IS NULL;
END;

-- Conciliación (parcial o total) entre una línea deudora y una acreedora
-- de la MISMA cuenta conciliable (factura <-> pago, pago <-> extracto)
CREATE TABLE conciliacion (
  id              INTEGER PRIMARY KEY,
  linea_debe_id   INTEGER NOT NULL REFERENCES linea_asiento(id),
  linea_haber_id  INTEGER NOT NULL REFERENCES linea_asiento(id),
  monto_c         INTEGER NOT NULL CHECK (monto_c > 0),
  fecha           TEXT NOT NULL,
  deshecha_por    INTEGER REFERENCES conciliacion(id),   -- deshacer = registro nuevo, no borrar
  creado_por      INTEGER REFERENCES usuario(id),
  CHECK (linea_debe_id <> linea_haber_id)
);
CREATE INDEX conc_debe ON conciliacion(linea_debe_id);
CREATE INDEX conc_haber ON conciliacion(linea_haber_id);
CREATE TRIGGER conciliacion_misma_cuenta BEFORE INSERT ON conciliacion
BEGIN
  SELECT RAISE(ABORT, 'conciliacion entre cuentas distintas o no conciliables')
   WHERE (SELECT cuenta_id FROM linea_asiento WHERE id = NEW.linea_debe_id)
      <> (SELECT cuenta_id FROM linea_asiento WHERE id = NEW.linea_haber_id)
      OR (SELECT c.conciliable FROM cuenta c JOIN linea_asiento l ON l.cuenta_id = c.id
           WHERE l.id = NEW.linea_debe_id) = 0;
  SELECT RAISE(ABORT, 'conciliacion excede el saldo abierto de la linea deudora')
   WHERE NEW.monto_c > (SELECT l.debe_c FROM linea_asiento l WHERE l.id = NEW.linea_debe_id)
        - COALESCE((SELECT SUM(monto_c) FROM conciliacion
                     WHERE linea_debe_id = NEW.linea_debe_id AND deshecha_por IS NULL), 0);
  SELECT RAISE(ABORT, 'conciliacion excede el saldo abierto de la linea acreedora')
   WHERE NEW.monto_c > (SELECT l.haber_c FROM linea_asiento l WHERE l.id = NEW.linea_haber_id)
        - COALESCE((SELECT SUM(monto_c) FROM conciliacion
                     WHERE linea_haber_id = NEW.linea_haber_id AND deshecha_por IS NULL), 0);
END;

-- Extractos bancarios (importados de CSV de Banco General, BAC, Yappy…)
CREATE TABLE extracto_linea (
  id           INTEGER PRIMARY KEY,
  diario_id    INTEGER NOT NULL REFERENCES diario(id),
  fecha        TEXT NOT NULL,
  descripcion  TEXT NOT NULL,
  referencia   TEXT,
  monto_c      INTEGER NOT NULL,           -- + entra, - sale
  huella       TEXT NOT NULL,              -- hash(fecha|monto|desc|ref|ordinal del archivo): evita C-08
  asiento_id   INTEGER REFERENCES asiento(id),
  UNIQUE (diario_id, huella)
);

-- Documentos comerciales (factura, nota de crédito, factura de proveedor)
CREATE TABLE documento (
  id            INTEGER PRIMARY KEY,
  tipo          TEXT NOT NULL CHECK (tipo IN ('factura','nota_credito','factura_proveedor','nc_proveedor')),
  tercero_id    INTEGER NOT NULL REFERENCES tercero(id),
  fecha         TEXT NOT NULL,
  vence         TEXT,
  venta_id      INTEGER REFERENCES venta(id),
  origen_doc_id INTEGER REFERENCES documento(id),   -- NC -> factura que corrige
  motivo        TEXT,
  estado        TEXT NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador','publicado')),
  asiento_id    INTEGER UNIQUE REFERENCES asiento(id),
  subtotal_c    INTEGER NOT NULL DEFAULT 0,
  impuesto_c    INTEGER NOT NULL DEFAULT 0,
  total_c       INTEGER NOT NULL DEFAULT 0,
  -- Factura electrónica DGI (SFEP) vía PAC: se llena con la respuesta del PAC
  fe_estado     TEXT NOT NULL DEFAULT 'no_aplica'
                CHECK (fe_estado IN ('no_aplica','pendiente','enviada','autorizada','rechazada','anulada')),
  fe_cufe       TEXT UNIQUE,
  fe_qr         TEXT,
  fe_protocolo  TEXT,
  fe_xml_r2     TEXT,                       -- clave del XML firmado en R2
  fe_pdf_r2     TEXT,                       -- clave del CAFE/PDF en R2
  clave_idem    TEXT UNIQUE,
  CHECK (tipo NOT IN ('nota_credito','nc_proveedor') OR (origen_doc_id IS NOT NULL AND motivo IS NOT NULL)),
  CHECK (total_c = subtotal_c + impuesto_c)
);
CREATE TRIGGER documento_publicado_inmutable BEFORE UPDATE ON documento
WHEN OLD.estado = 'publicado' AND (
     NEW.total_c <> OLD.total_c OR NEW.tercero_id <> OLD.tercero_id OR NEW.fecha <> OLD.fecha
  OR NEW.estado <> OLD.estado OR NEW.subtotal_c <> OLD.subtotal_c OR NEW.impuesto_c <> OLD.impuesto_c)
BEGIN SELECT RAISE(ABORT, 'documento publicado: se corrige con nota de credito'); END;
CREATE TRIGGER documento_no_delete_publicado BEFORE DELETE ON documento
WHEN OLD.estado = 'publicado'
BEGIN SELECT RAISE(ABORT, 'documento publicado: no se borra'); END;

CREATE TABLE documento_linea (
  id            INTEGER PRIMARY KEY,
  documento_id  INTEGER NOT NULL REFERENCES documento(id),
  variante_id   INTEGER REFERENCES variante(id),
  descripcion   TEXT NOT NULL,
  cantidad_mil  INTEGER NOT NULL CHECK (cantidad_mil > 0),
  precio_unit_c INTEGER NOT NULL CHECK (precio_unit_c >= 0),  -- sin ITBMS
  descuento_pb  INTEGER NOT NULL DEFAULT 0 CHECK (descuento_pb BETWEEN 0 AND 10000),
  impuesto_id   INTEGER REFERENCES impuesto(id),
  subtotal_c    INTEGER NOT NULL,          -- calculado por el código y guardado (lo que se imprimió)
  impuesto_c    INTEGER NOT NULL,          -- ITBMS POR LÍNEA (SFEP lo pide por ítem; ver C-01/E-01)
  cuenta_id     INTEGER NOT NULL REFERENCES cuenta(id)
);
CREATE INDEX docl_doc ON documento_linea(documento_id);

CREATE TABLE pago (
  id           INTEGER PRIMARY KEY,
  tipo         TEXT NOT NULL CHECK (tipo IN ('cobro','pago')),
  tercero_id   INTEGER NOT NULL REFERENCES tercero(id),
  diario_id    INTEGER NOT NULL REFERENCES diario(id),
  metodo       TEXT NOT NULL CHECK (metodo IN ('efectivo','tarjeta','yappy','transferencia','cheque')),
  fecha        TEXT NOT NULL,
  monto_c      INTEGER NOT NULL CHECK (monto_c > 0),
  cheque_num   TEXT,
  asiento_id   INTEGER UNIQUE REFERENCES asiento(id),
  clave_idem   TEXT UNIQUE
);

-- Presupuestos (gerencia)
CREATE TABLE presupuesto (
  id        INTEGER PRIMARY KEY,
  nombre    TEXT NOT NULL,
  desde     TEXT NOT NULL,
  hasta     TEXT NOT NULL,
  CHECK (desde <= hasta)
);
CREATE TABLE presupuesto_linea (
  id             INTEGER PRIMARY KEY,
  presupuesto_id INTEGER NOT NULL REFERENCES presupuesto(id),
  cuenta_id      INTEGER NOT NULL REFERENCES cuenta(id),
  analitica      TEXT,
  planeado_c     INTEGER NOT NULL
);

-- Vistas contables (todo sale de lo publicado)
CREATE VIEW v_mayor AS
SELECT l.cuenta_id, a.fecha, a.diario_id, a.numero, l.tercero_id, l.debe_c, l.haber_c, l.analitica
  FROM linea_asiento l JOIN asiento a ON a.id = l.asiento_id
 WHERE a.estado = 'publicado';

CREATE VIEW v_balance_comprobacion AS
SELECT c.codigo, c.nombre, c.tipo,
       COALESCE(SUM(m.debe_c),0) AS debe_c, COALESCE(SUM(m.haber_c),0) AS haber_c,
       COALESCE(SUM(m.debe_c),0) - COALESCE(SUM(m.haber_c),0) AS saldo_c
  FROM cuenta c LEFT JOIN v_mayor m ON m.cuenta_id = c.id
 GROUP BY c.id;

CREATE VIEW v_itbms AS            -- resumen de ITBMS (débito - crédito fiscal)
SELECT i.nombre, a.fecha, SUM(l.base_c) AS base_c, SUM(l.haber_c) - SUM(l.debe_c) AS itbms_c
  FROM linea_asiento l JOIN asiento a ON a.id = l.asiento_id JOIN impuesto i ON i.id = l.impuesto_id
 WHERE a.estado = 'publicado'
 GROUP BY i.id, a.fecha;

CREATE VIEW v_abierto_por_linea AS   -- saldo pendiente por línea conciliable (antigüedad de saldos)
SELECT l.id AS linea_id, l.tercero_id, l.cuenta_id, l.vence,
       l.debe_c - COALESCE((SELECT SUM(monto_c) FROM conciliacion k WHERE k.linea_debe_id = l.id AND k.deshecha_por IS NULL),0) AS abierto_debe_c,
       l.haber_c - COALESCE((SELECT SUM(monto_c) FROM conciliacion k WHERE k.linea_haber_id = l.id AND k.deshecha_por IS NULL),0) AS abierto_haber_c
  FROM linea_asiento l JOIN cuenta c ON c.id = l.cuenta_id JOIN asiento a ON a.id = l.asiento_id
 WHERE c.conciliable = 1 AND a.estado = 'publicado';

-- ---------------------------------------------------------------------
-- 3. Catálogo, variantes y precios
-- ---------------------------------------------------------------------
CREATE TABLE categoria (
  id        INTEGER PRIMARY KEY,
  nombre    TEXT NOT NULL,
  slug      TEXT NOT NULL UNIQUE,
  padre_id  INTEGER REFERENCES categoria(id),
  orden     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE producto (                  -- plantilla
  id            INTEGER PRIMARY KEY,
  nombre        TEXT NOT NULL,
  slug          TEXT NOT NULL UNIQUE,
  categoria_id  INTEGER REFERENCES categoria(id),
  descripcion   TEXT,
  ficha         TEXT,                    -- JSON (medidas, materiales) — sin inventar contenido
  tipo          TEXT NOT NULL DEFAULT 'almacenable' CHECK (tipo IN ('almacenable','servicio','combo')),
  impuesto_venta_id  INTEGER REFERENCES impuesto(id),
  impuesto_compra_id INTEGER REFERENCES impuesto(id),
  publicado_web INTEGER NOT NULL DEFAULT 0 CHECK (publicado_web IN (0,1)),
  activo        INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1)),
  actualizado_en TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE atributo (
  id      INTEGER PRIMARY KEY,
  nombre  TEXT NOT NULL UNIQUE           -- 'Tamaño', 'Color'
);
CREATE TABLE atributo_valor (
  id          INTEGER PRIMARY KEY,
  atributo_id INTEGER NOT NULL REFERENCES atributo(id),
  valor       TEXT NOT NULL,             -- 'Queen', 'King'
  UNIQUE (atributo_id, valor)
);

CREATE TABLE variante (
  id           INTEGER PRIMARY KEY,
  producto_id  INTEGER NOT NULL REFERENCES producto(id),
  sku          TEXT NOT NULL UNIQUE,     -- '1062010735N', 'DSRSOQ'
  codigo_barras TEXT UNIQUE,
  precio_c     INTEGER NOT NULL CHECK (precio_c >= 0),   -- precio de lista (copiado del Excel, no calculado)
  activo       INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1))
);
CREATE TABLE variante_valor (
  variante_id       INTEGER NOT NULL REFERENCES variante(id),
  atributo_valor_id INTEGER NOT NULL REFERENCES atributo_valor(id),
  PRIMARY KEY (variante_id, atributo_valor_id)
);

CREATE TABLE combo_componente (          -- combo = varias variantes a un precio
  combo_variante_id      INTEGER NOT NULL REFERENCES variante(id),
  componente_variante_id INTEGER NOT NULL REFERENCES variante(id),
  cantidad_mil           INTEGER NOT NULL CHECK (cantidad_mil > 0),
  PRIMARY KEY (combo_variante_id, componente_variante_id),
  CHECK (combo_variante_id <> componente_variante_id)
);

CREATE TABLE imagen (                    -- binarios en R2, nunca en la base
  id          INTEGER PRIMARY KEY,
  producto_id INTEGER NOT NULL REFERENCES producto(id),
  variante_id INTEGER REFERENCES variante(id),
  r2_clave    TEXT NOT NULL UNIQUE,
  alt         TEXT NOT NULL,
  orden       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE lista_precio (
  id      INTEGER PRIMARY KEY,
  nombre  TEXT NOT NULL UNIQUE,           -- 'Público', 'Mayorista'
  desde   TEXT,
  hasta   TEXT
);
CREATE TABLE lista_precio_item (
  lista_id     INTEGER NOT NULL REFERENCES lista_precio(id),
  variante_id  INTEGER NOT NULL REFERENCES variante(id),
  precio_c     INTEGER NOT NULL CHECK (precio_c >= 0),
  PRIMARY KEY (lista_id, variante_id)
);

-- ---------------------------------------------------------------------
-- 4. Inventario (movimientos inmutables; existencia y costo = derivados)
-- ---------------------------------------------------------------------
CREATE TABLE ubicacion (
  id      INTEGER PRIMARY KEY,
  nombre  TEXT NOT NULL UNIQUE,
  tipo    TEXT NOT NULL CHECK (tipo IN ('interna','proveedor','cliente','ajuste','transito'))
);

CREATE TABLE movimiento_stock (
  id               INTEGER PRIMARY KEY,
  variante_id      INTEGER NOT NULL REFERENCES variante(id),
  desde_id         INTEGER NOT NULL REFERENCES ubicacion(id),
  hacia_id         INTEGER NOT NULL REFERENCES ubicacion(id),
  cantidad_mil     INTEGER NOT NULL CHECK (cantidad_mil > 0),
  costo_unit_c     INTEGER NOT NULL CHECK (costo_unit_c >= 0), -- entradas: costo real (incl. flete/aduana prorrateado); salidas: AVCO vigente
  fecha            TEXT NOT NULL,
  origen           TEXT NOT NULL CHECK (origen IN ('compra','venta','devolucion','ajuste','conteo','traslado')),
  origen_id        INTEGER,
  asiento_id       INTEGER REFERENCES asiento(id),   -- valoración (inventario vs costo de venta)
  motivo           TEXT,
  clave_idem       TEXT UNIQUE,
  CHECK (desde_id <> hacia_id)
);
CREATE INDEX mov_variante ON movimiento_stock(variante_id, fecha);
CREATE TRIGGER mov_stock_sin_update BEFORE UPDATE ON movimiento_stock
BEGIN SELECT RAISE(ABORT, 'movimiento de stock inmutable: haga un movimiento contrario'); END;
CREATE TRIGGER mov_stock_sin_delete BEFORE DELETE ON movimiento_stock
BEGIN SELECT RAISE(ABORT, 'movimiento de stock inmutable'); END;

-- Costo promedio ponderado (AVCO): historial solo-anexar; el vigente es el último.
CREATE TABLE costo_promedio (
  id            INTEGER PRIMARY KEY,
  variante_id   INTEGER NOT NULL REFERENCES variante(id),
  movimiento_id INTEGER NOT NULL UNIQUE REFERENCES movimiento_stock(id),
  costo_unit_c  INTEGER NOT NULL CHECK (costo_unit_c >= 0),
  existencia_mil INTEGER NOT NULL,         -- existencia interna tras el movimiento
  fecha         TEXT NOT NULL
);
CREATE INDEX costo_var ON costo_promedio(variante_id, id);
CREATE TRIGGER costo_sin_update BEFORE UPDATE ON costo_promedio
BEGIN SELECT RAISE(ABORT, 'historial de costo inmutable'); END;
CREATE TRIGGER costo_sin_delete BEFORE DELETE ON costo_promedio
BEGIN SELECT RAISE(ABORT, 'historial de costo inmutable'); END;

CREATE VIEW v_existencia AS
SELECT v.id AS variante_id, u.id AS ubicacion_id,
       COALESCE((SELECT SUM(cantidad_mil) FROM movimiento_stock m WHERE m.variante_id = v.id AND m.hacia_id = u.id),0)
     - COALESCE((SELECT SUM(cantidad_mil) FROM movimiento_stock m WHERE m.variante_id = v.id AND m.desde_id = u.id),0) AS cantidad_mil
  FROM variante v CROSS JOIN ubicacion u
 WHERE u.tipo = 'interna';

CREATE VIEW v_costo_vigente AS
SELECT c.variante_id, c.costo_unit_c, c.existencia_mil, c.fecha
  FROM costo_promedio c
 WHERE c.id = (SELECT MAX(id) FROM costo_promedio c2 WHERE c2.variante_id = c.variante_id);

-- Reservas para la tienda web (carrito/pedido sin confirmar) — expiran.
CREATE TABLE reserva_stock (
  id           INTEGER PRIMARY KEY,
  variante_id  INTEGER NOT NULL REFERENCES variante(id),
  venta_id     INTEGER NOT NULL REFERENCES venta(id),
  cantidad_mil INTEGER NOT NULL CHECK (cantidad_mil > 0),
  vence_en     TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- 5. Ventas y cotizaciones (tienda física y web en la misma tabla)
-- ---------------------------------------------------------------------
CREATE TABLE venta (
  id            INTEGER PRIMARY KEY,
  numero        TEXT UNIQUE,               -- S00001
  tercero_id    INTEGER NOT NULL REFERENCES tercero(id),
  vendedora_id  INTEGER REFERENCES usuario(id),
  canal         TEXT NOT NULL CHECK (canal IN ('tienda','web','whatsapp','brian')),
  estado        TEXT NOT NULL DEFAULT 'cotizacion'
                CHECK (estado IN ('carrito','cotizacion','enviada','confirmada','facturada','cancelada')),
  fecha         TEXT NOT NULL,
  valida_hasta  TEXT,
  padrino_id    INTEGER REFERENCES tercero(id),   -- «Invitado por»
  canje_id      INTEGER REFERENCES canje(id),     -- premio de descuento cobrado en la venta
  entrega       TEXT,                              -- JSON (dirección, método)
  subtotal_c    INTEGER NOT NULL DEFAULT 0,
  impuesto_c    INTEGER NOT NULL DEFAULT 0,
  total_c       INTEGER NOT NULL DEFAULT 0,
  clave_idem    TEXT UNIQUE,
  CHECK (total_c = subtotal_c + impuesto_c)
);
CREATE INDEX venta_estado ON venta(estado, fecha);

CREATE TABLE venta_linea (
  id            INTEGER PRIMARY KEY,
  venta_id      INTEGER NOT NULL REFERENCES venta(id),
  variante_id   INTEGER REFERENCES variante(id),
  descripcion   TEXT NOT NULL,
  cantidad_mil  INTEGER NOT NULL CHECK (cantidad_mil > 0),
  precio_unit_c INTEGER NOT NULL CHECK (precio_unit_c >= 0),
  descuento_pb  INTEGER NOT NULL DEFAULT 0 CHECK (descuento_pb BETWEEN 0 AND 10000),
  impuesto_id   INTEGER REFERENCES impuesto(id),
  subtotal_c    INTEGER NOT NULL,
  impuesto_c    INTEGER NOT NULL
);
CREATE INDEX vental_venta ON venta_linea(venta_id);

-- ---------------------------------------------------------------------
-- 6. Socios D'CASA: libro de puntos inmutable (como hoy en dcasa_socios)
-- ---------------------------------------------------------------------
CREATE TABLE socio_compra (               -- una compra que da puntos (nace de la factura pagada)
  id            INTEGER PRIMARY KEY,
  tercero_id    INTEGER NOT NULL REFERENCES tercero(id),
  documento_id  INTEGER UNIQUE REFERENCES documento(id),
  monto_c       INTEGER NOT NULL CHECK (monto_c >= 0),
  reglas_version INTEGER NOT NULL,          -- versión de puntos.json con que se calculó
  estado        TEXT NOT NULL DEFAULT 'vigente' CHECK (estado IN ('vigente','anulada')),
  fecha         TEXT NOT NULL
);

CREATE TABLE premio (
  id           INTEGER PRIMARY KEY,
  nombre       TEXT NOT NULL,
  tipo         TEXT NOT NULL CHECK (tipo IN ('descuento','producto')),
  puntos       INTEGER,                   -- NULL = PENDIENTE: no se canjea (regla 1)
  valor_c      INTEGER,
  variante_id  INTEGER REFERENCES variante(id),
  activo       INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1))
);

CREATE TABLE canje (
  id          INTEGER PRIMARY KEY,
  codigo      TEXT NOT NULL UNIQUE,       -- 72 h
  tercero_id  INTEGER NOT NULL REFERENCES tercero(id),
  premio_id   INTEGER NOT NULL REFERENCES premio(id),
  estado      TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','entregado','cancelado','vencido')),
  vence_en    TEXT NOT NULL,
  creado_en   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
-- un pendiente por premio y socio
CREATE UNIQUE INDEX canje_un_pendiente ON canje(tercero_id, premio_id) WHERE estado = 'pendiente';

CREATE TABLE puntos_movimiento (          -- EL LIBRO. Saldo = SUM(puntos). Sin columna de saldo.
  id            INTEGER PRIMARY KEY,
  tercero_id    INTEGER NOT NULL REFERENCES tercero(id),
  puntos        INTEGER NOT NULL CHECK (puntos <> 0),
  tipo          TEXT NOT NULL CHECK (tipo IN ('compra','referido_padrino','referido_invitado','cumpleanos',
                                              'canje_reserva','canje_devolucion','ajuste','anulacion','migracion')),
  motivo        TEXT NOT NULL,
  compra_id     INTEGER REFERENCES socio_compra(id),
  canje_id      INTEGER REFERENCES canje(id),
  contrario_de  INTEGER UNIQUE REFERENCES puntos_movimiento(id),  -- corrección = asiento contrario
  reglas_version INTEGER,
  usuario_id    INTEGER REFERENCES usuario(id),
  clave_idem    TEXT UNIQUE,
  creado_en     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX pts_tercero ON puntos_movimiento(tercero_id);
-- Regla 4: el referido se paga UNA vez por invitado (con su primera compra que da puntos)
CREATE UNIQUE INDEX pts_referido_una_vez ON puntos_movimiento(compra_id, tipo)
  WHERE tipo IN ('referido_padrino','referido_invitado') AND contrario_de IS NULL;
CREATE TRIGGER pts_sin_update BEFORE UPDATE ON puntos_movimiento
BEGIN SELECT RAISE(ABORT, 'el libro de puntos no se edita: use un asiento contrario con motivo'); END;
CREATE TRIGGER pts_sin_delete BEFORE DELETE ON puntos_movimiento
BEGIN SELECT RAISE(ABORT, 'el libro de puntos no se borra'); END;
CREATE TRIGGER pts_contrario_exacto BEFORE INSERT ON puntos_movimiento
WHEN NEW.contrario_de IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'el contrario debe anular exactamente al original')
   WHERE NEW.puntos <> -(SELECT puntos FROM puntos_movimiento WHERE id = NEW.contrario_de)
      OR NEW.tercero_id <> (SELECT tercero_id FROM puntos_movimiento WHERE id = NEW.contrario_de);
END;

CREATE VIEW v_saldo_puntos AS
SELECT tercero_id, SUM(puntos) AS saldo FROM puntos_movimiento GROUP BY tercero_id;

-- ---------------------------------------------------------------------
-- 7. Cola de salida hacia sistemas externos (PAC, Odoo durante la
--    transición, WhatsApp). Patrón «outbox»: se escribe en el MISMO batch
--    que el hecho de negocio y un consumidor (Queue/Workflow) lo envía.
-- ---------------------------------------------------------------------
CREATE TABLE outbox (
  id          INTEGER PRIMARY KEY,
  destino     TEXT NOT NULL CHECK (destino IN ('pac','odoo','whatsapp','correo')),
  tipo        TEXT NOT NULL,
  entidad_id  INTEGER,
  carga       TEXT NOT NULL,               -- JSON
  estado      TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','enviado','error')),
  intentos    INTEGER NOT NULL DEFAULT 0,
  clave_idem  TEXT NOT NULL UNIQUE,
  creado_en   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX outbox_pend ON outbox(estado, id);
