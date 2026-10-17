"""Lectura de los CSV que deja la receta de migración (clientes, productos, inventario).

Funciones PURAS (sin base de datos): reciben el texto del archivo y devuelven filas ya limpias y los avisos que
hay que mostrar. Los archivos son UTF-8 (con BOM), separados por coma, con punto decimal y fechas AAAA-MM-DD. Una celda
vacía significa «ese dato no existe en el sistema anterior».
"""
import csv
import io
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from odoo.addons.dcasa_catalogo.reglas import clase_de_fila_inventario
from odoo.addons.dcasa_socios.models import bien_escrito
from odoo.tools import email_normalize

COLUMNAS_CLIENTES = ('id_viejo', 'nombre')
COLUMNAS_PRODUCTOS = ('codigo', 'nombre')
COLUMNAS_INVENTARIO = ('codigo_producto', 'cantidad')
COLUMNAS_PRECIOS = ('id_proveedor_viejo', 'codigo_producto', 'precio')
COLUMNAS_VENTAS = ('numero_orden', 'id_cliente_viejo')
COLUMNAS_COMPRAS = ('numero_orden', 'id_proveedor_viejo')
COLUMNAS_LINEAS = ('numero_orden', 'cantidad', 'precio_unitario')

_SEPARADORES_DE_TELEFONO = re.compile(r'[/;,|]|\s+y\s+|\s+o\s+', re.IGNORECASE)
_SI = {'si', 'sí', 's', 'true', '1', 'yes', 'y', 'x'}
_NO = {'no', 'n', 'false', '0'}


class ErrorDeArchivo(Exception):
    """El archivo no sirve (no se puede leer o le falta una columna): el texto se le muestra tal cual a quien carga."""


def texto_de_bytes(contenido):
    """El texto de un archivo subido (bytes). UTF-8 con o sin BOM; si no lo es, se pide guardarlo así."""
    try:
        return contenido.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ErrorDeArchivo(
            'El archivo no está en UTF-8. Ábrelo y guárdalo como «CSV UTF-8»; si es el de la receta, '
            'no lo abras con Excel y súbelo tal cual.') from error


def _delimitador(texto):
    primera = texto.lstrip('﻿').split('\n', 1)[0]
    return max((',', ';', '\t'), key=primera.count) if any(d in primera for d in (',', ';', '\t')) else ','


def _encabezado(nombre):
    """El nombre de una columna sin importar cómo se escribió: «Código Combo» y «codigo_combo» son la misma."""
    claro = unicodedata.normalize('NFKD', nombre or '').encode('ascii', 'ignore').decode().strip().lower()
    return re.sub(r'[\s\-]+', '_', claro)


def leer_csv(texto, requeridas, nombre_del_archivo):
    """Las filas del CSV como diccionarios con las celdas sin espacios sobrantes.

    ``requeridas`` son las columnas sin las que no se puede cargar; faltar una es un error del archivo. Las columnas se
    reconocen por su encabezado (en cualquier orden, con o sin mayúsculas, tildes o espacios).
    """
    texto = (texto or '').lstrip('﻿')
    if not texto.strip():
        raise ErrorDeArchivo(f'{nombre_del_archivo} está vacío.')
    lector = csv.DictReader(io.StringIO(texto), delimiter=_delimitador(texto))
    columnas = [_encabezado(c) for c in (lector.fieldnames or [])]
    faltan = [c for c in requeridas if c not in columnas]
    if faltan:
        raise ErrorDeArchivo(
            f'A {nombre_del_archivo} le falta la columna «{faltan[0]}». ¿Es el archivo correcto? '
            f'Las columnas que trae son: {", ".join(columnas) or "ninguna"}.')
    filas = []
    for fila in lector:
        filas.append({_encabezado(k): (v or '').strip() for k, v in fila.items() if k is not None})
    return filas


def numero(texto, columna, fila):
    """``'12.5'`` → 12.5; vacío → ``None``. Un número mal escrito es un error del archivo (con su fila)."""
    texto = (texto or '').strip()
    if not texto:
        return None
    try:
        return float(Decimal(texto))
    except InvalidOperation as error:
        raise ErrorDeArchivo(f'Fila {fila}: «{texto}» no es un número en la columna {columna}.') from error


