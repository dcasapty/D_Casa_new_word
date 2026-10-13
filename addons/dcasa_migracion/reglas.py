"""Lectura de los CSV que deja la receta de migración (clientes, productos, inventario).

Funciones PURAS (sin base de datos): reciben el texto del archivo y devuelven filas ya limpias y los avisos que
hay que mostrar. Los archivos son UTF-8 (con BOM), separados por coma, con punto decimal y fechas AAAA-MM-DD. Una celda
vacía significa «ese dato no existe en el sistema anterior».
"""
import csv
import io
import re
from decimal import Decimal, InvalidOperation

from odoo.addons.dcasa_catalogo.reglas import clase_de_fila_inventario
from odoo.tools import email_normalize

COLUMNAS_CLIENTES = ('id_viejo', 'nombre')
COLUMNAS_PRODUCTOS = ('codigo', 'nombre')
COLUMNAS_INVENTARIO = ('codigo_producto', 'cantidad')

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


def leer_csv(texto, requeridas, nombre_del_archivo):
    """Las filas del CSV como diccionarios con las celdas sin espacios sobrantes.

    ``requeridas`` son las columnas sin las que no se puede cargar; faltar una es un error del archivo.
    """
    texto = (texto or '').lstrip('﻿')
    if not texto.strip():
        raise ErrorDeArchivo(f'{nombre_del_archivo} está vacío.')
    lector = csv.DictReader(io.StringIO(texto), delimiter=_delimitador(texto))
    columnas = [(c or '').strip().lower() for c in (lector.fieldnames or [])]
    faltan = [c for c in requeridas if c not in columnas]
    if faltan:
        raise ErrorDeArchivo(
            f'A {nombre_del_archivo} le falta la columna «{faltan[0]}». ¿Es el archivo correcto? '
            f'Las columnas que trae son: {", ".join(columnas) or "ninguna"}.')
    filas = []
    for fila in lector:
        filas.append({(k or '').strip().lower(): (v or '').strip() for k, v in fila.items() if k is not None})
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


def filas_clientes(texto):
    """``(filas, errores)`` de clientes.csv.

    Cada fila: ``id_viejo`` (entero), ``nombre``, ``es_empresa``, ``vat``, ``dv``, ``telefono``, ``correo``,
    ``direccion``, ``ciudad`` y ``notas`` (datos que no caben en su campo y se guardan en la nota de la ficha).
    Una fila sin nombre, con un número viejo que no es entero o repetido en el archivo, no se carga: va a ``errores``
    como ``(id_viejo, nombre, motivo)``.
    """
    filas, errores, vistos = [], [], set()
    for posicion, celdas in enumerate(leer_csv(texto, COLUMNAS_CLIENTES, 'clientes.csv'), start=2):
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
        telefono, otros = separar_telefonos(celdas.get('celular', ''))
        if otros:
            notas.append('Otros teléfonos en el sistema anterior: ' + ', '.join(otros))
        correo = celdas.get('correo', '')
        if correo and not email_normalize(correo, strict=False):
            notas.append(f'Correo mal escrito en el sistema anterior: {correo}')
            correo = ''
        dv = celdas.get('dv', '')
        if dv and not dv.isdigit():
            notas.append(f'DV mal escrito en el sistema anterior: {dv}')
            dv = ''
        filas.append({
            'id_viejo': id_viejo,
            'nombre': nombre,
            'es_empresa': celdas.get('tipo', '').lower() == 'empresa',
            'vat': celdas.get('cedula_ruc', ''),
            'dv': dv,
            'telefono': telefono,
            'correo': correo,
            'direccion': celdas.get('direccion', ''),
            'ciudad': celdas.get('ciudad', ''),
            'notas': notas,
        })
    return filas, errores


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
