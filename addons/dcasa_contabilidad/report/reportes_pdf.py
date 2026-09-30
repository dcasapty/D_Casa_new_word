from odoo import api, models


class ReporteContablePdf(models.AbstractModel):
    _name = 'report.dcasa_contabilidad.reporte_contable'
    _description = 'Reporte contable en PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        datos = self.env['dcasa.reporte.contable'].obtener(
            data.get('reporte', 'balance_comprobacion'), desde=data.get('desde'), hasta=data.get('hasta'),
            borradores=data.get('borradores', False), cuenta_ids=data.get('cuenta_ids'))
        moneda = self.env.company.currency_id
        return {
            'doc_ids': docids,
            'docs': self.env.company,
            'datos': datos,
            'm': lambda valor: moneda.format(valor or 0.0) if valor else '—',
        }