def si_o_no(texto, por_defecto=True):
    limpio = (texto or '').strip().lower()
    if limpio in _SI:
        return True
    if limpio in _NO:
        return False
    return por_defecto


# ----------------------------------------------------------------------------------------------
# Clientes
# ----------------------------------------------------------------------------------------------

def separar_telefonos(texto):
    """``'60000005/2000005'`` → ``('60000005', ['2000005'])``: el primer número con cifras suficientes es el principal.

    El campo Teléfono del sistema anterior es texto libre (puede traer un fijo, un celular o dos números). Solo el
    principal va al campo de teléfono (que identifica a la persona); los demás se guardan en las notas, sin perderlos.
    """
    piezas = [p.strip() for p in _SEPARADORES_DE_TELEFONO.split(texto or '') if p and p.strip()]
    if not piezas:
        return '', []
    con_cifras = [p for p in piezas if len(re.sub(r'\D', '', p)) >= 7]
    principal = con_cifras[0] if con_cifras else piezas[0]
    donde = piezas.index(principal)
    return principal, piezas[:donde] + piezas[donde + 1:]


def _primero(celdas, *nombres):
    """La primera celda con dato entre varias columnas posibles (clientes.csv y proveedores.csv no las llaman igual)."""
    for nombre in nombres:
        if celdas.get(nombre):
            return celdas[nombre]
    return ''


def filas_clientes(texto):
    """``(filas, errores)`` de clientes.csv (ver ``filas_contactos``)."""
    return filas_contactos(texto, 'clientes.csv')


def filas_proveedores(texto):
    """``(filas, errores)`` de proveedores.csv: mismo formato que clientes.csv."""
    return filas_contactos(texto, 'proveedores.csv')


def filas_contactos(texto, nombre_del_archivo):
    """``(filas, errores)`` de clientes.csv o proveedores.csv. Las columnas son casi las mismas: el RUC puede llamarse
    ``cedula_ruc`` o ``ruc`` y el teléfono ``celular`` o ``telefono``; ``pais`` solo lo trae proveedores.csv.

    Cada fila: ``id_viejo`` (entero), ``nombre``, ``es_empresa``, ``vat``, ``dv``, ``telefono``, ``correo``,
    ``direccion``, ``ciudad``, ``pais`` (el nombre, si el archivo lo trae) y ``notas`` (datos que no caben en su
    campo y se guardan en la nota de la ficha).
    Una fila sin nombre, con un número viejo que no es entero o repetido en el archivo, no se carga: va a ``errores``
    como ``(id_viejo, nombre, motivo)``.
    """
    filas, errores, vistos = [], [], set()
    for posicion, celdas in enumerate(leer_csv(texto, COLUMNAS_CLIENTES, nombre_del_archivo), start=2):
        crudo = celdas.get('id_viejo', '')
        nombre = re.sub(r'\s+', ' ', celdas.get('nombre', '')).strip()
        if not crudo.isdigit():
            errores.append((crudo or f'fila {posicion}', nombre, 'el número del sistema anterior no es un entero'))
            continue
        id_viejo = int(crudo)
        if not nombre:
            errores.append((id_viejo, '', 'no tiene nombre'))
            continue
        if id_viejo in vistos:
            errores.append((id_viejo, nombre, 'el mismo número aparece dos veces en el archivo'))
            continue
        vistos.add(id_viejo)
        notas = []
        telefono, otros = separar_telefonos(_primero(celdas, 'celular', 'telefono'))
        if otros:
            notas.append('Otros teléfonos en el sistema anterior: ' + ', '.join(otros))
        correo = celdas.get('correo', '')
        problema, sugerencia = bien_escrito.problema_del_correo(correo) if correo else (None, None)
        if correo and not email_normalize(correo, strict=False):
            notas.append(f'Correo mal escrito en el sistema anterior: {correo}')
            correo = ''
        elif problema == 'dedo':
            # Un error de dedo («gmial.com») no se carga como si fuera bueno: se anota y se le pide al cliente.
            notas.append(f'Correo mal escrito en el sistema anterior: {correo} (¿{sugerencia}?)')
            correo = ''
        elif problema == 'relleno':
            notas.append(f'Correo de relleno en el sistema anterior: {correo}')
            correo = ''
        dv = celdas.get('dv', '')
        if dv and not dv.isdigit():
            notas.append(f'DV mal escrito en el sistema anterior: {dv}')
            dv = ''
        filas.append({
            'id_viejo': id_viejo,
            'nombre': nombre,
            'es_empresa': celdas.get('tipo', '').lower() == 'empresa',
            'vat': _primero(celdas, 'cedula_ruc', 'ruc'),
            'dv': dv,
            'telefono': telefono,
            'correo': correo,
            'direccion': celdas.get('direccion', ''),
            'ciudad': celdas.get('ciudad', ''),
            'pais': celdas.get('pais', ''),
            'notas': notas,
        })
    return filas, errores


