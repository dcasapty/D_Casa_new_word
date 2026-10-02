from odoo import api, models
from odoo.addons.dcasa_contabilidad.controllers.main import _filas_planas

# Reportes con su propia tabla en el PDF; el resto (y los comparativos) usan la tabla genérica.
CON_PLANTILLA = ('balance_comprobacion', 'libro_mayor', 'estado_resultados', 'balance_general', 'itbms', 'analitica')


class ReporteContablePdf(models.AbstractModel):
    _name = 'report.dcasa_contabilidad.reporte_contable'
    _description = 'Reporte contable en PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        datos = self.env['dcasa.reporte.contable'].obtener(
            data.get('reporte', 'balance_comprobacion'), desde=data.get('desde'), hasta=data.get('hasta'),
            borradores=data.get('borradores', False), cuenta_ids=data.get('cuenta_ids'),
            comparar=data.get('comparar'))
        moneda = self.env.company.currency_id
        generico = datos['reporte'] not in CON_PLANTILLA or bool(datos.get('comparado'))
        encabezados, filas = _filas_planas(datos) if generico else ([], [])

        def m(valor):
            return moneda.format(valor or 0.0) if valor else '—'

        sin_moneda = {i for i, nombre in enumerate(encabezados) if nombre in ('Días', 'Variación %')}

        def celda(valor, columna):
            if not isinstance(valor, (int, float)) or isinstance(valor, bool):
                return valor, False
            if columna in sin_moneda:
                return (f'{valor:g}{" %" if encabezados[columna].endswith("%") else ""}' if valor != '' else ''), True
            return m(valor), True

        return {
            'doc_ids': docids,
            'docs': self.env.company,
            'datos': datos,
            'm': m,
            'generico': generico,
            'encabezados': encabezados,
            'filas_planas': [([celda(v, i) for i, v in enumerate(valores)], estilo) for valores, estilo in filas],
        }
