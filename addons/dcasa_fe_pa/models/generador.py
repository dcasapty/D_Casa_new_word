"""Generador del documento electrónico rFE (XML) a partir de un dict neutro.

Python puro (lxml), sin Odoo. ``account.move._l10n_pa_fe_datos()`` arma el dict; aquí
solo se escribe el XML en el orden de la Ficha Técnica.

ESTRUCTURA: los nombres de los elementos y el orden de ``gDGen`` (iAmb, iTpEmis, iDoc, dNroDF,
dPtoFacDF, dFechaEm, iNatOp, iTipoOp, iDest, iFormCAFE, iEntCAFE, dEnvFE, iProGen, dInfEmFE,
gEmis, gDatRec), ``gItem`` (dSecItem, dDescProd, dCodProd, dCantCodInt, gPrecios…) y ``gTot``
coinciden en dos fuentes secundarias independientes (ver docs/FACTURA_ELECTRONICA.md). El resto
del orden y los grupos de referencia (gDFRef) y de pago son SEGÚN FUENTE SECUNDARIA y quedan
por validar contra ``FE_v1.00.xsd`` (``validar_xsd``) cuando se tenga el paquete oficial.

La firma digital (XMLDSig) NO se hace aquí: en el modelo con PAC la firma la pone el PAC o el
emisor con su certificado según el contrato; queda como punto de extensión del adaptador.
"""
import os

from lxml import etree

from . import catalogos as C

RUTA_XSD = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'xsd', 'FE_v1.00.xsd')


def monto(valor, decimales=2):
    """123.4 → '123.40'; para precios unitarios admite hasta 6 decimales sin ceros sobrantes."""
    texto = f'{round(float(valor or 0.0), decimales):.{decimales}f}'
    if decimales > 2:
        entero, fraccion = texto.split('.')
        fraccion = fraccion.rstrip('0').ljust(2, '0')
        texto = f'{entero}.{fraccion}'
    return texto


def _q(nombre):
    return f'{{{C.NAMESPACE}}}{nombre}'


def _hijo(padre, nombre, valor=None):
    nodo = etree.SubElement(padre, _q(nombre))
    if valor is not None:
        nodo.text = str(valor)
    return nodo


def _opcional(padre, nombre, valor):
    if valor not in (None, '', False):
        _hijo(padre, nombre, valor)


def _ruc(padre, nombre, datos):
    grupo = _hijo(padre, nombre)
    _hijo(grupo, 'dTipoRuc', datos['tipo_ruc'])
    _hijo(grupo, 'dRuc', datos['ruc'])
    _hijo(grupo, 'dDV', datos['dv'])
    return grupo


def _ubicacion(padre, nombre, ubicacion):
    if not ubicacion:
        return
    grupo = _hijo(padre, nombre)
    _hijo(grupo, 'dCodUbi', ubicacion['codigo'])
    _hijo(grupo, 'dCorreg', ubicacion['corregimiento'])
    _hijo(grupo, 'dDistr', ubicacion['distrito'])
    _hijo(grupo, 'dProv', ubicacion['provincia'])


def _general(raiz, gen):
    grupo = _hijo(raiz, 'gDGen')
    for campo in ('iAmb', 'iTpEmis'):
        _hijo(grupo, campo, gen[campo])
    _opcional(grupo, 'dFechaCont', gen.get('dFechaCont'))
    _opcional(grupo, 'dMotCont', gen.get('dMotCont'))
    for campo in ('iDoc', 'dNroDF', 'dPtoFacDF', 'dSeg', 'dFechaEm'):
        _hijo(grupo, campo, gen[campo])
    for campo in ('iNatOp', 'iTipoOp', 'iDest', 'iFormCAFE', 'iEntCAFE', 'dEnvFE', 'iProGen'):
        _hijo(grupo, campo, gen[campo])
    _opcional(grupo, 'iTipoTranVenta', gen.get('iTipoTranVenta'))
    _opcional(grupo, 'dInfEmFE', gen.get('dInfEmFE'))
    return grupo


def _emisor(grupo_general, emisor):
    grupo = _hijo(grupo_general, 'gEmis')
    _ruc(grupo, 'gRucEmi', emisor)
    _hijo(grupo, 'dNombEm', emisor['nombre'])
    _hijo(grupo, 'dSucEm', emisor['sucursal'])
    _opcional(grupo, 'dCoordEm', emisor.get('coordenadas'))
    _hijo(grupo, 'dDirecEm', emisor['direccion'])
    _ubicacion(grupo, 'gUbiEm', emisor.get('ubicacion'))
    for telefono in emisor.get('telefonos', [])[:3]:
        _hijo(grupo, 'dTfnEm', telefono)
    for correo in emisor.get('correos', [])[:3]:
        _hijo(grupo, 'dCorElectEmi', correo)


