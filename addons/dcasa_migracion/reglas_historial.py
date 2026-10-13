"""Lectura de las facturas y los pagos del año (``receta\\exportar_facturas.py``), sin base de datos.

Cinco archivos: ``facturas_clientes.csv`` y ``facturas_clientes_lineas.csv``, ``facturas_proveedores.csv`` y
``facturas_proveedores_lineas.csv``, y ``pagos.csv``. Los montos de una nota de crédito vienen en positivo: lo que dice
que resta es la columna ``tipo`` (``nota_credito``). Una celda vacía significa «ese dato no existe en el sistema
anterior». Aquí solo se revisa que cada fila se pueda leer; que los totales cuadren lo revisa la carga contra Odoo.
"""
import hashlib
import re

from .reglas import _fecha, leer_csv, numero

COLUMNAS_FACTURAS = {'cliente': ('numero', 'id_cliente_viejo', 'total'),
                     'proveedor': ('numero', 'id_proveedor_viejo', 'total')}
COLUMNAS_FACTURAS_LINEAS = ('numero', 'cantidad', 'precio_unitario')
COLUMNAS_PAGOS = ('fecha', 'tipo', 'id_contacto_viejo', 'monto')
ARCHIVOS = {'cliente': ('facturas_clientes.csv', 'facturas_clientes_lineas.csv'),
            'proveedor': ('facturas_proveedores.csv', 'facturas_proveedores_lineas.csv')}
TIPOS_DE_FACTURA = {'': False, 'factura': False, 'nota_credito': True}
TIPOS_DE_PAGO = {'cobro': 'cliente', 'pago': 'proveedor'}


def xmlid_factura(numero_de_factura):
    """El id externo de una factura cargada: el número que tenía en el sistema anterior, sin barras."""
    return 'dcasa_factura_' + re.sub(r'[^A-Za-z0-9_]', '_', numero_de_factura)


def _montos(celdas, columnas, fila):
    return {c: (numero(celdas.get(c), c, fila) or 0.0) for c in columnas}


def _linea(celdas, fila):
    cantidad = numero(celdas.get('cantidad'), 'cantidad', fila)
    precio = numero(celdas.get('precio_unitario'), 'precio_unitario', fila)
    return {
        'codigo': celdas.get('codigo_producto', ''), 'nombre': re.sub(r'\s+', ' ', celdas.get('nombre_producto', '')),
        'cantidad': 0.0 if cantidad is None else cantidad, 'precio': 0.0 if precio is None else precio,
        'descuento': numero(celdas.get('descuento'), 'descuento', fila) or 0.0,
        'impuesto': celdas.get('impuesto', ''), 'subtotal': numero(celdas.get('subtotal'), 'subtotal', fila),
        'cuenta': celdas.get('cuenta_ingreso') or celdas.get('cuenta_gasto') or '',
    }


def _factura(celdas, fila, rol):
    """La factura de una fila, o ``(None, motivo)`` si no se puede leer."""
    numero_de_factura = celdas.get('numero', '')
    columna_contacto = COLUMNAS_FACTURAS[rol][1]
    contacto = celdas.get(columna_contacto, '')
    if not numero_de_factura:
        return None, 'le falta el número de factura'
    if not contacto.isdigit():
        return None, f'el número del {rol} no es un entero (columna {columna_contacto})'
    tipo = celdas.get('tipo', '').lower()
    if tipo not in TIPOS_DE_FACTURA:
        return None, f'el tipo «{tipo}» no es factura ni nota_credito'
    try:
        fecha, vencimiento = _fecha(celdas.get('fecha', '')), _fecha(celdas.get('fecha_vencimiento', ''))
    except ValueError:
        return None, 'una fecha está mal escrita (AAAA-MM-DD)'
    if not fecha:
        return None, 'le falta la fecha'
    montos = _montos(celdas, ('base_imponible', 'impuesto', 'total', 'pagado', 'saldo'), fila)
    return {
        'numero': numero_de_factura, 'nota': TIPOS_DE_FACTURA[tipo], 'fecha': fecha, 'vencimiento': vencimiento,
        'id_contacto': int(contacto), 'moneda': celdas.get('moneda', '').upper(), 'base': montos['base_imponible'],
        'impuesto': montos['impuesto'], 'total': montos['total'], 'pagado': montos['pagado'],
        'saldo': montos['saldo'], 'estado_pago': celdas.get('estado_pago', ''), 'diario': celdas.get('diario', ''),
        'origen': celdas.get('orden_origen', ''),
        'referencia': celdas.get('referencia_fiscal') or celdas.get('referencia_proveedor') or '',
        'original': celdas.get('factura_original', ''), 'condicion': celdas.get('condicion_pago', ''),
        'lineas': [],
    }, None


