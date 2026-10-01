"""Valida esquema_d1.sql en SQLite en memoria y ejercita sus invariantes.

Uso: python3 docs/auditoria/ronda3/reconstruccion/validar_esquema.py
No toca ninguna base real. Sale con código != 0 si algo falla.
"""
import pathlib
import sqlite3
import sys

AQUI = pathlib.Path(__file__).parent
sql = (AQUI / 'esquema_d1.sql').read_text(encoding='utf-8')

db = sqlite3.connect(':memory:')
db.execute('PRAGMA foreign_keys = ON')
db.executescript(sql)

ok = 0
fallos = []


def debe_fallar(nombre, sentencia, args=(), contiene=''):
    global ok
    try:
        db.execute(sentencia, args)
    except sqlite3.DatabaseError as e:  # IntegrityError incluido
        if contiene and contiene not in str(e):
            fallos.append(f'{nombre}: falló con otro error: {e}')
        else:
            ok += 1
        return
    fallos.append(f'{nombre}: NO falló y debía fallar')


def comprobar(nombre, cond):
    global ok
    if cond:
        ok += 1
    else:
        fallos.append(nombre)


x = db.execute
objs = x("SELECT type, count(*) FROM sqlite_master GROUP BY type").fetchall()
print('Objetos creados:', dict(objs))

# --- datos base -------------------------------------------------------
x("INSERT INTO config VALUES ('fecha_bloqueo','2026-08-31')")
x("INSERT INTO usuario (id,nombre,rol) VALUES (1,'Dueño','admin')")
cuentas = [
    (1, '1.1.01', 'Caja', 'banco', 0),
    (2, '1.1.02', 'Banco General', 'banco', 0),
    (3, '1.1.03', 'Clientes', 'por_cobrar', 1),
    (4, '2.1.01', 'ITBMS por pagar', 'impuesto_por_pagar', 0),
    (5, '4.1.01', 'Ventas', 'ingreso', 0),
    (6, '1.1.09', 'Pagos por aplicar', 'activo_corriente', 1),
]
x_many = db.executemany
x_many("INSERT INTO cuenta (id,codigo,nombre,tipo,conciliable) VALUES (?,?,?,?,?)", cuentas)
x("INSERT INTO diario (id,codigo,nombre,tipo,prefijo) VALUES (1,'VEN','Ventas','venta','INV/2026/')")
x("INSERT INTO diario (id,codigo,nombre,tipo,prefijo) VALUES (2,'BNK1','Banco','banco','BNK1/2026/')")
x("INSERT INTO impuesto (id,nombre,tasa_pb,uso,precio_incluye,cuenta_id) VALUES (1,'ITBMS 7%',700,'venta',0,4)")
x("INSERT INTO tercero (id,nombre,celular_digitos,socio_codigo) VALUES (10,'Cliente 00821','50760000001','DCA0001')")
x("INSERT INTO tercero (id,nombre,celular_digitos,socio_codigo) VALUES (11,'Padrino','50760000002','DCA0002')")

# --- factura 00821: 171.97 + 158.02 = 329.99 ; ITBMS 12.04 + 11.06 = 23.10 ; total 353.09
x("INSERT INTO asiento (id,diario_id,fecha,referencia,origen) VALUES (100,1,'2026-09-15','INV 00821','documento')")
lineas = [
    (100, 3, 10, 35309, 0, None, None),
    (100, 5, 10, 0, 17197, None, None),
    (100, 5, 10, 0, 15802, None, None),
    (100, 4, 10, 0, 1204, 1, 17197),
    (100, 4, 10, 0, 1106, 1, 15802),
]
x_many("INSERT INTO linea_asiento (asiento_id,cuenta_id,tercero_id,debe_c,haber_c,impuesto_id,base_c) "
       "VALUES (?,?,?,?,?,?,?)", lineas)
