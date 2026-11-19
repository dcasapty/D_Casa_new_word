{
    'name': "D'CASA Panamá — Comisión del sitio web",
    'summary': "Mide las ventas por internet como una sucursal y calcula, libra y liquida la comisión del sitio web",
    'description': """
La comisión por las ventas del sitio web (decisión de Gerencia, 2026-11-19; ver ``docs/COMISION_WEB.md``):

* **Medición siempre activa**: cada factura pagada por completo que sale de un pedido online tiene su fila en «Ventas
  del
  sitio» (cómo llegó, cómo pagó, lo vendido, envío, devoluciones), aunque todavía no haya porcentaje.
* **Reglas por versión** (Nómina › Comisión del sitio web › Reglas): el porcentaje fijo de cada venta, la tarifa fija
  por
  mantener la plataforma, cómo se arma la base (ITBMS, envío, descuentos, devoluciones y comisión de la pasarela, cada
  uno con su ejemplo en pantalla) y quiénes reciben, con su reparto. Solo hacia adelante y sin cifras de fábrica.
* **Libro inmutable** por persona y concepto, con reversos por devoluciones, pagos revertidos y facturas anuladas.
* **Liquidaciones** de cualquier periodo: propuesta, aprobación (quien cobra no aprueba) y pago. Nada se paga solo.
* Una venta online **nunca** es de una vendedora (bono por meta, Inicio ni programa de vendedores): lo decide una sola
  definición compartida (``dcasa_base``).
""",
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_nomina', 'dcasa_invoice', 'dcasa_conversaciones', 'website_sale', 'delivery',
                'hr'],
    'data': [
        'security/comision_web_security.xml',
        'security/ir.model.access.csv',
        'data/comision_web_data.xml',
        'views/reglas_views.xml',
        'views/venta_views.xml',
        'views/liquidacion_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
