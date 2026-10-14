from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from . import reglas as R
from . import reglas_vendedores as RV
from .dcasa_compra import inicio_del_mes_en_panama

TIPOS_COMISION = [('directa', 'Venta propia'), ('patrocinio', 'Patrocinio')]

# Por qué una comisión salió en cero (o salió recortada). Queda escrito en la comisión: Gerencia lo ve y el vendedor
# lo entiende. Un tope o una regla nunca hace fallar la venta.
RESULTADOS = [
    ('pagada', 'Pagada'),
    ('recortada', 'Pagada, recortada por un tope'),
    ('compra-propia', 'No se paga: es una compra del propio vendedor o de alguien de su misma ficha.'),
    ('dentro-de-la-colmena', 'No se paga: compró alguien de su misma colmena (su patrocinador o uno de sus directos).'),
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
        """Cuántas ventas propias (con comisión pagada) lleva el vendedor en el mes."""
        inicio = inicio_del_mes_en_panama(fields.Datetime.now())
        return self.sudo().search_count([
            ('partner_id', '=', vendedor.id), ('tipo', '=', 'directa'), ('anulada_en', '=', False),
            ('puntos', '>', 0), ('registrada_en', '>=', inicio)])

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

        directa = self._calcular_directa(vendedor, cliente, neto, reglas, via)
        # El cliente ya recibió sus puntos de Socios: lo que sobra del techo se reparte entre vendedor y patrocinador.
        puntos_del_cliente = sum(move.sudo().dcasa_compra_ids.filtered(lambda c: not c.anulada_en).mapped('puntos'))
        patrocinador = vendedor.dcasa_vendedor_patrocinador_id
        # El patrocinio nace de una venta que sí pagó al vendedor directo (sin comisión directa no hay patrocinio) y,
        # salvo que las reglas digan otra cosa, de una venta con código: la recompra de un cliente ligado no lo da.
        paga_patrocinio = via != 'vinculo' or RV.patrocinio_paga_en_recompras(reglas)
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
        comision = self.sudo().create({
            **base, 'partner_id': beneficiario.id, 'tipo': tipo,
            'puntos_calculados': calculo.get('calculados', calculo['puntos']), 'puntos': puntos_finales,
            'resultado': resultado, 'registrada_en': ahora,
            'disponible_desde': RV.disponible_desde(ahora, reglas) if puntos_finales else False,
        })
        if puntos_finales > 0:
            texto = 'Venta {}' if tipo == 'directa' else 'Venta de un vendedor de tu colmena {}'
            self.env['dcasa.vend.movimiento']._asentar(
                beneficiario, 'comision' if tipo == 'directa' else 'patrocinio', puntos_finales, autor,
                comision_id=comision.id, origen_partner_id=(origen or comision.cliente_id).id,
                motivo=texto.format(comision.name), disponible_desde=comision.disponible_desde)
        return comision

    def _calcular_directa(self, vendedor, cliente, neto, reglas, via=None):
        """El resultado de la comisión del vendedor que trajo la venta, antes de los topes de la venta."""
        def sin(resultado):
            return {'puntos': 0, 'resultado': resultado}
        if vendedor.dcasa_vendedor_estado != 'activo' or not vendedor.active:
            return sin('vendedor-suspendido')
        if vendedor._dcasa_es_la_misma_persona(cliente):
            return sin('compra-propia')
        bloquear = RV.seccion(reglas).get('bloquearComprasDentroDeLaColmena', True)
        if bloquear and vendedor._dcasa_en_la_colmena_de(cliente):
            return sin('dentro-de-la-colmena')
        try:
            puntos = RV.comision_directa(neto, reglas, self._ventas_netas_recientes(vendedor, reglas))
        except R.FaltaConfigurar:
            return sin('sin-configurar')
        if via == 'vinculo':
            # El cliente ya era de este vendedor y llegó sin código: la recompra paga una fracción.
            puntos = RV.aplicar_factor_de_recompra(puntos, reglas)
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
