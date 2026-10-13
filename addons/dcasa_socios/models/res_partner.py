import os
import secrets

from passlib.context import CryptContext

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain

from . import reglas as R

# El PIN se deriva con PBKDF2-SHA256 y una sal por socio. Antes de derivar se le
# concatena la PIMIENTA (variable de entorno DCASA_PIN_PEPPER), que vive fuera
# de la base: un volcado robado sin ella no se puede atacar por fuerza bruta, y
# seis dígitos se rompen en segundos sin ella.
PIN_CRYPT = CryptContext(schemes=['pbkdf2_sha256'], pbkdf2_sha256__default_rounds=120_000)
ESTADOS_SOCIO = [('activo', 'Activo'), ('suspendido', 'Suspendido')]
# Quién puede tocar la cuenta de un socio desde el backend. Odoo expone por RPC
# (/web/dataset/call_kw, /json/2) todo método público: el grupo se exige en el
# servidor, no solo en el botón.
GRUPO_VENDEDORA = 'sales_team.group_sale_salesman'
GRUPO_GERENTE = 'sales_team.group_sale_manager'


class ResPartner(models.Model):
    _inherit = 'res.partner'
    # El código de socio también encuentra a la persona en cualquier campo de contacto.
    _rec_names_search = ['complete_name', 'email', 'ref', 'vat', 'company_registry', 'dcasa_socio_codigo']

    @api.depends('phone')
    def _compute_dcasa_telefono_digitos(self):
        for partner in self:
            partner.dcasa_telefono_digitos = R.celular_normal(partner.phone) or False

    @api.model
    def _search_display_name(self, operator, value):
        """«6123», «61234567» o «6123-4567» encuentran al cliente por su teléfono o celular."""
        dominio = super()._search_display_name(operator, value)
        digitos = R.solo_digitos(value) if isinstance(value, str) else ''
        if operator == 'ilike' and len(digitos) >= 4 and len(digitos) >= len(value.replace(' ', '')) - 2:
            dominio = Domain.OR([dominio, [('dcasa_telefono_digitos', 'ilike', digitos)],
                                 [('dcasa_celular', 'ilike', digitos)]])
        return dominio

    @api.onchange('phone')
    def _onchange_dcasa_phone_duplicado(self):
        """Avisa ANTES de guardar si ese celular ya es de otro cliente (y de quién)."""
        celular = R.celular_normal(self.phone)
        if not R.celular_valido(celular):
            return None
        otro = self.sudo().with_context(active_test=False).search([
            ('id', 'not in', self.ids + ([self._origin.id] if self._origin.id else [])),
            '|', ('dcasa_telefono_digitos', '=', celular), ('dcasa_celular', '=', celular),
        ], limit=1)
        if otro:
            return {'warning': {
                'title': self.env._('Ese celular ya está registrado'),
                'message': self.env._(
                    'El %(celular)s ya es de %(nombre)s. Busca esa ficha en vez de crear otra: '
                    'un celular, un cliente.', celular=R.celular_fmt(celular), nombre=otro.display_name),
            }}
        return None

    # --- La ficha ------------------------------------------------------------
    # Un cliente y un socio son LA MISMA FICHA: el contacto de Odoo. Estar en el
    # programa es un estado suyo: con PIN es un socio; sin PIN es un cliente que
    # todavía no la reclamó, y sus puntos corren igual.
    dcasa_socio_codigo = fields.Char(
        string='Código de socio', readonly=True, copy=False, index='btree_not_null',
        help="Su identificador en el programa y su código para invitar (DCA + 6).")
    dcasa_celular = fields.Char(
        string='Celular del programa', copy=False, index='btree_not_null',
        help='Ocho dígitos nacionales. Es la llave del socio: un celular, una ficha.')
    dcasa_telefono_digitos = fields.Char(
        string='Teléfono (solo números)', compute='_compute_dcasa_telefono_digitos', store=True,
        index='btree_not_null', help='Para encontrar al cliente escribiendo su celular con o sin guion.')
    dcasa_socio_estado = fields.Selection(ESTADOS_SOCIO, string='Estado en el programa', default='activo',
                                          copy=False)
    dcasa_cumple = fields.Char(string='Cumpleaños (MM-DD)', copy=False,
                               help='Sin año: no hace falta para felicitar a nadie.')
    dcasa_creado_por = fields.Char(string='Alta por', readonly=True, copy=False,
                                   help="'qr' si se registró solo, o el usuario que abrió la ficha.")

    # --- Referido --------------------------------------------------------------
    dcasa_referido_por_id = fields.Many2one(
        'res.partner', string='Invitado por', copy=False, index='btree_not_null', ondelete='restrict',
        domain="[('dcasa_socio_codigo', '!=', False)]",
        help='Se escribe una vez y no se modifica jamás. El padrino gana cuando esta persona hace '
             'su primera compra con puntos.')
    dcasa_referido_en = fields.Datetime(string='Invitado el', readonly=True, copy=False)
    dcasa_referido_pagado_en = fields.Datetime(
        string='Referido pagado el', readonly=True, copy=False,
        help='Cuándo se le pagó al padrino. Impide pagar dos veces.')
    dcasa_ahijado_ids = fields.One2many('res.partner', 'dcasa_referido_por_id', string='Personas que invitó')

    # --- Consentimiento (Ley 81 de 2019) ---------------------------------------
    dcasa_terminos_version = fields.Integer(string='Versión de términos aceptada', readonly=True, copy=False)
    dcasa_terminos_aceptados_en = fields.Datetime(string='Términos aceptados el', readonly=True, copy=False)

    # --- PIN y candado ----------------------------------------------------------
    dcasa_pin_hash = fields.Char(copy=False, groups='base.group_system')
    dcasa_pin_cambiado_en = fields.Datetime(readonly=True, copy=False)
    dcasa_pin_temporal = fields.Boolean(readonly=True, copy=False,
                                        help='La vendedora lo reinició: el socio elige uno nuevo al entrar.')
    dcasa_intentos_fallidos = fields.Integer(readonly=True, copy=False)
    dcasa_bloqueado_hasta = fields.Datetime(string='Bloqueado hasta', readonly=True, copy=False)
    dcasa_reclamada = fields.Boolean(string='Ficha reclamada', compute='_compute_dcasa_reclamada',
                                     help='Tiene PIN: entró al programa. Sin PIN, sus puntos le esperan.')

    # --- Puntos -----------------------------------------------------------------
    dcasa_movimiento_ids = fields.One2many('dcasa.movimiento', 'partner_id', string='Movimientos de puntos')
    dcasa_compra_ids = fields.One2many('dcasa.compra', 'partner_id', string='Compras con puntos')
    dcasa_saldo = fields.Integer(string='Puntos', compute='_compute_dcasa_saldo', search='_search_dcasa_saldo',
                                 help='La suma de su libro de puntos. No se guarda en ningún otro sitio.')
    dcasa_ahijados_count = fields.Integer(string='Invitados', compute='_compute_dcasa_ahijados_count')

    _dcasa_socio_codigo_unico = models.Constraint('UNIQUE(dcasa_socio_codigo)', 'Ese código de socio ya existe.')
    _dcasa_celular_unico = models.Constraint(
        'UNIQUE(dcasa_celular)', 'Ese celular ya es de otra ficha: un celular, un socio.')
    _dcasa_no_es_su_padrino = models.Constraint(
        'CHECK(dcasa_referido_por_id IS NULL OR dcasa_referido_por_id <> id)',
        'Nadie es su propio padrino.')

    # ------------------------------------------------------------------------
    # Cómputos
    # ------------------------------------------------------------------------

    @api.depends('dcasa_pin_cambiado_en')
    def _compute_dcasa_reclamada(self):
        for partner, reclamada in zip(self, self.sudo().mapped(lambda p: bool(p.dcasa_pin_hash)), strict=True):
            partner.dcasa_reclamada = reclamada

    @api.depends('dcasa_movimiento_ids.puntos')
    def _compute_dcasa_saldo(self):
        saldos = self.env['dcasa.movimiento']._saldos(self.filtered('id'))
        for partner in self:
            partner.dcasa_saldo = saldos.get(partner.id, 0)

    def _search_dcasa_saldo(self, operator, value):
        operadores = {'>': '>', '>=': '>=', '<': '<', '<=': '<=', '=': '=', '!=': '!='}
        if operator not in operadores or not isinstance(value, int):
            return NotImplemented
        self.env['dcasa.movimiento'].flush_model(['partner_id', 'puntos'])
        self.env.cr.execute(
            f'SELECT partner_id FROM dcasa_movimiento GROUP BY partner_id HAVING SUM(puntos) {operadores[operator]} %s',
            [value],
        )
        con_saldo = [fila[0] for fila in self.env.cr.fetchall()]
        # Quien no tiene asientos tiene saldo 0.
        if self._saldo_cero_cumple(operator, value):
            con_asientos = self.env['dcasa.movimiento'].sudo().search([]).partner_id.ids
            return ['|', ('id', 'in', con_saldo), ('id', 'not in', con_asientos)]
        return [('id', 'in', con_saldo)]

    @staticmethod
    def _saldo_cero_cumple(operator, value):
        return {'>': 0 > value, '>=': 0 >= value, '<': 0 < value, '<=': 0 <= value,
                '=': value == 0, '!=': value != 0}[operator]

    def _compute_dcasa_ahijados_count(self):
        for partner in self:
            partner.dcasa_ahijados_count = len(partner.dcasa_ahijado_ids)

    # ------------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._dcasa_normalizar(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._dcasa_normalizar(vals)
        if vals.get('dcasa_referido_por_id'):
            self._dcasa_check_padrino_se_escribe_una_vez(vals['dcasa_referido_por_id'])
            vals.setdefault('dcasa_referido_en', fields.Datetime.now())
        elif 'dcasa_referido_por_id' in vals and self.filtered('dcasa_referido_por_id'):
            raise UserError(self.env._('Quién invitó a una persona se escribe una vez y no se borra.'))
        return super().write(vals)

    @api.model
    def _dcasa_normalizar(self, vals):
        if 'dcasa_celular' in vals:
            vals['dcasa_celular'] = R.celular_normal(vals['dcasa_celular']) or False
        if 'dcasa_cumple' in vals:
            vals['dcasa_cumple'] = (vals['dcasa_cumple'] or '').strip() or False

    def _dcasa_check_padrino_se_escribe_una_vez(self, padrino_id):
        for partner in self:
            if partner.dcasa_referido_por_id and partner.dcasa_referido_por_id.id != padrino_id:
                raise UserError(self.env._(
                    '%s ya tiene quien lo invitó (%s). Eso no se cambia nunca: si se pudiera, bastaría '
                    'con esperar a que alguien compre mucho para reclamarlo.',
                    partner.display_name, partner.dcasa_referido_por_id.display_name))
            if not partner.dcasa_referido_por_id and partner.sudo()._dcasa_compras_con_puntos():
                raise UserError(self.env._(
                    '%s ya compró con puntos: el padrino se registra antes de su primera compra.',
                    partner.display_name))

    @api.constrains('dcasa_celular')
    def _check_dcasa_celular(self):
        for partner in self.filtered('dcasa_celular'):
            if not R.celular_valido(partner.dcasa_celular):
                raise ValidationError(self.env._(
                    'Ese celular no parece de Panamá. Son 8 números, como 6026-1919.'))

    @api.constrains('dcasa_cumple')
    def _check_dcasa_cumple(self):
        for partner in self:
            if not R.cumple_valido(partner.dcasa_cumple):
                raise ValidationError(self.env._('Esa fecha de cumpleaños no existe (formato MM-DD).'))

    @api.constrains('dcasa_referido_por_id')
    def _check_dcasa_referido_mutuo(self):
        for partner in self.filtered('dcasa_referido_por_id'):
            if partner.dcasa_referido_por_id.dcasa_referido_por_id == partner:
                raise ValidationError(self.env._('Dos personas no pueden haberse invitado la una a la otra.'))

    # ------------------------------------------------------------------------
    # Ficha
    # ------------------------------------------------------------------------

    def _dcasa_asegurar_ficha(self, creado_por=None):
        """Le da código de socio si no lo tiene. Devuelve la ficha (el partner comercial)."""
        ficha = self.commercial_partner_id.sudo()
        if not ficha.dcasa_socio_codigo:
            for _intento in range(10):
                codigo = R.nuevo_codigo_socio()
                if not self.sudo().with_context(active_test=False).search_count(
                        [('dcasa_socio_codigo', '=', codigo)], limit=1):
                    break
            valores = {
                'dcasa_socio_codigo': codigo,
                'dcasa_creado_por': creado_por or self.env.user.login,
            }
            # Si la vendedora ya anotó su celular en el contacto, esa es la llave de la ficha.
            celular = R.celular_normal(ficha.phone)
            if not ficha.dcasa_celular and R.celular_valido(celular) and not self.sudo().with_context(
                    active_test=False).search_count([('dcasa_celular', '=', celular)], limit=1):
                valores['dcasa_celular'] = celular
            ficha.write(valores)
            bienvenida = R.cargar_reglas()['bienvenida'].get('puntos')
            if bienvenida:
                self.env['dcasa.movimiento']._asentar(ficha, 'bienvenida', bienvenida, 'sistema',
                                                     motivo='Bienvenida al programa')
        return ficha

    @api.model
    def _dcasa_por_codigo(self, codigo):
        codigo = R.codigo_normal(codigo)
        if not R.es_codigo_valido(codigo):
            return self.browse()
        return self.sudo().with_context(active_test=False).search([('dcasa_socio_codigo', '=', codigo)], limit=1)

    @api.model
    def _dcasa_por_celular(self, celular):
        normal = R.celular_normal(celular)
        if not normal:
            return self.browse()
        return self.sudo().with_context(active_test=False).search([('dcasa_celular', '=', normal)], limit=1)

    def _dcasa_compras_con_puntos(self):
        """Compras activas que dieron puntos: las que cuentan como "ya compró"."""
        self.ensure_one()
        return self.env['dcasa.compra'].sudo().search([
            ('partner_id', '=', self.commercial_partner_id.id),
            ('anulada_en', '=', False),
            ('puntos', '>', 0),
        ])

    def _dcasa_asignar_padrino(self, padrino, cuando=None):
        """Registra quién lo invitó si todavía se puede. Nunca falla: devuelve si se asignó."""
        self.ensure_one()
        ficha = self.commercial_partner_id.sudo()
        padrino = padrino.commercial_partner_id.sudo()
        if (
            not padrino or not padrino.dcasa_socio_codigo or padrino == ficha
            or padrino.dcasa_socio_estado != 'activo' or not padrino.active
            or ficha.dcasa_referido_por_id or ficha._dcasa_compras_con_puntos()
            or padrino.dcasa_referido_por_id == ficha
        ):
            return False
        ficha.write({'dcasa_referido_por_id': padrino.id, 'dcasa_referido_en': cuando or fields.Datetime.now()})
        return True

    def _is_public(self):
        """El visitante sin sesión de la tienda web: su ficha nunca entra al programa."""
        self.ensure_one()
        return any(user._is_public() for user in self.with_context(active_test=False).user_ids)

    def _dcasa_nombre_publico(self):
        self.ensure_one()
        partes = (self.name or '').split()
        return R.nombre_publico(partes[0] if partes else '', ' '.join(partes[1:]))

    def _dcasa_resumen_portal(self):
        """Lo que ve el usuario de la tienda en /my: su misma ficha es la del programa.

        Valores planos (sin registros) para la plantilla del portal. ``es_socio`` es tener PIN;
        sin PIN los puntos corren igual y se le invita a activar el programa.
        """
        self.ensure_one()
        ficha = self.commercial_partner_id.sudo()
        if not ficha or ficha._is_public():
            return None
        Canje = self.env['dcasa.canje'].sudo()
        return {
            'es_socio': bool(ficha.dcasa_reclamada and ficha.dcasa_socio_estado == 'activo'),
            'codigo': ficha.dcasa_socio_codigo or '',
            'saldo': ficha.dcasa_saldo,
            'saldo_fmt': R.como_puntos(ficha.dcasa_saldo),
            'premios_pendientes': Canje.search_count([('partner_id', '=', ficha.id), ('estado', '=', 'solicitado')]),
            'invitados': len(ficha.dcasa_ahijado_ids.filtered('active')),
        }

    # ------------------------------------------------------------------------
    # PIN
    # ------------------------------------------------------------------------

    @api.model
    def _dcasa_pimienta(self):
        pimienta = os.environ.get('DCASA_PIN_PEPPER')
        if not pimienta:
            raise R.FaltaConfigurar('DCASA_PIN_PEPPER', 'Falta la pimienta del PIN (variable DCASA_PIN_PEPPER).')
        return pimienta

    def _dcasa_guardar_pin(self, pin, temporal=False):
        self.ensure_one()
        self.sudo().write({
            'dcasa_pin_hash': PIN_CRYPT.hash(pin + self._dcasa_pimienta()),
            'dcasa_pin_cambiado_en': fields.Datetime.now(),
            'dcasa_pin_temporal': temporal,
            'dcasa_intentos_fallidos': 0,
            'dcasa_bloqueado_hasta': False,
        })

    def _dcasa_pin_correcto(self, pin):
        self.ensure_one()
        guardado = self.sudo().dcasa_pin_hash
        return bool(guardado) and PIN_CRYPT.verify((pin or '') + self._dcasa_pimienta(), guardado)

    # ------------------------------------------------------------------------
    # Acciones del equipo
    # ------------------------------------------------------------------------

    def _dcasa_exigir_grupo(self, grupo):
        """Corta antes de cualquier ``sudo()`` si quien llama no tiene el grupo (el superusuario pasa)."""
        if not self.env.su and not self.env.user.has_group(grupo):
            raise AccessError(self.env._('No tienes permiso para esta acción del programa de socios.'))

    def action_dcasa_crear_ficha(self):
        self._dcasa_exigir_grupo(GRUPO_VENDEDORA)
        for partner in self:
            partner._dcasa_asegurar_ficha()
        return True

    def action_dcasa_ver_movimientos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Puntos de %s', self.display_name),
            'res_model': 'dcasa.movimiento',
            'view_mode': 'list,pivot',
            'domain': [('partner_id', '=', self.commercial_partner_id.id)],
        }

    def action_dcasa_ajustar(self):
        self._dcasa_exigir_grupo(GRUPO_GERENTE)
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Ajustar puntos'),
            'res_model': 'dcasa.ajuste.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.commercial_partner_id.id},
        }

    def action_dcasa_reiniciar_pin(self):
        """Gerencia le dicta un PIN temporal; el socio elige uno nuevo al entrar.

        Solo gerencia: el PIN temporal sale en la respuesta, y con él y el celular
        cualquiera entra a la cuenta del socio y canjea sus puntos.
        """
        self._dcasa_exigir_grupo(GRUPO_GERENTE)
        self.ensure_one()
        ficha = self.commercial_partner_id
        if not ficha.dcasa_reclamada:
            # El consentimiento lo da la persona: una vendedora no la mete al programa.
            raise UserError(self.env._(
                'Esta ficha todavía no se reclamó: la persona entra sola desde /socios con su celular.'))
        while True:
            temporal = ''.join(secrets.choice('0123456789') for _ in range(R.LARGO_PIN))
            if not R.problema_del_pin(temporal, ficha.dcasa_celular or ''):
                break
        ficha._dcasa_guardar_pin(temporal, temporal=True)
        # Rastro de quién lo hizo (nunca el PIN).
        ficha._dcasa_dejar_rastro(self.env._('PIN reiniciado por %s: el socio elige uno nuevo al entrar.',
                                             self.env.user.name))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('PIN temporal: %s', temporal),
                'message': self.env._('Díctaselo al socio. Al entrar tendrá que elegir uno nuevo.'),
                'sticky': True,
                'type': 'warning',
            },
        }

    def action_dcasa_desbloquear(self):
        """Botón de gerencia: quita el candado de intentos fallidos."""
        self._dcasa_exigir_grupo(GRUPO_GERENTE)
        self._dcasa_desbloquear()
        for ficha in self.commercial_partner_id:
            ficha._dcasa_dejar_rastro(self.env._('Cuenta de socio desbloqueada por %s.', self.env.user.name))
        return True

    def _dcasa_desbloquear(self):
        """Pone a cero el candado. Privado: lo usa el login de /socios tras un PIN correcto."""
        self.commercial_partner_id.sudo().write({'dcasa_intentos_fallidos': 0, 'dcasa_bloqueado_hasta': False})

    def action_dcasa_suspender(self):
        self._dcasa_exigir_grupo(GRUPO_GERENTE)
        self.commercial_partner_id.write({'dcasa_socio_estado': 'suspendido'})
        return True

    def action_dcasa_activar(self):
        self._dcasa_exigir_grupo(GRUPO_GERENTE)
        self.commercial_partner_id.write({'dcasa_socio_estado': 'activo'})
        return True

    def _dcasa_dejar_rastro(self, texto):
        """Nota interna en el chatter de la ficha, a nombre de quien hizo la acción."""
        self.ensure_one()
        self.message_post(body=texto, message_type='comment', subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------------
    # Candado
    # ------------------------------------------------------------------------

    def _dcasa_registrar_fallo(self):
        self.ensure_one()
        ficha = self.sudo()
        fallos = ficha.dcasa_intentos_fallidos + 1
        ficha.write({
            'dcasa_intentos_fallidos': fallos,
            'dcasa_bloqueado_hasta': R.bloqueo_tras(fallos, fields.Datetime.now()) or ficha.dcasa_bloqueado_hasta,
        })

    def _dcasa_bloqueada(self):
        self.ensure_one()
        return R.sigue_bloqueada(self.sudo().dcasa_bloqueado_hasta, fields.Datetime.now())

    @api.model
    def _dcasa_huella_pin(self, partner):
        """Lo que se guarda en la sesión: si el PIN cambia, las sesiones viejas dejan de valer."""
        return fields.Datetime.to_string(partner.sudo().dcasa_pin_cambiado_en) or ''
