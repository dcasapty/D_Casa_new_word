"""Carga de las facturas y los pagos del año del sistema anterior (``reglas_historial``).

Es la contabilidad: lo que entra queda **publicado**, con el número que la factura ya tenía (la numeración nueva sigue
desde el último), y cada pago queda enlazado a las facturas que pagaba. Reglas:

* Todo lo cargado lleva ``dcasa_historica``: es historia. No se manda a la DGI, no da puntos de Socios y no mueve la
  tienda. El número de factura electrónica no se carga (la exportación no lo trae).
* Una factura solo entra si Odoo la arma con los mismos importes del archivo (base, impuesto y total, con 2 centavos de
  tolerancia): si no cuadra, no entra y el informe dice cuánto difiere. Nada entra al libro con un total distinto.
* Las cuentas contables son las de aquí (la del producto, la del diario y la del cliente o proveedor). Equivalencias con
  las cuentas del sistema anterior: decisión del contador, todavía no se aplican.
* Un cobro o pago ya conciliado con el banco en el sistema anterior entra directo a la cuenta del banco; uno sin
  conciliar queda como pago en tránsito, esperando el extracto, igual que estaba.
* Cada documento guarda su número anterior como id externo (``__import__``): volver a cargar no repite nada. Los pagos
  no tienen número: su id sale de sus propios datos.
* Cada documento va en su propio savepoint, y la carga trabaja por **tandas** (``Presupuesto``): una factura o un pago
  tarda ~0.2 s, y una petición larga no es segura. Se pulsa «Cargar» las veces que haga falta.
"""
import logging
import re
import time

from odoo import fields
from odoo.addons.dcasa_base import itbms_de_venta
from odoo.exceptions import UserError
from odoo.tools import plaintext2html

from .contactos import _motivo
from .documentos import ERRORES, _contacto, _documento_ya_cargado, _registrar
from .precios import _producto
from .reglas_historial import xmlid_factura

_logger = logging.getLogger(__name__)

TOLERANCIA = 0.02
SEGUNDOS_POR_TANDA = 40
TIPOS_DE_MOVIMIENTO = {('cliente', False): 'out_invoice', ('cliente', True): 'out_refund',
                       ('proveedor', False): 'in_invoice', ('proveedor', True): 'in_refund'}
CONTEXTO = {'tracking_disable': True, 'mail_create_nolog': True, 'mail_notrack': True}


class Presupuesto:
    """Cuánto se puede trabajar en una petición: por segundos y, en las pruebas, por cantidad de documentos."""

    def __init__(self, segundos=None, documentos=None):
        self._limite = None if segundos is None else time.monotonic() + segundos
        self._documentos = documentos

    def agotado(self):
        if self._documentos is not None and self._documentos <= 0:
            return True
        return self._limite is not None and time.monotonic() > self._limite

    def gastar(self):
        if self._documentos is not None:
            self._documentos -= 1


def _resumen():
    return {'creados': [], 'ya_estaban': [], 'con_error': [], 'para_revisar': [], 'faltan': 0}


# ----------------------------------------------------------------------------------------------
# Impuestos, monedas y diarios
# ----------------------------------------------------------------------------------------------

def _impuesto(env, texto, rol, memoria):
    """Los impuestos de una línea a partir del nombre que tenía en el sistema anterior. Vacío = sin impuesto. El
    nombre exacto, o cualquier «ITBMS 7%», es el ITBMS de la empresa; otro nombre es un error que dice cuál."""
    texto = (texto or '').strip()
    if texto in memoria:
        return memoria[texto]
    impuesto = env['account.tax']
    if texto:
        impuesto = env['account.tax'].search([
            ('name', '=', texto), ('type_tax_use', '=', 'sale' if rol == 'cliente' else 'purchase'),
            ('company_id', '=', env.company.id)], limit=1)
        if not impuesto and re.search(r'itbms\s*7\s*%', texto, re.IGNORECASE):
            impuesto = itbms_de_venta(env, env.company) if rol == 'cliente' else env.company.account_purchase_tax_id
        if not impuesto:
            raise UserError(f'el impuesto «{texto}» no existe aquí (crea uno con ese nombre o cámbialo en el archivo)')
    memoria[texto] = impuesto
    return impuesto


