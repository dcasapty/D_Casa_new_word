"""Las bases de las ventas del Inicio: qué pedidos cuentan, en qué día y cuánto falta por cobrar de ellos.

Todas parten de lo **vendido** de siempre (``sale.order._dcasa_dominio_vendido``): pedido confirmado, facturado por
completo y con todas sus facturas publicadas; los montos son los del pedido, sin ITBMS (netos de notas de crédito igual
que hoy: una nota que devuelve todo saca el pedido de lo vendido). Encima de eso (decisión de la dueña, 2026-10-17):

* ``vendido``: el día de la venta (``dcasa_fecha_venta``, la fecha de su última factura). Es la base del Inicio de la
  vendedora, de su meta y de Brian cuando pregunta quien vende; Gerencia ya no la ve.
* ``completadas``: las ventas cuyas facturas quedaron **pagadas al 100 %** (``paid`` o ``in_payment``), contadas el día
  del pago que dejó el saldo en cero (nunca antes del día de la venta). Ese día sale de las mismas conciliaciones que
  lista el cuadro de pagos de la factura (``account.move._dcasa_pagos()`` de ``dcasa_invoice``), leídas de una vez.
* ``con_abonos``: las ventas con **al menos un pago** (completas o parciales), por su valor total, el día de la venta.
  «Falta por cobrar» es el saldo de esas facturas, con ITBMS, como el que ve el cliente, **al cierre del periodo** (o a
  su hora de corte): lo que se había pagado hasta ese día, no lo que se pagó después.

Una venta facturada sin ningún pago no cuenta ni en «Completadas» ni en «Con abonos» (a propósito: hoy sí contaba).

**Cobrado** es el mismo en las dos: los cobros de clientes registrados (en proceso o pagados), con ITBMS, por su fecha;
la misma definición que la caja del Inicio (``_dominio_de_cobros``). Para una vendedora son los cobros aplicados a las
facturas de SUS ventas (el «Vendedor» del pedido), no los que ella registró: Caja registra muchos.

**Hasta la misma hora** (``corte``, en UTC sin zona): el último día del periodo cuenta solo lo que **a esa hora ya
estaba registrado** en el sistema. Una factura, un pago o una conciliación tienen fecha (el día del negocio) y hora de
registro (``create_date``). La regla honesta y comprobable es «lo que el Inicio habría mostrado ese día a esa hora»:

* vendido / con abonos: la venta cuenta si todas sus facturas se habían registrado a esa hora (y, con abonos, si ya
  tenía un abono registrado);
* completadas: si todas sus facturas y conciliaciones (los pagos aplicados) se habían registrado a esa hora;
* cobrado: si el cobro se había registrado a esa hora (``account.payment.create_date``).

Lo que se registra tarde (un pago de ayer anotado hoy, o cargado del sistema anterior) no tiene hora de ese día: cuenta
en los días completos, pero no en el corte. Los días anteriores al último del periodo cuentan completos.
"""
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .tablero import BASE_COMPLETADAS, BASE_CON_ABONOS, BASE_VENDIDO, BASES_DE_GERENCIA, SIN_VENDEDORA

PAGADA = ('paid', 'in_payment')
CAMPOS_DEL_PEDIDO = ['dcasa_fecha_venta', 'amount_untaxed', 'amount_tax', 'amount_total', 'user_id']


