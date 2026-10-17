"""«Imprimir documentos» con la hoja de condiciones de abono (copia cliente y copia empresa).

Una casilla más en el cuadro de dcasa_invoice: «Condiciones de abono (2 copias)». Viene marcada solo en el PRIMER abono
(la factura tiene exactamente un pago y todavía saldo) y desmarcada en los demás; si ninguna factura del cuadro puede
llevar la hoja (sin abonos o sin condiciones escritas), no se muestra. En el PDF unido va justo después de la factura
del cliente (que en un abono sale como ABONO) y antes de la copia de la empresa.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

CLAVE = 'condiciones'
INFORME = 'dcasa_abonos.action_report_condiciones_abono'


class DcasaImpresionPaquete(models.TransientModel):
    _inherit = 'dcasa.impresion.paquete'

    incluir_condiciones = fields.Boolean(
        'Condiciones de abono (2 copias)', compute='_compute_incluir_condiciones', store=True, readonly=False,
        help='La hoja de condiciones de abono, una copia para el cliente y otra para la tienda, con el código de cada '
             'mueble, lo abonado y el saldo. Viene marcada en el primer abono.')
    condiciones_disponibles = fields.Boolean(
        compute='_compute_condiciones_disponibles',
        help='Alguna factura del cuadro tiene al menos un abono y su empresa tiene las condiciones escritas.')

    @api.depends('move_ids')
    def _compute_condiciones_disponibles(self):
        for cuadro in self:
            cuadro.condiciones_disponibles = bool(cuadro._facturas_con_condiciones(cuadro.move_ids))

    @api.depends('move_ids')
    def _compute_incluir_condiciones(self):
        for cuadro in self:
            con_hoja = cuadro._facturas_con_condiciones(cuadro.move_ids)
            cuadro.incluir_condiciones = any(factura._dcasa_primer_abono() for factura in con_hoja)

    @api.model
    def _facturas_con_condiciones(self, facturas):
        """Las facturas (de cliente, publicadas) que pueden llevar la hoja de condiciones."""
        validas, _otras = self._separar_validas(facturas)
        return validas.filtered(lambda factura: factura._dcasa_condiciones_imprimible())

    @api.model
    def _claves_documentos(self):
        """Las condiciones van justo después de la factura del cliente (y antes de la copia de la empresa)."""
        claves = super()._claves_documentos()
        despues_de = claves.index('cliente') + 1 if 'cliente' in claves else len(claves)
        return claves[:despues_de] + [CLAVE] + claves[despues_de:]

    @api.model
    def _pdfs_adicionales(self, facturas, claves):
        """La hoja de cada factura que puede llevarla; las demás simplemente no la llevan."""
        resultado = super()._pdfs_adicionales(facturas, claves)
        if CLAVE not in claves:
            return resultado
        con_hoja = self._facturas_con_condiciones(facturas)
        if con_hoja:
            resultado[CLAVE] = self._pdfs_por_registro(self.env.ref(INFORME), con_hoja)
        elif list(claves) == [CLAVE]:
            raise UserError(self.env._(
                'Las condiciones de abono se imprimen de una factura de cliente publicada que ya tiene al menos un '
                'abono, y con las condiciones escritas en Ajustes › Empresas, pestaña «Documentos D\'CASA». '
                'Ninguna de las facturas elegidas las puede llevar.'))
        return resultado
