"""Datos fiscales para la factura electrónica: empresa, cliente, producto, impuesto y diario.

Todo es opcional mientras la facturación electrónica esté apagada (por defecto): estos
campos no cambian nada del flujo actual. Al encenderla, ``account.move`` los valida antes
de publicar y dice en español qué falta.
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from . import catalogos as C


class ResPartner(models.Model):
    _inherit = 'res.partner'

    l10n_pa_tipo_receptor = fields.Selection(
        C.TIPOS_RECEPTOR, string='Tipo de receptor (FE)',
        help='Cómo se identifica a este cliente en la factura electrónica de la DGI. Vacío: se deduce '
             '(extranjero si el país no es Panamá; contribuyente si tiene RUC con DV; si no, consumidor final).')
    l10n_pa_tipo_ruc = fields.Selection(
        C.TIPOS_RUC, string='Tipo de contribuyente (FE)',
        help='Persona natural o jurídica. Vacío: jurídica si el contacto es una empresa.')
    l10n_pa_cod_ubicacion = fields.Char(
        string='Código de ubicación (DGI)', size=8,
        help='Provincia-distrito-corregimiento según el catálogo de la DGI, p. ej. «8-8-8». '
             'Pídelo al contador o al PAC: no se adivina.')
    l10n_pa_corregimiento = fields.Char(string='Corregimiento')
    l10n_pa_distrito = fields.Char(string='Distrito')
    l10n_pa_provincia = fields.Char(string='Provincia')

    @api.model
    def _commercial_fields(self):
        return super()._commercial_fields() + ['l10n_pa_tipo_receptor', 'l10n_pa_tipo_ruc']

    def _l10n_pa_fe_tipo_receptor(self):
        """El tipo de receptor elegido o, si está vacío, el que se deduce de la ficha."""
        self.ensure_one()
        ficha = self.commercial_partner_id
        if ficha.l10n_pa_tipo_receptor:
            return ficha.l10n_pa_tipo_receptor
        if ficha.country_id and ficha.country_id.code != 'PA':
            return C.RECEPTOR_EXTRANJERO
        if ficha.vat and ficha.l10n_pa_dv:
            return C.RECEPTOR_CONTRIBUYENTE
        return C.RECEPTOR_CONSUMIDOR_FINAL

    def _l10n_pa_fe_tipo_ruc(self):
        self.ensure_one()
        ficha = self.commercial_partner_id
        return ficha.l10n_pa_tipo_ruc or ('2' if ficha.is_company else '1')

    def _l10n_pa_fe_ubicacion(self):
        """dict de ubicación DGI o None si no está completa."""
        self.ensure_one()
        valores = (self.l10n_pa_cod_ubicacion, self.l10n_pa_corregimiento, self.l10n_pa_distrito,
                   self.l10n_pa_provincia)
        if not all(valores):
            return None
        return dict(zip(('codigo', 'corregimiento', 'distrito', 'provincia'), valores, strict=True))


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_pa_fe_activo = fields.Boolean(
        string='Facturación electrónica activa',
        help='Apagado: Odoo factura como siempre y nada se envía a la DGI.')
    l10n_pa_fe_adaptador = fields.Selection(
        [('simulado', 'Simulado (pruebas y staging, no envía nada)')], string='Proveedor (PAC)',
        help='El adaptador del Proveedor Autorizado Calificado. Sin PAC no se envía nada.')
    l10n_pa_fe_ambiente = fields.Selection(C.AMBIENTES, string='Ambiente DGI', default='2', required=True)
    l10n_pa_fe_tipo_ruc = fields.Selection(C.TIPOS_RUC, string='Tipo de contribuyente', default='2')
    l10n_pa_fe_sucursal = fields.Char(string='Código de sucursal (DGI)', size=4, default='0000',
                                      help='4 dígitos; 0000 es la casa matriz (SEGÚN FUENTE SECUNDARIA).')
    l10n_pa_fe_coordenadas = fields.Char(string='Coordenadas del local',
                                         help='Latitud,longitud del punto de facturación, si el PAC la pide.')
    l10n_pa_cod_ubicacion = fields.Char(related='partner_id.l10n_pa_cod_ubicacion', readonly=False)
    l10n_pa_corregimiento = fields.Char(related='partner_id.l10n_pa_corregimiento', readonly=False)
    l10n_pa_distrito = fields.Char(related='partner_id.l10n_pa_distrito', readonly=False)
    l10n_pa_provincia = fields.Char(related='partner_id.l10n_pa_provincia', readonly=False)
    l10n_pa_fe_forma_cafe = fields.Selection(
        [('1', 'Sin CAFE'), ('2', 'Cinta de papel'), ('3', 'Papel carta')], string='Formato del CAFE',
        default='3', help='iFormCAFE: cómo se imprime el comprobante auxiliar (SEGÚN FUENTE SECUNDARIA).')
    l10n_pa_fe_entrega_cafe = fields.Selection(
        [('1', 'Sin CAFE'), ('2', 'En papel'), ('3', 'Electrónico')], string='Entrega del CAFE',
        default='2', help='iEntCAFE: cómo recibe el cliente el comprobante (SEGÚN FUENTE SECUNDARIA).')
    l10n_pa_fe_forma_pago = fields.Selection(
        C.FORMAS_PAGO, string='Forma de pago por defecto', default='02',
        help='Para facturas de contado que aún no tienen pago registrado al publicarse.')
    l10n_pa_fe_reintentos = fields.Integer(
        string='Reintentos antes de contingencia', default=6,
        help='Fallos de comunicación seguidos con el PAC antes de pasar el documento a contingencia.')
    l10n_pa_fe_contingencia = fields.Boolean(
        string='Modo contingencia', help='Mientras esté marcado, los documentos nuevos se emiten en '
                                         'contingencia y se transmiten cuando el PAC responda.')
    l10n_pa_fe_contingencia_inicio = fields.Datetime(string='Contingencia desde')
    l10n_pa_fe_contingencia_motivo = fields.Char(string='Motivo de la contingencia', size=C.MOTIVO_MAX)

    @api.constrains('l10n_pa_fe_sucursal')
    def _check_l10n_pa_fe_sucursal(self):
        for company in self:
            sucursal = company.l10n_pa_fe_sucursal
            if sucursal and (len(sucursal) != 4 or not sucursal.isdigit()):
                raise ValidationError(self.env._('El código de sucursal son 4 dígitos, p. ej. 0000.'))

    @api.constrains('l10n_pa_fe_contingencia', 'l10n_pa_fe_contingencia_motivo')
    def _check_l10n_pa_fe_contingencia(self):
        for company in self.filtered('l10n_pa_fe_contingencia'):
            if len((company.l10n_pa_fe_contingencia_motivo or '').strip()) < C.MOTIVO_MIN:
                raise ValidationError(self.env._(
                    'Para entrar en contingencia escribe el motivo (al menos %s caracteres), '
                    'p. ej. «Sin internet en la tienda».', C.MOTIVO_MIN))

    def _l10n_pa_fe_operando(self):
        """True solo si está activa Y tiene PAC: sin las dos cosas no cambia nada."""
        self.ensure_one()
        return bool(self.l10n_pa_fe_activo and self.l10n_pa_fe_adaptador)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    l10n_pa_cpbs = fields.Char(
        string='Código CPBS', size=4,
        help='Codificación Panameña de Bienes y Servicios (4 dígitos). Según fuentes secundarias es '
             'obligatorio cuando se le factura al Gobierno; para los demás clientes es opcional.')

    @api.constrains('l10n_pa_cpbs')
    def _check_l10n_pa_cpbs(self):
        for producto in self:
            if producto.l10n_pa_cpbs and (len(producto.l10n_pa_cpbs) != 4 or not producto.l10n_pa_cpbs.isdigit()):
                raise ValidationError(self.env._('El código CPBS son 4 dígitos, p. ej. 5612.'))


class AccountTax(models.Model):
    _inherit = 'account.tax'

    l10n_pa_tasa_itbms = fields.Selection(
        C.TASAS_ITBMS, string='Código DGI de la tasa ITBMS',
        help='Vacío: se deduce del porcentaje (0 %, 7 %, 10 % o 15 %).')

    def _l10n_pa_fe_codigo_itbms(self):
        """'01' para el ITBMS 7 %. None si no es un impuesto de ITBMS que la DGI reconozca."""
        self.ensure_one()
        if self.l10n_pa_tasa_itbms:
            return self.l10n_pa_tasa_itbms
        if self.amount_type != 'percent':
            return None
        return C.codigo_tasa(self.amount)


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    l10n_pa_fe_punto = fields.Char(
        string='Punto de facturación (DGI)', size=3, default='001',
        help='3 dígitos (001–999). Cada punto lleva su propia numeración de 10 dígitos que no se reinicia.')
    l10n_pa_fe_forma_pago = fields.Selection(
        C.FORMAS_PAGO, string='Forma de pago DGI',
        help='Solo en diarios de banco o caja: con qué código se informa un pago hecho por este diario '
             '(Efectivo → 02, Tarjeta → 03/04, Yappy → confirmar con el contador).')

    @api.constrains('l10n_pa_fe_punto')
    def _check_l10n_pa_fe_punto(self):
        for diario in self:
            punto = diario.l10n_pa_fe_punto
            if punto and (len(punto) != 3 or not punto.isdigit() or punto == '000'):
                raise ValidationError(self.env._('El punto de facturación son 3 dígitos entre 001 y 999.'))

    def _l10n_pa_fe_siguiente_numero(self, tipo_documento):
        """Siguiente dNroDF (10 dígitos) para este punto y tipo de documento. No se reinicia nunca."""
        self.ensure_one()
        codigo = f'dcasa_fe_pa.{self.company_id.id}.{self.l10n_pa_fe_punto}.{tipo_documento}'
        Secuencia = self.env['ir.sequence'].sudo()
        secuencia = Secuencia.search([('code', '=', codigo), ('company_id', '=', self.company_id.id)], limit=1)
        if not secuencia:
            secuencia = Secuencia.create({
                'name': f'FE DGI punto {self.l10n_pa_fe_punto} documento {tipo_documento}',
                'code': codigo, 'padding': 10, 'number_increment': 1, 'number_next': 1,
                'implementation': 'no_gap', 'company_id': self.company_id.id,
            })
        return secuencia.next_by_id()


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_pa_fe_activo = fields.Boolean(related='company_id.l10n_pa_fe_activo', readonly=False)
    l10n_pa_fe_adaptador = fields.Selection(related='company_id.l10n_pa_fe_adaptador', readonly=False)
    l10n_pa_fe_ambiente = fields.Selection(related='company_id.l10n_pa_fe_ambiente', readonly=False)
    l10n_pa_fe_contingencia = fields.Boolean(related='company_id.l10n_pa_fe_contingencia', readonly=False)
    l10n_pa_fe_contingencia_motivo = fields.Char(related='company_id.l10n_pa_fe_contingencia_motivo',
                                                 readonly=False)
    l10n_pa_fe_contingencia_inicio = fields.Datetime(related='company_id.l10n_pa_fe_contingencia_inicio',
                                                     readonly=False)
