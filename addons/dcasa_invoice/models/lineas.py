"""Cómo se lee una línea (de factura o de pedido) en un documento de D'CASA.

* El código va en su propia columna: la descripción no repite «[IM-2001] … / IM-2001».
* Flete, envío y servicios (armado, instalación) se imprimen en un bloque aparte,
  debajo de los muebles, para que el cliente vea qué pagó por el producto y qué por
  llevárselo a casa.

Qué es «flete / envío» (en este orden; basta con una):
1. El producto está en la categoría «Flete y envío» (``dcasa_invoice.categ_flete``) o en
   una hija suya.
2. Su referencia interna es ``DCASA-FLETE`` (producto de este módulo) o ``DCASA-ENTREGA``
   (el que usa la tienda web para las entregas).
3. Es el producto de un transportista (``delivery.carrier``), si el módulo está instalado.

Qué es «servicio»: cualquier producto de tipo servicio (Odoo ``type == 'service'``). El
flete es un servicio más; solo cambia el título del bloque. Cada línea decide si va aparte
con ``_dcasa_va_aparte()``; otros módulos lo cambian (el premio de Socios D'CASA es un
servicio, pero se queda entre los muebles porque es un descuento, no algo que se cobra).
"""
import re

CODIGOS_FLETE = ('DCASA-FLETE', 'DCASA-ENTREGA')
XMLID_CATEGORIA_FLETE = 'dcasa_invoice.categ_flete'

_CODIGO_DELANTE = re.compile(r'^\s*\[(?P<codigo>[^\]]+)\]\s*')


def codigo_y_descripcion(nombre, codigo_producto=None):
    """('IM-2001', 'COLCHON IMPERIAL TWIN') a partir de '[IM-2001] COLCHON IMPERIAL TWIN / IM-2001'.

    El código sale de la referencia interna del producto o, si no hay, del «[…]» con que
    Odoo arranca el nombre. La descripción no lo repite ni delante ni detrás.
    """
    texto = (nombre or '').strip()
    codigo = (codigo_producto or '').strip()
    coincidencia = _CODIGO_DELANTE.match(texto)
    if coincidencia:
        if not codigo:
            codigo = coincidencia.group('codigo').strip()
        if coincidencia.group('codigo').strip() == codigo:
            texto = texto[coincidencia.end():]
    if codigo:
        # «… / IM-2001» o «… - IM-2001» al final de la primera línea: el sistema anterior lo repetía.
        lineas = texto.split('\n')
        lineas[0] = re.sub(r'\s*[/\-–]\s*' + re.escape(codigo) + r'\s*$', '', lineas[0], flags=re.IGNORECASE)
        texto = '\n'.join(lineas)
    return codigo, texto.strip()


def quitar_referencia_delante(texto, referencia):
    """«[IM-2001] Colchón» → «Colchón» (solo si el texto empieza con la referencia dada, entre corchetes)."""
    texto = texto or ''
    referencia = (referencia or '').strip()
    prefijo = f'[{referencia}]'
    if referencia and texto.startswith(prefijo):
        return texto[len(prefijo):].lstrip()
    return texto



def quitar_nombre_repetido(descripcion, nombres):
    """La descripción de la entrega sin el nombre del producto delante, sin importar mayúsculas ni espacios.

    «[823QBR] Cama Queen  color Brown 823QBR» con el nombre «[823QBR] CAMA QUEEN COLOR BROWN 823QBR» → «»; si debajo
    alguien escribió «Armar en casa», queda eso. Odoo solo la omite si empieza EXACTAMENTE igual que el nombre, y la
    guardada puede traer el de antes (otras mayúsculas o espacios) o compararse con el nombre ya en formato título:
    la nota de entrega despachada imprimía el producto dos veces (caja, 2026-10-23)."""
    renglones = (descripcion or '').split('\n')
    palabras = renglones[0].split()
    comparables = [palabra.casefold() for palabra in palabras]
    for nombre in sorted({(nombre or '').strip() for nombre in nombres} - {''}, key=lambda n: len(n.split()),
                         reverse=True):
        del_nombre = [palabra.casefold() for palabra in nombre.split()]
        if comparables[:len(del_nombre)] == del_nombre:
            renglones[0] = ' '.join(palabras[len(del_nombre):])
            break
    return '\n'.join(renglones).strip()

def codigo_a_imprimir(empresa, producto, codigo_del_proveedor):
    """Lo que va en la columna «Código»: el del proveedor de siempre o, si la empresa enciende «Mostrar el código
    público…», el código público del producto (DC-K7M4PX). Sin código público (flete, servicios, líneas sin producto)
    queda vacío: nunca se muestra el del proveedor con el interruptor encendido."""
    if not empresa.dcasa_mostrar_codigo_publico:
        return codigo_del_proveedor
    return (producto.dcasa_codigo_publico or '') if producto else ''


def es_flete(producto):
    """True si el producto es flete o envío (ver el criterio arriba)."""
    if not producto:
        return False
    if (producto.default_code or '').strip().upper() in CODIGOS_FLETE:
        return True
    categoria = producto.env.ref(XMLID_CATEGORIA_FLETE, raise_if_not_found=False)
    if categoria and producto.categ_id and str(categoria.id) in producto.categ_id.parent_path.split('/'):
        return True
    if 'delivery.carrier' in producto.env:
        return bool(producto.env['delivery.carrier'].sudo().with_context(active_test=False).search_count(
            [('product_id', '=', producto.id)], limit=1))
    return False


def es_servicio(producto):
    return bool(producto) and producto.type == 'service'


def separar(lineas, es_producto):
    """(principales, servicios): las que van aparte se separan solo si hay algo que no lo haga.

    Las secciones y notas se quedan en la tabla principal. Si todo son servicios (una
    factura solo de flete, por ejemplo) no hay nada que separar.
    """
    servicios = lineas.filtered(lambda linea: es_producto(linea) and linea._dcasa_va_aparte())
    bienes = lineas.filtered(lambda linea: es_producto(linea) and not linea._dcasa_va_aparte())
    if not servicios or not bienes:
        return lineas, lineas.browse()
    return lineas - servicios, servicios


def titulo_servicios(lineas):
    fletes = [es_flete(linea.product_id) for linea in lineas]
    if all(fletes):
        return 'Flete y envío'
    if not any(fletes):
        return 'Servicios'
    return 'Flete y servicios'


def etiqueta_impuestos(impuestos):
    """Lo que va en la columna ITBMS: «7%» para un porcentaje; para otro tipo, la etiqueta del impuesto."""
    partes = []
    for impuesto in impuestos:
        if impuesto.amount_type == 'percent':
            partes.append(f'{impuesto.amount:g}%')
        else:
            partes.append(impuesto.tax_label or impuesto.name)
    return ', '.join(parte for parte in partes if parte)


def total_descuento(lineas, moneda, campo_cantidad='quantity'):
    """Lo que se rebajó en las líneas, sin impuesto: suma de cantidad × precio × descuento."""
    total = sum(linea.price_unit * linea[campo_cantidad] * linea.discount / 100.0
                for linea in lineas if linea.discount and linea.discount > 0)
    return moneda.round(total) if moneda else total
