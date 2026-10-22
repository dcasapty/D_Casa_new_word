"""«Reponer» (Compras › Reponer): cuánto pedirle a cada proveedor según el ritmo de venta y lo que tarda en llegar.

Pedido de la dueña (2026-10-19 y 22): todo viene de China y tarda de 3 a 4 meses; quiere saber, por producto, en
cuánto tiempo se queda sin él y cuánto pedir para cubrir la llegada. Una fila por producto vendido en las **facturas
publicadas** de los últimos N meses (1 a 12; de fábrica 5); las notas de crédito restan. Son las mismas unidades que
«Lo más vendido» del Inicio (``dcasa.tablero._unidades_por_producto`` sobre la base «Facturado»): sin servicios,
flete, anticipos ni líneas sin producto. Lo que no se vendió en la ventana no sale (la pantalla lo dice).

* **Se vende al mes** = vendido ÷ N.
* **Disponible hoy (sin lo ya vendido)** = lo que hay en las ubicaciones internas (``en_bodega``) − lo que espera
  entrega a clientes (``por_entregar``: movimientos de existencias de una ubicación interna a una de cliente, ni hechos,
  ni cancelados, ni en borrador; en una entrega en varios pasos solo cuenta el último, el que sale al cliente, y lo ya
  entregado ya salió de la bodega: nada se cuenta dos veces). Decisión de la dueña (2026-10-22): lo vendido que sigue
  en bodega «no está disponible a no ser que se revierta la entrega»; si se devuelve, vuelve a la bodega y cuenta
  solo. Puede dar negativo (se vendió más de lo que hay): se muestra así y suma a lo que hay que pedir.
  En el código, ``existencia`` es este disponible. **Viene en camino**: compras confirmadas que todavía no se reciben.
* **Alcanza para** = (disponible + en camino) ÷ se vende al mes, en meses (un mes = 30 días); 0 si da negativo.
* **Tarda en llegar**: los días de entrega (``delay``) del precio de proveedor principal (el primero del producto, el
  orden de Odoo). Odoo pone **1 día** de fábrica a todo precio de proveedor y la carga del sistema anterior pone 0 si
  no venía: por eso 0 o 1 día cuentan como **falta**, salvo que alguien lo haya puesto a propósito desde esta pantalla
  o desde Brian (``dcasa_llegada_puesta``). Sin el dato, la fila lo dice y **no** calcula cuánto pedir.
* **Pedir** = se vende al mes × (meses que tarda + meses de reserva) − disponible − en camino, hacia arriba, solo si da
  más de 0. **Pedir ya**: lo que hay y lo que viene no alcanza para lo que tarda en llegar un pedido nuevo.

Ninguna otra cifra: nada se rellena a ojo. Solo Gerencia y los administradores: cada método exige el grupo en el
servidor (``_exigir_gerencia``) ANTES de leer con sudo, y todo se filtra a las empresas de quien mira. La pantalla es
la acción cliente ``dcasa_reponer`` (``static/src/js/reponer.js``); el Excel lo arma el servidor
(``controllers/reponer.py``); Brian lee lo mismo (``que_reponer``) y pone el tiempo de llegada
(``poner_tiempo_llegada``).
"""
import io
import math
import re
import unicodedata
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .tablero import BASE_FACTURADO

GRUPOS_REPONER = ('dcasa_base.group_gerencia', 'base.group_system')
MESES_POR_DEFECTO = 5
MESES_MAXIMO = 12
RESERVA_MAXIMA = 12
DIAS_POR_MES = 30
LLEGADA_MAXIMA_DIAS = 730            # 24 meses
DIA_DE_FABRICA = 1                   # lo que Odoo pone solo en cada precio de proveedor
PROVEEDORES_A_LA_VISTA = 40

# De más urgente a menos: el orden de la lista y de los grupos.
ESTADOS = ('ya', 'pedir', 'falta', 'sin_proveedor', 'alcanza')
AVISOS = {
    'ya': 'Pedir ya',
    'pedir': 'Pedir',
    'falta': 'Falta el tiempo de llegada',
    'sin_proveedor': 'Sin proveedor',
    'alcanza': 'Alcanza',
}


def normalizar(texto):
    """Minúsculas y sin tildes, para buscar «Panamá» con «panama»."""
    texto = unicodedata.normalize('NFKD', str(texto or '').lower())
    return ''.join(letra for letra in texto if not unicodedata.combining(letra)).strip()


def cifra(valor):
    """``3`` → «3», ``2.5`` → «2.5» (punto decimal, como en Panamá)."""
    valor = round(valor, 1)
    return str(int(valor)) if valor == int(valor) else f'{valor:.1f}'