def _fecha(texto):
    """``'2026-10-01'`` → la misma fecha; vacío → ``None``; otra cosa → ``ValueError``."""
    return date.fromisoformat(texto).isoformat() if texto else None


def filas_precios_proveedor(texto):
    """``(filas, errores)`` de precios_proveedor.csv: lo que cobra cada proveedor por cada producto.

    Cada fila: ``id_proveedor_viejo`` (entero), ``codigo`` y ``nombre`` del producto (el código puede faltar: entonces
    se busca por nombre), ``precio``, ``moneda``, ``cantidad_minima`` (1 si no viene o es 0), ``descuento`` (%),
    ``plazo`` (días de entrega) y las fechas ``desde`` y ``hasta`` de vigencia. Una fila sin proveedor entero, sin
    código ni nombre, con precio vacío o negativo o con una fecha mal escrita va a ``errores`` como
    ``(id_proveedor_viejo, producto, motivo)``. Un precio 0 no es un error: «no se registró» (la carga lo deja pasar
    sin cargarlo).
    """
    filas, errores = [], []
    for posicion, celdas in enumerate(leer_csv(texto, COLUMNAS_PRECIOS, 'precios_proveedor.csv'), start=2):
        crudo = celdas.get('id_proveedor_viejo', '')
        codigo = celdas.get('codigo_producto', '')
        nombre = re.sub(r'\s+', ' ', celdas.get('nombre_producto', '')).strip()
        if not crudo.isdigit():
            errores.append((crudo or f'fila {posicion}', codigo or nombre, 'el número del proveedor no es un entero'))
            continue
        if not codigo and not nombre:
            errores.append((int(crudo), '', 'no tiene código ni nombre de producto'))
            continue
        precio = numero(celdas.get('precio'), 'precio', posicion)
        if precio is None or precio < 0:
            errores.append((int(crudo), codigo or nombre, 'el precio falta o es negativo'))
            continue
        try:
            desde, hasta = _fecha(celdas.get('vigente_desde', '')), _fecha(celdas.get('vigente_hasta', ''))
        except ValueError:
            errores.append((int(crudo), codigo or nombre, 'una fecha de vigencia está mal escrita (AAAA-MM-DD)'))
            continue
        minima = numero(celdas.get('cantidad_minima'), 'cantidad_minima', posicion)
        descuento = numero(celdas.get('descuento'), 'descuento', posicion)
        plazo = numero(celdas.get('plazo_entrega_dias'), 'plazo_entrega_dias', posicion)
        filas.append({
            'id_proveedor_viejo': int(crudo), 'codigo': codigo, 'nombre': nombre, 'precio': precio,
            'moneda': celdas.get('moneda', ''), 'cantidad_minima': minima if minima and minima > 0 else 1.0,
            'descuento': descuento or 0.0, 'plazo': int(plazo or 0), 'desde': desde, 'hasta': hasta})
    return filas, errores


# ----------------------------------------------------------------------------------------------
# Órdenes pendientes (ventas y compras)
# ----------------------------------------------------------------------------------------------

def _pendiente(celdas, columna, total, hecho):
    """La cantidad pendiente: la que trae el archivo o, si falta, lo pedido menos lo hecho."""
    crudo = celdas.get(columna, '')
    if crudo != '':
        return numero(crudo, columna, 0) or 0.0
    return max((total or 0.0) - (hecho or 0.0), 0.0)