def _moneda(env, codigo):
    moneda = env.company.currency_id
    if codigo and codigo != moneda.name:
        moneda = env['res.currency'].with_context(active_test=False).search([('name', '=', codigo)], limit=1)
        if not moneda:
            raise UserError(f'no conozco la moneda {codigo}')
    return moneda


def _diarios(env):
    """Los diarios de banco y efectivo por nombre (sin mayúsculas): ahí caen los cobros y pagos."""
    diarios = env['account.journal'].search([('type', 'in', ('bank', 'cash')), ('company_id', '=', env.company.id)])
    return {diario.name.strip().lower(): diario for diario in diarios}


# ----------------------------------------------------------------------------------------------
# Facturas
# ----------------------------------------------------------------------------------------------

def _cuadrar(movimiento, factura):
    """Odoo debe haber armado los mismos importes que el archivo; si no, la factura no entra."""
    moneda = movimiento.currency_id
    for nombre, esperado, aqui in (('la base', factura['base'], movimiento.amount_untaxed),
                                   ('el impuesto', factura['impuesto'], movimiento.amount_tax),
                                   ('el total', factura['total'], movimiento.amount_total)):
        if abs(esperado - aqui) > TOLERANCIA:
            raise UserError(f'{nombre} no cuadra: el archivo dice {moneda.format(esperado)} y aquí salió '
                            f'{moneda.format(aqui)}')


def _crear_factura(env, Movimiento, factura, rol, contacto, memoria):
    lineas = []
    for linea in factura['lineas']:
        impuestos = _impuesto(env, linea['impuesto'], rol, memoria)
        _plantilla, variante = _producto(env, linea)
        valores = {
            'name': linea['nombre'] or linea['codigo'] or 'Producto del sistema anterior',
            'quantity': linea['cantidad'], 'price_unit': linea['precio'], 'discount': linea['descuento'],
            'tax_ids': [(6, 0, impuestos.ids)]}
        if variante:
            valores['product_id'] = variante.id
        lineas.append((0, 0, valores))
    valores = {
        'move_type': TIPOS_DE_MOVIMIENTO[(rol, factura['nota'])], 'partner_id': contacto, 'name': factura['numero'],
        'date': factura['fecha'], 'invoice_date': factura['fecha'],
        'invoice_date_due': factura['vencimiento'] or factura['fecha'], 'ref': factura['referencia'] or False,
        'invoice_origin': factura['origen'] or False, 'currency_id': _moneda(env, factura['moneda']).id,
        'narration': plaintext2html(f'Cargada del sistema anterior: {factura["numero"]}.'),
        'dcasa_historica': True, 'invoice_line_ids': lineas}
    if factura['nota'] and factura['original']:
        original = _documento_ya_cargado(env, 'account.move', xmlid_factura(factura['original']))
        if original:
            valores['reversed_entry_id'] = original.id
    movimiento = Movimiento.create(valores)
    movimiento.action_post()
    _cuadrar(movimiento, factura)
    return movimiento


