"""«Forma de pago» de cada factura: con qué se cobró (pedido de la dueña y del jefe, 2026-11-19): «en la lista de
Facturas no hay una columna en la que pueda ver el método de pago con el que se cobró; nos interesa ver, filtrar y
bajar el Excel con ese dato».

**Qué es.** En D'CASA la forma de pago es el **diario del pago** (Efectivo, Yappy, Tarjeta, Banco…): lo mismo que
muestra «Cobrado por forma de pago» del tablero. Por eso la definición de qué pagos cuentan no se repite aquí: sale de
``dcasa.tablero._dominio_de_cobros`` (pagos de clientes, ``inbound``, en proceso o pagados) sin sus fechas, y una
prueba compara las dos pantallas para que nunca discrepen.

**Los campos** (guardados, para filtrar, agrupar y exportar):

* ``dcasa_diario_pago_ids``: los diarios de los pagos aplicados a la factura (para filtrar por diario). Solo lo ven
  quienes pueden leer diarios (Facturación y contabilidad): un cliente del portal que lee su factura no tiene permiso
  sobre los diarios y, sin esta restricción, leerla entera le daría error.
* ``dcasa_forma_pago``: esos mismos diarios con su nombre, unidos con « + » (``Efectivo + Yappy``). Es texto: lo ve
  quien ve la factura.

**Las decisiones** (cada una tiene su prueba en ``tests/test_forma_pago.py``):

* *Pagada en parte con un diario y el resto con otro* (abonos, apartados de ``dcasa_abonos``): salen los dos diarios,
  ``Efectivo + Yappy``. Solo cuenta lo ya aplicado: una factura con un primer abono dice solo con qué se abonó.
* *Orden:* alfabético por el nombre del diario (sin importar mayúsculas), no el cronológico. Así el mismo conjunto de
  diarios da siempre el mismo texto y «Agrupar por Forma de pago» no parte en dos «Efectivo + Yappy» y
  «Yappy + Efectivo». Un diario repetido (dos abonos en efectivo) sale una sola vez.
* *Idioma:* el nombre de un diario es traducible («Bank» / «Banco» en los diarios del plan contable) y el texto se
  guarda en la base. Se lee SIEMPRE en el idioma de D'CASA (``DCASA_LANG``, ``es_419``), tanto para el texto como para
  el orden, sin importar quién dispare el cálculo: la actualización del módulo y un cron corren sin idioma o en inglés,
  una usuaria en español; si el texto dependiera de eso, el mismo diario quedaría escrito de dos maneras, «Agrupar» lo
  partiría en dos y buscar «Banco» no encontraría las facturas guardadas como «Bank».
* *Pago anulado, rechazado, en borrador, desconciliado o devuelto:* deja de contar y el campo se pone al día solo
  (depende de lo mismo que el estado de pago de Odoo: ``_compute_payment_state``). Se mira la conciliación de verdad
  (``account.partial.reconcile``), no ``matched_payment_ids``, que Odoo deja puesto aunque el pago se desconcilie.
* *Nota de crédito conciliada contra la factura:* no es un pago ni un diario, pero explica por qué no se cobró todo:
  la factura dice ``Nota de crédito`` al final (``Efectivo + Nota de crédito``; una factura anulada del todo con una
  nota dice solo ``Nota de crédito``). No entra en ``dcasa_diario_pago_ids``. La palabra no se traduce a propósito: se
  guarda en la base y no puede cambiar con el idioma de quien dispara el cálculo.
* *Factura sin cobrar* (borrador, publicada sin pagos, anulada): vacío. «Sin pagar» ya lo dice el Estado, y un vacío
  deja la columna limpia; al agrupar, esas facturas salen juntas en «Ninguno».
* *Factura PAGADA sin ningún pago ni nota de crédito detectados* (``payment_state`` en pagada o en pago): dice
  «Sin pago registrado». Es lo que pasa con un cobro conciliado directo contra una línea del extracto del banco o con un
  asiento manual: Odoo la da por pagada, pero no hay un pago de Odoo del que sacar el diario, y dejarla en blanco se
  confundiría con «sin cobrar». No inventa un diario: dice lo que falta. Una factura en cero no entra (queda en blanco).
  Sin decidir por la contadora: ver la pregunta abierta en ``docs/CONTABILIDAD.md``.
* *Qué documentos:* facturas y recibos de clientes (``out_invoice``, ``out_receipt``). Las notas de crédito de
  clientes (``out_refund``) quedan vacías: no son un cobro, y la factura a la que se aplicaron ya lo dice. Las de
  proveedores y los asientos no llevan la columna.
* *Un cobro conciliado directo con una línea del extracto del banco* (sin un pago de por medio) no es un pago de Odoo y
  no cuenta como diario (tampoco entra en el «Cobrado por forma de pago» del tablero): la factura sale con
  «Sin pago registrado».

**Rendimiento.** El campo se calcula en lote: una sola consulta SQL para toda la tanda de facturas y una lectura
agrupada de los pagos y los diarios, sin una consulta por factura (al actualizar el módulo en producción se calcula para
todas las facturas que ya existen, de a 1000; ``tests/test_forma_pago.py`` cuenta las consultas).
"""
from collections import defaultdict