def _ordenes(texto_cabecera, texto_lineas, nombre_cabecera, nombre_lineas, columnas_cabecera, columna_contacto,
             lector_de_linea):
    """Une cada orden con sus líneas. ``(ordenes, errores)``; un error es ``(numero_orden, motivo)``."""
    ordenes, errores, por_numero, rechazadas = [], [], {}, set()
    for posicion, celdas in enumerate(leer_csv(texto_cabecera, columnas_cabecera, nombre_cabecera), start=2):
        numero_orden = celdas.get('numero_orden', '')
        crudo = celdas.get(columna_contacto, '')
        if not numero_orden or not crudo.isdigit():
            errores.append((numero_orden or f'fila {posicion}', 'le falta el número de orden o el número del contacto'))
            continue
        if numero_orden in por_numero:
            errores.append((numero_orden, 'la orden aparece dos veces'))
            continue
        try:
            fecha = _fecha(celdas.get('fecha', ''))
        except ValueError:
            errores.append((numero_orden, 'la fecha está mal escrita (AAAA-MM-DD)'))
            rechazadas.add(numero_orden)
            continue
        orden = {'numero': numero_orden, 'id_contacto': int(crudo), 'fecha': fecha,
                 'total': numero(celdas.get('total'), 'total', posicion), 'lineas': [],
                 'referencia': celdas.get('referencia_proveedor', '')}
        por_numero[numero_orden] = orden
        ordenes.append(orden)
    for posicion, celdas in enumerate(leer_csv(texto_lineas, COLUMNAS_LINEAS, nombre_lineas), start=2):
        orden = por_numero.get(celdas.get('numero_orden', ''))
        if orden is None and celdas.get('numero_orden', '') in rechazadas:
            continue  # la orden ya se reportó con error: sus líneas no se reportan otra vez
        if orden is None:
            errores.append((celdas.get('numero_orden', '') or f'fila {posicion}',
                            f'una línea de {nombre_lineas} no tiene su orden en {nombre_cabecera}'))
            continue
        orden['lineas'].append(lector_de_linea(celdas, posicion))
    return ordenes, errores


def _linea_comun(celdas, posicion):
    cantidad = numero(celdas.get('cantidad'), 'cantidad', posicion) or 0.0
    return {
        'linea': celdas.get('linea', ''), 'codigo': celdas.get('codigo_producto', ''),
        'nombre': re.sub(r'\s+', ' ', celdas.get('nombre_producto', '')).strip(), 'cantidad': cantidad,
        'precio': numero(celdas.get('precio_unitario'), 'precio_unitario', posicion) or 0.0,
        'descuento': numero(celdas.get('descuento'), 'descuento', posicion) or 0.0,
    }


def _linea_de_venta(celdas, posicion):
    linea = _linea_comun(celdas, posicion)
    entregada = numero(celdas.get('cantidad_entregada'), 'cantidad_entregada', posicion) or 0.0
    facturada = numero(celdas.get('cantidad_facturada'), 'cantidad_facturada', posicion) or 0.0
    linea.update({
        'tipo': celdas.get('tipo_producto', ''), 'entregada': entregada, 'facturada': facturada,
        'pend_entregar': _pendiente(celdas, 'pendiente_entregar', linea['cantidad'], entregada),
        'pend_facturar': _pendiente(celdas, 'pendiente_facturar', linea['cantidad'], facturada)})
    return linea


def _linea_de_compra(celdas, posicion):
    linea = _linea_comun(celdas, posicion)
    recibida = numero(celdas.get('cantidad_recibida'), 'cantidad_recibida', posicion) or 0.0
    facturada = numero(celdas.get('cantidad_facturada'), 'cantidad_facturada', posicion) or 0.0
    linea.update({
        'recibida': recibida, 'facturada': facturada,
        'pend_recibir': _pendiente(celdas, 'pendiente_recibir', linea['cantidad'], recibida),
        'pend_facturar': _pendiente(celdas, 'pendiente_facturar', linea['cantidad'], facturada)})
    return linea


def filas_ventas_pendientes(texto_ordenes, texto_lineas):
    """``(ordenes, errores)`` de ventas_pendientes.csv y ventas_pendientes_lineas.csv.

    Cada orden: ``numero``, ``id_contacto`` (el cliente), ``fecha``, ``total`` y ``lineas`` con ``codigo``, ``nombre``,
    ``tipo``, ``cantidad``, ``precio``, ``descuento``, ``entregada``, ``facturada``, ``pend_entregar`` y
    ``pend_facturar``.
    """
    return _ordenes(texto_ordenes, texto_lineas, 'ventas_pendientes.csv', 'ventas_pendientes_lineas.csv',
                    COLUMNAS_VENTAS, 'id_cliente_viejo', _linea_de_venta)