def cargar_facturas(env, facturas, rol, presupuesto):
    """Publica las facturas (primero las facturas, al final las notas de crédito). Devuelve ``{'creados': [numero],
    'ya_estaban': [numero], 'con_error': [(numero, motivo)], 'para_revisar': [(numero, motivo)], 'faltan': n}``:
    ``para_revisar`` son facturas que SÍ entraron pero conviene mirar (total 0 o con fecha futura) y ``faltan``
    cuántas quedaron sin intentar porque se acabó el presupuesto de la tanda. No hace commit."""
    Movimiento = env['account.move'].with_context(**CONTEXTO)
    memoria, resumen, hoy = {}, _resumen(), fields.Date.context_today(env['account.move'])
    for factura in sorted(facturas, key=lambda f: f['nota']):
        numero = factura['numero']
        nombre = xmlid_factura(numero)
        if _documento_ya_cargado(env, 'account.move', nombre):
            resumen['ya_estaban'].append(numero)
            continue
        if presupuesto.agotado():
            resumen['faltan'] += 1
            continue
        presupuesto.gastar()
        contacto = _contacto(env, factura['id_contacto'])
        if not contacto:
            resumen['con_error'].append((numero, f'el {rol} n.º {factura["id_contacto"]} no está cargado: carga '
                                                 f'primero {"clientes" if rol == "cliente" else "proveedores"}.csv'))
            continue
        try:
            with env.cr.savepoint():
                movimiento = _crear_factura(env, Movimiento, factura, rol, contacto, memoria)
                _registrar(env, nombre, movimiento)
        except ERRORES as error:
            resumen['con_error'].append((numero, _motivo(error)))
            continue
        resumen['creados'].append(numero)
        if not factura['total']:
            resumen['para_revisar'].append((numero, 'total 0'))
        if fields.Date.to_date(factura['fecha']) > hoy:
            resumen['para_revisar'].append((numero, f'fecha futura ({factura["fecha"]})'))
    _logger.info('Carga de facturas de %ss: %s creadas, %s ya estaban, %s con error, %s por cargar.', rol,
                 len(resumen['creados']), len(resumen['ya_estaban']), len(resumen['con_error']), resumen['faltan'])
    return resumen


# ----------------------------------------------------------------------------------------------
# Pagos
# ----------------------------------------------------------------------------------------------

def rotulo_de_pago(pago):
    """Cómo se nombra un pago en el informe (no tiene número): fecha, monto y su referencia."""
    return f'{pago["fecha"]} · {pago["monto"]:.2f} · {pago["referencia"] or pago["diario"]}'


def _conciliar(env, pago, datos):
    """Aplica el pago a las facturas que decía pagar y devuelve los números que no están cargados. Solo se aplica
    contra facturas publicadas de la misma ficha y de la misma cuenta por cobrar o por pagar."""
    facturas, faltan = env['account.move'], []
    for numero in datos['facturas']:
        movimiento = _documento_ya_cargado(env, 'account.move', xmlid_factura(numero))
        if movimiento:
            facturas |= movimiento
        else:
            faltan.append(numero)
    destino = pago.destination_account_id
    ficha = pago.partner_id.commercial_partner_id
    lineas_del_pago = pago.move_id.line_ids.filtered(lambda linea: linea.account_id == destino and not linea.reconciled)
    lineas_de_facturas = facturas.filtered(
        lambda m: m.state == 'posted' and m.commercial_partner_id == ficha
    ).line_ids.filtered(lambda linea: linea.account_id == destino and not linea.reconciled)
    if lineas_del_pago and lineas_de_facturas:
        (lineas_del_pago | lineas_de_facturas).reconcile()
    return faltan


def _crear_pago(env, Pago, datos, contacto, diario):
    cobro = datos['rol'] == 'cliente'
    memo = ' · '.join(filter(None, [datos['referencia'], f'Método: {datos["metodo"]}' if datos['metodo'] else '',
                                    'Cargado del sistema anterior']))
    valores = {
        'payment_type': 'inbound' if cobro else 'outbound', 'partner_type': 'customer' if cobro else 'supplier',
        'partner_id': contacto, 'amount': datos['monto'], 'date': datos['fecha'], 'journal_id': diario.id,
        'currency_id': _moneda(env, datos['moneda']).id, 'memo': memo}
    pago = Pago.create(valores)
    if datos['conciliado'] and diario.default_account_id:
        # Ya estaba conciliado con el banco: va directo a la cuenta del banco, sin pasar por pagos en tránsito. Se
        # escribe después de crear (Odoo recalcula la cuenta en tránsito al crear el pago).
        pago.outstanding_account_id = diario.default_account_id
    pago.action_post()
    return pago


