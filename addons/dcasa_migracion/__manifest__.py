{
    'name': "D'CASA Panamá — Cargar datos del sistema anterior",
    'summary': "Carga única de clientes, productos y existencias exportados por la receta de migración",
    'description': """
Carga única de lo que sale de la receta de migración (Cowork) al ERP nuevo:

* Clientes (clientes.csv): una ficha por cliente, con su número del sistema anterior; respeta el candado
  de contactos (un celular, un correo, un RUC: una sola ficha) y no los junta ni los pisa.
* Productos y existencias (productos.csv + inventario.csv): usa las reglas de la dueña de «Inventario del
  sistema anterior» (la llave es el código; no se pisan nombres ni fotos).
* «Revisar» muestra qué pasaría sin cambiar nada; «Cargar» lo hace. Solo para administradores.
* Los archivos viajan por la pantalla de Odoo: nunca por el repositorio ni por GitHub. El módulo no trae
  datos de personas.
""",
    'version': '19.0.1.0.0',
    'category': 'Hidden',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'dcasa_contactos', 'dcasa_catalogo'],
    'data': [
        'security/ir.model.access.csv',
        'views/carga_views.xml',
    ],
    'installable': True,
}