debe_fallar('publicar sin numero', "UPDATE asiento SET estado='publicado' WHERE id=100", contiene='falta numero')
x("UPDATE asiento SET estado='publicado', numero='INV/2026/00821' WHERE id=100")
comprobar('total factura 353.09', x("SELECT debe_c FROM linea_asiento WHERE asiento_id=100 AND cuenta_id=3").fetchone()[0] == 35309)
comprobar('ITBMS 23.10', x("SELECT SUM(itbms_c) FROM v_itbms").fetchone()[0] == 2310)
comprobar('base ITBMS 329.99', x("SELECT SUM(base_c) FROM v_itbms").fetchone()[0] == 32999)
comprobar('balance de comprobación cuadra', x("SELECT SUM(saldo_c) FROM v_balance_comprobacion").fetchone()[0] == 0)

debe_fallar('editar linea publicada', "UPDATE linea_asiento SET debe_c=1 WHERE asiento_id=100 AND cuenta_id=3", contiene='inmutables')
debe_fallar('borrar linea publicada', "DELETE FROM linea_asiento WHERE asiento_id=100", contiene='inmutables')
debe_fallar('agregar linea a publicado', "INSERT INTO linea_asiento (asiento_id,cuenta_id,debe_c) VALUES (100,1,5)", contiene='no se agregan')
debe_fallar('borrar asiento publicado', "DELETE FROM asiento WHERE id=100", contiene='asiento contrario')
debe_fallar('despublicar', "UPDATE asiento SET estado='borrador' WHERE id=100", contiene='inmutable')
debe_fallar('linea con debe y haber', "INSERT INTO linea_asiento (asiento_id,cuenta_id,debe_c,haber_c) VALUES (100,1,5,5)")

# asiento descuadrado
x("INSERT INTO asiento (id,diario_id,fecha,numero) VALUES (101,1,'2026-09-16','X1')")
x("INSERT INTO linea_asiento (asiento_id,cuenta_id,debe_c) VALUES (101,3,100)")
x("INSERT INTO linea_asiento (asiento_id,cuenta_id,haber_c) VALUES (101,5,99)")
debe_fallar('publicar descuadrado', "UPDATE asiento SET estado='publicado' WHERE id=101", contiene='descuadrado')

# periodo bloqueado
x("INSERT INTO asiento (id,diario_id,fecha,numero) VALUES (102,1,'2026-08-31','X2')")
x("INSERT INTO linea_asiento (asiento_id,cuenta_id,debe_c) VALUES (102,3,100)")
x("INSERT INTO linea_asiento (asiento_id,cuenta_id,haber_c) VALUES (102,5,100)")
debe_fallar('publicar en periodo bloqueado', "UPDATE asiento SET estado='publicado' WHERE id=102", contiene='bloqueado')

# reversa sin motivo
debe_fallar('reversa sin motivo', "INSERT INTO asiento (diario_id,fecha,reversa_de) VALUES (1,'2026-09-20',100)")

# --- cobro parcial y conciliación ------------------------------------
x("INSERT INTO asiento (id,diario_id,fecha,numero,origen) VALUES (200,2,'2026-09-16','BNK1/2026/0001','pago')")
x("INSERT INTO linea_asiento (id,asiento_id,cuenta_id,tercero_id,debe_c) VALUES (2001,200,2,10,20000)")
x("INSERT INTO linea_asiento (id,asiento_id,cuenta_id,tercero_id,haber_c) VALUES (2002,200,3,10,20000)")
x("UPDATE asiento SET estado='publicado' WHERE id=200")
linea_factura = x("SELECT id FROM linea_asiento WHERE asiento_id=100 AND cuenta_id=3").fetchone()[0]
x("INSERT INTO conciliacion (linea_debe_id,linea_haber_id,monto_c,fecha) VALUES (?,?,?,?)",
  (linea_factura, 2002, 20000, '2026-09-16'))
comprobar('saldo abierto factura 153.09',
          x("SELECT abierto_debe_c FROM v_abierto_por_linea WHERE linea_id=?", (linea_factura,)).fetchone()[0] == 15309)
debe_fallar('sobre-conciliar', "INSERT INTO conciliacion (linea_debe_id,linea_haber_id,monto_c,fecha) VALUES (?,?,?,?)",
            (linea_factura, 2002, 1, '2026-09-16'), contiene='excede')
