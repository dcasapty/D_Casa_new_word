import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from . import reglas as R
from . import reglas_vendedores as RV
from .dcasa_compra import inicio_del_mes_en_panama

_logger = logging.getLogger(__name__)

TIPOS_COMISION = [('directa', 'Venta propia'), ('patrocinio', 'Patrocinio')]

# Por qué una comisión salió en cero (o salió recortada). Queda escrito en la comisión: Gerencia lo ve y el vendedor
# lo entiende. Un tope o una regla nunca hace fallar la venta.
RESULTADOS = [
    ('pagada', 'Pagada'),
    ('recortada', 'Pagada, recortada por un tope'),
    ('compra-propia', 'No se paga: es una compra del propio vendedor o de alguien de su misma ficha.'),
    ('dentro-de-la-colmena', 'No se paga: compró alguien de su misma colmena (su patrocinador o uno de sus directos).'),
    ('comprador-es-vendedor', 'No se paga: quien compró también es vendedor del programa.'),
    ('registrada-por-el-vendedor', 'No se paga: el propio vendedor registró esta venta en caja.'),
    ('vendedor-suspendido', 'No se paga: el vendedor está suspendido.'),
    ('bajo-el-minimo', 'No se paga: la venta no llegó al mínimo.'),
    ('ya-pago-la-primera', 'No se paga: solo la primera compra del cliente da comisión.'),
    ('techo-agotado', 'No se paga: la venta ya llegó a su techo de costo.'),
    ('tope-del-mes', 'No se paga: el vendedor llegó a su tope de este mes.'),
    ('patrocinador-sin-ventas', 'No se paga el patrocinio: el patrocinador no tiene ventas propias este mes.'),
    ('freno-global', 'No se paga: el programa llegó al freno global de este mes.'),
    ('sin-configurar', 'No se paga: falta una cifra del programa.'),
]
PAGADOS = ('pagada', 'recortada')


