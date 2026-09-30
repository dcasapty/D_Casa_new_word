"""Exportación a Excel de los reportes contables."""
import io
import json

from odoo import http
from odoo.http import content_disposition, request

AZUL = '#1340B1'


def _filas_planas(datos):
    """(encabezados, filas, formatos) de cualquier reporte, listas para una hoja de cálculo.

    Formatos: 't' texto, 'm' monto, 'b' fila en negrita (subtotal o total).
    """
    reporte = datos['reporte']
    if reporte == 'balance_comprobacion':
        enc = ['Código', 'Cuenta', 'Saldo inicial', 'Debe', 'Haber', 'Saldo final']
        filas = [([f['codigo'], f['nombre'], f['inicial'], f['debe'], f['haber'], f['final']], '')
                 for f in datos['filas']]
        t = datos['totales']
        filas.append((['', 'Totales', t['inicial'], t['debe'], t['haber'], t['final']], 'b'))
        return enc, filas
    if reporte == 'libro_mayor':
        enc = ['Fecha', 'Asiento', 'Diario', 'Tercero', 'Concepto', 'Debe', 'Haber', 'Saldo']
        filas = []
        for c in datos['cuentas']:
            filas.append(([f"{c['codigo']} {c['nombre']}", '', '', '', 'Saldo inicial', '', '', c['inicial']], 'b'))
            for linea in c['lineas']:
                filas.append(([linea['fecha'], linea['asiento'], linea['diario'], linea['tercero'], linea['concepto'],
                               linea['debe'], linea['haber'], linea['saldo']], ''))
            filas.append((['', '', '', '', 'Total de la cuenta', c['debe'], c['haber'], c['final']], 'b'))
        return enc, filas
    if reporte in ('estado_resultados', 'balance_general'):
        enc = ['Código', 'Cuenta', 'Monto']
        filas = []
        for s in datos['secciones']:
            filas.append((['', s['titulo'], ''], 'b'))
            filas += [([f['codigo'], f['nombre'], f['monto']], '') for f in s['filas']]
            filas.append((['', f"Total {s['titulo'].lower()}", s['total']], 'b'))
        if reporte == 'estado_resultados':
            r = datos['resumen']
            filas += [(['', 'Utilidad bruta', r['utilidad_bruta']], 'b'),
                      (['', 'Utilidad operativa', r['utilidad_operativa']], 'b'),
                      (['', 'Utilidad neta', r['utilidad_neta']], 'b')]
        else:
            t = datos['totales']
            filas += [(['', 'Total activo', t['activo']], 'b'),
                      (['', 'Total pasivo y patrimonio', t['pasivo_y_patrimonio']], 'b')]
        return enc, filas
    if reporte == 'itbms':
        enc = ['Impuesto', 'Tipo', 'Base imponible', 'ITBMS']
        filas = [([f['nombre'], 'Ventas' if f['tipo'] == 'venta' else 'Compras', f['base'], f['impuesto']], '')
                 for f in datos['filas']]
        r = datos['resumen']
        filas += [(['Débito fiscal (ventas)', '', '', r['debito_fiscal']], 'b'),
                  (['Crédito fiscal (compras)', '', '', r['credito_fiscal']], 'b'),
                  (['ITBMS a pagar', '', '', r['a_pagar']], 'b')]
        return enc, filas
    if reporte == 'analitica':
        enc = ['Plan', 'Cuenta analítica', 'Ingresos', 'Costos y gastos', 'Margen']
        return enc, [([f['plan'], f['nombre'], f['ingresos'], f['costos'], f['margen']], '') for f in datos['filas']]
    raise ValueError(reporte)


def libro_excel(datos):
    import xlsxwriter  # noqa: PLC0415

    salida = io.BytesIO()
    libro = xlsxwriter.Workbook(salida, {'in_memory': True})
    hoja = libro.add_worksheet(datos['titulo'][:31])
    titulo = libro.add_format({'bold': True, 'font_size': 14, 'font_color': AZUL})
    sub = libro.add_format({'font_color': '#5B6478'})
    enc_f = libro.add_format({'bold': True, 'bg_color': AZUL, 'font_color': '#FFFFFF', 'border': 0})
    monto = libro.add_format({'num_format': '#,##0.00;[Red]-#,##0.00'})
    monto_b = libro.add_format({'num_format': '#,##0.00;[Red]-#,##0.00', 'bold': True, 'top': 1})
    texto_b = libro.add_format({'bold': True, 'top': 1})

    hoja.write(0, 0, f"{datos.get('empresa', '')} · {datos['titulo']}", titulo)
    hoja.write(1, 0, f"Del {datos['desde']} al {datos['hasta']} · montos en {datos['moneda']['simbolo']}", sub)
    encabezados, filas = _filas_planas(datos)
    for col, nombre in enumerate(encabezados):
        hoja.write(3, col, nombre, enc_f)
    for i, (valores, estilo) in enumerate(filas, start=4):
        for col, valor in enumerate(valores):
            numero = isinstance(valor, (int, float)) and not isinstance(valor, bool)
            formato = (monto_b if numero else texto_b) if estilo == 'b' else (monto if numero else None)
            hoja.write(i, col, valor, formato)
    anchos = [max(len(str(encabezados[c])), *(len(str(v[c])) for v, _e in filas)) if filas else 12
              for c in range(len(encabezados))]
    for col, ancho in enumerate(anchos):
        hoja.set_column(col, col, min(max(ancho + 2, 10), 60))
    hoja.freeze_panes(4, 0)
    libro.close()
    return salida.getvalue()


class DcasaContabilidadController(http.Controller):

    @http.route('/dcasa/contabilidad/excel', type='http', auth='user', methods=['GET'])
    def exportar_excel(self, reporte, desde=None, hasta=None, borradores=None, cuentas=None, **_kw):
        cuenta_ids = [int(c) for c in json.loads(cuentas)] if cuentas else None
        datos = request.env['dcasa.reporte.contable'].obtener(
            reporte, desde=desde or None, hasta=hasta or None, borradores=borradores == '1', cuenta_ids=cuenta_ids)
        nombre = f"{datos['titulo']} {datos['desde']} a {datos['hasta']}.xlsx"
        return request.make_response(libro_excel(datos), headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(nombre)),
        ])