def cargar_pagos(env, pagos, presupuesto):
    """Publica los cobros y pagos y los aplica a sus facturas. Devuelve lo mismo que ``cargar_facturas`` (con el
    rótulo del pago en lugar del número) y, además, ``sin_facturas`` (cuántos no dicen qué pagan: quedan como saldo a
    favor) y ``facturas_no_cargadas`` (``[(rótulo, [números])]``: pagos que citan facturas que no están aquí). Un
    pago que ya estaba y quedó a medias se vuelve a aplicar. No hace commit."""
    Pago = env['account.payment'].with_context(**CONTEXTO)
    diarios, resumen = _diarios(env), _resumen()
    resumen.update({'sin_facturas': 0, 'facturas_no_cargadas': []})
    for datos in pagos:
        rotulo = rotulo_de_pago(datos)
        nombre = f'dcasa_pago_{datos["clave"]}'
        existente = _documento_ya_cargado(env, 'account.payment', nombre)
        if existente:
            resumen['ya_estaban'].append(rotulo)
            if datos['facturas'] and not existente.is_reconciled:
                _conciliar(env, existente, datos)
            continue
        if presupuesto.agotado():
            resumen['faltan'] += 1
            continue
        presupuesto.gastar()
        contacto = _contacto(env, datos['id_contacto'])
        diario = diarios.get(datos['diario'].strip().lower())
        if not contacto:
            resumen['con_error'].append((rotulo, f'el contacto n.º {datos["id_contacto"]} no está cargado'))
            continue
        if not diario:
            resumen['con_error'].append((rotulo, f'no hay un diario de banco o efectivo llamado «{datos["diario"]}»'))
            continue
        try:
            with env.cr.savepoint():
                pago = _crear_pago(env, Pago, datos, contacto, diario)
                faltan = _conciliar(env, pago, datos)
                _registrar(env, nombre, pago)
        except ERRORES as error:
            resumen['con_error'].append((rotulo, _motivo(error)))
            continue
        resumen['creados'].append(rotulo)
        if not datos['facturas']:
            resumen['sin_facturas'] += 1
        if faltan:
            resumen['facturas_no_cargadas'].append((rotulo, faltan))
    _logger.info('Carga de pagos: %s creados, %s ya estaban, %s con error, %s por cargar.',
                 len(resumen['creados']), len(resumen['ya_estaban']), len(resumen['con_error']), resumen['faltan'])
    return resumen


# ----------------------------------------------------------------------------------------------
# Antes de empezar y al terminar
# ----------------------------------------------------------------------------------------------

def revisar_previa(env, facturas_clientes, facturas_proveedores, pagos):
    """Revisa TODO el archivo sin cargar nada (a diferencia del ensayo, que solo alcanza la primera tanda) y dice lo
    que va a fallar: ``contactos`` sin ficha, ``impuestos`` que no existen, ``diarios`` que no existen, ``productos``
    que no están en el catálogo (esas líneas entran sin producto) y ``facturas`` que citan los pagos y no están."""
    contactos, impuestos, diarios, productos, citadas = {}, {}, {}, {}, set()
    memoria, vistos, existentes = {}, {}, _diarios(env)
    por_numero = {f['numero'] for f in facturas_clientes + facturas_proveedores}
    for rol, facturas in (('cliente', facturas_clientes), ('proveedor', facturas_proveedores)):
        for factura in facturas:
            if not _contacto(env, factura['id_contacto']):
                contactos[(rol, factura['id_contacto'])] = contactos.get((rol, factura['id_contacto']), 0) + 1
            for linea in factura['lineas']:
                try:
                    _impuesto(env, linea['impuesto'], rol, memoria)
                except UserError as error:
                    impuestos[linea['impuesto']] = (str(error), impuestos.get(linea['impuesto'], ('', 0))[1] + 1)
                clave = linea['codigo'] or linea['nombre']
                if clave not in vistos:
                    vistos[clave] = bool(_producto(env, linea)[1])
                if not vistos[clave]:
                    productos[clave] = productos.get(clave, 0) + 1
    for pago in pagos:
        if not _contacto(env, pago['id_contacto']):
            contactos[(pago['rol'], pago['id_contacto'])] = contactos.get((pago['rol'], pago['id_contacto']), 0) + 1
        if pago['diario'].strip().lower() not in existentes:
            diarios[pago['diario']] = diarios.get(pago['diario'], 0) + 1
        citadas.update(n for n in pago['facturas'] if n not in por_numero)
    return {
        'contactos': sorted((rol, id_viejo, n) for (rol, id_viejo), n in contactos.items()),
        'impuestos': sorted((nombre, mensaje, n) for nombre, (mensaje, n) in impuestos.items()),
        'diarios': sorted(diarios.items()), 'productos': sorted(productos.items()),
        'facturas': sorted(n for n in citadas if not _documento_ya_cargado(env, 'account.move', xmlid_factura(n))),
    }


