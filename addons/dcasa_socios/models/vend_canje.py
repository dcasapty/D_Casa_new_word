from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from . import reglas as R
from . import reglas_vendedores as RV
from .dcasa_canje import ESTADOS_CANJE
from .dcasa_compra import inicio_del_mes_en_panama

GRUPO_VENDEDORA = 'sales_team.group_sale_salesman'


class DcasaPremio(models.Model):
    """El catálogo de premios es uno solo; unos son para socios y otros para vendedores."""

    _inherit = 'dcasa.premio'

    para_vendedores = fields.Boolean(
        string='Para vendedores', copy=False,
        help='Solo lo ven y lo canjean los vendedores, con sus puntos de vendedor. Los socios no lo ven.')

    @api.constrains('para_vendedores', 'puntos', 'costo')
    def _check_vendedores_no_bajo_el_costo(self):
        """Un premio de vendedores nunca se vende por debajo de lo que cuesta: los puntos son un tope de gasto,
        no una forma de regalar mercancía."""
        reglas = R.cargar_reglas()
        por_dolar = (reglas.get('canje') or {}).get('puntosPorDolar')
        if not por_dolar:
            return
        for premio in self.filtered('para_vendedores'):
            minimo = RV.puntos_minimos_de_premio(premio.costo, por_dolar, reglas)
            if premio.costo and premio.puntos < minimo:
                raise ValidationError(self.env._(
                    'El premio «%(premio)s» cuesta %(costo)s a D’CASA y pide %(puntos)s puntos: '
                    'tiene que pedir al menos %(minimo)s (su costo en puntos, con el margen que exige el programa).',
                    premio=premio.name, costo=premio.costo, puntos=premio.puntos, minimo=minimo))

    @api.model
    def _catalogo(self, tipo=None):
        """El catálogo de los socios no enseña los premios de los vendedores."""
        return super()._catalogo(tipo).filtered(lambda premio: not premio.para_vendedores)

    @api.model
    def _catalogo_vendedores(self):
        premios = self.sudo().search([('para_vendedores', '=', True), ('libre', '=', False)])
        return premios.filtered(lambda premio: premio._disponible())


