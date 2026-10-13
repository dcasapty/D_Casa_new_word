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