def tiempo_de_llegada(dias):
    """``90`` → «3 meses», ``45`` → «45 días», ``30`` → «1 mes», ``1`` → «1 día»."""
    if dias and dias % DIAS_POR_MES == 0:
        meses = dias // DIAS_POR_MES
        return '1 mes' if meses == 1 else f'{meses} meses'
    return '1 día' if dias == 1 else f'{dias} días'


def tiempo_que_alcanza(meses):
    """Para cuánto alcanza: «Ya no hay», «12 días», «1 mes», «2.5 meses», «más de 24 meses»."""
    if meses <= 0:
        return 'Ya no hay'
    if meses > 24:
        return 'más de 24 meses'
    dias = round(meses * DIAS_POR_MES)
    if dias < DIAS_POR_MES:
        return 'menos de 1 día' if dias < 1 else ('1 día' if dias == 1 else f'{dias} días')
    texto = cifra(meses)
    return '1 mes' if texto == '1' else f'{texto} meses'


class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

    dcasa_llegada_puesta = fields.Boolean(
        'Tiempo de llegada puesto a propósito', copy=False,
        help='Lo marca Compras › Reponer (o Brian) al guardar el tiempo de llegada del proveedor. Sin esta marca, '
             '0 o 1 día cuenta como «falta»: es lo que Odoo pone solo.')