class DcasaVendCanje(models.Model):
    """Un premio de vendedor pedido. Los puntos salen AL PEDIR, como una reserva (igual que en Socios); si el código
    vence o se cancela, un asiento contrario los devuelve enteros. Solo se canjea con puntos YA disponibles."""

    _name = 'dcasa.vend.canje'
    _description = 'Canje de puntos de vendedor'
    _order = 'solicitado_en desc, id desc'
    _rec_name = 'codigo'

    codigo = fields.Char(required=True, readonly=True, index=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Vendedor', required=True, readonly=True, index=True,
                                 ondelete='restrict')
    premio_id = fields.Many2one('dcasa.premio', required=True, readonly=True, ondelete='restrict')
    premio_nombre = fields.Char(string='Nombre del premio', required=True, readonly=True)
    puntos = fields.Integer(required=True, readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True, default=lambda self: self.env.company.currency_id)
    valor = fields.Monetary(readonly=True)
    costo = fields.Monetary(readonly=True)
    estado = fields.Selection(ESTADOS_CANJE, required=True, readonly=True, default='solicitado', index=True)
    origen = fields.Selection([('panel', 'Panel del vendedor'), ('mostrador', 'Mostrador')], required=True,
                              readonly=True, default='panel')
    solicitado_en = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now, index=True)
    expira_en = fields.Datetime(string='Vence', required=True, readonly=True)
    entregado_en = fields.Datetime(readonly=True)
    entregado_por = fields.Char(readonly=True)
    cerrado_en = fields.Datetime(readonly=True)
    cerrado_motivo = fields.Char(readonly=True)

    _codigo_unico = models.Constraint('UNIQUE(codigo)', 'Ese código de canje ya existe.')

    @api.model
    def _pedir(self, partner, premio, origen='panel'):
        reglas = R.cargar_reglas()
        canje_reglas = RV.seccion(reglas).get('canje') or {}
        ficha = partner.commercial_partner_id.sudo()
        premio = premio.sudo()
        if not RV.seccion(reglas).get('programaActivo'):
            raise UserError(self.env._('El programa de vendedores todavía no está encendido.'))
        # Serializa los pedidos del mismo vendedor (igual que Socios): dos toques seguidos no gastan dos veces el saldo.
        self.env.cr.execute('UPDATE res_partner SET write_date = write_date WHERE id = %s', [ficha.id])
        ficha.invalidate_recordset(['dcasa_vend_saldo', 'dcasa_vend_disponible'])
        if ficha.dcasa_vendedor_estado != 'activo':
            raise UserError(self.env._('Tu cuenta de vendedor no está activa. Escríbenos por WhatsApp y lo revisamos.'))
        if ficha.dcasa_vendedor_tipo == 'externo' and not canje_reglas.get('externosHabilitado'):
            raise UserError(self.env._(
                'El canje para vendedores externos todavía no está habilitado. Tus puntos se siguen acumulando '
                'y no se pierden: escríbenos por WhatsApp y te avisamos cuando se abra.'))
        if not premio.para_vendedores or not premio._disponible():
            raise UserError(self.env._('Ese premio se agotó o no está disponible para vendedores. Elige otro.'))
        minimo = canje_reglas.get('puntosMinimosParaCanjear')
        if minimo is not None and premio.puntos < minimo:
            raise UserError(self.env._('El canje mínimo es de %s puntos.', R.como_puntos(minimo)))
        if self.sudo().search_count([('partner_id', '=', ficha.id), ('premio_id', '=', premio.id),
                                     ('estado', '=', 'solicitado')], limit=1):
            raise UserError(self.env._('Ya tienes ese premio pedido. Enséñalo en la tienda antes de que venza.'))
        tope = canje_reglas.get('canjesPorVendedorAlMes')
        if tope is not None:
            del_mes = self.sudo().search_count([
                ('partner_id', '=', ficha.id), ('estado', 'in', ('solicitado', 'entregado')),
                ('solicitado_en', '>=', inicio_del_mes_en_panama(fields.Datetime.now()))])
            if del_mes >= tope:
                raise UserError(self.env._('Llegaste al máximo de %s canjes de este mes.', tope))
        disponible = ficha.dcasa_vend_disponible
        if disponible < premio.puntos:
            raise UserError(self.env._(
                'Te faltan %s puntos disponibles para ese premio (los de ventas recientes se liberan en unos días).',
                R.como_puntos(R.faltan_para(disponible, premio.puntos))))
        ahora = fields.Datetime.now()
        for _intento in range(10):
            codigo = R.nuevo_codigo_canje()
            if not self.sudo().search_count([('codigo', '=', codigo)], limit=1):
                break
        canje = self.sudo().create({
            'codigo': codigo, 'partner_id': ficha.id, 'premio_id': premio.id, 'premio_nombre': premio.name,
            'puntos': premio.puntos, 'valor': premio.valor, 'costo': premio.costo, 'origen': origen,
            'solicitado_en': ahora,
            'expira_en': ahora + timedelta(hours=canje_reglas.get('vigenciaDelCodigoHoras') or 72),
        })
        self.env['dcasa.vend.movimiento']._asentar(
            ficha, 'canje', -premio.puntos, 'vendedor' if origen == 'panel' else self.env.user.login,
            canje_id=canje.id, motivo=f'Pediste: {canje.premio_nombre}', disponible_desde=ahora)
        if premio.stock_limitado:
            premio.stock -= 1
        return canje

    def _exigir_vendedora(self):
        if not self.env.su and not self.env.user.has_group(GRUPO_VENDEDORA):
            raise AccessError(self.env._('Solo el equipo de ventas entrega o cancela premios.'))

    def action_entregar(self):
        self._exigir_vendedora()
        for canje in self.sudo():
            if canje.estado != 'solicitado':
                raise UserError(self.env._('El premio %s ya no está pendiente.', canje.codigo))
            canje.write({'estado': 'entregado', 'entregado_en': fields.Datetime.now(),
                         'entregado_por': self.env.user.login})
        return True

    def _cerrar(self, estado, motivo, autor):
        Movimiento = self.env['dcasa.vend.movimiento'].sudo()
        for canje in self.sudo().filtered(lambda c: c.estado == 'solicitado'):
            canje.write({'estado': estado, 'cerrado_en': fields.Datetime.now(), 'cerrado_motivo': motivo})
            asiento = Movimiento.search([('canje_id', '=', canje.id), ('tipo', '=', 'canje')], limit=1)
            if asiento:
                asiento._reversar(motivo, autor)
            if canje.premio_id.stock_limitado:
                canje.premio_id.stock += 1

    def action_cancelar(self):
        self._exigir_vendedora()
        self._cerrar('cancelado', self.env._('Lo canceló la tienda. Te devolvimos los puntos.'), self.env.user.login)
        return True

    def _cancelar_por_vendedor(self):
        self._cerrar('cancelado', 'Lo cancelaste tú.', 'vendedor')

    @api.model
    def _vencer_codigos(self):
        vencidos = self.sudo().search([('estado', '=', 'solicitado'), ('expira_en', '<=', fields.Datetime.now())],
                                      limit=500)
        vencidos._cerrar('vencido', 'Venció el código sin pasar por la tienda. Te devolvimos los puntos.', 'sistema')


class DcasaCanje(models.Model):
    """El cron horario de Socios también vence los códigos de los vendedores (no hace falta otro cron)."""

    _inherit = 'dcasa.canje'

    @api.model
    def _cron_programa(self):
        res = super()._cron_programa()
        self.env['dcasa.vend.canje']._vencer_codigos()
        self.env['dcasa.vend.comision']._revisar_pagos()
        return res
