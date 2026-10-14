import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import reglas as R
from . import reglas_vendedores as RV

ESTADOS_VENDEDOR = [('activo', 'Activo'), ('suspendido', 'Suspendido')]
TIPOS_VENDEDOR = [('empleado', 'Empleado de D’CASA'), ('externo', 'Persona de afuera')]
GRUPO_VENDEDORA = 'sales_team.group_sale_salesman'
GRUPO_GERENTE = 'sales_team.group_sale_manager'
# Versión de los términos del programa de vendedores (sube cuando cambian las condiciones).
VERSION_TERMINOS_VENDEDORES = 1


def _id_fiscal(valor):
    """Cédula o RUC sin guiones, puntos ni espacios, en mayúsculas: «8-888-888» y «8888888» son la misma."""
    return re.sub(r'[^0-9A-Za-z]', '', valor or '').upper()


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # --- La ficha del vendedor ---------------------------------------------------
    # Un vendedor es la MISMA ficha que el cliente y el socio (llave: celular). Ser vendedor es un estado más.
    dcasa_vendedor_codigo = fields.Char(
        string='Código de vendedor', readonly=True, copy=False, index='btree_not_null',
        help='VEN + 6. Es lo que el vendedor le da a quien compra para que la venta cuente como suya.')
    dcasa_vendedor_estado = fields.Selection(ESTADOS_VENDEDOR, string='Estado como vendedor', copy=False,
                                             help='Vacío: no es vendedor.')
    dcasa_vendedor_tipo = fields.Selection(TIPOS_VENDEDOR, string='Tipo de vendedor', copy=False)
    dcasa_vendedor_afiliado_en = fields.Datetime(string='Afiliado el', readonly=True, copy=False)
    dcasa_vendedor_afiliado_por = fields.Char(string='Afiliado por', readonly=True, copy=False)
    dcasa_vend_terminos_version = fields.Integer(string='Términos de vendedor aceptados', readonly=True, copy=False)
    dcasa_vend_terminos_en = fields.Datetime(string='Términos de vendedor aceptados el', readonly=True, copy=False)

    # --- La colmena (un solo nivel) ------------------------------------------------
    dcasa_vendedor_patrocinador_id = fields.Many2one(
        'res.partner', string='Patrocinado por', copy=False, index='btree_not_null', ondelete='restrict',
        domain="[('dcasa_vendedor_codigo', '!=', False)]",
        help='Quién lo trajo como vendedor. Se escribe una vez y no se cambia jamás. Gana un porcentaje de sus '
             'ventas; de los vendedores que él traiga, nada (un solo nivel).')
    dcasa_vendedor_directo_ids = fields.One2many('res.partner', 'dcasa_vendedor_patrocinador_id',
                                                 string='Vendedores que patrocina')
    dcasa_vend_directos_count = fields.Integer(string='Directos', compute='_compute_dcasa_vend_directos_count')

    # --- El cliente ligado a un vendedor ---------------------------------------------
    dcasa_vendedor_ligado_id = fields.Many2one(
        'res.partner', string='Cliente de (vendedor)', copy=False, index='btree_not_null', ondelete='restrict',
        help='El vendedor que lo trajo con su código. Mientras dure el vínculo (vendedores.vinculacion.meses), sus '
             'compras cuentan para ese vendedor aunque lleguen sin código.')
    dcasa_vendedor_ligado_en = fields.Datetime(string='Ligado el', readonly=True, copy=False)

    # --- Puntos de vendedor ----------------------------------------------------------
    dcasa_vend_movimiento_ids = fields.One2many('dcasa.vend.movimiento', 'partner_id',
                                                string='Movimientos de puntos de vendedor')
    dcasa_vend_comision_ids = fields.One2many('dcasa.vend.comision', 'partner_id', string='Comisiones')
    dcasa_vend_saldo = fields.Integer(
        string='Puntos de vendedor', compute='_compute_dcasa_vend_saldo', search='_search_dcasa_vend_saldo',
        help='La suma de su libro de vendedor. No se guarda en ningún otro sitio.')
    dcasa_vend_disponible = fields.Integer(string='Disponibles para canjear', compute='_compute_dcasa_vend_saldo')
    dcasa_vend_por_liberar = fields.Integer(
        string='Por liberar', compute='_compute_dcasa_vend_saldo',
        help='Puntos de ventas recientes: esperan unos días por si hay devoluciones.')

    _dcasa_vendedor_codigo_unico = models.Constraint(
        'UNIQUE(dcasa_vendedor_codigo)', 'Ese código de vendedor ya existe.')
    _dcasa_no_es_su_patrocinador = models.Constraint(
        'CHECK(dcasa_vendedor_patrocinador_id IS NULL OR dcasa_vendedor_patrocinador_id <> id)',
        'Nadie se patrocina a sí mismo.')

    # ------------------------------------------------------------------------
    # Cómputos
    # ------------------------------------------------------------------------

    @api.depends('dcasa_vendedor_directo_ids.dcasa_vendedor_codigo')
    def _compute_dcasa_vend_directos_count(self):
        for partner in self:
            directos = partner.dcasa_vendedor_directo_ids.filtered('dcasa_vendedor_codigo')
            partner.dcasa_vend_directos_count = len(directos)

    @api.depends('dcasa_vend_movimiento_ids.puntos', 'dcasa_vend_movimiento_ids.disponible_desde')
    def _compute_dcasa_vend_saldo(self):
        Movimiento = self.env['dcasa.vend.movimiento']
        ids = self.filtered('id')
        totales, disponibles = Movimiento._saldos(ids), Movimiento._saldos_disponibles(ids)
        for partner in self:
            partner.dcasa_vend_saldo = totales.get(partner.id, 0)
            partner.dcasa_vend_disponible = disponibles.get(partner.id, 0)
            partner.dcasa_vend_por_liberar = partner.dcasa_vend_saldo - partner.dcasa_vend_disponible

    def _search_dcasa_vend_saldo(self, operator, value):
        operadores = {'>': '>', '>=': '>=', '<': '<', '<=': '<=', '=': '=', '!=': '!='}
        if operator not in operadores or not isinstance(value, int):
            return NotImplemented
        self.env['dcasa.vend.movimiento'].flush_model(['partner_id', 'puntos'])
        self.env.cr.execute(
            'SELECT partner_id FROM dcasa_vend_movimiento GROUP BY partner_id '
            f'HAVING SUM(puntos) {operadores[operator]} %s', [value])
        con_saldo = [fila[0] for fila in self.env.cr.fetchall()]
        # Quien no tiene asientos tiene saldo 0.
        if self._saldo_cero_cumple(operator, value):
            con_asientos = self.env['dcasa.vend.movimiento'].sudo().search([]).partner_id.ids
            return ['|', ('id', 'in', con_saldo), ('id', 'not in', con_asientos)]
        return [('id', 'in', con_saldo)]

    # ------------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------------

    def write(self, vals):
        if vals.get('dcasa_vendedor_patrocinador_id'):
            for partner in self:
                actual = partner.dcasa_vendedor_patrocinador_id
                if actual and actual.id != vals['dcasa_vendedor_patrocinador_id']:
                    raise UserError(self.env._(
                        '%s ya tiene quien lo patrocina (%s). Eso no se cambia nunca: si se pudiera, bastaría con '
                        'esperar a que alguien venda mucho para quitárselo.',
                        partner.display_name, actual.display_name))
        elif 'dcasa_vendedor_patrocinador_id' in vals and self.filtered('dcasa_vendedor_patrocinador_id'):
            raise UserError(self.env._('Quién patrocina a un vendedor se escribe una vez y no se borra.'))
        return super().write(vals)

    @api.constrains('dcasa_vendedor_patrocinador_id')
    def _check_dcasa_colmena_sin_ciclos(self):
        for partner in self.filtered('dcasa_vendedor_patrocinador_id'):
            ancestro, vistos = partner.dcasa_vendedor_patrocinador_id, {partner.id}
            while ancestro:
                if ancestro.id in vistos:
                    raise ValidationError(self.env._('Una colmena no puede cerrarse en círculo.'))
                vistos.add(ancestro.id)
                ancestro = ancestro.dcasa_vendedor_patrocinador_id

    # ------------------------------------------------------------------------
    # Quién es quién (antifraude)
    # ------------------------------------------------------------------------

    def _dcasa_es_la_misma_persona(self, otro):
        """¿Son la misma persona? Misma ficha, misma cédula o RUC, mismo celular o mismo correo: el vendedor no gana
        por sus propias compras ni por las de alguien que comparte sus datos."""
        self.ensure_one()
        a, b = self.commercial_partner_id.sudo(), otro.commercial_partner_id.sudo()
        if a == b:
            return True
        if _id_fiscal(a.vat) and _id_fiscal(a.vat) == _id_fiscal(b.vat):
            return True
        celulares = {x for x in (a.dcasa_celular, R.celular_normal(a.phone)) if x}
        celulares_b = {x for x in (b.dcasa_celular, R.celular_normal(b.phone)) if x}
        if celulares & celulares_b:
            return True
        return bool(a.email and b.email and a.email.strip().lower() == b.email.strip().lower())

    def _dcasa_en_la_colmena_de(self, otro):
        """¿``otro`` es el patrocinador de este vendedor o uno de sus directos?"""
        self.ensure_one()
        persona = otro.commercial_partner_id
        patrocinador = self.dcasa_vendedor_patrocinador_id
        return bool(persona) and (persona == patrocinador or persona.dcasa_vendedor_patrocinador_id == self)

    # ------------------------------------------------------------------------
    # Afiliar
    # ------------------------------------------------------------------------

    @api.model
    def _dcasa_vendedor_por_codigo(self, codigo):
        codigo = RV.codigo_vendedor_normal(codigo)
        if not RV.es_codigo_vendedor_valido(codigo):
            return self.browse()
        return self.sudo().with_context(active_test=False).search([('dcasa_vendedor_codigo', '=', codigo)], limit=1)

    def _dcasa_afiliar_vendedor(self, tipo, patrocinador=None, autor=None, acepto_terminos=False):
        """Hace vendedor a esta ficha. Devuelve la ficha.

        Exige: que la persona acepte los términos (el consentimiento lo da ella; aquí queda anotado quién lo recogió),
        su cédula o RUC (con ella se evita que gane por sus propias compras) y un celular válido (su llave para
        entrar a /socios). El patrocinador, si lo hay, tiene que ser un vendedor activo, que no se cierre un círculo y
        que no pase el tope de directos.
        """
        self.ensure_one()
        ficha = self.commercial_partner_id.sudo()
        if ficha.dcasa_vendedor_codigo:
            raise UserError(self.env._('%s ya es vendedor.', ficha.display_name))
        if tipo not in dict(TIPOS_VENDEDOR):
            raise UserError(self.env._('Elige si es empleado o persona de afuera.'))
        if not acepto_terminos:
            raise UserError(self.env._('La persona tiene que leer y aceptar los términos del programa de vendedores.'))
        if not _id_fiscal(ficha.vat):
            raise UserError(self.env._(
                'Falta su cédula o RUC en la ficha. Se necesita para su constancia y para que nunca gane por sus '
                'propias compras.'))
        celular = ficha.dcasa_celular or R.celular_normal(ficha.phone)
        if not R.celular_valido(celular):
            raise UserError(self.env._(
                'Falta un celular de Panamá válido (8 números): es con lo que entra a su cuenta.'))
        if ficha.dcasa_socio_estado == 'suspendido':
            raise UserError(self.env._('Esta persona está suspendida en Socios: primero se reactiva.'))
        patrocinador = patrocinador.commercial_partner_id.sudo() if patrocinador else self.env['res.partner']
        if patrocinador:
            self._dcasa_validar_patrocinador(ficha, patrocinador)
        for _intento in range(10):
            codigo = RV.nuevo_codigo_vendedor()
            if not self.sudo().with_context(active_test=False).search_count(
                    [('dcasa_vendedor_codigo', '=', codigo)], limit=1):
                break
        ficha._dcasa_asegurar_ficha(creado_por=autor)
        ahora = fields.Datetime.now()
        ficha.write({
            'dcasa_vendedor_codigo': codigo, 'dcasa_vendedor_estado': 'activo', 'dcasa_vendedor_tipo': tipo,
            'dcasa_vendedor_afiliado_en': ahora, 'dcasa_vendedor_afiliado_por': autor or self.env.user.login,
            'dcasa_vend_terminos_version': VERSION_TERMINOS_VENDEDORES, 'dcasa_vend_terminos_en': ahora,
            **({'dcasa_vendedor_patrocinador_id': patrocinador.id} if patrocinador else {}),
        })
        ficha._dcasa_dejar_rastro(self.env._(
            'Afiliado como vendedor (%(tipo)s) por %(quien)s%(patrocinador)s. Aceptó los términos v%(version)s.',
            tipo=dict(TIPOS_VENDEDOR)[tipo], quien=autor or self.env.user.name,
            patrocinador=self.env._(' · patrocinado por %s', patrocinador.display_name) if patrocinador else '',
            version=VERSION_TERMINOS_VENDEDORES))
        return ficha

    def _dcasa_validar_patrocinador(self, ficha, patrocinador):
        if patrocinador == ficha:
            raise UserError(self.env._('Nadie se patrocina a sí mismo.'))
        if not patrocinador.dcasa_vendedor_codigo or patrocinador.dcasa_vendedor_estado != 'activo' \
                or not patrocinador.active:
            raise UserError(self.env._('Quien patrocina tiene que ser un vendedor activo.'))
        if ficha._dcasa_es_la_misma_persona(patrocinador):
            raise UserError(self.env._('Esa persona comparte sus datos con quien la patrocina: no puede ser.'))
        tope = RV.tope_de_directos(R.cargar_reglas())
        if tope is not None and patrocinador.dcasa_vend_directos_count >= tope:
            raise UserError(self.env._(
                '%(nombre)s ya tiene %(tope)s vendedores patrocinados, que es el máximo de una colmena.',
                nombre=patrocinador.display_name, tope=tope))

    # ------------------------------------------------------------------------
    # Acciones del equipo
    # ------------------------------------------------------------------------

    def action_dcasa_afiliar_vendedor(self):
        self._dcasa_exigir_grupo(GRUPO_VENDEDORA)
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Afiliar como vendedor'),
            'res_model': 'dcasa.afiliar.vendedor.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.commercial_partner_id.id},
        }

    def action_dcasa_suspender_vendedor(self):
        self._dcasa_exigir_grupo(GRUPO_GERENTE)
        for ficha in self.commercial_partner_id:
            ficha.sudo().write({'dcasa_vendedor_estado': 'suspendido'})
            ficha._dcasa_dejar_rastro(self.env._('Vendedor suspendido por %s.', self.env.user.name))
        return True

    def action_dcasa_reactivar_vendedor(self):
        self._dcasa_exigir_grupo(GRUPO_GERENTE)
        for ficha in self.commercial_partner_id.filtered('dcasa_vendedor_codigo'):
            ficha.sudo().write({'dcasa_vendedor_estado': 'activo'})
            ficha._dcasa_dejar_rastro(self.env._('Vendedor reactivado por %s.', self.env.user.name))
        return True

    def action_dcasa_ver_movimientos_vendedor(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Puntos de vendedor de %s', self.display_name),
            'res_model': 'dcasa.vend.movimiento',
            'view_mode': 'list,pivot',
            'domain': [('partner_id', '=', self.commercial_partner_id.id)],
        }

    def action_dcasa_ajustar_vendedor(self):
        self._dcasa_exigir_grupo(GRUPO_GERENTE)
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Ajustar puntos de vendedor'),
            'res_model': 'dcasa.vend.ajuste.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.commercial_partner_id.id},
        }

    def _dcasa_vend_resumen_panel(self):
        """Lo que ve el vendedor en su panel: valores planos (sin registros) para la plantilla."""
        self.ensure_one()
        ficha = self.commercial_partner_id.sudo()
        if not ficha.dcasa_vendedor_codigo:
            return None
        reglas = R.cargar_reglas()
        Comision = self.env['dcasa.vend.comision'].sudo()
        inicio_mes = fields.Datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        del_mes = Comision.search([('partner_id', '=', ficha.id), ('anulada_en', '=', False),
                                   ('registrada_en', '>=', inicio_mes)])
        return {
            'codigo': ficha.dcasa_vendedor_codigo,
            'estado': ficha.dcasa_vendedor_estado,
            'saldo': ficha.dcasa_vend_saldo,
            'disponible': ficha.dcasa_vend_disponible,
            'por_liberar': ficha.dcasa_vend_por_liberar,
            'puntos_del_mes': sum(del_mes.mapped('puntos')),
            'ventas_del_mes': len(del_mes.filtered(lambda c: c.tipo == 'directa' and c.puntos)),
            'directos': ficha.dcasa_vend_directos_count,
            'tope_directos': RV.tope_de_directos(reglas),
            'programa_activo': bool(RV.seccion(reglas).get('programaActivo')),
        }
