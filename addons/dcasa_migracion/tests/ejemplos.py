"""Archivos de ejemplo con datos 100 % inventados (los mismos 5 casos que describió la receta de migración).

Las cédulas empiezan por «0-» (no corresponde a ninguna provincia) y los correos son de dominios de ejemplo: ninguna
fila puede coincidir con una persona real.
"""

BOM = '﻿'

CLIENTES = BOM + '\n'.join([
    'id_viejo,nombre,tipo,cedula_ruc,dv,celular,correo,direccion,ciudad',
    '90001,Cliente de Prueba 1,persona,0-000-0001,,6000-0001,,,',
    '90002,Cliente de Prueba 2,persona,0-000-0002,,+507 6000-0002,prueba2@ejemplo.com,'
    'Calle Ficticia 2,Ciudad de Prueba',
    '90003,Empresa de Prueba 3 S.A.,empresa,0000000-0-000003,99,6000-0003,contacto@empresa-prueba.com,'
    '"Edificio Prueba, Local 3",Ciudad de Prueba',
    '90004,Cliente de Prueba 4,persona,,,,,,',
    '90005,Cliente de Prueba 5,persona,0-000-0005,98,60000005/2000005,,,',
    '',
])

PROVEEDORES = BOM + '\n'.join([
    'id_viejo,nombre,tipo,ruc,dv,telefono,correo,direccion,ciudad,pais',
    '70001,Proveedor de Prueba 1 S.A.,empresa,0000000-0-000001,99,200-0001,ventas@proveedor1-prueba.com,'
    '"Zona de Prueba, Galera 1",Ciudad de Prueba,Panamá',
    '70002,Proveedor de Prueba 2 Ltd.,empresa,PRUEBA-0002,,+86 000 0000 0002,contacto@proveedor2-prueba.com,,,China',
    '70003,Proveedor de Prueba 3,persona,0-000-0003,,6000-0003,,,,Panamá',
    '70004,Proveedor de Prueba 4 S.A.,empresa,0000000-0-000004,98,,,,,',
    '70005,Proveedor de Prueba 5 Corp.,empresa,,,+1 000 000 0005,info@proveedor5-prueba.com,Calle Ficticia 5,'
    'Ciudad de Prueba,Estados Unidos',
    '',
])

PRODUCTOS = BOM + '''id_viejo,codigo,nombre,categoria,precio_de_venta,costo,activo,codigo_de_barras
80001,PRUEBA-001,Producto de Prueba 1,MUEBLES / CAMAS,199.99,120,si,0000000000017
80002,PRUEBA-002,Producto de Prueba 2,ELECTRODOMESTICOS / VENTILADORES,45.5,28.75,si,
80003,,Producto de Prueba 3,MUEBLES,89,0,si,
80004,PRUEBA-004,Producto de Prueba 4,,0,15,no,
80005,PRUEBA-005,Combo de Prueba 5,MUEBLES / CAMAS,350,,si,
'''

INVENTARIO = BOM + '''codigo_producto,cantidad,bodega,fecha_del_dato
PRUEBA-001,12,D'CASA Principal,2026-10-12
PRUEBA-002,3,D'CASA Principal,2026-10-12
,7,D'CASA Principal,2026-10-12
PRUEBA-004,-2,D'CASA Principal,2026-10-12
PRUEBA-005,1.5,D'CASA Principal,2026-10-12
'''

PRECIOS = BOM + '\n'.join([
    'id_proveedor_viejo,codigo_producto,nombre_producto,precio,moneda,cantidad_minima,descuento,plazo_entrega_dias,'
    'vigente_desde,vigente_hasta',
    '70001,PRUEBA-001,Producto de Prueba 1,85.5,USD,0,0,0,,',
    '70001,PRUEBA-002,Producto de Prueba 2,22,USD,0,0,0,,',
    '70002,PRUEBA-003,Producto de Prueba 3,140,USD,1,0,0,,',
    '70004,,Producto de Prueba 4,0,USD,0,0,0,,',
    '70005,PRUEBA-005,Producto de Prueba 5,61.25,USD,0,0,0,,',
    '',
])


def como_bytes(texto):
    return texto.encode('utf-8')