def filas_compras_pendientes(texto_ordenes, texto_lineas):
    """``(ordenes, errores)`` de compras_pendientes.csv y compras_pendientes_lineas.csv (el contacto es el proveedor;
    ``referencia`` es la del proveedor; cada línea trae ``recibida``, ``facturada``, ``pend_recibir`` y
    ``pend_facturar``)."""
    return _ordenes(texto_ordenes, texto_lineas, 'compras_pendientes.csv', 'compras_pendientes_lineas.csv',
                    COLUMNAS_COMPRAS, 'id_proveedor_viejo', _linea_de_compra)


# ----------------------------------------------------------------------------------------------
# Productos y existencias
# ----------------------------------------------------------------------------------------------

def existencias_por_codigo(texto):
    """``({código: cantidad total}, [cantidades de las filas sin código])`` de inventario.csv.

    Las cantidades de un mismo código se suman (varias bodegas). Una fila sin código no se puede enlazar con ningún
    producto: sus cantidades salen aparte para contarlas a mano.
    """
    por_codigo, sin_codigo = {}, []
    for posicion, celdas in enumerate(leer_csv(texto, COLUMNAS_INVENTARIO, 'inventario.csv'), start=2):
        cantidad = numero(celdas.get('cantidad'), 'cantidad', posicion)
        if cantidad is None:
            continue
        codigo = celdas.get('codigo_producto', '')
        if codigo:
            por_codigo[codigo] = por_codigo.get(codigo, 0.0) + cantidad
        else:
            sin_codigo.append(cantidad)
    return por_codigo, sin_codigo


def filas_catalogo(texto_productos, texto_inventario=None):
    """``(filas, avisos)`` para la carga del inventario anterior (``dcasa_catalogo``), de productos.csv e
    inventario.csv.

    * Solo los productos activos; los archivados se cuentan y no se cargan.
    * Un precio o un costo en 0 (o vacío) quiere decir «no se registró»: no se usa (un costo 0 jamás borra el real).
    * Un producto con código recibe sus existencias (0 si no aparece en el inventario). Uno sin código no recibe
      ninguna: su existencia no se puede enlazar y se cuenta a mano.
    * Sin inventario.csv no se toca ninguna existencia.
    ``avisos``: ``archivados``, ``sin_codigo`` (productos activos sin código), ``existencias_sin_codigo`` (cantidades de
    filas del inventario sin código), ``huerfanos`` (códigos con existencias que no son un producto activo) y
    ``decimales`` (los llena la carga: existencias con decimales que se redondean a unidades enteras).
    """
    existencias = None
    sin_codigo_inventario = []
    if texto_inventario is not None:
        existencias, sin_codigo_inventario = existencias_por_codigo(texto_inventario)
    avisos = {'archivados': 0, 'sin_codigo': [], 'existencias_sin_codigo': sin_codigo_inventario, 'huerfanos': [],
              'decimales': []}
    filas, codigos_activos = [], set()
    for posicion, celdas in enumerate(leer_csv(texto_productos, COLUMNAS_PRODUCTOS, 'productos.csv'), start=2):
        nombre = re.sub(r'\s+', ' ', celdas.get('nombre', '')).strip()
        if not nombre:
            continue
        if not si_o_no(celdas.get('activo'), por_defecto=True):
            avisos['archivados'] += 1
            continue
        codigo = celdas.get('codigo', '')
        precio = numero(celdas.get('precio_de_venta'), 'precio_de_venta', posicion)
        costo = numero(celdas.get('costo'), 'costo', posicion)
        if codigo:
            codigos_activos.add(codigo)
        else:
            avisos['sin_codigo'].append(nombre)
        filas.append({
            'pagina': None,
            'fila': posicion,
            'nombre': nombre,
            'codigo': codigo,
            'llave': codigo or nombre,
            'precio': precio or None,
            'costo': costo or None,
            'a_la_mano': (existencias.get(codigo, 0.0) if codigo else None) if existencias is not None else None,
            'dudas': '',
            'clase': clase_de_fila_inventario(nombre),
        })
    if existencias is not None:
        avisos['huerfanos'] = sorted((c, q) for c, q in existencias.items() if c not in codigos_activos)
    return filas, avisos
