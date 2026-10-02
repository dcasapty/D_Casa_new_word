"""Exportación a Excel de los reportes contables."""
import io
import json

from odoo import http
from odoo.http import content_disposition, request

AZUL = '#1340B1'


def _detalle_tarjeta(tarjeta):
    if 'vencido' in tarjeta:
        return f"Vencido: {tarjeta['vencido']:,.2f}"
    if 'debito' in tarjeta:
        return f"Ventas {tarjeta['debito']:,.2f} − compras {tarjeta['credito']:,.2f}"
    if 'comparado' in tarjeta:
        return f"Periodo anterior: {tarjeta['comparado']:,.2f}"
    return tarjeta.get('nota', '')


def _plano_comprobacion(datos):
    enc = ['Código', 'Cuenta', 'Saldo inicial', 'Debe', 'Haber', 'Saldo final']
    filas = [([f['codigo'], f['nombre'], f['inicial'], f['debe'], f['haber'], f['final']], '')
             for f in datos['filas']]
    t = datos['totales']
    filas.append((['', 'Totales', t['inicial'], t['debe'], t['haber'], t['final']], 'b'))
    return enc, filas


def _plano_mayor(datos):
    enc = ['Fecha', 'Asiento', 'Diario', 'Tercero', 'Concepto', 'Debe', 'Haber', 'Saldo']
    filas = []
    for c in datos['cuentas']:
        filas.append(([f"{c['codigo']} {c['nombre']}", '', '', '', 'Saldo inicial', '', '', c['inicial']], 'b'))
        for linea in c['lineas']:
            filas.append(([linea['fecha'], linea['asiento'], linea['diario'], linea['tercero'], linea['concepto'],
                           linea['debe'], linea['haber'], linea['saldo']], ''))
        filas.append((['', '', '', '', 'Total de la cuenta', c['debe'], c['haber'], c['final']], 'b'))
    return enc, filas


def _plano_secciones(datos):
    reporte = datos['reporte']
    comp = datos.get('comparado')
    enc = ['Código', 'Cuenta', 'Monto']
    if comp:
        enc = ['Código', 'Cuenta', f"{datos['desde']} a {datos['hasta']}", f"{comp['desde']} a {comp['hasta']}",
               'Variación', 'Variación %']

    def fila(codigo, nombre, monto, anterior=None):
        valores = [codigo, nombre, monto]
        if comp:
            anterior = anterior or 0.0
            pct = round((monto - anterior) / abs(anterior) * 100, 1) if anterior else ''
            valores += [anterior, round(monto - anterior, 2), pct]
        return valores

    cifras = datos.get('resumen') or datos.get('totales') or {}
    cifras_ant = (comp or {}).get('resumen') or (comp or {}).get('totales') or {}
    filas = []
    for s in datos['secciones']:
        filas.append((['', s['titulo']] + [''] * (len(enc) - 2), 'b'))
        filas += [(fila(f['codigo'], f['nombre'], f['monto'], f.get('comparado')), '') for f in s['filas']]
        filas.append((fila('', f"Total {s['titulo'].lower()}", s['total'], s.get('comparado')), 'b'))
    if reporte == 'estado_resultados':
        totales = [('Utilidad bruta', 'utilidad_bruta'), ('Utilidad operativa', 'utilidad_operativa'),
                   ('Utilidad neta', 'utilidad_neta')]
    elif reporte == 'balance_general':
        totales = [('Total activo', 'activo'), ('Total pasivo y patrimonio', 'pasivo_y_patrimonio')]
    else:
        totales = [('Efectivo al inicio', 'efectivo_inicial'), ('Variación del efectivo', 'variacion'),
                   ('Efectivo al final', 'efectivo_final')]
    filas += [(fila('', nombre, cifras[clave], cifras_ant.get(clave)), 'b') for nombre, clave in totales]
    return enc, filas