from odoo import api, fields, models
from odoo.addons.dcasa_base import DCASA_LANG
from odoo.tools import SQL

NOTA_DE_CREDITO = 'Nota de crédito'
SIN_PAGO_REGISTRADO = 'Sin pago registrado'
SEPARADOR = ' + '
# Los documentos de cliente que se cobran. Las notas de crédito (out_refund) no son un cobro.
TIPOS_CON_FORMA_DE_PAGO = ('out_invoice', 'out_receipt')


class AccountMoveFormaPago(models.Model):
    _inherit = 'account.move'

    dcasa_diario_pago_ids = fields.Many2many(
        'account.journal', 'dcasa_move_diario_pago_rel', 'move_id', 'journal_id', string='Diarios de los pagos',
        compute='_compute_dcasa_forma_pago', store=True, copy=False, readonly=True,
        groups='account.group_account_invoice,account.group_account_readonly,account.group_account_manager',
        help='Los diarios de los pagos aplicados a la factura (Efectivo, Yappy, Tarjeta…). Sirve para filtrar.')
    dcasa_forma_pago = fields.Char(
        'Forma de pago', compute='_compute_dcasa_forma_pago', store=True, copy=False, readonly=True,
        help='Con qué se cobró la factura: los diarios de sus pagos unidos con « + » (Efectivo + Yappy). '
             'Con una nota de crédito aplicada, sale «Nota de crédito». Vacío si todavía no se cobró nada. Si la '
             'factura está pagada pero no hay ningún pago de Odoo (por ejemplo, se concilió directo con el extracto '
             'del banco), dice «Sin pago registrado».')

    # Las mismas dependencias del estado de pago de Odoo (``_compute_payment_state``): cambia la conciliación o cambia
    # el estado del pago. Más lo que cambia el texto: el tipo del pago, el diario y su nombre.
    # (``line_ids.matched_*`` y ``matched_payment_ids`` se parecen a ``reconciled_payment_ids`` y no sobran: el cálculo
    # parte de la conciliación de verdad y de las notas de crédito, que no son pagos y ``reconciled_payment_ids`` no
    # trae, y ``reconciled_payment_ids`` también incluye lo que Odoo deja atado aunque se desconcilie. ``payment_state``
    # y ``amount_total`` son para «Sin pago registrado».)
    @api.depends('move_type', 'payment_state', 'amount_total', 'matched_payment_ids', 'line_ids.matched_debit_ids',
                 'line_ids.matched_credit_ids', 'reconciled_payment_ids.state', 'reconciled_payment_ids.payment_type',
                 'reconciled_payment_ids.journal_id.name', 'reconciled_payment_ids.journal_id.currency_id')
    def _compute_dcasa_forma_pago(self):
        con_forma = self.filtered(lambda factura: factura.id and factura.move_type in TIPOS_CON_FORMA_DE_PAGO)
        sin_forma = self - con_forma
        sin_forma.dcasa_forma_pago = False
        sin_forma.dcasa_diario_pago_ids = False
        if not con_forma:
            return
        pagos_de, con_nota = con_forma._dcasa_pagos_y_notas_aplicados()
        Pago = self.env['account.payment']
        todos = Pago.browse({pago for ids in pagos_de.values() for pago in ids})
        todos.fetch(['state', 'payment_type', 'journal_id'])
        cuentan = todos.filtered_domain(self._dcasa_dominio_de_pago_que_cuenta())
        # Se arma todo primero y se asigna por grupos: las facturas que comparten diarios (o texto) se escriben juntas,
        # así lo que cuesta escribir depende de cuántas combinaciones de diarios hay, no de cuántas facturas.
        por_diarios, por_texto = defaultdict(self.browse), defaultdict(self.browse)
        idioma = self._dcasa_idioma_del_texto()
        for factura in con_forma:
            diarios = (Pago.browse(pagos_de.get(factura.id, ())) & cuentan).journal_id.with_context(lang=idioma)
            diarios = diarios.sorted(lambda diario: (diario.display_name.casefold(), diario.id))
            nombres = list(dict.fromkeys(diarios.mapped('display_name')))
            if factura.id in con_nota:
                nombres.append(NOTA_DE_CREDITO)
            if not nombres and factura.payment_state in ('paid', 'in_payment') \
                    and not factura.currency_id.is_zero(factura.amount_total):
                nombres.append(SIN_PAGO_REGISTRADO)
            por_diarios[tuple(diarios.ids)] |= factura
            por_texto[SEPARADOR.join(nombres) or False] |= factura
        for ids, facturas in por_diarios.items():
            facturas.dcasa_diario_pago_ids = self.env['account.journal'].browse(ids)
        for texto, facturas in por_texto.items():
            facturas.dcasa_forma_pago = texto

    @api.model
    def _dcasa_idioma_del_texto(self):
        """El idioma con que se escribe el texto guardado: el de D'CASA, siempre el mismo (no el de quien dispara el
        cálculo). Si ese idioma no está activo (una base sin ``dcasa_base`` al día), inglés, también fijo."""
        return self.env['res.lang']._get_code(DCASA_LANG) or 'en_US'

    @api.model
    def _dcasa_dominio_de_pago_que_cuenta(self):
        """Qué pagos cuentan como cobro: los de ``dcasa.tablero._dominio_de_cobros`` (pagos de clientes recibidos y
        confirmados, en proceso o pagados) sin sus fechas: para una factura cuenta el pago sin importar el día. Una
        sola definición de «cobro» para el tablero y para esta columna."""
        dominio = self.env['dcasa.tablero']._dominio_de_cobros(False, False)
        return [condicion for condicion in dominio if condicion[0] != 'date']

    def _dcasa_pagos_y_notas_aplicados(self):
        """Lo aplicado a estas facturas, en una sola consulta: ``({factura: {pagos}}, {facturas con una nota de crédito
        conciliada})``. Se parte de la conciliación (``account.partial.reconcile``) de lo que se le debe al cliente
        (cuenta por cobrar): el otro lado de cada conciliación es un pago, una nota de crédito u otra cosa (una
        diferencia de cambio, un extracto del banco) que aquí no cuenta. Los pagos que Odoo ata a la factura sin
        asiento (``matched_payment_ids`` sin ``move_id``, lo que usa para decir «en pago») también se suman."""
        ids = tuple(self.ids)
        self.env['account.move'].flush_model(['move_type'])
        self.env['account.move.line'].flush_model(['move_id', 'account_id'])
        self.env['account.partial.reconcile'].flush_model(['debit_move_id', 'credit_move_id'])
        self.env['account.payment'].flush_model(['move_id'])
        self.env['account.account'].flush_model(['account_type'])
        consultas = [SQL("""
            SELECT propia.move_id AS factura, pago.id AS pago, otro_asiento.move_type AS tipo
              FROM account_partial_reconcile parcial
              JOIN account_move_line propia ON propia.id = parcial.%(propia)s
              JOIN account_account cuenta ON cuenta.id = propia.account_id
              JOIN account_move_line otra ON otra.id = parcial.%(otra)s
              JOIN account_move otro_asiento ON otro_asiento.id = otra.move_id
              LEFT JOIN account_payment pago ON pago.move_id = otro_asiento.id
             WHERE propia.move_id IN %(ids)s
               AND cuenta.account_type = 'asset_receivable'
               AND otro_asiento.id != propia.move_id
        """, propia=SQL.identifier(propia), otra=SQL.identifier(otra), ids=ids)
            for propia, otra in (('debit_move_id', 'credit_move_id'), ('credit_move_id', 'debit_move_id'))]
        pagos_de = defaultdict(set)
        con_nota = set()
        for fila in self.env.execute_query_dict(SQL(' UNION ALL ').join(consultas)):
            if fila['pago']:
                pagos_de[fila['factura']].add(fila['pago'])
            elif fila['tipo'] == 'out_refund':
                con_nota.add(fila['factura'])
        for factura in self:
            pagos_de[factura.id].update(factura.matched_payment_ids.filtered(lambda pago: not pago.move_id).ids)
        return pagos_de, con_nota