class DcasaTableroBases(models.AbstractModel):
    _inherit = 'dcasa.tablero'

    # ------------------------------------------------------------------
    # Lo que pide la pantalla: base y vendedora (validado en el servidor)
    # ------------------------------------------------------------------

    @api.model
    def _bases_de_ventas(self):
        """Las dos posiciones del interruptor del Inicio de Gerencia, con su línea corta."""
        return [
            {'clave': BASE_COMPLETADAS, 'nombre': self.env._('Completadas'),
             'detalle': self.env._('Pagadas al 100 %, el día del último pago')},
            {'clave': BASE_CON_ABONOS, 'nombre': self.env._('Con abonos'),
             'detalle': self.env._('Con al menos un abono, por su valor total')},
        ]

    @api.model
    def _base_pedida(self, base):
        """La base que pide Gerencia; sin base, «Completadas» (con la que abre el Inicio)."""
        if base in (None, False, ''):
            return BASE_COMPLETADAS
        if base not in BASES_DE_GERENCIA:
            raise UserError(self.env._('Elige «Completadas» o «Con abonos».'))
        return base

    @api.model
    def _vendedor_pedido(self, vendedor):
        """``None`` (todo el equipo), ``'sin'`` (ventas sin vendedora) o el id de un usuario interno.

        Solo Gerencia y los administradores miran las ventas de otra persona: a cualquier otro se le rechaza un
        ``vendedor`` que no sea el suyo (``AccessError``), aunque lo mande a mano por RPC."""
        if vendedor in (None, False, ''):
            return None
        es_texto_numerico = isinstance(vendedor, str) and vendedor.isdigit()
        if not self._ve_utilidad():
            if (isinstance(vendedor, int) and not isinstance(vendedor, bool) and vendedor == self.env.uid) or \
                    (es_texto_numerico and int(vendedor) == self.env.uid):
                return self.env.uid
            raise AccessError(self.env._('Solo Gerencia y los administradores ven las ventas de otra persona.'))
        if vendedor == SIN_VENDEDORA:
            return SIN_VENDEDORA
        if isinstance(vendedor, bool) or not (isinstance(vendedor, int) or es_texto_numerico):
            raise UserError(self.env._('Elige una vendedora de la lista.'))
        usuario = self.env['res.users'].sudo().with_context(active_test=False).browse(int(vendedor)).exists()
        if not usuario or usuario.share:
            raise UserError(self.env._('Esa vendedora no existe.'))
        return usuario.id

    @api.model
    def _clausula_vendedor(self, vendedor):
        """El filtro por el «Vendedor» del pedido (``user_id``): de quién es cada venta."""
        if vendedor in (None, False):
            return []
        if vendedor == SIN_VENDEDORA:
            return [('user_id', '=', False)]
        return [('user_id', '=', getattr(vendedor, 'id', vendedor))]

    # ------------------------------------------------------------------
    # Facturas y pagos de los pedidos (una lectura para todos)
    # ------------------------------------------------------------------

    @api.model
    def _facturas_por_pedido(self, pedidos):
        """``{pedido_id: facturas de cliente publicadas}`` (las que hacen la venta)."""
        return {
            pedido.id: pedido.order_line.invoice_lines.move_id.filtered(
                lambda m: m.state == 'posted' and m.move_type == 'out_invoice')
            for pedido in pedidos.sudo()
        }

    @api.model
    def _pagos_de_facturas(self, facturas):
        """``{factura_id: [pago]}`` con ``pago = {'fecha', 'tope', 'monto', 'es_nota', 'registro'}``.

        Son las conciliaciones de cada factura, sin las diferencias de cambio: las mismas que lista su cuadro de
        pagos (``_dcasa_pagos``). ``fecha`` es la del pago (o de la nota de crédito); ``tope``, la mayor entre la del
        pago y la de la factura (``max_date``: un pago anticipado no completa una venta antes de que exista);
        ``registro``, cuándo se aplicó el pago a la factura (para el corte a la misma hora)."""
        pagos = {factura_id: [] for factura_id in facturas.ids}
        if not facturas:
            return pagos
        parciales = self.env['account.partial.reconcile'].sudo().search_fetch(
            ['|', ('debit_move_id.move_id', 'in', facturas.ids), ('credit_move_id.move_id', 'in', facturas.ids)],
            ['debit_move_id', 'credit_move_id', 'amount', 'max_date', 'exchange_move_id', 'create_date'])
        de_cambio = parciales.exchange_move_id
        for parcial in parciales:
            for propia, otra in ((parcial.debit_move_id, parcial.credit_move_id),
                                 (parcial.credit_move_id, parcial.debit_move_id)):
                factura_id = propia.move_id.id
                if factura_id not in pagos or otra.move_id in de_cambio:
                    continue
                pagos[factura_id].append({
                    'fecha': otra.date, 'tope': parcial.max_date, 'monto': parcial.amount,
                    'es_nota': otra.move_id.move_type in ('out_refund', 'in_refund'), 'registro': parcial.create_date,
                })
        return pagos

    # ------------------------------------------------------------------
    # Qué pedidos cuentan en un periodo
    # ------------------------------------------------------------------

    @api.model
    def _pedidos_de(self, d0, d1, base, vendedor=None, corte=None):
        """Los pedidos de ``base`` en los días ``d0``–``d1`` (ambos incluidos) y lo leído para medirlos.

        Devuelve ``(pedidos, facturas, pagos)``: ``facturas`` y ``pagos`` vienen vacíos si la base no los necesitó.
        ``corte`` aplica solo al día ``d1`` (ver el docstring del módulo)."""
        Order = self.env['sale.order']
        comun = Order._dcasa_dominio_vendido() + self._clausula_vendedor(vendedor)
        if base == BASE_COMPLETADAS:
            return self._completadas(d0, d1, comun, corte)
        if base not in (BASE_VENDIDO, BASE_CON_ABONOS):
            raise UserError(self.env._('Elige «Completadas» o «Con abonos».'))
        en_el_periodo = [('dcasa_fecha_venta', '>=', fields.Date.to_string(d0)),
                         ('dcasa_fecha_venta', '<=', fields.Date.to_string(d1))]
        pedidos = Order.search_fetch(comun + en_el_periodo, CAMPOS_DEL_PEDIDO)
        if base == BASE_VENDIDO and not corte:
            return pedidos, {}, {}
        facturas = self._facturas_por_pedido(pedidos)
        pagos = self._pagos_de_facturas(self._todas(facturas)) if base == BASE_CON_ABONOS else {}

        def cuenta(pedido):
            propias = facturas[pedido.id]
            en_el_corte = bool(corte) and pedido.dcasa_fecha_venta == d1
            if en_el_corte and any(factura.create_date > corte for factura in propias):
                return False
            if base == BASE_VENDIDO:
                return True
            abonos = [pago for factura in propias for pago in pagos[factura.id] if not pago['es_nota']]
            if en_el_corte:
                abonos = [pago for pago in abonos if pago['registro'] <= corte]
            return bool(abonos)

        return pedidos.filtered(cuenta), facturas, pagos

    @api.model
    def _completadas(self, d0, d1, comun, corte=None):
        """Las ventas que quedaron pagadas al 100 % entre ``d0`` y ``d1``, el día del pago que las completó.

        Primero se buscan las conciliaciones con fecha en el periodo (una venta completada en él tiene su último pago
        ahí); de esas facturas salen los pedidos candidatos, y de cada pedido se miran TODAS sus facturas: si alguna
        debe algo, la venta todavía no está completa."""
        Order = self.env['sale.order']
        cercanos = self.env['account.partial.reconcile'].sudo().search_fetch(
            [('max_date', '>=', d0), ('max_date', '<=', d1)], ['debit_move_id', 'credit_move_id'])
        facturas_pagadas = (cercanos.debit_move_id.move_id | cercanos.credit_move_id.move_id).filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted' and m.payment_state in PAGADA)
        candidatos = facturas_pagadas.line_ids.sale_line_ids.order_id
        if not candidatos:
            return Order.browse(), {}, {}
        pedidos = Order.search_fetch(comun + [('id', 'in', candidatos.ids)], CAMPOS_DEL_PEDIDO)
        facturas = self._facturas_por_pedido(pedidos)
        pagos = self._pagos_de_facturas(self._todas(facturas))

        def cuenta(pedido):
            propias = facturas[pedido.id]
            if not propias or any(factura.payment_state not in PAGADA for factura in propias):
                return False
            topes = [pago['tope'] for factura in propias for pago in pagos[factura.id]]
            if not topes:
                return False
            dia = max(*topes, pedido.dcasa_fecha_venta)
            if not d0 <= dia <= d1:
                return False
            if corte and dia == d1:
                registros = [factura.create_date for factura in propias] \
                    + [pago['registro'] for factura in propias for pago in pagos[factura.id]]
                return all(registro <= corte for registro in registros)
            return True

        return pedidos.filtered(cuenta), facturas, pagos

    @api.model
    def _todas(self, facturas_por_pedido):
        """Todas las facturas de cliente de los pedidos, en un solo recordset (solo ``out_invoice``: el ``sudo`` nunca
        devuelve facturas de proveedor ni asientos; aquí además solo se suman montos)."""
        ids = {factura_id for facturas in facturas_por_pedido.values() for factura_id in facturas.ids}
        return self.env['account.move'].sudo().browse(sorted(ids)).filtered(lambda m: m.move_type == 'out_invoice')

    # ------------------------------------------------------------------
    # Las cifras de un periodo
    # ------------------------------------------------------------------

    @api.model
    def _medir(self, d0, d1, base, vendedor=None, corte=None, con_ganancia=False, con_cobrado=False):
        """Las cifras de un periodo en una base: ``pedidos`` (los que cuentan), ``cuantas``, ``sin_itbms``,
        ``itbms``, ``total``, ``ganancia`` (si se pide), ``falta_por_cobrar`` (solo «Con abonos», con ITBMS) y
        ``cobrado`` (si se pide y quien mira ve los cobros; con ITBMS)."""
        pedidos, facturas, pagos = self._pedidos_de(d0, d1, base, vendedor, corte)
        medida = {
            'pedidos': pedidos,
            'cuantas': len(pedidos),
            'sin_itbms': sum(pedidos.mapped('amount_untaxed')),
            'itbms': sum(pedidos.mapped('amount_tax')),
            'total': sum(pedidos.mapped('amount_total')),
            'ganancia': None,
            'falta_por_cobrar': None,
            'cobrado': None,
        }
        if con_ganancia:
            medida['ganancia'] = self._ganancia_de([('id', 'in', pedidos.ids)])
        if base == BASE_CON_ABONOS:
            medida['falta_por_cobrar'] = self._falta_por_cobrar(pedidos, facturas, pagos, d1, corte)
        if con_cobrado and self._puede('account.payment'):
            medida['cobrado'] = self._cobrado(d0, d1, vendedor, corte)
        return medida

    @api.model
    def _falta_por_cobrar(self, pedidos, facturas, pagos, d1, corte=None):
        """Lo que faltaba por cobrar de esas ventas al cierre del día ``d1`` (o a su hora de corte), con ITBMS: el total
        de sus facturas menos lo pagado (y las notas de crédito aplicadas) con fecha hasta ese día."""
        falta = 0.0
        for pedido in pedidos:
            for factura in facturas[pedido.id]:
                pagado = sum(
                    pago['monto'] for pago in pagos[factura.id]
                    if pago['fecha'] < d1 or (pago['fecha'] == d1 and (not corte or pago['registro'] <= corte)))
                falta += max(factura.amount_total - pagado, 0.0)
        return round(falta, 2)

    @api.model
    def _dominio_de_cobros(self, d0, d1):
        """Lo cobrado a clientes entre dos días (con ITBMS): pagos recibidos y confirmados (en proceso o pagados), por
        su fecha. La misma definición de «Cobrado hoy» de la caja del Inicio."""
        return [('payment_type', '=', 'inbound'), ('state', 'in', ('in_process', 'paid')),
                ('date', '>=', d0), ('date', '<=', d1)]

    @api.model
    def _cobrado(self, d0, d1, vendedor=None, corte=None):
        """Lo cobrado entre ``d0`` y ``d1``. Con ``vendedor``: solo lo aplicado a las facturas de sus ventas (el
        «Vendedor» del pedido), aunque lo haya registrado Caja. Un cobro sin aplicar a una factura (un anticipo suelto)
        o aplicado a una factura sin pedido cuenta en el total del equipo, pero no es de ninguna vendedora."""
        dominio = self._dominio_de_cobros(d0, d1)
        if corte:
            dominio += ['|', ('date', '<', d1), ('create_date', '<=', corte)]
        Payment = self.env['account.payment']
        if vendedor in (None, False):
            grupos = Payment._read_group(dominio, [], ['amount:sum'])
            return (grupos[0][0] if grupos else 0.0) or 0.0
        lineas = Payment.search_fetch(dominio, ['move_id']).sudo().move_id.line_ids
        if not lineas:
            return 0.0
        de_los_cobros = set(lineas.ids)
        parciales = self.env['account.partial.reconcile'].sudo().search_fetch(
            ['|', ('debit_move_id', 'in', lineas.ids), ('credit_move_id', 'in', lineas.ids)],
            ['debit_move_id', 'credit_move_id', 'amount'])
        buscado = False if vendedor == SIN_VENDEDORA else vendedor
        duenos = {}

        def dueno(factura):
            """El «Vendedor» del pedido de la factura (el del pedido más antiguo si fueran varios)."""
            if factura.id not in duenos:
                pedidos = factura.line_ids.sale_line_ids.order_id.sorted('id')
                duenos[factura.id] = pedidos[:1].user_id.id if pedidos else None
            return duenos[factura.id]

        total = 0.0
        for parcial in parciales:
            for propia, otra in ((parcial.debit_move_id, parcial.credit_move_id),
                                 (parcial.credit_move_id, parcial.debit_move_id)):
                factura = otra.move_id
                if propia.id in de_los_cobros and factura.move_type == 'out_invoice' and factura.state == 'posted':
                    duena = dueno(factura)
                    if duena is not None and (duena or False) == buscado:
                        total += parcial.amount
        return round(total, 2)

    @api.model
    def _por_vendedora(self, pedidos):
        """``{user_id o 'sin': (cuantas, sin_itbms)}`` de un conjunto de pedidos."""
        suma = defaultdict(lambda: [0, 0.0])
        for pedido in pedidos:
            clave = pedido.user_id.id or SIN_VENDEDORA
            suma[clave][0] += 1
            suma[clave][1] += pedido.amount_untaxed
        return suma