def _receptor(grupo_general, receptor):
    grupo = _hijo(grupo_general, 'gDatRec')
    _hijo(grupo, 'iTipoRec', receptor['tipo'])
    if receptor.get('ruc'):
        _ruc(grupo, 'gRucRec', receptor)
    _opcional(grupo, 'dNombRec', receptor.get('nombre'))
    _opcional(grupo, 'dDirecRec', receptor.get('direccion'))
    _ubicacion(grupo, 'gUbiRec', receptor.get('ubicacion'))
    if receptor.get('id_extranjero'):
        extranjero = _hijo(grupo, 'gIdExt')
        _hijo(extranjero, 'dIdExt', receptor['id_extranjero'])
        _opcional(extranjero, 'dPaisExt', receptor.get('pais_extranjero'))
    for telefono in receptor.get('telefonos', [])[:3]:
        _hijo(grupo, 'dTfnRec', telefono)
    for correo in receptor.get('correos', [])[:3]:
        _hijo(grupo, 'dCorElectRec', correo)
    _hijo(grupo, 'cPaisRec', receptor['pais'])


def _referencias(grupo_general, referencias):
    for referencia in referencias or []:
        grupo = _hijo(grupo_general, 'gDFRef')
        _ruc(grupo, 'gRucEmDFRef', referencia['emisor'])
        _hijo(grupo, 'dNombEmRef', referencia['emisor']['nombre'])
        _hijo(grupo, 'dFechaDFRef', referencia['fecha'])
        numero = _hijo(grupo, 'gDFRefNum')
        _hijo(_hijo(numero, 'gDFRefFE'), 'dCUFERef', referencia['cufe'])


def _item(raiz, item):
    grupo = _hijo(raiz, 'gItem')
    _hijo(grupo, 'dSecItem', item['secuencia'])
    _hijo(grupo, 'dDescProd', item['descripcion'])
    _opcional(grupo, 'dCodProd', item.get('codigo'))
    _opcional(grupo, 'cUnidad', item.get('unidad'))
    _hijo(grupo, 'dCantCodInt', monto(item['cantidad'], 6))
    if item.get('cpbs'):
        _hijo(grupo, 'dCodCPBSabr', item['cpbs'][:2])
        _hijo(grupo, 'dCodCPBScmp', item['cpbs'])
    precios = _hijo(grupo, 'gPrecios')
    _hijo(precios, 'dPrUnit', monto(item['precio_unitario'], 6))
    if item.get('descuento_unitario'):
        _hijo(precios, 'dPrUnitDesc', monto(item['descuento_unitario'], 6))
    _hijo(precios, 'dPrItem', monto(item['precio_item']))
    _hijo(precios, 'dValTotItem', monto(item['valor_total']))
    itbms = _hijo(grupo, 'gITBMSItem')
    _hijo(itbms, 'dTasaITBMS', item['tasa'])
    _hijo(itbms, 'dValITBMS', monto(item['itbms']))


def _totales(raiz, tot):
    grupo = _hijo(raiz, 'gTot')
    _hijo(grupo, 'dTotNeto', monto(tot['neto']))
    _hijo(grupo, 'dTotITBMS', monto(tot['itbms']))
    _hijo(grupo, 'dTotGravado', monto(tot['gravado']))
    if tot.get('descuento'):
        _hijo(grupo, 'dTotDesc', monto(tot['descuento']))
    _hijo(grupo, 'dVTot', monto(tot['total']))
    _hijo(grupo, 'dTotRec', monto(tot['recibido']))
    _hijo(grupo, 'dVuelto', monto(tot.get('vuelto', 0.0)))
    _hijo(grupo, 'iPzPag', tot['tiempo_pago'])
    _hijo(grupo, 'dNroItems', tot['nro_items'])
    _hijo(grupo, 'dVTotItems', monto(tot['total_items']))
    for forma in tot['formas_pago']:
        pago = _hijo(grupo, 'gFormaPago')
        _hijo(pago, 'iFormaPago', forma['codigo'])
        _opcional(pago, 'dFormaPagoDesc', forma.get('descripcion'))
        _hijo(pago, 'dVlrCuota', monto(forma['valor']))
    for plazo in tot.get('plazos', []):
        cuota = _hijo(grupo, 'gPagPlazo')
        _hijo(cuota, 'dSecItem', plazo['secuencia'])
        _hijo(cuota, 'dFecItPlazo', plazo['fecha'])
        _hijo(cuota, 'dValItPlazo', monto(plazo['valor']))


def generar_xml(datos):
    """dict neutro → bytes del rFE (UTF-8, sin firma)."""
    raiz = etree.Element(_q('rFE'), nsmap={None: C.NAMESPACE})
    _hijo(raiz, 'dVerForm', datos.get('version', C.VERSION_FORMATO))
    _hijo(raiz, 'dId', datos['cufe'])
    general = _general(raiz, datos['gen'])
    _emisor(general, datos['emisor'])
    _receptor(general, datos['receptor'])
    _referencias(general, datos.get('referencias'))
    for item in datos['items']:
        _item(raiz, item)
    _totales(raiz, datos['totales'])
    return etree.tostring(raiz, xml_declaration=True, encoding='UTF-8', pretty_print=True)


def validar_xsd(xml, ruta=RUTA_XSD):
    """Valida contra el XSD oficial si está en ``xsd/``.

    Devuelve ``None`` si no hay XSD (no se puede afirmar nada), ``[]`` si valida o la lista
    de errores del esquema.
    """
    if not ruta or not os.path.exists(ruta):
        return None
    esquema = etree.XMLSchema(etree.parse(ruta))
    documento = etree.fromstring(xml)
    if esquema.validate(documento):
        return []
    return [f'línea {error.line}: {error.message}' for error in esquema.error_log]