VENTAS = BOM + '\n'.join([
    'numero_orden,id_cliente_viejo,fecha,total,estado_entrega,estado_facturacion,pendiente',
    'S99901,90001,2026-09-02,450,completa,por facturar,facturar',
    'S99902,90002,2026-09-15,1299.99,completa,por facturar,entregar y facturar',
    'S99903,90003,2026-10-01,89,completa,facturada,entregar',
    'S99904,90001,2026-10-08,215.5,,facturada,entregar',
    'S99905,90005,2026-10-11,60,completa,por facturar,facturar',
    '',
])

VENTAS_LINEAS = BOM + '\n'.join([
    'numero_orden,linea,codigo_producto,nombre_producto,tipo_producto,cantidad,precio_unitario,descuento,'
    'cantidad_entregada,cantidad_facturada,pendiente_entregar,pendiente_facturar',
    'S99901,1,PRUEBA-001,Producto de Prueba 1,bien,2,199.99,0,2,0,0,2',
    'S99901,2,ENVIO-PRUEBA,Servicio de Prueba (entrega),servicio,1,25,0,0,0,0,1',
    'S99902,1,PRUEBA-005,Combo de Prueba 5,combo,1,1299.99,0,0,0,0,0',
    'S99902,2,PRUEBA-002,Producto de Prueba 2,bien,1,0,0,0,0,1,1',
    'S99903,1,PRUEBA-003,Producto de Prueba 3,bien,3,29.67,0,2,3,1,0',
    '',
])

COMPRAS = BOM + '\n'.join([
    'numero_orden,id_proveedor_viejo,referencia_proveedor,fecha,total,estado_recepcion,estado_facturacion,pendiente',
    'P99901,70001,FAC-PRUEBA-001,2026-08-03,5400,completa,por facturar,facturar',
    'P99902,70002,,2026-08-20,12850.75,completa,por facturar,facturar',
    'P99903,70001,FAC-PRUEBA-003,2026-09-10,980,completa,por facturar,recibir',
    'P99904,70004,,2026-10-02,2300,pendiente,nada que facturar,recibir',
    'P99905,70005,PI-PRUEBA-005,2026-10-08,760,pendiente,facturada,recibir',
    '',
])

COMPRAS_LINEAS = BOM + '\n'.join([
    'numero_orden,linea,codigo_producto,nombre_producto,cantidad,precio_unitario,descuento,cantidad_recibida,'
    'cantidad_facturada,pendiente_recibir,pendiente_facturar',
    'P99901,1,PRUEBA-001,Producto de Prueba 1,20,85.5,0,20,0,0,20',
    'P99901,2,PRUEBA-002,Producto de Prueba 2,50,22,0,50,0,0,50',
    'P99903,1,PRUEBA-003,Producto de Prueba 3,10,98,0,8,0,2,8',
    'P99904,1,PRUEBA-004,Producto de Prueba 4,25,92,0,0,0,25,0',
    'P99905,1,PRUEBA-005,Producto de Prueba 5,12,63.33,0,0,12,12,0',
    '',
])

FACTURAS_CLIENTES = BOM + '\n'.join([
    'numero,tipo,fecha,fecha_vencimiento,id_cliente_viejo,moneda,base_imponible,impuesto,total,pagado,saldo,'
    'estado_pago,diario,orden_origen,referencia_fiscal,factura_original,condicion_pago,vendedor',
    'INV/2026/90001,factura,2026-08-03,2026-08-03,90001,USD,100,7,107,107,0,pagada,Ventas,S90001,,,Pago inmediato,'
    'Vendedor Ejemplo 1',
    'INV/2026/90002,factura,2026-08-15,2026-09-14,90002,USD,250,17.5,267.5,100,167.5,parcial,Ventas,S90002,'
    'FE-0000000001,,30 días,Vendedor Ejemplo 2',
    'INV/2026/90003,factura,2026-09-01,2026-09-01,90003,USD,45,3.15,48.15,0,48.15,sin_pagar,Ventas,,,,,',
    'RINV/2026/90001,nota_credito,2026-09-05,2026-09-05,90001,USD,20,1.4,21.4,21.4,0,pagada,Ventas,S90001,,'
    'INV/2026/90001,,Vendedor Ejemplo 1',
    'INV/2026/90004,factura,2026-10-10,2026-10-25,90004,USD,1200,84,1284,1284,0,pagada,Ventas,S90004,,,15 días,'
    'Vendedor Ejemplo 2',
    '',
])