debe_fallar('conciliar cuentas distintas', "INSERT INTO conciliacion (linea_debe_id,linea_haber_id,monto_c,fecha) VALUES (?,?,?,?)",
            (2001, 2002, 1, '2026-09-16'), contiene='cuentas distintas')

# --- extracto: misma huella no se duplica --------------------------------
x("INSERT INTO extracto_linea (diario_id,fecha,descripcion,monto_c,huella) VALUES (2,'2026-09-16','ACH',20000,'h1')")
debe_fallar('extracto duplicado', "INSERT INTO extracto_linea (diario_id,fecha,descripcion,monto_c,huella) VALUES (2,'2026-09-16','ACH',20000,'h1')")

# --- documento: NC exige origen y motivo; total = subtotal + impuesto -------
x("INSERT INTO documento (id,tipo,tercero_id,fecha,subtotal_c,impuesto_c,total_c,estado,asiento_id) "
  "VALUES (1,'factura',10,'2026-09-15',32999,2310,35309,'publicado',100)")
debe_fallar('NC sin origen', "INSERT INTO documento (tipo,tercero_id,fecha) VALUES ('nota_credito',10,'2026-09-20')")
debe_fallar('total incoherente', "INSERT INTO documento (tipo,tercero_id,fecha,subtotal_c,impuesto_c,total_c) VALUES ('factura',10,'2026-09-20',100,7,100)")
debe_fallar('editar factura publicada', "UPDATE documento SET total_c=1, subtotal_c=1, impuesto_c=0 WHERE id=1", contiene='nota de credito')
x("UPDATE documento SET fe_estado='autorizada', fe_cufe='FE0120000155779346-2-2026-...' WHERE id=1")  # la FE sí se completa
comprobar('FE se puede completar tras publicar', x("SELECT fe_estado FROM documento WHERE id=1").fetchone()[0] == 'autorizada')

# --- catálogo e inventario ----------------------------------------------
x("INSERT INTO producto (id,nombre,slug) VALUES (1,'Cama con estantes','cama-con-estantes')")
x("INSERT INTO variante (id,producto_id,sku,precio_c) VALUES (1,1,'1062010735N',15802)")
debe_fallar('sku duplicado', "INSERT INTO variante (producto_id,sku,precio_c) VALUES (1,'1062010735N',1)")
x("INSERT INTO ubicacion (id,nombre,tipo) VALUES (1,'Bodega La Chorrera','interna'),(2,'Proveedores','proveedor'),(3,'Clientes','cliente')")
x("INSERT INTO movimiento_stock (id,variante_id,desde_id,hacia_id,cantidad_mil,costo_unit_c,fecha,origen) VALUES (1,1,2,1,5000,9000,'2026-09-01','compra')")
x("INSERT INTO costo_promedio (variante_id,movimiento_id,costo_unit_c,existencia_mil,fecha) VALUES (1,1,9000,5000,'2026-09-01')")
x("INSERT INTO movimiento_stock (id,variante_id,desde_id,hacia_id,cantidad_mil,costo_unit_c,fecha,origen) VALUES (2,1,2,1,5000,11000,'2026-09-05','compra')")
# AVCO: (5*90 + 5*110)/10 = 100.00
x("INSERT INTO costo_promedio (variante_id,movimiento_id,costo_unit_c,existencia_mil,fecha) VALUES (1,2,10000,10000,'2026-09-05')")
x("INSERT INTO movimiento_stock (id,variante_id,desde_id,hacia_id,cantidad_mil,costo_unit_c,fecha,origen) VALUES (3,1,1,3,1000,10000,'2026-09-15','venta')")
comprobar('existencia 9 und', x("SELECT cantidad_mil FROM v_existencia WHERE variante_id=1 AND ubicacion_id=1").fetchone()[0] == 9000)
comprobar('costo vigente 100.00', x("SELECT costo_unit_c FROM v_costo_vigente WHERE variante_id=1").fetchone()[0] == 10000)
debe_fallar('editar movimiento de stock', "UPDATE movimiento_stock SET cantidad_mil=1 WHERE id=1", contiene='inmutable')
debe_fallar('borrar historial de costo', "DELETE FROM costo_promedio", contiene='inmutable')

