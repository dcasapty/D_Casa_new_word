"""Ajustes de bodega (uno por empresa): las cuentas de las mermas, el tope del aviso y las alertas por Telegram.

* **Cuentas de las mermas**: vienen VACÍAS. Las elige la contadora (DECISIONES_CONTABLES F6 e I5: el plan de cuentas
  se revisa juntos; el de Panamá instalado no trae una cuenta de mermas). Sin ellas la merma se registra igual (baja
  la existencia y queda su costo), pero el asiento queda pendiente y la pantalla lo dice.
* **Tope del aviso**: 0.5 % de lo comprado en el mes (F6, cifra decidida por la gerencia el 17/10/2026).
* **Alertas diarias por Telegram a Gerencia**: apagadas de fábrica y sin umbral. Cada alerta sale solo si la dueña la
  enciende y pone su umbral; no se inventa ninguno.
"""
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

# F6 (DECISIONES_CONTABLES.md): «aviso si pasa del 0.5 % de lo comprado». Cifra de la gerencia, no del código.
TOPE_MERMAS_PCT = 0.5
GRUPOS_GERENCIA = ('dcasa_base.group_gerencia', 'base.group_system')


class DcasaExistenciasConfig(models.Model):
    _name = 'dcasa.existencias.config'
    _description = 'Ajustes de bodega: mermas y alertas'
    _rec_name = 'company_id'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    # --- Mermas (F6) -----------------------------------------------------------------------------
    mermas_cuenta_gasto_id = fields.Many2one(
        'account.account', 'Cuenta de las mermas (gasto)', check_company=True,
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost', 'expense_other'))]",
        help='La partida propia del estado de resultados: «Mermas, daños, muestras y regalos». La elige la contadora.')
    mermas_cuenta_contra_id = fields.Many2one(
        'account.account', 'Cuenta que se rebaja', check_company=True,
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'asset_cash', 'off_balance'))]",
        help='Lo que sale de la bodega: la cuenta de inventario (si lleva el inventario al día) o la de compras o '
             'costo (si lo cuenta a fin de mes). Depende de cómo lleva el inventario la contadora: ella la elige.')
    mermas_diario_id = fields.Many2one('account.journal', 'Diario de las mermas', check_company=True,
                                       domain="[('type', '=', 'general')]",
                                       help='Vacío: el diario de valoración de inventario de Odoo, si existe.')
    mermas_tope_pct = fields.Float(
        'Avisar si las mermas del mes pasan de (% de lo comprado)', default=TOPE_MERMAS_PCT, digits=(5, 2),
        help='Decisión de la gerencia (F6): 0.5 % de lo que se compró en el mes. Lo comprado = lo que entró a la '
             'bodega desde los proveedores (recepciones validadas), a su costo y sin ITBMS.')

    # --- Alertas diarias por Telegram (apagadas de fábrica) --------------------------------------
    alertas_activas = fields.Boolean(
        'Mandar alertas diarias por Telegram a Gerencia', default=False,
        help='Un mensaje al día (temprano en la mañana) a cada persona de Gerencia que vinculó su Telegram con '
             'Brian, solo si hay algo que avisar.')
    alerta_stock_bajo = fields.Boolean('Productos por agotarse')
    alerta_stock_bajo_unidades = fields.Integer(
        'Cuando queden estas unidades o menos',
        help='Escribe tu umbral. 0 = solo los que ya se agotaron.')
    alerta_ajustes = fields.Boolean('Ajustes grandes de existencias')
    alerta_ajustes_unidades = fields.Integer('Cuando un ajuste cambie al menos (unidades)',
                                             help='Vacío o 0: no se mira por unidades.')
    alerta_ajustes_monto = fields.Monetary('o cuando cambie al menos (dinero, a costo)',
                                           help='Vacío o 0: no se mira por dinero.')
    alerta_cierre = fields.Boolean('Mes sin cerrar')
    alerta_cierre_dia = fields.Integer(
        'Desde este día del mes siguiente',
        help='Si el mes anterior sigue sin cerrar desde este día, avisa cada mañana. La gerencia decidió cerrar a '
             'más tardar el día 5 (DECISIONES_CONTABLES I1); el día del aviso lo pones tú.')
    alerta_mermas = fields.Boolean('Mermas del mes sobre el tope',
                                   help='Usa el tope de arriba (decisión de la gerencia).')
    alertas_ultima = fields.Datetime('Última revisión de alertas', readonly=True)
    alertas_ultimo_envio = fields.Text('Último mensaje enviado', readonly=True)

    _una_por_empresa = models.Constraint('UNIQUE(company_id)', 'Cada empresa tiene un solo ajuste de bodega.')

    @api.constrains('alerta_stock_bajo', 'alerta_stock_bajo_unidades', 'alerta_ajustes', 'alerta_ajustes_unidades',
                    'alerta_ajustes_monto', 'alerta_cierre', 'alerta_cierre_dia', 'mermas_tope_pct')
    def _check_umbrales(self):
        for config in self:
            if config.alerta_stock_bajo_unidades < 0 or config.alerta_ajustes_unidades < 0 \
                    or config.alerta_ajustes_monto < 0 or config.mermas_tope_pct < 0:
                raise ValidationError(self.env._('Los umbrales no pueden ser negativos.'))
            if config.alerta_ajustes and not (config.alerta_ajustes_unidades or config.alerta_ajustes_monto):
                raise ValidationError(self.env._(
                    'Para avisar de ajustes grandes escribe desde cuántas unidades o desde cuánto dinero.'))
            if config.alerta_cierre and not 1 <= config.alerta_cierre_dia <= 28:
                raise ValidationError(self.env._('El día del aviso del cierre va del 1 al 28.'))

    @api.model
    def _de(self, company=None):
        """El ajuste de la empresa (lo crea vacío la primera vez). Devuelve el registro con sudo: lo usan las mermas,
        la bitácora y el cron, que ya comprobaron quién llama."""
        company = company or self.env.company
        config = self.sudo().search([('company_id', '=', company.id)], limit=1)
        return config or self.sudo().create({'company_id': company.id})

    def _diario_mermas(self):
        self.ensure_one()
        return self.mermas_diario_id or self.company_id.sudo().account_stock_journal_id

    def _faltan_cuentas_mermas(self):
        """Lo que falta para contabilizar una merma (nombres para la pantalla). Vacío = todo listo."""
        self.ensure_one()
        faltan = []
        if not self.mermas_cuenta_gasto_id:
            faltan.append(self._fields['mermas_cuenta_gasto_id'].string)
        if not self.mermas_cuenta_contra_id:
            faltan.append(self._fields['mermas_cuenta_contra_id'].string)
        if not self._diario_mermas():
            faltan.append(self._fields['mermas_diario_id'].string)
        return faltan

    def _exigir_gerencia(self):
        if not self.env.su and not any(self.env.user.has_group(g) for g in GRUPOS_GERENCIA):
            raise AccessError(self.env._('Solo Gerencia cambia los ajustes de bodega.'))

    def write(self, vals):
        if not self.env.su:
            self._exigir_gerencia()
        return super().write(vals)

    @api.model
    def action_abrir(self):
        """Abre el ajuste de la empresa activa (lo crea vacío la primera vez)."""
        self._exigir_gerencia()
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self._de().id,
            'view_mode': 'form', 'target': 'current', 'name': self.env._('Ajustes de bodega y mermas'),
        }

    def action_contabilizar_pendientes(self):
        """Las mermas que se confirmaron antes de elegir las cuentas quedan con su asiento."""
        self._exigir_gerencia()
        self.ensure_one()
        pendientes = self.env['stock.scrap'].sudo().search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'done'),
            ('dcasa_contabilidad', '=', 'falta_cuenta')], order='date_done, id')
        if not pendientes:
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': self.env._('Mermas'), 'type': 'info',
                               'message': self.env._('No hay mermas esperando su asiento.')}}
        if self._faltan_cuentas_mermas():
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': self.env._('Mermas'), 'type': 'warning',
                               'message': self.env._('Falta elegir: %s.', ', '.join(self._faltan_cuentas_mermas()))}}
        hechas, fallas = pendientes._dcasa_contabilizar()
        mensaje = self.env._('Se contabilizaron %s merma(s).', hechas)
        if fallas:
            mensaje += ' ' + self.env._('No se pudieron %s (mira su historial: suele ser un mes ya cerrado).', fallas)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': self.env._('Mermas'), 'message': mensaje,
                           'type': 'warning' if fallas or not hechas else 'success'}}