def filas_facturas(texto_facturas, texto_lineas, rol):
    """``(facturas, errores)`` de las facturas de ``rol`` (``'cliente'`` o ``'proveedor'``) con sus líneas.

    Cada factura: ``numero``, ``nota`` (True si es nota de crédito), ``fecha``, ``vencimiento``, ``id_contacto``,
    ``moneda``, ``base``, ``impuesto``, ``total``, ``pagado``, ``saldo``, ``origen`` (orden de venta o de compra),
    ``referencia`` (número fiscal o el del proveedor), ``original`` (la factura que corrige una nota) y ``lineas``
    con ``codigo``, ``nombre``, ``cantidad``, ``precio``, ``descuento``, ``impuesto`` (el nombre del impuesto) y
    ``cuenta``. Un error es ``(numero, motivo)``: la factura se salta y las demás siguen. Una factura sin líneas
    también es un error (no hay con qué armarla).
    """
    nombre_cabecera, nombre_lineas = ARCHIVOS[rol]
    facturas, errores, por_numero, rechazadas = [], [], {}, set()
    for posicion, celdas in enumerate(leer_csv(texto_facturas, COLUMNAS_FACTURAS[rol], nombre_cabecera), start=2):
        factura, motivo = _factura(celdas, posicion, rol)
        numero_de_factura = celdas.get('numero', '')
        if factura is None:
            errores.append((numero_de_factura or f'fila {posicion}', motivo))
            rechazadas.add(numero_de_factura)
        elif numero_de_factura in por_numero:
            errores.append((numero_de_factura, 'la factura aparece dos veces'))
        else:
            por_numero[numero_de_factura] = factura
            facturas.append(factura)
    for posicion, celdas in enumerate(leer_csv(texto_lineas, COLUMNAS_FACTURAS_LINEAS, nombre_lineas), start=2):
        numero_de_factura = celdas.get('numero', '')
        factura = por_numero.get(numero_de_factura)
        if factura is not None:
            factura['lineas'].append(_linea(celdas, posicion))
        elif numero_de_factura not in rechazadas:
            errores.append((numero_de_factura or f'fila {posicion}',
                            f'una línea de {nombre_lineas} no tiene su factura en {nombre_cabecera}'))
    sin_lineas = [f for f in facturas if not f['lineas']]
    for factura in sin_lineas:
        errores.append((factura['numero'], f'la factura no tiene líneas en {nombre_lineas}'))
    return [f for f in facturas if f['lineas']], errores


def filas_pagos(texto):
    """``(pagos, errores)`` de pagos.csv. Cada pago: ``numero`` (el del sistema anterior, si el archivo trae la
    columna ``numero``), ``clave`` (única y estable: sirve de id externo; sale del número y, sin él, de los datos del
    pago), ``fecha``, ``rol`` (``'cliente'`` para un cobro, ``'proveedor'`` para un pago), ``id_contacto``, ``monto``
    (positivo), ``moneda``, ``diario`` (el nombre), ``metodo``, ``referencia``, ``facturas`` (los números que paga, en
    orden) y ``conciliado`` (True si el banco ya lo había conciliado; lo dudoso cuenta como sin conciliar). Un error
    es ``('fila N', motivo)``."""
    pagos, errores, vistos, numeros = [], [], {}, set()
    for posicion, celdas in enumerate(leer_csv(texto, COLUMNAS_PAGOS, 'pagos.csv'), start=2):
        etiqueta = f'fila {posicion}'
        tipo = celdas.get('tipo', '').lower()
        contacto = celdas.get('id_contacto_viejo', '')
        monto = numero(celdas.get('monto'), 'monto', posicion)
        try:
            fecha = _fecha(celdas.get('fecha', ''))
        except ValueError:
            fecha = None
        if tipo not in TIPOS_DE_PAGO:
            errores.append((etiqueta, f'el tipo «{tipo}» no es cobro ni pago'))
        elif not contacto.isdigit():
            errores.append((etiqueta, 'el número del contacto no es un entero'))
        elif not fecha:
            errores.append((etiqueta, 'la fecha falta o está mal escrita (AAAA-MM-DD)'))
        elif monto is None or monto <= 0:
            errores.append((etiqueta, 'el monto falta o no es mayor que cero'))
        else:
            facturas = [f.strip() for f in celdas.get('facturas_que_paga', '').split('|') if f.strip()]
            numero_del_pago = celdas.get('numero') or celdas.get('numero_pago', '')
            if numero_del_pago and numero_del_pago in numeros:
                errores.append((etiqueta, f'el pago {numero_del_pago} aparece dos veces'))
                continue
            numeros.add(numero_del_pago)
            if numero_del_pago:
                clave = re.sub(r'[^A-Za-z0-9_]', '_', numero_del_pago)
            else:
                huella = '|'.join([fecha, tipo, contacto, f'{monto:.2f}', celdas.get('diario', ''),
                                   celdas.get('referencia', ''), '|'.join(facturas)])
                base = hashlib.sha1(huella.encode(), usedforsecurity=False).hexdigest()[:20]
                vistos[base] = vistos.get(base, 0) + 1
                clave = f'{base}_{vistos[base]}'
            pagos.append({
                'numero': numero_del_pago, 'clave': clave, 'fecha': fecha, 'rol': TIPOS_DE_PAGO[tipo],
                'id_contacto': int(contacto), 'monto': monto, 'moneda': celdas.get('moneda', '').upper(),
                'diario': celdas.get('diario', ''), 'metodo': celdas.get('metodo', ''),
                'referencia': celdas.get('referencia', ''), 'facturas': facturas,
                'conciliado': celdas.get('estado', '').lower() == 'conciliado',
            })
    return pagos, errores