def _plano_antiguedad(datos):
    enc = ['Tercero', 'Documento', 'Vence', 'Días'] + [t['nombre'] for t in datos['tramos']] + ['Total']
    claves = [t['clave'] for t in datos['tramos']]
    filas = []
    for f in datos['filas']:
        filas.append(([f['nombre'], '', '', ''] + [f['tramos'][k] for k in claves] + [f['total']], 'b'))
        for d in f['documentos']:
            filas.append((['', d['documento'], d['vence'], d['dias']]
                          + [d['monto'] if d['tramo'] == k else '' for k in claves] + [d['monto']], ''))
    t = datos['totales']
    filas.append((['Total', '', '', ''] + [t[k] for k in claves] + [t['total']], 'b'))
    return enc, filas


def _plano_resumen(datos):
    enc = ['Concepto', 'Monto', 'Detalle']
    filas = [([t['titulo'], t['valor'], _detalle_tarjeta(t)], '') for t in datos['tarjetas']]
    filas.append((['Bancos y caja', '', ''], 'b'))
    filas += [([b['nombre'], b['saldo'], f"{b['por_conciliar']} por conciliar"], '') for b in datos['bancos']]
    filas.append((['Quién te debe más', '', ''], 'b'))
    filas += [([d['nombre'], d['total'], f"Vencido {d['vencido']:,.2f}"], '') for d in datos['deudores']]
    return enc, filas


def _plano_itbms(datos):
    enc = ['Impuesto', 'Tipo', 'Base imponible', 'ITBMS']
    filas = [([f['nombre'], 'Ventas' if f['tipo'] == 'venta' else 'Compras', f['base'], f['impuesto']], '')
             for f in datos['filas']]
    r = datos['resumen']
    filas += [(['Débito fiscal (ventas)', '', '', r['debito_fiscal']], 'b'),
              (['Crédito fiscal (compras)', '', '', r['credito_fiscal']], 'b'),
              (['ITBMS a pagar', '', '', r['a_pagar']], 'b')]
    return enc, filas


def _plano_analitica(datos):
    enc = ['Plan', 'Cuenta analítica', 'Ingresos', 'Costos y gastos', 'Margen']
    return enc, [([f['plan'], f['nombre'], f['ingresos'], f['costos'], f['margen']], '') for f in datos['filas']]


PLANOS = {
    'balance_comprobacion': _plano_comprobacion,
    'libro_mayor': _plano_mayor,
    'estado_resultados': _plano_secciones,
    'balance_general': _plano_secciones,
    'flujo_efectivo': _plano_secciones,
    'por_cobrar': _plano_antiguedad,
    'por_pagar': _plano_antiguedad,
    'resumen': _plano_resumen,
    'itbms': _plano_itbms,
    'analitica': _plano_analitica,
}


def _filas_planas(datos):
    """(encabezados, filas) de cualquier reporte, listas para una hoja de cálculo o el PDF genérico.

    Cada fila es (valores, estilo); estilo 'b' = fila en negrita (subtotal o total).
    """
    if datos['reporte'] not in PLANOS:
        raise ValueError(datos['reporte'])
    return PLANOS[datos['reporte']](datos)


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
    periodo = (f"Al {datos['hasta']}" if datos['desde'] == datos['hasta'] or datos['reporte'] == 'balance_general'
               else f"Del {datos['desde']} al {datos['hasta']}")
    if datos.get('comparado'):
        periodo += f" · comparado con {datos['comparado']['desde']} a {datos['comparado']['hasta']}"
    hoja.write(1, 0, f"{periodo} · montos en {datos['moneda']['simbolo']}", sub)
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
    def exportar_excel(self, reporte, desde=None, hasta=None, borradores=None, cuentas=None, comparar=None, **_kw):
        cuenta_ids = [int(c) for c in json.loads(cuentas)] if cuentas else None
        datos = request.env['dcasa.reporte.contable'].obtener(
            reporte, desde=desde or None, hasta=hasta or None, borradores=borradores == '1', cuenta_ids=cuenta_ids,
            comparar=comparar or None)
        nombre = f"{datos['titulo']} {datos['desde']} a {datos['hasta']}.xlsx"
        return request.make_response(libro_excel(datos), headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(nombre)),
        ])
