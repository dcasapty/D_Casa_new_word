{
    'name': "D'CASA Panamá — Contabilidad",
    'summary': "Contabilidad a medida: resumen, reportes con comparativos, conciliación con reglas, cierre de mes",
    'description': """
El sistema contable de D'CASA, construido sobre la contabilidad de Odoo Community
(partida doble, plan contable de Panamá, ITBMS):

* Resumen para la dueña: dinero en bancos, quién te debe, cuánto debes, ITBMS y
  utilidad del periodo contra el anterior.
* Reportes: estado de resultados, balance general y flujo de efectivo (con
  comparativo contra el periodo anterior o el año pasado), cuentas por cobrar y por
  pagar por antigüedad, libro mayor, balance de comprobación, ITBMS y analítica;
  detalle hasta el asiento, exportación a Excel e impresión en PDF.
* Conciliación bancaria: importar el extracto (CSV de cualquier banco, con formatos
  guardados por banco y vista previa; OFX/QFX; CAMT.053) sin duplicar, sugerencias
  de facturas y pagos, reglas de conciliación (las de Odoo) que se aplican solas o
  con un clic, y registro directo de comisiones o gastos.
* Cierre de mes: lista de chequeo con datos reales y fecha de bloqueo (y de ITBMS);
  reabrir pide motivo y queda en el historial.
* Contabilidad analítica: planes y cuentas (canal de venta) y rentabilidad por cuenta.
* Presupuestos por cuenta contable (y cuenta analítica) con lo real y el % ejecutado.
* Cheques con formato propio, monto en letras en español.
* «En desarrollo»: nómina, facturación electrónica DGI y consolidación.
""",
    'version': '19.0.1.1.0',
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
        'views/formato_extracto_views.xml',
        'views/cierre_views.xml',
        'views/cuenta_views.xml',
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
