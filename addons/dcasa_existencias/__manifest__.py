{
    'name': "D'CASA Panamá — Control de existencias",
    'summary': 'Mermas, daños, muestras y regalos con su costo y su cuenta; bitácora de bodega con motivo; alertas '
               'diarias por Telegram a Gerencia (apagadas de fábrica)',
    'description': """
Control de lo que sale o cambia en la bodega sin una venta (etapa 4 de PRIORIDADES y F6 de DECISIONES_CONTABLES):

* **Mermas, daños, muestras y regalos (F6)**: se registran con su código (motivo), su costo y, para reclamarle, el
  proveedor. Al confirmarlas (solo Gerencia) baja la existencia con el desecho de Odoo y, si la contadora ya eligió
  las cuentas, queda el asiento en la cuenta de mermas: una partida propia del estado de resultados, mes a mes y en
  el año. Resumen del mes con el **aviso del 0.5 % de lo comprado** (cifra de la gerencia) y el reclamo al proveedor
  en PDF. Sin cuenta elegida, la pantalla lo dice: no se inventan cuentas.
* **Bitácora de bodega**: cada ajuste de existencias (Inventario físico, Escáner › Contar, Brian, deshacer un ajuste,
  mermas) con el antes → después, el motivo (obligatorio) y quién lo hizo. Solo la lee Gerencia; nadie la edita.
* **Hueco del Inventario físico cerrado**: «Inventario físico», «Desechos», «Deshacer el ajuste» y el desecho desde
  una entrega son de Gerencia (menús y servidor), y ningún movimiento hacia o desde «Ajuste de inventario» lo hace
  quien no es Gerencia, ni por RPC.
* **Alertas diarias por Telegram a Gerencia** (stock bajo, ajustes grandes, cierre de mes y mermas sobre el tope):
  apagadas de fábrica y sin umbrales: cada una sale solo si la dueña la enciende y pone su umbral.
""",
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_brian', 'dcasa_contabilidad', 'dcasa_interfaz', 'stock_account',
                'purchase_stock', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/reglas.xml',
        'data/datos.xml',
        'report/reclamo.xml',
        'views/config_views.xml',
        'views/merma_views.xml',
        'views/bitacora_views.xml',
        'views/inventario_views.xml',
        'wizard/resumen_views.xml',
        'wizard/reclamo_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
