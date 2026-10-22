"""Configuración contable de la nómina (una por empresa): diario y cuentas del asiento.

Las cuentas se proponen buscando por código en el plan contable de Panamá (``l10n_pa``): 514 gastos en
salarios, 515 gastos en cargas sociales, 241 sueldos a pagar, 242 cargas sociales a pagar, 232 impuesto sobre
la renta a pagar, 243 provisión para sueldo anual complementario y 134 anticipo al personal (adelantos y
préstamos). Son una propuesta: **las confirma el
contador** (Nómina › Configuración). Una cuenta vacía impide confirmar la planilla que la necesita.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

# campo → (código del plan l10n_pa, para qué sirve)
CUENTAS = {
    'cuenta_gasto_sueldos_id': ('514', 'Gasto: sueldos y salarios'),
    'cuenta_gasto_cargas_id': ('515', 'Gasto: cargas sociales del patrono'),
    'cuenta_sueldos_pagar_id': ('241', 'Sueldos por pagar'),
    'cuenta_css_pagar_id': ('242', 'Seguro social por pagar'),
    'cuenta_se_pagar_id': ('242', 'Seguro educativo por pagar'),
    'cuenta_rp_pagar_id': ('242', 'Riesgo profesional por pagar'),
    'cuenta_isr_pagar_id': ('232', 'ISR retenido por pagar'),
    'cuenta_decimo_id': ('243', 'Provisión del décimo tercer mes'),
    'cuenta_prestamos_id': ('134', 'Adelantos y préstamos al personal (por cobrar)'),
}


class DcasaNominaConfig(models.Model):
    _name = 'dcasa.nomina.config'
    _description = 'Configuración contable de la nómina'
    _rec_name = 'company_id'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    diario_id = fields.Many2one('account.journal', 'Diario de la planilla', domain="[('type', '=', 'general')]",
                                check_company=True)
    cuenta_gasto_sueldos_id = fields.Many2one('account.account', CUENTAS['cuenta_gasto_sueldos_id'][1],
                                              check_company=True)
    cuenta_gasto_cargas_id = fields.Many2one('account.account', CUENTAS['cuenta_gasto_cargas_id'][1],
                                             check_company=True)
    cuenta_sueldos_pagar_id = fields.Many2one('account.account', CUENTAS['cuenta_sueldos_pagar_id'][1],
                                              check_company=True)
    cuenta_css_pagar_id = fields.Many2one('account.account', CUENTAS['cuenta_css_pagar_id'][1], check_company=True)
    cuenta_se_pagar_id = fields.Many2one('account.account', CUENTAS['cuenta_se_pagar_id'][1], check_company=True)
    cuenta_rp_pagar_id = fields.Many2one('account.account', CUENTAS['cuenta_rp_pagar_id'][1], check_company=True)
    cuenta_isr_pagar_id = fields.Many2one('account.account', CUENTAS['cuenta_isr_pagar_id'][1], check_company=True)
    cuenta_decimo_id = fields.Many2one('account.account', CUENTAS['cuenta_decimo_id'][1], check_company=True)
    cuenta_otros_descuentos_id = fields.Many2one(
        'account.account', 'Otros descuentos (los escritos a mano)', check_company=True,
        help='Cuenta contra la que se acreditan los descuentos que se escriben a mano en la planilla. Los adelantos '
             'y préstamos registrados en Nómina › Adelantos y préstamos usan su propia cuenta.')
    cuenta_prestamos_id = fields.Many2one(
        'account.account', CUENTAS['cuenta_prestamos_id'][1], check_company=True,
        help='Lo que los colaboradores le deben a la empresa por adelantos y préstamos: sube al entregarlos y baja '
             'con cada cuota de la planilla. El plan de cuentas de Panamá trae la 134 «Anticipo al Personal»; '
             'el contador la confirma.')
    cuenta_reembolsos_id = fields.Many2one(
        'account.account', 'Gasto por defecto de los reembolsos', check_company=True,
        help='Cuenta de gasto que se propone al registrar un reembolso (se puede cambiar en cada uno).')
    provisionar_decimo = fields.Boolean(
        'Provisionar el décimo tercer mes en cada planilla',
        help='Marcado: cada planilla quincenal también registra el gasto de la parte del décimo (1/12 de lo '
             'devengado) contra la cuenta de provisión, y al pagar la partida se descuenta de esa cuenta. '
             'Desmarcado: el gasto se registra cuando se paga cada partida. Lo decide el contador.')

    _una_por_empresa = models.Constraint('UNIQUE(company_id)', 'Cada empresa tiene una sola configuración.')

    @api.model
    def _de(self, company=None):
        """La configuración de la empresa; si no existe se crea con las cuentas que propone el plan contable.

        Método privado que devuelve el registro con ``sudo()``: lo usan los botones de la nómina (que ya comprobaron
        el grupo) y los reembolsos de cualquier colaborador (para proponer la cuenta de gasto)."""
        company = company or self.env.company
        config = self.sudo().search([('company_id', '=', company.id)], limit=1)
        return config or self.sudo().create({'company_id': company.id, **self._propuesta(company)})

    @api.model
    def _propuesta(self, company):
        Cuenta = self.env['account.account'].sudo().with_company(company)
        valores = {}
        for campo, (codigo, _nombre) in CUENTAS.items():
            cuenta = Cuenta.search([('code', '=', codigo)], limit=1)
            if cuenta:
                valores[campo] = cuenta.id
        diario = self.env['account.journal'].sudo().search(
            [('company_id', '=', company.id), ('code', '=', 'NOM')], limit=1)
        if not diario:
            diario = self.env['account.journal'].sudo().create({
                'name': self.env._('Nómina'), 'code': 'NOM', 'type': 'general', 'company_id': company.id})
        valores['diario_id'] = diario.id
        return valores

    def _exigir(self, *campos):
        """Falla con la lista de cuentas que faltan para lo que se va a contabilizar."""
        self.ensure_one()
        faltan = [CUENTAS[c][1] if c in CUENTAS else self._fields[c].string for c in campos if not self[c]]
        if not self.diario_id:
            faltan.insert(0, self._fields['diario_id'].string)
        if faltan:
            raise UserError(self.env._(
                'Falta configurar en Nómina › Configuración: %s. El contador las confirma.', ', '.join(faltan)))

    @api.model
    def action_abrir(self):
        """Abre la configuración de la empresa activa (la crea con lo que propone el plan contable)."""
        self.check_access('read')
        config = self._de()
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': config.id,
            'view_mode': 'form', 'target': 'current', 'name': self.env._('Configuración de la nómina'),
        }
