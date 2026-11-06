{
    'name': "D'CASA Panamá — Envíos (calculadora)",
    'summary': 'Cuánto cuesta un envío desde la tienda: buscar el lugar como lo dice el cliente, el precio con su '
               'desglose y la tarifa que aprueba Gerencia',
    'description': """
Pedido de la dueña (2026-11-06): poner la calculadora de envíos (el HTML de la propuesta) en el menú «Envíos», con el
scroll que funcione, y dejar el código listo para que, el día que D'CASA tenga su propia flota, el cliente calcule su
envío en la página web.

* **Calculadora** (Envíos › Calculadora, todo el equipo): el buscador grande (sin tildes, abreviaturas, frases, errores
  de dedo, lugares conocidos), filtros por tipo y distrito, el precio con su desglose, «Copiar el precio», la ruta en
  Google Maps desde la tienda, «¿Quisiste decir…?», «Agregar este lugar» (queda el nombre de quien lo agregó) y
  «Calcular por kilómetros» con la tabla por tramos. Mientras la tarifa no esté aprobada: «Tarifa en revisión».
* **Lugares** (lista, se exporta a Excel con el precio) y **Tarifa** (Gerencia y administradores: la fórmula, los
  cargos aparte, subir o bajar todo en %, aprobarla con quién y cuándo, el historial y «Cargar lugares y tarifa desde
  el archivo»).
* **Un solo motor** en Python, sin Odoo (``motor/``): la fórmula y el buscador portados con fidelidad del HTML. Lo usan
  la pantalla (por RPC), Brian (``cotizar_envio``) y, mañana, la web y Juan: ``dcasa.envio.lugar.buscar_para_cotizar``
  y ``dcasa.envio.tarifa.cotizar_lugar`` / ``cotizar_km``. Todavía no hay ruta pública (ver docs/ENVIOS.md).
* Los datos (los lugares y los precios) **no** van en el repositorio: Gerencia sube el archivo.

Ver docs/ENVIOS.md.
""",
    'version': '19.0.1.0.0',
    'category': 'Inventory/Delivery',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_interfaz', 'dcasa_contabilidad', 'dcasa_brian', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/lugar_views.xml',
        'views/tarifa_views.xml',
        'wizard/importar_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dcasa_envios/static/src/scss/*.scss',
            'dcasa_envios/static/src/js/*.js',
            'dcasa_envios/static/src/xml/*.xml',
        ],
    },
    'uninstall_hook': '_dcasa_envios_uninstall',
    'installable': True,
}