class DcasaReponer(models.AbstractModel):
    _name = 'dcasa.reponer'
    _description = 'Reponer: cuánto pedirle al proveedor'

    # ------------------------------------------------------------------
    # Permisos y parámetros
    # ------------------------------------------------------------------

    @api.model
    def _exigir_gerencia(self):
        if not any(self.env.user.has_group(grupo) for grupo in GRUPOS_REPONER):
            raise AccessError(self.env._('«Reponer» es solo de Gerencia y los administradores.'))

    @api.model
    def _validar(self, meses, reserva):
        """``(meses, reserva)`` ya revisados: de 1 a 12 meses de ventas y de 0 a 12 meses de reserva."""
        try:
            meses = int(MESES_POR_DEFECTO if meses is None or meses is False or meses == '' else meses)
            reserva = float(str(0 if reserva is None or reserva is False or reserva == '' else reserva).replace(
                ',', '.'))
        except (TypeError, ValueError):
            raise UserError(self.env._('Revisa los meses: van en números.')) from None
        if not 1 <= meses <= MESES_MAXIMO:
            raise UserError(self.env._('Elige de 1 a %(maximo)s meses de ventas.', maximo=MESES_MAXIMO))
        if not math.isfinite(reserva) or not 0 <= reserva <= RESERVA_MAXIMA:
            raise UserError(self.env._('La reserva va de 0 a %(maximo)s meses.', maximo=RESERVA_MAXIMA))
        return meses, reserva

    @api.model
    def _ventana(self, meses, hasta=None):
        """Los últimos ``meses`` meses hasta ``hasta`` (hoy si no se dice), los dos días incluidos."""
        hasta = hasta or fields.Date.context_today(self)
        return hasta - relativedelta(months=meses) + timedelta(days=1), hasta

    @api.model
    def _proveedor(self, proveedor_id):
        """El proveedor elegido (``res.partner`` con sudo) o ``None`` («Todos»)."""
        if not proveedor_id:
            return None
        try:
            socio = self.env['res.partner'].sudo().browse(int(proveedor_id)).exists()
        except (TypeError, ValueError):
            socio = None
        if not socio:
            raise UserError(self.env._('Ese proveedor ya no existe: búscalo otra vez.'))
        return socio

    @api.model
    def _a_dias(self, cantidad, unidad):
        """``(3, 'meses')`` → 90; ``(45, 'dias')`` → 45. De 1 día a 24 meses."""
        try:
            numero = float(str(cantidad).replace(',', '.'))
        except (TypeError, ValueError):
            numero = float('nan')
        if unidad not in ('dias', 'meses') or not math.isfinite(numero) or numero <= 0:
            raise UserError(self.env._('Escribe cuánto tarda en llegar: un número de días o de meses.'))
        dias = round(numero * DIAS_POR_MES) if unidad == 'meses' else round(numero)
        if not 1 <= dias <= LLEGADA_MAXIMA_DIAS:
            raise UserError(self.env._('El tiempo de llegada va de 1 día a 24 meses.'))
        return dias

    @staticmethod
    def _dias_de_llegada(precio):
        """Los días que tarda en llegar según ese precio de proveedor, o ``None`` si falta (ver el docstring)."""
        if precio.dcasa_llegada_puesta or precio.delay > DIA_DE_FABRICA:
            return precio.delay
        return None

    # ------------------------------------------------------------------
    # El cálculo
    # ------------------------------------------------------------------

    @api.model
    def _empresas(self):
        return self.env.companies.ids

    @api.model
    def _principales(self, productos):
        """``{product.product id: product.supplierinfo}``: el precio de proveedor principal de cada variante, el
        primero de sus precios (el orden de Odoo), el de esa variante o el de todo el producto; proveedor activo."""
        variantes = {}
        for producto in productos:
            variantes.setdefault(producto.product_tmpl_id.id, []).append(producto)
        principal = {}
        precios = self.env['product.supplierinfo'].sudo().search(
            [('product_tmpl_id', 'in', list(variantes)), ('company_id', 'in', [False] + self._empresas()),
             ('partner_id.active', '=', True)])
        for precio in precios:
            for producto in variantes[precio.product_tmpl_id.id]:
                if producto.id not in principal and (not precio.product_id or precio.product_id == producto):
                    principal[producto.id] = precio
        return principal

    @api.model
    def _vendidos(self, meses, hasta=None):
        """``{product.product id: unidades}`` de las facturas publicadas de la ventana menos las notas de crédito
        (las de «Lo más vendido»); solo lo que da más de 0."""
        desde, hasta = self._ventana(meses, hasta)
        tablero = self.env['dcasa.tablero']
        unidades = tablero._unidades_por_producto(tablero._filas(desde, hasta, BASE_FACTURADO))
        return {producto.id: cantidad for producto, (cantidad, _monto) in unidades.items() if round(cantidad, 2) > 0}

    @api.model
    def _calcular(self, meses=MESES_POR_DEFECTO, reserva=0, proveedor=None, hasta=None):
        """Las filas de «Reponer», de más urgente a menos: ``[{'producto_id', 'producto', 'referencia',
        'proveedor_id', 'proveedor', 'vendido', 'ritmo', 'en_bodega', 'por_entregar', 'existencia' (= disponible hoy:
        en bodega − por entregar), 'pedido', 'alcanza_meses', 'alcanza',
        'llegada_dias', 'llegada', 'pedir', 'pedir_ya', 'estado', 'aviso'}]``. ``llegada_dias`` y ``pedir`` son
        ``None`` cuando falta el tiempo de llegada (o el proveedor).

        Lecturas agrupadas (una por tipo de dato, nunca una por producto), con ``sudo`` tras comprobar el grupo y
        siempre filtradas a las empresas de quien mira."""
        self._exigir_gerencia()
        meses, reserva = self._validar(meses, reserva)
        vendidos = self._vendidos(meses, hasta)
        if not vendidos:
            return []
        empresas = self._empresas()
        productos = self.env['product.product'].sudo().with_context(active_test=False).browse(list(vendidos))
        principal = self._principales(productos)
        if proveedor:
            productos = productos.filtered(lambda p: p.id in principal and principal[p.id].partner_id == proveedor)
            if not productos:
                return []

        existencia = {producto.id: cantidad for producto, cantidad in self.env['stock.quant'].sudo()._read_group(
            [('product_id', 'in', productos.ids), ('location_id.usage', '=', 'internal'),
             ('company_id', 'in', empresas)], ['product_id'], ['quantity:sum'])}
        # Lo vendido que sigue en bodega esperando entrega: lo que falta salir hacia un cliente (en la unidad del
        # producto). Solo el movimiento que sale al cliente: en una entrega en varios pasos no se cuenta dos veces.
        por_entregar = {producto.id: cantidad for producto, cantidad in self.env['stock.move'].sudo()._read_group(
            [('product_id', 'in', productos.ids), ('state', 'not in', ('draft', 'done', 'cancel')),
             ('location_id.usage', '=', 'internal'), ('location_dest_id.usage', '=', 'customer'),
             ('company_id', 'in', empresas)], ['product_id'], ['product_qty:sum'])}
        pedido = dict.fromkeys(productos.ids, 0.0)
        for linea in self.env['purchase.order.line'].sudo().search_fetch(
                [('product_id', 'in', productos.ids), ('order_id.state', '=', 'purchase'),
                 ('company_id', 'in', empresas)], ['product_id', 'product_qty', 'qty_received', 'product_uom_id']):
            falta = max(linea.product_qty - linea.qty_received, 0.0)
            unidad = linea.product_id.uom_id
            if falta and linea.product_uom_id and unidad and linea.product_uom_id != unidad:
                falta = linea.product_uom_id._compute_quantity(falta, unidad)
            pedido[linea.product_id.id] += falta

        filas = []
        for producto in productos.with_context(display_default_code=False):
            vendido = round(vendidos[producto.id], 2)
            ritmo = vendido / meses
            en_bodega = round(existencia.get(producto.id, 0.0), 2)
            comprometido = round(por_entregar.get(producto.id, 0.0), 2)
            hay = round(en_bodega - comprometido, 2)
            en_camino = round(pedido[producto.id], 2)
            alcanza = max(hay + en_camino, 0.0) / ritmo
            precio = principal.get(producto.id)
            dias = self._dias_de_llegada(precio) if precio else None
            if dias is None:
                pedir, pedir_ya = None, False
                estado = 'falta' if precio else 'sin_proveedor'
            else:
                llegada = dias / DIAS_POR_MES
                pedir = max(math.ceil(round(ritmo * (llegada + reserva) - hay - en_camino, 6)), 0)
                pedir_ya = round(alcanza, 6) < round(llegada, 6)
                estado = 'ya' if pedir_ya else ('pedir' if pedir else 'alcanza')
            socio = precio.partner_id if precio else None
            filas.append({
                'producto_id': producto.id, 'producto': producto.display_name,
                'referencia': producto.default_code or '',
                'proveedor_id': socio.id if socio else False, 'proveedor': socio.display_name if socio else '',
                'vendido': vendido, 'ritmo': round(ritmo, 2), 'en_bodega': en_bodega, 'por_entregar': comprometido,
                'existencia': hay, 'pedido': en_camino,
                'alcanza_meses': round(alcanza, 2), 'alcanza': tiempo_que_alcanza(alcanza),
                'llegada_dias': dias,
                'llegada': tiempo_de_llegada(dias) if dias is not None else (
                    self.env._('Falta') if precio else self.env._('Sin proveedor')),
                'pedir': pedir, 'pedir_ya': pedir_ya, 'estado': estado, 'aviso': AVISOS[estado],
            })
        filas.sort(key=lambda fila: (ESTADOS.index(fila['estado']), fila['alcanza_meses'], -(fila['pedir'] or 0),
                                     fila['producto'].lower()))
        return filas

    @api.model
    def _grupos(self, filas):
        """Las filas por proveedor principal, con sus totales: ``[{'proveedor_id', 'proveedor', 'filas', 'ya',
        'vendido', 'ritmo', 'existencia', 'pedido', 'pedir', 'calculables'}]`` (``calculables``: cuántas filas tienen
        cuánto pedir; sin ninguna, el total de «Pedir» es «—»). Primero el que tiene más «Pedir ya» y lo más
        urgente; «Sin proveedor» al final."""
        grupos = {}
        for fila in filas:
            grupo = grupos.setdefault(fila['proveedor_id'], {
                'proveedor_id': fila['proveedor_id'], 'proveedor': fila['proveedor'] or self.env._('Sin proveedor'),
                'filas': [], 'ya': 0, 'vendido': 0.0, 'ritmo': 0.0, 'existencia': 0.0, 'pedido': 0.0, 'pedir': 0,
                'calculables': 0})
            grupo['filas'].append(fila)
            grupo['ya'] += int(fila['pedir_ya'])
            grupo['calculables'] += fila['pedir'] is not None
            grupo['pedir'] += fila['pedir'] or 0
            for clave in ('vendido', 'ritmo', 'existencia', 'pedido'):
                grupo[clave] = round(grupo[clave] + fila[clave], 2)
        return sorted(grupos.values(), key=lambda g: (
            not g['proveedor_id'], -g['ya'], min(ESTADOS.index(f['estado']) for f in g['filas']),
            min(f['alcanza_meses'] for f in g['filas']), g['proveedor'].lower()))

    @api.model
    def _sin_ventas(self, proveedor, filas):
        """Cuántos productos activos tienen a ``proveedor`` de principal y no salen en ``filas`` (no se vendieron)."""
        plantillas = self.env['product.supplierinfo'].sudo().search(
            [('partner_id', '=', proveedor.id), ('company_id', 'in', [False] + self._empresas())]).product_tmpl_id
        variantes = plantillas.filtered('active').product_variant_ids
        principal = self._principales(variantes)
        vistos = {fila['producto_id'] for fila in filas}
        return sum(1 for variante in variantes
                   if variante.id not in vistos and variante.id in principal
                   and principal[variante.id].partner_id == proveedor)

    # ------------------------------------------------------------------
    # Proveedores: ficha, buscador y tiempo de llegada
    # ------------------------------------------------------------------

    @api.model
    def _fichas(self, ids):
        """``{id: {'id', 'nombre', 'telefono', 'ruc', 'productos', 'ultima_compra', 'llegada'}}`` de esos
        proveedores (``llegada``: ``_resumen_llegada``)."""
        socios = self.env['res.partner'].sudo().browse(ids).exists()
        if not socios:
            return {}
        empresas = self._empresas()
        precios = self.env['product.supplierinfo'].sudo().search_fetch(
            [('partner_id', 'in', socios.ids), ('company_id', 'in', [False] + empresas),
             ('product_tmpl_id.active', '=', True)],
            ['partner_id', 'product_tmpl_id', 'delay', 'dcasa_llegada_puesta'])
        productos, dias = {}, {}
        for precio in precios:
            productos.setdefault(precio.partner_id.id, set()).add(precio.product_tmpl_id.id)
            dias.setdefault(precio.partner_id.id, []).append(self._dias_de_llegada(precio))
        ultima = {}
        for socio, aprobada, ordenada in self.env['purchase.order'].sudo()._read_group(
                [('partner_id', 'child_of', socios.ids), ('state', '=', 'purchase'), ('company_id', 'in', empresas)],
                ['partner_id'], ['date_approve:max', 'date_order:max']):
            duenio = socio.id if socio.id in socios.ids else socio.commercial_partner_id.id
            momento = aprobada or ordenada
            if momento and (duenio not in ultima or momento > ultima[duenio]):
                ultima[duenio] = momento
        fichas = {}
        for socio in socios:
            momento = ultima.get(socio.id)
            fichas[socio.id] = {
                'id': socio.id, 'nombre': socio.display_name, 'telefono': socio.phone or '',
                'ruc': socio.vat or '', 'productos': len(productos.get(socio.id, ())),
                'ultima_compra': (fields.Datetime.context_timestamp(self, momento).strftime('%d/%m/%Y')
                                  if momento else ''),
                'llegada': self._resumen_llegada(dias.get(socio.id, [])),
            }
        return fichas

    @api.model
    def _resumen_llegada(self, dias):
        """``{'dias', 'texto', 'falta', 'precios'}`` del tiempo de llegada de un proveedor, a partir de los días de
        cada uno de sus precios (``None`` = falta): ``dias`` solo si todos tardan lo mismo; ``falta``, a cuántos
        precios les falta; ``precios``, cuántos tiene."""
        conocidos = sorted({d for d in dias if d is not None})
        falta = sum(1 for d in dias if d is None)
        if not dias:
            texto = self.env._('Todavía no tiene productos con su precio de proveedor')
        elif not conocidos:
            texto = self.env._('Falta el tiempo de llegada')
        else:
            if len(conocidos) == 1:
                texto = tiempo_de_llegada(conocidos[0])
            else:
                texto = self.env._('De %(menos)s a %(mas)s', menos=tiempo_de_llegada(conocidos[0]),
                                   mas=tiempo_de_llegada(conocidos[-1]))
            if falta == 1:
                texto += ' · ' + self.env._('a 1 producto le falta')
            elif falta:
                texto += ' · ' + self.env._('a %(n)s productos les falta', n=falta)
        return {'dias': conocidos[0] if len(conocidos) == 1 and not falta else None, 'texto': texto,
                'falta': falta, 'precios': len(dias)}

    @api.model
    def _ids_proveedores(self):
        """Los proveedores: quien tiene precios de proveedor, quien ya recibió una compra confirmada y quien está
        marcado como proveedor; activos y de las empresas de quien mira, por nombre."""
        empresas = self._empresas()
        ids = set(self.env['product.supplierinfo'].sudo().search(
            [('company_id', 'in', [False] + empresas)]).partner_id.ids)
        compras = self.env['purchase.order'].sudo().search([('state', '=', 'purchase'), ('company_id', 'in', empresas)])
        ids |= set(compras.partner_id.commercial_partner_id.ids)
        ids |= set(self.env['res.partner'].sudo().search([('supplier_rank', '>', 0)]).ids)
        return self.env['res.partner'].sudo().search(
            [('id', 'in', list(ids)), ('company_id', 'in', [False] + empresas)], order='name, id')

    def _motivo(self, socio, clave, digitos, ruc):
        """Por qué ``socio`` coincide con lo escrito (``''`` = por su nombre) o ``None`` si no coincide."""
        if clave in normalizar(socio.name) or (socio.ref and clave in normalizar(socio.ref)):
            return ''
        telefono = re.sub(r'\D', '', socio.phone or '')
        if digitos and telefono and digitos in telefono:
            return self.env._('Teléfono %(telefono)s', telefono=socio.phone)
        if ruc and socio.vat and ruc in re.sub(r'[\s.\-]', '', socio.vat).lower():
            return self.env._('RUC %(ruc)s', ruc=socio.vat)
        return None

    @api.model
    def buscar_proveedores(self, texto=''):
        """El buscador de proveedores de la pantalla: lo escrito puede ser parte del nombre, el teléfono, el RUC o
        el nombre o código de un producto que vende. ``{'proveedores': [ficha + 'coincide'], 'total', 'texto'}``;
        sin texto, todos (los primeros 40 por nombre)."""
        self._exigir_gerencia()
        texto = str(texto or '').strip()[:80]
        socios = self._ids_proveedores()
        coincide = {}
        if texto:
            clave = normalizar(texto)
            sin_signos = re.sub(r'[\s.\-+()/]', '', texto)
            digitos = sin_signos if sin_signos.isdigit() and len(sin_signos) >= 3 else ''
            ruc = sin_signos.lower() if len(sin_signos) >= 3 else ''
            for socio in socios:
                motivo = self._motivo(socio, clave, digitos, ruc)
                if motivo is not None:
                    coincide[socio.id] = motivo
            # Por un producto que vende (nombre, código, código de barras o su código/nombre en el proveedor).
            productos = self.env['product.product'].sudo().search(
                ['|', '|', ('name', 'ilike', texto), ('default_code', 'ilike', texto), ('barcode', 'ilike', texto)],
                limit=200)
            precios = self.env['product.supplierinfo'].sudo().search(
                [('company_id', 'in', [False] + self._empresas()), ('partner_id', 'in', socios.ids), '|', '|',
                 ('product_tmpl_id', 'in', productos.product_tmpl_id.ids), ('product_code', 'ilike', texto),
                 ('product_name', 'ilike', texto)])
            for precio in precios:
                if precio.partner_id.id not in coincide:
                    coincide[precio.partner_id.id] = self.env._(
                        'Vende «%(producto)s»', producto=precio.product_tmpl_id.with_context(
                            display_default_code=False).display_name)
            socios = socios.filtered(lambda s: s.id in coincide).sorted(
                lambda s: (bool(coincide[s.id]), normalizar(s.name)))
        total = len(socios)
        socios = socios[:PROVEEDORES_A_LA_VISTA]
        fichas = self._fichas(socios.ids)
        return {'proveedores': [dict(fichas[s.id], coincide=coincide.get(s.id, '')) for s in socios],
                'total': total, 'texto': texto}

    @api.model
    def _poner_llegada(self, proveedor, dias):
        """Guarda ``dias`` como el tiempo de llegada de todos los precios de ``proveedor`` (los de las empresas de
        quien mira) y lo anota en su ficha. Devuelve cuántos precios cambió."""
        self._exigir_gerencia()
        precios = self.env['product.supplierinfo'].sudo().search(
            [('partner_id', '=', proveedor.id), ('company_id', 'in', [False] + self._empresas())])
        if not precios:
            raise UserError(self.env._(
                '%(proveedor)s todavía no tiene productos con su precio de proveedor: agrégaselo en la ficha del '
                'producto, pestaña «Compra».', proveedor=proveedor.display_name))
        precios.write({'delay': dias, 'dcasa_llegada_puesta': True})
        proveedor.sudo().message_post(
            body=self.env._('Tiempo de llegada: %(tiempo)s (%(dias)s días), puesto desde Compras › Reponer por '
                            '%(quien)s.', tiempo=tiempo_de_llegada(dias), dias=dias, quien=self.env.user.name),
            subtype_xmlid='mail.mt_note', author_id=self.env.user.partner_id.id)
        return len(precios)

    @api.model
    def poner_llegada(self, proveedor_id, cantidad, unidad='meses'):
        """Botón «Guardar» del tiempo de llegada: ``cantidad`` días o meses (un mes = 30 días). Devuelve la ficha
        del proveedor al día."""
        self._exigir_gerencia()
        proveedor = self._proveedor(proveedor_id)
        if not proveedor:
            raise UserError(self.env._('Elige un proveedor.'))
        self._poner_llegada(proveedor, self._a_dias(cantidad, unidad))
        return self._fichas(proveedor.ids)[proveedor.id]

    # ------------------------------------------------------------------
    # La pantalla y el Excel
    # ------------------------------------------------------------------

    @api.model
    def obtener(self, meses=MESES_POR_DEFECTO, reserva=0, proveedor_id=False):
        """Todo lo que pinta la pantalla: la ventana, el proveedor elegido, las filas, los grupos y el resumen."""
        self._exigir_gerencia()
        meses, reserva = self._validar(meses, reserva)
        proveedor = self._proveedor(proveedor_id)
        filas = self._calcular(meses, reserva, proveedor)
        desde, hasta = self._ventana(meses)
        grupos = self._grupos(filas)
        fichas = self._fichas([g['proveedor_id'] for g in grupos if g['proveedor_id']]
                              + ([proveedor.id] if proveedor else []))
        for grupo in grupos:
            grupo['llegada'] = fichas[grupo['proveedor_id']]['llegada'] if grupo['proveedor_id'] else None
            grupo['producto_ids'] = [fila['producto_id'] for fila in grupo.pop('filas')]
        resumen = dict.fromkeys(ESTADOS, 0)
        for fila in filas:
            resumen[fila['estado']] += 1
        return {
            'meses': meses, 'reserva': reserva,
            'desde': desde.strftime('%d/%m/%Y'), 'hasta': hasta.strftime('%d/%m/%Y'),
            'proveedor': fichas[proveedor.id] if proveedor else None,
            'sin_ventas': self._sin_ventas(proveedor, filas) if proveedor else None,
            'filas': filas, 'grupos': grupos, 'resumen': resumen,
            'unidades': sum(fila['pedir'] or 0 for fila in filas),
        }

    @api.model
    def _excel(self, meses=MESES_POR_DEFECTO, reserva=0, proveedor_id=False):
        """``(nombre, contenido)`` del Excel: la hoja «Reponer» (lo mismo que la pantalla, de más urgente a menos) y
        «Por proveedor» (sus totales)."""
        import xlsxwriter  # noqa: PLC0415 (como el exportar de Odoo: solo se carga al usarlo)

        self._exigir_gerencia()
        meses, reserva = self._validar(meses, reserva)
        proveedor = self._proveedor(proveedor_id)
        filas = self._calcular(meses, reserva, proveedor)
        desde, hasta = self._ventana(meses)
        salida = io.BytesIO()
        libro = xlsxwriter.Workbook(salida, {'in_memory': True})
        formatos = {
            'titulo': libro.add_format({'bold': True, 'font_size': 14, 'font_color': '#1340B1'}),
            'nota': libro.add_format({'italic': True, 'font_color': '#44506A'}),
            'cabeza': libro.add_format({'bold': True, 'bg_color': '#1340B1', 'font_color': '#FFFFFF',
                                        'text_wrap': True, 'valign': 'vcenter', 'border': 1}),
            'entero': libro.add_format({'num_format': '#,##0'}),
            'decimal': libro.add_format({'num_format': '#,##0.0#'}),
            'urgente': libro.add_format({'bold': True, 'font_color': '#0B1F52'}),
            'total': libro.add_format({'bold': True, 'num_format': '#,##0.##', 'top': 1}),
        }
        quien = proveedor.display_name if proveedor else self.env._('Todos los proveedores')
        encabezado = [
            (self.env._('Reponer · %(quien)s', quien=quien), formatos['titulo']),
            (self.env._('Ventas del %(desde)s al %(hasta)s (%(meses)s meses, facturas menos notas de crédito) · '
                        'Reserva: %(reserva)s meses · Un mes = 30 días.', desde=desde.strftime('%d/%m/%Y'),
                        hasta=hasta.strftime('%d/%m/%Y'), meses=meses, reserva=cifra(reserva)), formatos['nota']),
            (self.env._('Disponible hoy = en bodega − lo vendido que espera entrega. Pedir = se vende al mes × '
                        '(meses que tarda + reserva) − disponible hoy − viene en camino. '
                        '«Pedir ya»: lo que hay y lo que viene no alcanza para lo que tarda en llegar.'),
             formatos['nota']),
        ]
        self._hoja_reponer(libro.add_worksheet(self.env._('Reponer')), formatos, encabezado, filas, meses)
        self._hoja_proveedores(libro.add_worksheet(self.env._('Por proveedor')), formatos, self._grupos(filas), meses)
        libro.close()
        sufijo = f'_{re.sub(r"[^a-z0-9]+", "-", normalizar(proveedor.display_name)).strip("-")}' if proveedor else ''
        return f'reponer{sufijo}_{hasta.isoformat()}.xlsx', salida.getvalue()

    def _columnas_comunes(self, meses):
        return [(self.env._('Vendido en %(meses)s meses', meses=meses), 12), (self.env._('Se vende al mes'), 11),
                (self.env._('Disponible hoy (sin lo ya vendido)'), 13), (self.env._('Viene en camino'), 11)]

    @staticmethod
    def _cabecera(hoja, fila, columnas, formato):
        for columna, (nombre, ancho) in enumerate(columnas):
            hoja.write(fila, columna, nombre, formato)
            hoja.set_column(columna, columna, ancho)
        hoja.set_row(fila, 32)

    def _hoja_reponer(self, hoja, formatos, encabezado, filas, meses):
        """La hoja «Reponer»: una fila por producto, como en la pantalla (números como números, para sumar)."""
        for numero, (texto, formato) in enumerate(encabezado):
            hoja.write(numero, 0, texto, formato)
        comunes = self._columnas_comunes(meses)
        columnas = ([(self.env._('Aviso'), 14), (self.env._('Producto'), 40), (self.env._('Referencia'), 14),
                     (self.env._('Proveedor'), 28)] + comunes[:2]
                    + [(self.env._('En bodega'), 10), (self.env._('Vendido por entregar'), 11)] + comunes[2:]
                    + [(self.env._('Alcanza para (meses)'), 12), (self.env._('Tarda en llegar (días)'), 12),
                       (self.env._('Pedir'), 10)])
        cabecera = len(encabezado) + 1
        self._cabecera(hoja, cabecera, columnas, formatos['cabeza'])
        for numero, fila in enumerate(filas, start=cabecera + 1):
            hoja.write(numero, 0, fila['aviso'], formatos['urgente'] if fila['pedir_ya'] else None)
            hoja.write(numero, 1, fila['producto'])
            hoja.write(numero, 2, fila['referencia'])
            hoja.write(numero, 3, fila['proveedor'] or self.env._('Sin proveedor'))
            claves = ('vendido', 'ritmo', 'en_bodega', 'por_entregar', 'existencia', 'pedido', 'alcanza_meses')
            for columna, clave in enumerate(claves, start=4):
                hoja.write_number(numero, columna, fila[clave], formatos['decimal'])
            if fila['llegada_dias'] is None:
                hoja.write(numero, 11, fila['llegada'])
                hoja.write(numero, 12, '—')
            else:
                hoja.write_number(numero, 11, fila['llegada_dias'], formatos['entero'])
                hoja.write_number(numero, 12, fila['pedir'], formatos['entero'])
        if filas:
            hoja.autofilter(cabecera, 0, cabecera + len(filas), len(columnas) - 1)
        else:
            hoja.write(cabecera + 1, 0, self.env._('No se vendió nada en esos meses.'), formatos['nota'])
        hoja.freeze_panes(cabecera + 1, 2)

    def _hoja_proveedores(self, hoja, formatos, grupos, meses):
        """La hoja «Por proveedor»: sus totales y, abajo, el total de todos (con fórmula, para que cuadre)."""
        from xlsxwriter.utility import xl_col_to_name  # noqa: PLC0415

        fichas = self._fichas([grupo['proveedor_id'] for grupo in grupos if grupo['proveedor_id']])
        columnas = ([(self.env._('Proveedor'), 32), (self.env._('Tarda en llegar'), 24), (self.env._('Productos'), 10),
                     (self.env._('Pedir ya'), 10)] + self._columnas_comunes(meses) + [(self.env._('Pedir'), 10)])
        self._cabecera(hoja, 0, columnas, formatos['cabeza'])
        valores = []
        for numero, grupo in enumerate(grupos, start=1):
            ficha = fichas.get(grupo['proveedor_id'])
            hoja.write(numero, 0, grupo['proveedor'])
            hoja.write(numero, 1, ficha['llegada']['texto'] if ficha else self.env._('Sin proveedor'))
            fila = [len(grupo['filas']), grupo['ya'], grupo['vendido'], grupo['ritmo'], grupo['existencia'],
                    grupo['pedido'], grupo['pedir']]
            for columna, valor in enumerate(fila, start=2):
                formato = formatos['entero'] if columna in (2, 3, 8) else formatos['decimal']
                hoja.write_number(numero, columna, valor, formato)
            if not grupo['calculables']:
                hoja.write(numero, 8, '—')
            valores.append(fila)
        if grupos:
            ultima = len(grupos) + 1
            hoja.write(ultima, 0, self.env._('Total'), formatos['total'])
            for indice, columna in enumerate(range(2, len(columnas))):
                letra = xl_col_to_name(columna)
                hoja.write_formula(ultima, columna, f'=SUM({letra}2:{letra}{ultima})', formatos['total'],
                                   round(sum(fila[indice] for fila in valores), 2))
        hoja.freeze_panes(1, 1)