# --- socios -----------------------------------------------------------------
x("UPDATE tercero SET padrino_id=11 WHERE id=10")
debe_fallar('padrino se escribe una vez', "UPDATE tercero SET padrino_id=NULL WHERE id=10", contiene='padrino')
debe_fallar('ser su propio padrino', "UPDATE tercero SET padrino_id=11 WHERE id=11")
x("INSERT INTO socio_compra (id,tercero_id,documento_id,monto_c,reglas_version,fecha) VALUES (1,10,1,32999,2,'2026-09-16')")
# Cifras de ejemplo SOLO para la prueba (las reales viven en puntos.json)
x("INSERT INTO puntos_movimiento (id,tercero_id,puntos,tipo,motivo,compra_id) VALUES (1,10,330,'compra','prueba',1)")
x("INSERT INTO puntos_movimiento (id,tercero_id,puntos,tipo,motivo,compra_id) VALUES (2,11,500,'referido_padrino','prueba',1)")
debe_fallar('referido pagado dos veces', "INSERT INTO puntos_movimiento (tercero_id,puntos,tipo,motivo,compra_id) VALUES (11,500,'referido_padrino','prueba',1)")
debe_fallar('editar libro de puntos', "UPDATE puntos_movimiento SET puntos=1 WHERE id=1", contiene='no se edita')
debe_fallar('borrar libro de puntos', "DELETE FROM puntos_movimiento WHERE id=1", contiene='no se borra')
debe_fallar('contrario inexacto', "INSERT INTO puntos_movimiento (tercero_id,puntos,tipo,motivo,contrario_de) VALUES (10,-100,'anulacion','x',1)", contiene='exactamente')
x("INSERT INTO puntos_movimiento (tercero_id,puntos,tipo,motivo,contrario_de) VALUES (10,-330,'anulacion','NC total',1)")
debe_fallar('anular dos veces', "INSERT INTO puntos_movimiento (tercero_id,puntos,tipo,motivo,contrario_de) VALUES (10,-330,'anulacion','otra vez',1)")
comprobar('saldo puntos = suma (0)', x("SELECT saldo FROM v_saldo_puntos WHERE tercero_id=10").fetchone()[0] == 0)
debe_fallar('movimiento de 0 puntos', "INSERT INTO puntos_movimiento (tercero_id,puntos,tipo,motivo) VALUES (10,0,'ajuste','x')")

# canje: un pendiente por premio
x("INSERT INTO premio (id,nombre,tipo,puntos) VALUES (1,'Descuento','descuento',NULL)")
x("INSERT INTO canje (codigo,tercero_id,premio_id,vence_en) VALUES ('C1',10,1,'2026-09-19')")
debe_fallar('dos canjes pendientes del mismo premio', "INSERT INTO canje (codigo,tercero_id,premio_id,vence_en) VALUES ('C2',10,1,'2026-09-19')")

# auditoría solo-anexar
x("INSERT INTO auditoria (usuario_id,canal,accion,entidad) VALUES (1,'brian','crear_factura','documento')")
debe_fallar('editar auditoria', "UPDATE auditoria SET accion='x'", contiene='solo-anexar')

# idempotencia
x("INSERT INTO outbox (destino,tipo,carga,clave_idem) VALUES ('pac','emitir','{}','fe-1')")
debe_fallar('outbox duplicado', "INSERT INTO outbox (destino,tipo,carga,clave_idem) VALUES ('pac','emitir','{}','fe-1')")

fk = x("PRAGMA foreign_key_check").fetchall()
comprobar('sin violaciones de FK', not fk)
tablas = x("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
print(f'Tablas: {tablas} · comprobaciones OK: {ok} · fallos: {len(fallos)}')
for f in fallos:
    print('  FALLO:', f)
print('SQLite', sqlite3.sqlite_version)
sys.exit(1 if fallos else 0)