FACTURAS_CLIENTES_LINEAS = BOM + '\n'.join([
    'numero,codigo_producto,nombre_producto,cantidad,precio_unitario,descuento,impuesto,subtotal,cuenta_ingreso',
    'INV/2026/90001,EJ-001,Producto Ejemplo 1,1,100,0,ITBMS 7% Ventas,100,000001',
    'INV/2026/90002,EJ-002,Producto Ejemplo 2,2,125,0,ITBMS 7% Ventas,250,000001',
    'INV/2026/90003,,Servicio Ejemplo de entrega,1,50,10,ITBMS 7% Ventas,45,000002',
    'RINV/2026/90001,EJ-001,Producto Ejemplo 1,1,20,0,ITBMS 7% Ventas,20,000001',
    'INV/2026/90004,EJ-003,Combo Ejemplo 3,1,1200,0,ITBMS 7% Ventas,1200,000001',
    '',
])

FACTURAS_PROVEEDORES = BOM + '\n'.join([
    'numero,referencia_proveedor,tipo,fecha,fecha_vencimiento,id_proveedor_viejo,moneda,base_imponible,impuesto,'
    'total,pagado,saldo,estado_pago,diario,orden_origen,factura_original,condicion_pago',
    'BILL/2026/90001,FAC-EJ-1001,factura,2026-08-02,2026-09-01,70001,USD,5000,350,5350,5350,0,pagada,Compras,'
    'P90001,,30 días',
    'BILL/2026/90002,FAC-EJ-1002,factura,2026-08-20,2026-08-20,70002,USD,12000,0,12000,6000,6000,parcial,Compras,'
    'P90002,,',
    'BILL/2026/90003,,factura,2026-09-10,2026-10-10,70001,USD,900,63,963,0,963,sin_pagar,Compras,,,30 días',
    'RBILL/2026/90001,NC-EJ-0001,nota_credito,2026-09-15,2026-09-15,70001,USD,100,7,107,107,0,pagada,Compras,,'
    'BILL/2026/90001,',
    'BILL/2026/90004,PI-EJ-0004,factura,2026-10-05,2026-11-04,70005,USD,760,53.2,813.2,0,813.2,sin_pagar,Compras,'
    'P90005,,30 días',
    '',
])

FACTURAS_PROVEEDORES_LINEAS = BOM + '\n'.join([
    'numero,codigo_producto,nombre_producto,cantidad,precio_unitario,descuento,impuesto,subtotal,cuenta_gasto',
    'BILL/2026/90001,EJ-001,Producto Ejemplo 1,50,100,0,ITBMS 7% Compras,5000,000010',
    'BILL/2026/90002,EJ-004,Producto Ejemplo 4,100,120,0,,12000,000010',
    'BILL/2026/90003,,Flete Ejemplo,1,900,0,ITBMS 7% Compras,900,000011',
    'RBILL/2026/90001,EJ-001,Producto Ejemplo 1,1,100,0,ITBMS 7% Compras,100,000010',
    'BILL/2026/90004,EJ-005,Producto Ejemplo 5,8,95,0,ITBMS 7% Compras,760,000010',
    '',
])

PAGOS = BOM + '\n'.join([
    'fecha,tipo,id_contacto_viejo,monto,moneda,diario,metodo,referencia,facturas_que_paga,estado',
    '2026-08-03,cobro,90001,107,USD,Caja Ejemplo,Manual,INV/2026/90001,INV/2026/90001,conciliado',
    '2026-08-20,cobro,90002,100,USD,Banco Ejemplo,Manual,INV/2026/90002,INV/2026/90002,sin_conciliar',
    '2026-08-25,pago,70002,6000,USD,Banco Ejemplo,Transferencia,Abono FAC-EJ-1002,BILL/2026/90002,conciliado',
    '2026-09-30,pago,70001,5350,USD,Banco Ejemplo,Manual,FAC-EJ-1001,BILL/2026/90001,conciliado',
    '2026-10-10,cobro,90004,1284,USD,Banco Ejemplo,Manual,Pago combinado,INV/2026/90004|INV/2026/90005,sin_conciliar',
    '',
])