class DcasaVendComision(models.Model):
    """Lo que una venta pagada le da a un vendedor (directa) o a su patrocinador (patrocinio).

    Se crea sola cuando la factura del cliente queda pagada. Se congelan la venta neta, la tasa, los puntos y la
    versión de las reglas: si mañana cambia la economía, esta comisión sigue explicando sus puntos. No se edita ni
    se borra: se anula.
    """

    _name = 'dcasa.vend.comision'
    _description = 'Comisión de vendedor'
    _order = 'registrada_en desc, id desc'

    name = fields.Char(string='Factura', required=True, readonly=True)
    factura_normal = fields.Char(required=True, readonly=True, index=True)
    move_id = fields.Many2one('account.move', string='Factura de Odoo', readonly=True, index='btree_not_null',
                              ondelete='restrict')
    partner_id = fields.Many2one('res.partner', string='Vendedor', required=True, readonly=True, index=True,
                                 ondelete='restrict')
    tipo = fields.Selection(TIPOS_COMISION, required=True, readonly=True)
    cliente_id = fields.Many2one('res.partner', string='Cliente', readonly=True, ondelete='restrict',
                                 help='Quién compró.')
    directo_id = fields.Many2one('res.partner', string='Vendedor directo', readonly=True, ondelete='restrict',
                                 help='En un patrocinio: el vendedor de la colmena que trajo la venta.')
    via = fields.Selection([('codigo', 'Código en la venta'), ('vinculo', 'Cliente ligado al vendedor')],
                           readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True,
                                  default=lambda self: self.env.company.currency_id)
    neto_centavos = fields.Integer(string='Venta neta (centavos)', readonly=True, required=True,
                                   help='Sin ITBMS y ya con los descuentos: lo que de verdad entró.')
    neto = fields.Monetary(string='Venta neta', compute='_compute_neto', store=True)
    puntos_calculados = fields.Integer(readonly=True, help='Lo que daba la regla antes de los topes.')
    puntos = fields.Integer(readonly=True, required=True)
    resultado = fields.Selection(RESULTADOS, required=True, readonly=True, index=True)
    reglas_version = fields.Integer(string='Versión de reglas', readonly=True, required=True)
    registrada_en = fields.Datetime(readonly=True, required=True, default=fields.Datetime.now, index=True)
    disponible_desde = fields.Datetime(readonly=True)
    anulada_en = fields.Datetime(readonly=True, copy=False)
    anulada_por = fields.Char(readonly=True, copy=False)
    anulada_motivo = fields.Char(readonly=True, copy=False)
    estado = fields.Selection([('activa', 'Activa'), ('anulada', 'Anulada')], compute='_compute_estado', store=True)

    _unica_por_factura = models.Constraint(
        'UNIQUE(factura_normal, partner_id, tipo)', 'Esa factura ya se registró para ese vendedor.')
    _puntos_sin_negativos = models.Constraint('CHECK(puntos >= 0 AND neto_centavos > 0)',
                                              'Una comisión no es negativa y sale de una venta mayor que cero.')

    @api.depends('neto_centavos')
    def _compute_neto(self):
        for comision in self:
            comision.neto = comision.neto_centavos / 100.0

    @api.depends('anulada_en')
    def _compute_estado(self):
        for comision in self:
            comision.estado = 'anulada' if comision.anulada_en else 'activa'

    # ------------------------------------------------------------------------
    # Quién gana por esta factura
    # ------------------------------------------------------------------------

    @api.model
    def _vendedor_de_la_factura(self, move, reglas):
        """``(vendedor, via)`` de una factura. Mientras el cliente siga ligado a un vendedor, la comisión es de ese
        vendedor: el código de otro no se lo quita (si no, bastaría con anotar el código propio en el mostrador)."""
        cliente = move.commercial_partner_id
        ligado = cliente.dcasa_vendedor_ligado_id
        meses = RV.meses_de_vinculacion(reglas)
        if ligado and meses and cliente.dcasa_vendedor_ligado_en \
                and cliente.dcasa_vendedor_ligado_en + timedelta(days=30 * meses) > fields.Datetime.now():
            return ligado, ('codigo' if move.dcasa_vendedor_id == ligado else 'vinculo')
        if move.dcasa_vendedor_id:
            return move.dcasa_vendedor_id.commercial_partner_id, 'codigo'
        return self.env['res.partner'], False

    @api.model
    def _ya_gano_en_el_mes(self, vendedor, tipos=('directa', 'patrocinio')):
        inicio = inicio_del_mes_en_panama(fields.Datetime.now())
        comisiones = self.sudo().search([
            ('partner_id', '=', vendedor.id), ('tipo', 'in', tipos), ('anulada_en', '=', False),
            ('registrada_en', '>=', inicio)])
        return sum(comisiones.mapped('puntos'))

    @api.model
    def _ventas_propias_del_mes(self, vendedor):
        """A cuántos clientes DISTINTOS les vendió el vendedor (con comisión pagada) en el mes: cinco ventas al mismo
        cliente no demuestran que sea un vendedor activo."""
        inicio = inicio_del_mes_en_panama(fields.Datetime.now())
        return len(self.sudo().search([
            ('partner_id', '=', vendedor.id), ('tipo', '=', 'directa'), ('anulada_en', '=', False),
            ('puntos', '>', 0), ('registrada_en', '>=', inicio)]).cliente_id)

    @api.model
    def _es_cliente_nuevo(self, move):
        """¿Es de verdad un cliente nuevo? Solo lo es quien se puede identificar (celular, cédula o correo) y no tiene
        ninguna compra pagada antes, ni él ni otra ficha que comparta esos datos (un duplicado o un número cambiado
        no vuelve «nuevo» a un cliente de la casa). Sin forma de identificarlo, se trata como cliente existente."""
        cliente = move.commercial_partner_id.sudo()
        if cliente._is_public():
            return False
        celular = cliente.dcasa_celular or R.celular_normal(cliente.phone)
        claves = [clave for clave in (
            ('vat', '=', cliente.vat) if cliente.vat else None,
            ('email', '=ilike', cliente.email) if cliente.email else None,
            ('dcasa_celular', '=', celular) if celular else None) if clave]
        if not claves:
            return False
        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        mismas = cliente | Partner.search(['|'] * (len(claves) - 1) + claves).commercial_partner_id
        if self.env['account.move'].sudo().search_count([
                ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('id', '!=', move.id),
                ('commercial_partner_id', 'in', mismas.ids),
                ('payment_state', 'in', ('paid', 'in_payment'))], limit=1):
            return False
        # Compras del sistema anterior que se cargaron a mano en Socios (sin factura en Odoo).
        return not self.env['dcasa.compra'].sudo().search_count([
            ('partner_id', 'in', mismas.ids), ('anulada_en', '=', False), ('move_id', '!=', move.id)], limit=1)

    @api.model
    def _datos_del_freno_global(self):
        """``(puntos emitidos, venta neta de la tienda)`` en los últimos 30 días, para el freno global."""
        desde = fields.Datetime.now() - timedelta(days=30)
        emitido = sum(self.sudo().search([('anulada_en', '=', False), ('registrada_en', '>=', desde)]).mapped('puntos'))
        ventas = self.env['account.move'].sudo()._read_group(
            [('move_type', 'in', ('out_invoice', 'out_refund')), ('state', '=', 'posted'),
             ('invoice_date', '>=', desde.date())], [], ['amount_untaxed_signed:sum'])
        return emitido, R.a_centavos(ventas[0][0] or 0)

    @api.model
    def _ventas_netas_recientes(self, vendedor, reglas):
        """Lo vendido por el vendedor en los últimos días del escalón (para subirle la tasa)."""
        dias = (RV.seccion(reglas).get('comision') or {}).get('diasParaEscalon')
        if not dias or not (RV.seccion(reglas).get('comision') or {}).get('escalones'):
            return 0
        desde = fields.Datetime.now() - timedelta(days=dias)
        comisiones = self.sudo().search([
            ('partner_id', '=', vendedor.id), ('tipo', '=', 'directa'), ('anulada_en', '=', False),
            ('puntos', '>', 0), ('registrada_en', '>=', desde)])
        return sum(comisiones.mapped('neto_centavos'))

    # ------------------------------------------------------------------------
    # Registrar
    # ------------------------------------------------------------------------

    @api.model
    def _registrar_desde_factura(self, move):
        """Una factura de cliente pagada con vendedor da sus comisiones. Idempotente. Nunca hace fallar el cobro."""
        reglas = R.cargar_reglas()
        if not RV.seccion(reglas).get('programaActivo'):
            return self.browse()
        vendedor, via = self._vendedor_de_la_factura(move, reglas)
        if not vendedor or not vendedor.dcasa_vendedor_codigo:
            return self.browse()
        factura = R.factura_normal(move.name)
        if self.sudo().search_count([('factura_normal', '=', factura), ('partner_id', '=', vendedor.id),
                                     ('tipo', '=', 'directa')], limit=1):
            return self.browse()
        neto = R.a_centavos(move.amount_untaxed_signed)
        if neto <= 0:
            return self.browse()
        cliente = move.commercial_partner_id
        base = {'name': move.name, 'factura_normal': factura, 'move_id': move.id, 'cliente_id': cliente.id,
                'via': via, 'neto_centavos': neto, 'reglas_version': reglas['version'],
                'currency_id': move.company_id.currency_id.id}
        autor = (move.invoice_user_id or self.env.user).login

        nuevo = self._es_cliente_nuevo(move)
        directa = self._calcular_directa(vendedor, cliente, neto, reglas, via, nuevo,
                                         move.sudo().dcasa_vendedor_anotado_por.partner_id)
        # El cliente ya recibió sus puntos de Socios (y el referido que esa compra disparó): lo que sobra del techo se
        # reparte entre vendedor y patrocinador.
        compras = move.sudo().dcasa_compra_ids.filtered(lambda c: not c.anulada_en)
        puntos_del_cliente = sum(self.env['dcasa.movimiento'].sudo().search([
            ('compra_id', 'in', compras.ids), ('tipo', 'in', ('compra', 'referido')), ('puntos', '>', 0)
        ]).mapped('puntos'))
        patrocinador = vendedor.dcasa_vendedor_patrocinador_id
        # El patrocinio nace de una venta que sí pagó al vendedor directo (sin comisión directa no hay patrocinio) y,
        # salvo que las reglas digan otra cosa, de una venta con código: la recompra de un cliente ligado no lo da.
        paga_patrocinio = (via != 'vinculo' or RV.patrocinio_paga_en_recompras(reglas)) \
            and (nuevo or not RV.patrocinio_solo_clientes_nuevos(reglas))
        patrocinio = (self._calcular_patrocinio(patrocinador, cliente, neto, reglas)
                      if patrocinador and paga_patrocinio and directa['resultado'] in PAGADOS else None)
        directa_final, patrocinio_final, recorte = directa['puntos'], (patrocinio or {}).get('puntos', 0), None
        if directa['resultado'] in PAGADOS:
            directa_final, patrocinio_final, recortado = RV.repartir_bajo_el_techo(
                directa['puntos'], patrocinio_final, puntos_del_cliente, neto, reglas)
            recorte = 'techo' if recortado else None
            # Último seguro: lo emitido a vendedores en 30 días nunca pasa de un porcentaje de todo lo vendido.
            emitido, ventas = self._datos_del_freno_global()
            directa_final, patrocinio_final, frenado = RV.repartir_bajo_el_freno_global(
                directa_final, patrocinio_final, emitido, ventas, reglas)
            recorte = 'freno' if frenado else recorte
        creadas = self._crear(base, vendedor, 'directa', directa, directa_final, recorte, reglas, autor)
        if patrocinio:
            creadas |= self._crear({**base, 'directo_id': vendedor.id}, patrocinador, 'patrocinio', patrocinio,
                                   patrocinio_final, recorte, reglas, autor, origen=vendedor)
        # Quedó ligado: la próxima compra de este cliente, aunque llegue sin código, también es de este vendedor.
        if directa['resultado'] in PAGADOS and RV.meses_de_vinculacion(reglas) and not cliente.dcasa_vendedor_ligado_id:
            cliente.sudo().write({'dcasa_vendedor_ligado_id': vendedor.id,
                                  'dcasa_vendedor_ligado_en': fields.Datetime.now()})
        return creadas

    def _crear(self, base, beneficiario, tipo, calculo, puntos_finales, recorte, reglas, autor, origen=None):
        """``recorte`` dice quién bajó los puntos de esta venta: ``'techo'``, ``'freno'`` o ``None``."""
        resultado = calculo['resultado']
        if resultado in PAGADOS:
            if puntos_finales <= 0:
                resultado = 'freno-global' if recorte == 'freno' else 'techo-agotado'
            elif resultado == 'recortada' or recorte or puntos_finales < calculo['puntos']:
                resultado = 'recortada'
            else:
                resultado = 'pagada'
        else:
            puntos_finales = 0
        ahora = fields.Datetime.now()
        ventas_previas = self.sudo().search_count([
            ('partner_id', '=', beneficiario.id), ('puntos', '>', 0), ('anulada_en', '=', False)])
        comision = self.sudo().create({
            **base, 'partner_id': beneficiario.id, 'tipo': tipo,
            'puntos_calculados': calculo.get('calculados', calculo['puntos']), 'puntos': puntos_finales,
            'resultado': resultado, 'registrada_en': ahora,
            'disponible_desde': RV.disponible_desde(ahora, reglas, ventas_previas) if puntos_finales else False,
        })
        if puntos_finales > 0:
            texto = 'Venta {}' if tipo == 'directa' else 'Venta de un vendedor de tu colmena {}'
            self.env['dcasa.vend.movimiento']._asentar(
                beneficiario, 'comision' if tipo == 'directa' else 'patrocinio', puntos_finales, autor,
                comision_id=comision.id, origen_partner_id=(origen or comision.cliente_id).id,
                motivo=texto.format(comision.name), disponible_desde=comision.disponible_desde)
        return comision

    def _calcular_directa(self, vendedor, cliente, neto, reglas, via=None, nuevo=True, anotador=None):
        """El resultado de la comisión del vendedor que trajo la venta, antes de los topes de la venta."""
        def sin(resultado):
            return {'puntos': 0, 'resultado': resultado}
        if vendedor.dcasa_vendedor_estado != 'activo' or not vendedor.active:
            return sin('vendedor-suspendido')
        if vendedor._dcasa_es_la_misma_persona(cliente):
            return sin('compra-propia')
        # Separación de funciones: quien teclea la venta en caja no se paga a sí mismo por su propio trabajo de caja.
        if anotador and via == 'codigo' and vendedor._dcasa_es_la_misma_persona(anotador):
            return sin('registrada-por-el-vendedor')
        bloquear = RV.seccion(reglas).get('bloquearComprasDentroDeLaColmena', True)
        if bloquear and vendedor._dcasa_en_la_colmena_de(cliente):
            return sin('dentro-de-la-colmena')
        # Un vendedor que compra con el código de otro cobra como un descuento disfrazado: las compras de cualquier
        # vendedor afiliado solo dan puntos de cliente.
        if cliente.commercial_partner_id.dcasa_vendedor_codigo:
            return sin('comprador-es-vendedor')
        try:
            puntos = RV.comision_directa(neto, reglas, self._ventas_netas_recientes(vendedor, reglas))
        except R.FaltaConfigurar:
            return sin('sin-configurar')
        if not nuevo:
            # Un cliente que ya había comprado no lo trajo el código: se paga una fracción (la recompra de un
            # cliente ligado a este vendedor, una; la venta con código a un cliente que ya era de la tienda, otra).
            ligado = cliente.dcasa_vendedor_ligado_id == vendedor
            puntos = (RV.aplicar_factor_de_recompra(puntos, reglas) if ligado or via == 'vinculo'
                      else RV.aplicar_factor_de_cliente_existente(puntos, reglas))
        if puntos <= 0:
            return sin('bajo-el-minimo')
        if (RV.seccion(reglas)['comision']['pagaEn'] == 'primera-compra'
                and self.sudo().search_count([
                    ('partner_id', '=', vendedor.id), ('cliente_id', '=', cliente.id), ('tipo', '=', 'directa'),
                    ('anulada_en', '=', False), ('puntos', '>', 0)], limit=1)):
            return sin('ya-pago-la-primera')
        tope = (RV.seccion(reglas).get('techos') or {}).get('porVendedorAlMesPuntos')
        permitido = RV.topar_al_mes(puntos, self._ya_gano_en_el_mes(vendedor), tope)
        if permitido <= 0:
            return sin('tope-del-mes')
        return {'puntos': permitido, 'calculados': puntos,
                'resultado': 'recortada' if permitido < puntos else 'pagada'}

    def _calcular_patrocinio(self, patrocinador, cliente, neto, reglas):
        """El resultado de lo que gana el patrocinador por la venta de su vendedor directo (un solo nivel)."""
        if patrocinador.dcasa_vendedor_estado != 'activo' or not patrocinador.active:
            return {'puntos': 0, 'resultado': 'vendedor-suspendido'}
        if patrocinador._dcasa_es_la_misma_persona(cliente):
            return {'puntos': 0, 'resultado': 'compra-propia'}
        try:
            puntos = RV.comision_patrocinio(neto, reglas)
        except R.FaltaConfigurar:
            return {'puntos': 0, 'resultado': 'sin-configurar'}
        if puntos <= 0:
            return {'puntos': 0, 'resultado': 'bajo-el-minimo'}
        minimas = RV.ventas_propias_minimas_para_patrocinar(reglas)
        if minimas and self._ventas_propias_del_mes(patrocinador) < minimas:
            return {'puntos': 0, 'resultado': 'patrocinador-sin-ventas'}
        ya_patrocinio = self._ya_gano_en_el_mes(patrocinador, ('patrocinio',))
        # El patrocinio nunca es la mayor parte de lo que gana el patrocinador: se topa contra su propia comisión.
        permitido = RV.topar_patrocinio(puntos, ya_patrocinio, self._ya_gano_en_el_mes(patrocinador, ('directa',)),
                                        reglas)
        tope = (RV.seccion(reglas).get('techos') or {}).get('patrocinioPorPatrocinadorAlMesPuntos')
        permitido = RV.topar_al_mes(permitido, ya_patrocinio, tope)
        if permitido <= 0:
            return {'puntos': 0, 'resultado': 'tope-del-mes'}
        return {'puntos': permitido, 'calculados': puntos,
                'resultado': 'recortada' if permitido < puntos else 'pagada'}

    # ------------------------------------------------------------------------
    # Anular
    # ------------------------------------------------------------------------

    @api.model
    def _revisar_pagos(self):
        """Cada día: una comisión cuya factura dejó de estar pagada (un contracargo, un pago desconciliado, un
        cheque devuelto) sin nota de crédito pierde sus puntos. Es la red que atrapa lo que ningún evento avisó."""
        desde = fields.Datetime.now() - timedelta(days=120)
        comisiones = self.sudo().search([
            ('anulada_en', '=', False), ('puntos', '>', 0), ('move_id', '!=', False), ('registrada_en', '>=', desde),
            ('move_id.payment_state', 'in', ('not_paid', 'partial'))])
        for comision in comisiones:
            try:
                with self.env.cr.savepoint():
                    comision._anular(self.env._(
                        'El pago de la factura %s se revirtió o ya no está completo.', comision.name), 'sistema')
            except Exception:  # noqa: BLE001  — una comisión mala no frena a las demás ni al resto del cron
                _logger.exception('No se pudo revisar la comisión %s', comision.id)
        return len(comisiones)

    def _anular(self, motivo, autor):
        """Anula la comisión y devuelve sus puntos con un asiento contrario (el libro no se edita)."""
        motivo = (motivo or '').strip()
        if not motivo:
            raise UserError(self.env._('Escribe por qué se anula: el vendedor lo va a leer en su cuenta.'))
        Movimiento = self.env['dcasa.vend.movimiento'].sudo()
        for comision in self.sudo():
            if comision.anulada_en:
                continue
            comision.write({'anulada_en': fields.Datetime.now(), 'anulada_por': autor, 'anulada_motivo': motivo})
            asientos = Movimiento.search([
                ('comision_id', '=', comision.id), ('tipo', 'in', ('comision', 'patrocinio'))])
            ya_reversados = Movimiento.search([('reversa_id', 'in', asientos.ids)]).reversa_id
            for asiento in asientos - ya_reversados:
                asiento._reversar(motivo, autor)
        return True

    def _devolucion_parcial(self, nota_credito, neto_factura_centavos, autor):
        """Una nota de crédito parcial descuenta la parte proporcional de los puntos de cada comisión."""
        devuelto = R.a_centavos(abs(nota_credito.amount_untaxed_signed))
        for comision in self.sudo().filtered(lambda c: not c.anulada_en and c.puntos):
            puntos = -(comision.puntos * devuelto // max(neto_factura_centavos, 1))
            if puntos:
                self.env['dcasa.vend.movimiento']._asentar(
                    comision.partner_id, 'ajuste', puntos, autor, comision_id=comision.id,
                    motivo=f'Devolución parcial ({nota_credito.name}) de la venta {comision.name}',
                    disponible_desde=comision.disponible_desde or fields.Datetime.now())