def cuadre(env, facturas):
    """Compara el archivo con lo que quedó en Odoo (solo las facturas ya cargadas). Devuelve ``{'cargadas': n,
    'archivo': {...}, 'aqui': {...}, 'saldos': [(numero, saldo del archivo, saldo aquí)], 'libro': x}``. Las notas de
    crédito restan. ``libro`` es lo que el libro mayor dice que deben (los clientes) o que se les debe (los
    proveedores) esas fichas: incluye los pagos que no se aplicaron a ninguna factura, por eso puede diferir de la suma
    de los saldos de las facturas."""
    cargadas = {}
    for factura in facturas:
        movimiento = _documento_ya_cargado(env, 'account.move', xmlid_factura(factura['numero']))
        if movimiento:
            cargadas[factura['numero']] = (factura, movimiento)
    archivo = dict.fromkeys(('base', 'impuesto', 'total', 'saldo'), 0.0)
    aqui = dict(archivo)
    saldos, fichas = [], env['res.partner']
    for factura, movimiento in cargadas.values():
        signo = -1 if factura['nota'] else 1
        for clave, valor in (('base', movimiento.amount_untaxed), ('impuesto', movimiento.amount_tax),
                             ('total', movimiento.amount_total), ('saldo', movimiento.amount_residual)):
            archivo[clave] += signo * factura[clave]
            aqui[clave] += signo * valor
        if abs(factura['saldo'] - movimiento.amount_residual) > TOLERANCIA:
            saldos.append((factura['numero'], factura['saldo'], movimiento.amount_residual))
        fichas |= movimiento.partner_id
    libro = 0.0
    if cargadas:
        por_cobrar = next(iter(cargadas.values()))[1].move_type.startswith('out_')
        lineas = env['account.move.line'].search([
            ('partner_id', 'in', fichas.ids), ('parent_state', '=', 'posted'), ('reconciled', '=', False),
            ('account_id.account_type', '=', 'asset_receivable' if por_cobrar else 'liability_payable')])
        libro = sum(lineas.mapped('amount_residual')) * (1 if por_cobrar else -1)
    return {'cargadas': len(cargadas), 'archivo': archivo, 'aqui': aqui, 'saldos': saldos, 'libro': libro}


def cargar_historial(env, leidos, presupuesto):
    """Todo el historial en su orden: facturas de clientes, de proveedores y, al final, los pagos (que se aplican a
    las facturas ya cargadas). ``leidos`` trae ``(filas, errores_de_filas)`` por archivo. Devuelve lo que muestra el
    informe: una entrada por parte, ``previa``, ``cuadre`` (solo cuando ya no falta nada) y ``faltan``."""
    def con_errores_de_filas(nombre, resumen):
        resumen['con_error'] = list(leidos[nombre][1]) + resumen['con_error']
        return resumen

    facturas = {'cliente': leidos.get('facturas_clientes', ([], []))[0],
                'proveedor': leidos.get('facturas_proveedores', ([], []))[0]}
    pagos = leidos.get('pagos', ([], []))[0]
    salida = {'previa': revisar_previa(env, facturas['cliente'], facturas['proveedor'], pagos)}
    for rol, nombre in (('cliente', 'facturas_clientes'), ('proveedor', 'facturas_proveedores')):
        if nombre in leidos:
            salida[nombre] = con_errores_de_filas(nombre, cargar_facturas(env, facturas[rol], rol, presupuesto))
    if 'pagos' in leidos:
        salida['pagos'] = con_errores_de_filas('pagos', cargar_pagos(env, pagos, presupuesto))
    partes = [salida[nombre] for nombre in ('facturas_clientes', 'facturas_proveedores', 'pagos') if nombre in salida]
    salida['faltan'] = sum(parte['faltan'] for parte in partes)
    if not salida['faltan']:
        salida['cuadre'] = {rol: cuadre(env, facturas[rol]) for rol in facturas if facturas[rol]}
    return salida

