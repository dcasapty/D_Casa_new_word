{
    'name': "D'CASA Panamá — Factura electrónica DGI (preparación)",
    'summary': "Terreno listo para la factura electrónica de la DGI: datos fiscales, documento rFE con CUFE, "
               "cola con reintentos y contingencia, PAC simulado. Apagado por defecto.",
    'description': """
Factura electrónica de Panamá (SFEP, Ley 256 de 2021) independiente del PAC
=========================================================================

* Apagado por defecto: sin activarlo y sin PAC, Odoo factura exactamente igual.
* Datos fiscales: tipo de receptor y de contribuyente del cliente (RUC/cédula con el DV
  de dcasa_base), ubicación DGI, código CPBS del producto, código DGI de la tasa ITBMS,
  punto de facturación y numeración propia de 10 dígitos por diario.
* ``dcasa.fe.documento`` por factura/nota de crédito: estado, XML rFE, CUFE, QR,
  protocolo, fecha de autorización y errores; histórico inmutable de intentos.
* Generador del rFE con validaciones previas en español y validación contra el XSD
  oficial cuando se copie en ``xsd/``.
* Interfaz de adaptador de PAC (enviar, consultar, anular, descargar) con un PAC
  simulado para pruebas y staging.
* Cola por cron con reintentos y modo contingencia.
* La factura impresa de dcasa_invoice muestra CUFE y QR cuando existen.

Fuentes, lo verificado y lo pendiente: docs/FACTURA_ELECTRONICA.md.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_invoice', 'account', 'l10n_pa'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/fe_documento_views.xml',
        'views/configuracion_views.xml',
        'views/report_invoice.xml',
    ],
    'installable': True,
}
