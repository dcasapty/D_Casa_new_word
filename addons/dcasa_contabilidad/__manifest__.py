{
    'name': "D'CASA Panamá — Contabilidad",
    'summary': "Contabilidad a medida: reportes, conciliación bancaria, analítica, presupuestos y cheques",
    'description': """
El sistema contable de D'CASA, construido sobre la contabilidad de Odoo Community
(partida doble, plan contable de Panamá, ITBMS):

* Reportes: libro mayor, balance de comprobación, estado de resultados, balance
  general y resumen de ITBMS; con rango de fechas, detalle hasta el asiento,
  exportación a Excel e impresión en PDF.
* Conciliación bancaria: importar el extracto del banco (CSV de Banco General,
  BAC, Banistmo, Yappy o cualquier CSV con fecha, descripción y monto), sugerencias
  de facturas y pagos por monto, cliente o referencia, conciliación en un clic y
  registro directo de comisiones o gastos.
* Contabilidad analítica: planes y cuentas (canal de venta) y rentabilidad por cuenta.
* Presupuestos por cuenta contable (y cuenta analítica) con lo real y el % ejecutado.
* Cheques con formato propio, monto en letras en español.
* «En desarrollo»: nómina, facturación electrónica DGI y consolidación.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_invoice', 'dcasa_interfaz', 'account', 'analytic', 'account_check_printing'],
    'data': [
        'security/ir.model.access.csv',
        'data/analitica_data.xml',
        'report/reportes_pdf.xml',
        'report/cheque.xml',
        'wizard/importar_extracto_views.xml',
        'views/presupuesto_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dcasa_contabilidad/static/src/scss/*.scss',
            'dcasa_contabilidad/static/src/js/*.js',
            'dcasa_contabilidad/static/src/xml/*.xml',
        ],
    },
    'post_init_hook': '_dcasa_contabilidad_post_init',
    'installable': True,
}
