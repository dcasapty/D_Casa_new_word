"""Las bases de las ventas del Inicio: qué cuenta, en qué día y cuánto falta por cobrar.

**Gerencia cuenta sobre las facturas** (decisión del jefe, A1 y A2 del 2026-10-17, ``docs/DECISIONES_CONTABLES.md``):
«vendido» son todas las **facturas de cliente publicadas**, la venta se cuenta **el día de la factura**, y debajo se
dice cuántas salieron de un pedido de una vendedora. Las tres posiciones del interruptor parten de ese mismo conjunto;
las **notas de crédito restan**, como en Contabilidad. Montos sin ITBMS (el ITBMS y el total aparte), en la moneda de la
empresa (``amount_*_signed``: una nota de crédito va en negativo).

* ``facturado`` (con la que abre, ``BASE_POR_DEFECTO``): todas las facturas y notas de crédito publicadas, por su
  fecha (la contable, la misma que usa Contabilidad: en una factura de cliente es la fecha de la factura). Es lo mismo
  que las «Ventas» de Contabilidad para esas fechas mientras todo lo que entra a ingresos venga de facturas.
* ``con_abonos``: las facturas con **al menos un pago** (completas o a medias; una nota de crédito aplicada no es un
  pago), por su valor total, el día de la factura. «Falta por cobrar» es el saldo de esas facturas, con ITBMS, **al
  cierre del periodo** (o a su hora de corte): lo pagado hasta ese día, no lo que se pagó después.
* ``completadas``: las facturas **pagadas al 100 %** (``paid`` o ``in_payment``), el día del pago que dejó el saldo en
  cero (nunca antes de la factura). Ese día sale de las mismas conciliaciones que lista el cuadro de pagos de la factura
  (``account.move._dcasa_pagos()`` de ``dcasa_invoice``), leídas de una vez para todo el periodo.

Una **nota de crédito** resta el día que dice Contabilidad (su fecha) en «Facturado». En las otras dos resta solo si su
factura cuenta ahí: en «Con abonos», si su factura tiene un abono; en «Completadas», si su factura está pagada al 100 %,
el día más tardío entre el de la nota y el que se completó la factura. Así una devolución entera saca la venta (una
factura anulada con su nota queda «revertida»: no está pagada ni tiene abonos) y una parcial resta solo lo devuelto. Su
factura es la que revierte (``reversed_entry_id``) o, si se hizo aparte, la factura con que se concilió. Una nota sin
factura solo cuenta en «Facturado».

**La vendedora de una factura**: si salió de un pedido, el «Vendedor» del pedido (el más antiguo si fueran varios), como
siempre; si no, el «Vendedor» de la factura (``invoice_user_id``). Sin ninguno, «Sin vendedora», igual que las facturas
del sistema anterior (no traen la vendedora). Una nota de crédito es de la vendedora de su factura (la que revierte
o, si se hizo aparte, con la que se concilió), no de quien la hizo: las notas las hace solo Gerencia.
**Cobrado** es el mismo en las tres: los cobros de clientes registrados (en proceso o pagados), con ITBMS, por su fecha;
para una vendedora, los cobros aplicados a SUS facturas (no los que ella registró: Caja registra muchos).

``vendido`` es la base de siempre de la **vendedora** (su Inicio, su meta y Brian cuando pregunta quien vende): pedidos
facturados por completo, el día de su última factura (``sale.order._dcasa_dominio_vendido``). No cambió.

**Hasta la misma hora** (``corte``, en UTC sin zona): el último día del periodo cuenta solo lo que **a esa hora ya
estaba registrado** en el sistema (``create_date``): una factura o nota, si ya estaba registrada; con abonos, si además
ya tenía un abono registrado; completada, si la factura y todos sus pagos aplicados ya estaban registrados; un cobro, si
ya estaba registrado. Lo que se registra tarde no tiene hora de ese día: cuenta en los días completos, no en el corte.
"""
from collections import defaultdict

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, UserError

