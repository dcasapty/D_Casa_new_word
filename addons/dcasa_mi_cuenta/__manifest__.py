{
    'name': "D'CASA Panamá — Mi cuenta (panel del cliente)",
    'summary': "El panel del cliente en /mi-cuenta: compras, abonos (cuánto le falta), entregas, puntos y datos, "
               "con celular + PIN o con la cuenta de la tienda",
    'description': """
Mi cuenta D'CASA
================

Un solo lugar para el cliente, sencillo y pensado para el celular (se usa de pie en el mostrador):

* **Inicio**: lo pendiente primero (la compra con saldo: «Te falta $X», lo pagado y hasta cuándo; o la entrega
  lista; o los premios por recoger), la última compra con su línea de tiempo, los puntos y WhatsApp.
* **Compras**: pedidos, cotizaciones, apartados y facturas sueltas en grupos («Por pagar», «Por entregar o
  retirar», «Ya las tienes», «Canceladas»), con foto del mueble y el detalle de cada abono.
* **Puntos**: lo que antes era /socios/cuenta, ordenado para el mostrador.
* **Mis datos**: solo lectura, cambiar el PIN o la contraseña y salir.

Las cifras de pago salen SOLO de ``account.move._dcasa_estado_abono()`` (dcasa_invoice): esta pantalla lee y no
escribe nada; los abonos se siguen registrando con «Pagar» en la factura, como siempre.

Se entra con la sesión de socio (celular + PIN, ``dcasa_socios``) o con la cuenta de la tienda (portal). Todo se
lee filtrando por la ficha comercial del cliente: un pedido o una factura de otra persona responde 404. A quien entra
con PIN no se le enseñan cédula, dirección, teléfonos ni PDF.
""",
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['website_dcasa', 'dcasa_socios', 'dcasa_invoice', 'sale_stock', 'website_sale', 'auth_signup'],
    'data': [
        'views/mi_cuenta_templates.xml',
        'views/herencias_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'dcasa_mi_cuenta/static/src/scss/mi_cuenta.scss',
            'dcasa_mi_cuenta/static/src/js/copiar.js',
        ],
    },
    'installable': True,
}
