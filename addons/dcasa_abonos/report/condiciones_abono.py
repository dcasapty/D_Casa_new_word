from odoo import api, models
from odoo.exceptions import AccessError, UserError

GRUPOS_QUE_IMPRIMEN = ('account.group_account_invoice', 'account.group_account_readonly')


class ReportCondicionesAbono(models.AbstractModel):
    """La hoja «Condiciones de abono» (copia cliente y copia empresa) de una factura con al menos un abono.

    Solo lee: no escribe nada, no toca la factura, sus pagos ni sus asientos. Revisa antes de pintar, con un mensaje
    que se entiende, que cada factura se pueda imprimir y que la empresa tenga las condiciones escritas.
    """
    _name = 'report.dcasa_abonos.report_condiciones_abono'
    _description = 'Condiciones de abono (copia cliente y copia empresa)'

    @api.model
    def _get_report_values(self, docids, data=None):
        usuario = self.env.user
        # Igual que «Imprimir documentos»: Facturación o lector contable. Un cliente del portal ve sus facturas, pero
        # no esta hoja (la copia de la empresa lleva la referencia del proveedor).
        if not any(usuario.has_group(grupo) for grupo in GRUPOS_QUE_IMPRIMEN):
            raise AccessError(self.env._('No tienes permiso para imprimir las condiciones de abono.'))
        facturas = self.env['account.move'].browse(docids).exists()
        if not facturas:
            raise UserError(self.env._('No hay ninguna factura para imprimir las condiciones de abono.'))
        motivos = [motivo for motivo in (factura._dcasa_condiciones_motivo() for factura in facturas) if motivo]
        if motivos:
            raise UserError(self.env._(
                'Las condiciones de abono se imprimen de una factura de cliente publicada que ya tiene al menos un '
                'abono.\n%(motivos)s', motivos='\n'.join(motivos)))
        for empresa in facturas.company_id:
            if not empresa._dcasa_abono_condiciones_lista():
                raise UserError(self.env._(
                    'Todavía no hay condiciones de abono escritas para %(empresa)s, así que la hoja no se imprime. '
                    'Escríbelas en Ajustes › Empresas › %(empresa)s, pestaña «Documentos D\'CASA», sección '
                    '«Condiciones de abono».', empresa=empresa.name))
        return {
            'doc_ids': facturas.ids,
            'doc_model': 'account.move',
            'docs': facturas,
        }