from .tablero import (
    BASE_COMPLETADAS,
    BASE_CON_ABONOS,
    BASE_FACTURADO,
    BASE_POR_DEFECTO,
    BASE_VENDIDO,
    BASES_DE_GERENCIA,
    SIN_VENDEDORA,
)

PAGADA = ('paid', 'in_payment')
CAMPOS_DEL_PEDIDO = ['dcasa_fecha_venta', 'amount_untaxed', 'amount_tax', 'amount_total', 'user_id']
CAMPOS_DE_LA_FACTURA = ['move_type', 'date', 'amount_untaxed_signed', 'amount_tax_signed', 'amount_total_signed',
                        'payment_state', 'invoice_user_id', 'reversed_entry_id', 'create_date', 'dcasa_historica']


class DcasaTableroBases(models.AbstractModel):
    _inherit = 'dcasa.tablero'

    # ------------------------------------------------------------------
    # Lo que pide la pantalla: base y vendedora (validado en el servidor)
    # ------------------------------------------------------------------

    @api.model
    def _bases_de_ventas(self):
        """Las tres posiciones del interruptor del Inicio de Gerencia, en su orden, con su línea corta."""
        nombres = {
            BASE_FACTURADO: (self.env._('Facturado'),
                             self.env._('Todas las facturas, igual que Contabilidad')),
            BASE_CON_ABONOS: (self.env._('Con abonos'), self.env._('Con al menos un abono, por su valor total')),
            BASE_COMPLETADAS: (self.env._('Completadas'), self.env._('Pagadas al 100 %, el día del último pago')),
        }
        return [{'clave': clave, 'nombre': nombres[clave][0], 'detalle': nombres[clave][1]}
                for clave in BASES_DE_GERENCIA]

    @api.model
    def _base_pedida(self, base):
        """La base que pide Gerencia; sin base, ``BASE_POR_DEFECTO`` (con la que abre el Inicio)."""
        if base in (None, False, ''):
            return BASE_POR_DEFECTO
        if base not in BASES_DE_GERENCIA:
            raise UserError(self.env._('Elige «Facturado», «Con abonos» o «Completadas».'))
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
        """El filtro por el «Vendedor» del pedido (``user_id``), para la base ``vendido`` (pedidos)."""
        if vendedor in (None, False):
            return []
        if vendedor == SIN_VENDEDORA:
            return [('user_id', '=', False)]
        return [('user_id', '=', getattr(vendedor, 'id', vendedor))]

    # ------------------------------------------------------------------
    # Facturas, pagos y vendedoras (una lectura para todos)
    # ------------------------------------------------------------------

    @api.model
    def _facturas_de_cliente(self, dominio):
        """Facturas y notas de crédito de cliente publicadas de las empresas de quien mira. Con ``sudo`` para sumar,
        siempre filtrado a documentos de cliente (``out_invoice`` / ``out_refund``): nunca facturas de proveedor ni
        asientos. Quien abre la lista que explica una cifra la ve con sus propios permisos."""
        return self.env['account.move'].sudo().search_fetch(
            [('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted'),
             ('company_id', 'in', self.env.companies.ids)] + dominio, CAMPOS_DE_LA_FACTURA, order='date, id')

    @api.model
    def _documentos(self, ids):
        """Los documentos de cliente de esos ids (con ``sudo``, ya filtrados a ``out_invoice`` / ``out_refund``)."""
        return self.env['account.move'].sudo().browse(sorted(set(ids))).filtered(
            lambda m: m.move_type in ('out_invoice', 'out_refund'))

    @api.model
    def _pagos_de_facturas(self, facturas):
        """``{factura_id: [pago]}``, cada ``pago`` con ``fecha``, ``tope``, ``monto``, ``es_nota``, ``registro``,
        ``otro`` y ``otro_tipo``.

        Son las conciliaciones de cada factura (o nota de crédito), sin las diferencias de cambio: las mismas que lista
        su cuadro de pagos (``_dcasa_pagos``). ``fecha`` es la del pago (o de la nota de crédito); ``tope``, la mayor
        entre la del pago y la de la factura (``max_date``: un pago anticipado no completa una venta antes de que
        exista); ``registro``, cuándo se aplicó el pago (para el corte a la misma hora); ``otro``, el asiento del otro
        lado (el pago, la nota o la factura) y ``otro_tipo``, su tipo. ``monto`` en la moneda de la empresa."""
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
                    'otro': otra.move_id.id, 'otro_tipo': otra.move_id.move_type,
                })
        return pagos

    @api.model
    def _duenas(self, documentos):
        """``{documento_id: (vendedora, de_pedido)}``: ``vendedora`` es el id del usuario o ``'sin'``; ``de_pedido``,
        si salió de un pedido con vendedora. Del pedido manda su «Vendedor» (el del más antiguo); sin pedido, el de la
        factura. Una nota de crédito es de la vendedora de la factura que revierte: Odoo no le copia el «Vendedor» y le
        pone a quien la hizo (Gerencia, que es quien autoriza las devoluciones). Las facturas del sistema anterior
        (``dcasa_historica``) van a «Sin vendedora»: el archivo no trae la vendedora y Odoo les pone a quien las
        cargó; lo mismo si el «Vendedor» es el usuario del sistema (OdooBot).

        Una nota hecha aparte (sin factura que revierta) y aplicada después a una factura es de la vendedora de esa
        factura (la misma de ``_factura_de_cada_nota``): las notas de crédito las hace solo Gerencia (A7, 2026-10-17),
        así que su «Vendedor» casi siempre es quien la autorizó, no quien vendió. Una nota sin ninguna factura sigue
        siendo de su «Vendedor»."""
        notas = documentos.filtered(lambda m: m.move_type == 'out_refund')
        de_la_nota = {nota.id: nota.reversed_entry_id for nota in notas
                      if nota.reversed_entry_id.move_type == 'out_invoice'}
        aparte = notas.filtered(lambda m: m.id not in de_la_nota)
        if aparte:
            de_la_nota.update(self._factura_de_cada_nota(aparte, self._pagos_de_facturas(aparte)))
        originales = self.env['account.move'].sudo().union(*de_la_nota.values())
        duenas = {}
        for documento in documentos | originales:
            pedidos = documento.line_ids.sale_line_ids.order_id
            if pedidos:
                usuario = pedidos.sorted('id')[:1].user_id
                duenas[documento.id] = (usuario.id or SIN_VENDEDORA, bool(usuario))
            else:
                usuario = documento.invoice_user_id
                if documento.dcasa_historica or usuario.id == SUPERUSER_ID:
                    usuario = usuario.browse()
                duenas[documento.id] = (usuario.id or SIN_VENDEDORA, False)
        for nota_id, factura in de_la_nota.items():
            duenas[nota_id] = duenas[factura.id]
        return duenas

    @api.model
    def _factura_de_cada_nota(self, notas, pagos_de_notas):
        """``{nota_id: factura}``: la factura que revierte cada nota de crédito o, si se hizo aparte, la factura de
        cliente con la que se concilió (la más antigua). Una nota sin factura no aparece."""
        facturas = {}
        for nota in notas:
            original = nota.reversed_entry_id
            if not (original and original.move_type == 'out_invoice' and original.state == 'posted'):
                conciliadas = sorted({pago['otro'] for pago in pagos_de_notas.get(nota.id, [])
                                      if pago['otro_tipo'] == 'out_invoice'})
                original = self._documentos(conciliadas[:1])
            if original:
                facturas[nota.id] = original
        return facturas

    @staticmethod
    def _dia_completada(factura, pagos):
        """El día en que la factura quedó pagada al 100 % (el del pago que dejó el saldo en cero, nunca antes de la
        factura) o ``None`` si todavía debe algo."""
        if factura.payment_state not in PAGADA:
            return None
        topes = [pago['tope'] for pago in pagos.get(factura.id, [])]
        if not topes:
            return None
        return max(*topes, factura.date)

    @staticmethod
    def _registrado(momento, dia, d1, corte):
        """Si algo del día ``dia`` ya estaba registrado a la hora de corte (solo el último día se corta)."""
        return not corte or dia != d1 or bool(momento and momento <= corte)

    # ------------------------------------------------------------------
    # Qué facturas cuentan en un periodo
    # ------------------------------------------------------------------

    @api.model
    def _filas(self, d0, d1, base, vendedor=None, corte=None):
        """Las facturas (y notas de crédito) de ``base`` en los días ``d0``–``d1``, ambos incluidos: una fila por
        documento (``_filas_y_pagos``)."""
        return self._filas_y_pagos(d0, d1, base, vendedor, corte)[0]

    @api.model
    def _filas_y_pagos(self, d0, d1, base, vendedor=None, corte=None):
        """``(filas, pagos)``: ``filas`` es una lista de ``{'id', 'documento', 'dia', 'es_nota', 'sin_itbms', 'itbms',
        'total', 'vendedora', 'de_pedido'}`` (montos con su signo: una nota en negativo) y ``pagos`` las conciliaciones
        leídas (``_pagos_de_facturas``). ``corte`` aplica solo al día ``d1`` (ver el docstring del módulo)."""
        if base not in BASES_DE_GERENCIA:
            raise UserError(self.env._('Elige «Facturado», «Con abonos» o «Completadas».'))
        desde, hasta = fields.Date.to_string(d0), fields.Date.to_string(d1)
        contadas = []          # (documento, día)
        pagos = {}
        if base == BASE_FACTURADO:
            for documento in self._facturas_de_cliente([('date', '>=', desde), ('date', '<=', hasta)]):
                contadas.append((documento, documento.date))
        elif base == BASE_CON_ABONOS:
            documentos = self._facturas_de_cliente([('date', '>=', desde), ('date', '<=', hasta)])
            notas = documentos.filtered(lambda m: m.move_type == 'out_refund')
            de_la_nota = self._factura_de_cada_nota(notas, self._pagos_de_facturas(notas))
            facturas = (documentos - notas).union(*de_la_nota.values())
            pagos = self._pagos_de_facturas(facturas)

            def con_abono(factura, en_el_corte):
                abonos = [pago for pago in pagos[factura.id] if not pago['es_nota']]
                if en_el_corte:
                    abonos = [pago for pago in abonos if pago['registro'] <= corte]
                return bool(abonos)

            for documento in documentos:
                factura = de_la_nota.get(documento.id) if documento.move_type == 'out_refund' else documento
                if factura and con_abono(factura, bool(corte) and documento.date == d1):
                    contadas.append((documento, documento.date))
        else:
            contadas, pagos = self._completadas(d0, d1, corte)
        filas = []
        if contadas:
            duenas = self._duenas(self._documentos([documento.id for documento, _dia in contadas]))
            redondear = self.env.company.currency_id.round
            for documento, dia in contadas:
                if not self._registrado(documento.create_date, dia, d1, corte):
                    continue
                vendedora, de_pedido = duenas[documento.id]
                if vendedor is not None and vendedora != vendedor:
                    continue
                filas.append({
                    'id': documento.id, 'documento': documento, 'dia': dia,
                    'es_nota': documento.move_type == 'out_refund',
                    'sin_itbms': redondear(documento.amount_untaxed_signed),
                    'itbms': redondear(documento.amount_tax_signed),
                    'total': redondear(documento.amount_total_signed),
                    'vendedora': vendedora, 'de_pedido': de_pedido,
                })
        return filas, pagos

    @api.model
    def _completadas(self, d0, d1, corte=None):
        """Las facturas que quedaron pagadas al 100 % entre ``d0`` y ``d1`` (el día del pago que las completó) y las
        notas de crédito de facturas completadas, el día más tardío entre el de la nota y el de la factura completa.

        Una factura completada en el periodo tiene su último pago ahí (``max_date``): de las conciliaciones con fecha en
        el periodo salen las candidatas. Devuelve ``(contadas, pagos)`` con ``contadas = [(documento, día)]``."""
        desde, hasta = fields.Date.to_string(d0), fields.Date.to_string(d1)
        cercanos = self.env['account.partial.reconcile'].sudo().search_fetch(
            [('max_date', '>=', desde), ('max_date', '<=', hasta)], ['debit_move_id', 'credit_move_id'])
        empresas = set(self.env.companies.ids)
        candidatas = self._documentos((cercanos.debit_move_id.move_id | cercanos.credit_move_id.move_id).ids).filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted' and m.payment_state in PAGADA
            and m.company_id.id in empresas)
        pagos = self._pagos_de_facturas(candidatas)
        notas = self._facturas_de_cliente([('move_type', '=', 'out_refund'), ('date', '>=', desde),
                                           ('date', '<=', hasta)])
        # Las notas de crédito de las candidatas que son de antes del periodo (se restan el día en que se completan).
        de_las_candidatas = {pago['otro'] for factura in candidatas for pago in pagos[factura.id] if pago['es_nota']}
        notas |= self._facturas_de_cliente([('move_type', '=', 'out_refund'), ('date', '<', desde), '|',
                                            ('reversed_entry_id', 'in', candidatas.ids),
                                            ('id', 'in', sorted(de_las_candidatas))])
        de_la_nota = self._factura_de_cada_nota(notas, self._pagos_de_facturas(notas))
        faltan = self._documentos([factura.id for factura in de_la_nota.values()]) - candidatas
        pagos.update(self._pagos_de_facturas(faltan))

        def registrada_a_la_hora(factura):
            """Si la factura y todos sus pagos aplicados ya estaban registrados a la hora de corte."""
            registros = [factura.create_date] + [pago['registro'] for pago in pagos[factura.id]]
            return all(registro and registro <= corte for registro in registros)

        contadas = []
        for factura in candidatas:
            dia = self._dia_completada(factura, pagos)
            if dia is None or not d0 <= dia <= d1:
                continue
            if corte and dia == d1 and not registrada_a_la_hora(factura):
                continue
            contadas.append((factura, dia))
        for nota in notas:
            factura = de_la_nota.get(nota.id)
            completada = self._dia_completada(factura, pagos) if factura else None
            if completada is None:
                continue
            dia = max(nota.date, completada)
            if not d0 <= dia <= d1:
                continue
            if corte and dia == d1 and completada == d1 and not registrada_a_la_hora(factura):
                continue
            contadas.append((nota, dia))
        return contadas, pagos

    # ------------------------------------------------------------------
    # Qué pedidos cuentan (la base ``vendido`` de la vendedora)
    # ------------------------------------------------------------------

    @api.model
    def _pedidos_vendidos(self, d0, d1, vendedor=None):
        """Los pedidos facturados por completo con su día de venta en ``d0``–``d1`` (lo de la vendedora)."""
        Order = self.env['sale.order']
        dominio = Order._dcasa_dominio_vendido(desde=d0, hasta=d1) + self._clausula_vendedor(vendedor)
        return Order.search_fetch(dominio, CAMPOS_DEL_PEDIDO)

    # ------------------------------------------------------------------
    # Las cifras de un periodo
    # ------------------------------------------------------------------

    @api.model
    def _medir(self, d0, d1, base, vendedor=None, corte=None, con_ganancia=False, con_cobrado=False):
        """Las cifras de un periodo en una base: ``cuantas`` (facturas; en ``vendido``, pedidos), ``notas`` (notas de
        crédito que restan), ``de_pedido`` (cuántas de esas facturas salieron de un pedido de una vendedora),
        ``sin_itbms``, ``itbms``, ``total``, ``ganancia`` (si se pide), ``falta_por_cobrar`` (solo «Con abonos», con
        ITBMS) y ``cobrado`` (si se pide y quien mira ve los cobros; con ITBMS). Trae también lo que se contó: ``filas``
        (facturas) o ``pedidos`` (``vendido``, sin corte), para la lista que lo explica."""
        if base == BASE_VENDIDO:
            pedidos = self._pedidos_vendidos(d0, d1, vendedor)
            medida = {
                'pedidos': pedidos,
                'cuantas': len(pedidos), 'notas': 0, 'de_pedido': len(pedidos),
                'sin_itbms': sum(pedidos.mapped('amount_untaxed')),
                'itbms': sum(pedidos.mapped('amount_tax')),
                'total': sum(pedidos.mapped('amount_total')),
                'ganancia': self._ganancia_de([('id', 'in', pedidos.ids)]) if con_ganancia else None,
                'falta_por_cobrar': None, 'cobrado': None,
            }
        else:
            filas, pagos = self._filas_y_pagos(d0, d1, base, vendedor, corte)
            facturas = [fila for fila in filas if not fila['es_nota']]
            redondear = self.env.company.currency_id.round
            medida = {
                'filas': filas,
                'cuantas': len(facturas), 'notas': len(filas) - len(facturas),
                'de_pedido': sum(1 for fila in facturas if fila['de_pedido']),
                'sin_itbms': redondear(sum(fila['sin_itbms'] for fila in filas)),
                'itbms': redondear(sum(fila['itbms'] for fila in filas)),
                'total': redondear(sum(fila['total'] for fila in filas)),
                'ganancia': self._ganancia_de_filas(filas) if con_ganancia else None,
                'falta_por_cobrar': None, 'cobrado': None,
            }
            if base == BASE_CON_ABONOS:
                medida['falta_por_cobrar'] = self._falta_por_cobrar(facturas, pagos, d1, corte)
        if con_cobrado and self._puede('account.payment'):
            medida['cobrado'] = self._cobrado(d0, d1, vendedor, corte)
        return medida

    @api.model
    def _falta_por_cobrar(self, facturas, pagos, d1, corte=None):
        """Lo que faltaba por cobrar de esas facturas al cierre del día ``d1`` (o a su hora de corte), con ITBMS: el
        total de cada una menos lo pagado (y las notas de crédito aplicadas) con fecha hasta ese día."""
        falta = 0.0
        for fila in facturas:
            pagado = sum(
                pago['monto'] for pago in pagos.get(fila['id'], [])
                if pago['fecha'] < d1 or (pago['fecha'] == d1 and (not corte or pago['registro'] <= corte)))
            falta += max(fila['total'] - pagado, 0.0)
        return round(falta, 2)

    @api.model
    def _ganancia_de_filas(self, filas):
        """La ganancia de esas facturas: venta neta menos costo, sin ITBMS (``_ganancia_por_documento``). Una factura
        con mercancía sin costo cargado no inventa ganancia: queda fuera y se cuenta aparte (``ventas_sin_costo``). Las
        notas de crédito restan la ganancia de lo devuelto."""
        por_documento = self._ganancia_por_documento([fila['id'] for fila in filas])
        utilidad = neta = 0.0
        con_costo = sin_costo = 0
        for fila in filas:
            ganancia = por_documento.get(fila['id'], {'neta': 0.0, 'utilidad': 0.0, 'sin_costo': False})
            if ganancia['sin_costo']:
                sin_costo += 1
                continue
            utilidad += ganancia['utilidad']
            neta += ganancia['neta']
            if not fila['es_nota']:
                con_costo += 1
        return {
            'valor': round(utilidad, 2),
            'porcentaje': round(utilidad / neta * 100, 1) if neta > 0 else None,
            # La venta de mercancía de esas mismas facturas: el margen sin redondear (Comparar lo da en puntos).
            'neta': neta,
            'ventas_con_costo': con_costo,
            'ventas_sin_costo': sin_costo,
        }

    @api.model
    def _ganancia_por_documento(self, ids):
        """``{documento_id: {'neta', 'utilidad', 'sin_costo'}}`` de facturas y notas de crédito de cliente, línea por
        línea, con la misma regla de los pedidos (``dcasa_base/models/utilidad.py``):

        * cuenta la **mercancía** (producto almacenable o consumible) y las líneas **negativas** que no son mercancía
          (el descuento global, el de importe fijo, un premio); el flete y los demás servicios positivos no entran;
        * el costo de una línea que salió de un pedido es el que el pedido guardó al confirmarse; el de una factura sin
          pedido (también las del sistema anterior) es el **costo de hoy del producto**, la misma regla que ya usan las
          ventas hechas antes de esta pantalla;
        * mercancía con costo 0, o una línea sin producto que suma, deja la factura «sin costo»: no inventa ganancia;
        * los anticipos no cuentan (la mercancía cuenta cuando se factura)."""
        if not ids:
            return {}
        lineas = self.env['account.move.line'].sudo().search_fetch(
            [('move_id', 'in', ids), ('move_id.move_type', 'in', ('out_invoice', 'out_refund')),
             ('display_type', '=', 'product')],
            ['move_id', 'product_id', 'quantity', 'balance', 'product_uom_id', 'sale_line_ids', 'is_downpayment'])
        resultado = {}
        for linea in lineas:
            ganancia = resultado.setdefault(linea.move_id.id, {'neta': 0.0, 'utilidad': 0.0, 'sin_costo': False})
            if linea.is_downpayment:
                continue
            signo = -1 if linea.move_id.move_type == 'out_refund' else 1
            venta = -linea.balance                 # con su signo: en una nota de crédito, negativa
            suma = venta * signo > 0               # suma a la venta (no es una rebaja)
            producto = linea.product_id
            if producto and producto.type == 'consu':
                costo = self._costo_unitario(linea)
                if costo <= 0:
                    ganancia['sin_costo'] = True
                    continue
                ganancia['neta'] += venta
                ganancia['utilidad'] += venta - costo * linea.quantity * signo
            elif suma and not producto:
                ganancia['sin_costo'] = True       # se vendió algo que no se sabe qué es: no se inventa su costo
            elif not suma and venta:
                ganancia['neta'] += venta          # una rebaja: baja lo cobrado y la ganancia
                ganancia['utilidad'] += venta
        return resultado

    @api.model
    def _costo_unitario(self, linea):
        """El costo de una unidad de la línea de factura, sin ITBMS, en su unidad: el que guardó el pedido al
        confirmarse o, sin pedido, el costo de hoy del producto."""
        venta = linea.sale_line_ids[:1]
        unidad = linea.product_uom_id
        if venta:
            costo = venta.dcasa_costo_unitario
            if venta.product_uom_id and unidad and venta.product_uom_id != unidad:
                costo = venta.product_uom_id._compute_price(costo, unidad)
            return costo
        producto = linea.product_id.with_company(linea.company_id)
        return producto.uom_id._compute_price(producto.standard_price, unidad or producto.uom_id)

    @api.model
    def _unidades_por_producto(self, filas):
        """``{producto: (unidades, sin_itbms)}`` de lo vendido en esas facturas, sin servicios (flete, descuentos) ni
        anticipos. Las notas de crédito restan las unidades devueltas."""
        ids = [fila['id'] for fila in filas]
        if not ids:
            return {}
        lineas = self.env['account.move.line'].sudo().search_fetch(
            [('move_id', 'in', ids), ('move_id.move_type', 'in', ('out_invoice', 'out_refund')),
             ('display_type', '=', 'product'), ('product_id', '!=', False), ('product_id.type', '!=', 'service'),
             ('is_downpayment', '=', False)],
            ['move_id', 'product_id', 'quantity', 'balance'])
        suma = {}
        for linea in lineas:
            signo = -1 if linea.move_id.move_type == 'out_refund' else 1
            unidades, sin_itbms = suma.get(linea.product_id, (0.0, 0.0))
            suma[linea.product_id] = (unidades + signo * linea.quantity, sin_itbms - linea.balance)
        return suma

    @api.model
    def _dominio_de_cobros(self, d0, d1):
        """Lo cobrado a clientes entre dos días (con ITBMS): pagos recibidos y confirmados (en proceso o pagados), por
        su fecha. La misma definición de «Cobrado hoy» de la caja del Inicio."""
        return [('payment_type', '=', 'inbound'), ('state', 'in', ('in_process', 'paid')),
                ('date', '>=', d0), ('date', '<=', d1)]

    @api.model
    def _cobrado(self, d0, d1, vendedor=None, corte=None):
        """Lo cobrado entre ``d0`` y ``d1``. Con ``vendedor``: solo lo aplicado a SUS facturas (la vendedora de la
        factura, ``_duenas``: la del pedido o, sin pedido, la de la factura), aunque lo haya registrado Caja. Un cobro
        sin aplicar a una factura (un anticipo suelto) cuenta en el total del equipo, pero no es de ninguna
        vendedora."""
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
        aplicados = []
        for parcial in parciales:
            for propia, otra in ((parcial.debit_move_id, parcial.credit_move_id),
                                 (parcial.credit_move_id, parcial.debit_move_id)):
                factura = otra.move_id
                if propia.id in de_los_cobros and factura.move_type == 'out_invoice' and factura.state == 'posted':
                    aplicados.append((factura.id, parcial.amount))
        if not aplicados:
            return 0.0
        duenas = self._duenas(self._documentos([factura_id for factura_id, _monto in aplicados]))
        return round(sum(monto for factura_id, monto in aplicados if duenas[factura_id][0] == vendedor), 2)

    @api.model
    def _por_vendedora(self, medida):
        """``{user_id o 'sin': [cuantas, sin_itbms]}`` de lo que se contó en una medida (facturas o pedidos). Las notas
        de crédito restan del monto de su vendedora y no cuentan como venta."""
        suma = defaultdict(lambda: [0, 0.0])
        if 'filas' in medida:
            for fila in medida['filas']:
                if not fila['es_nota']:
                    suma[fila['vendedora']][0] += 1
                suma[fila['vendedora']][1] += fila['sin_itbms']
        else:
            for pedido in medida['pedidos']:
                clave = pedido.user_id.id or SIN_VENDEDORA
                suma[clave][0] += 1
                suma[clave][1] += pedido.amount_untaxed
        return suma

    @api.model
    def _productos_mas_vendidos(self, medida, limite=5):
        """``[(producto, unidades, sin_itbms)]`` de lo que se contó en una medida, de más a menos unidades, sin
        servicios (flete, descuentos) ni anticipos: de las facturas o, en ``vendido``, de las líneas de los pedidos."""
        if 'filas' in medida:
            filas = [(producto, unidades, sin_itbms)
                     for producto, (unidades, sin_itbms) in self._unidades_por_producto(medida['filas']).items()
                     if unidades > 0]
        else:
            grupos = self.env['sale.order.line']._read_group(
                [('order_id', 'in', medida['pedidos'].ids), ('display_type', '=', False),
                 ('is_downpayment', '=', False), ('product_id.type', '!=', 'service')],
                ['product_id'], ['product_uom_qty:sum', 'price_subtotal:sum'])
            filas = [(producto, unidades, sin_itbms) for producto, unidades, sin_itbms in grupos if producto]
        return sorted(filas, key=lambda fila: (-fila[1], fila[0].id))[:limite]
