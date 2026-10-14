{
    'name': "D'CASA Panamá — Cargar datos del sistema anterior",
    'summary': "Carga única de clientes, proveedores, productos, existencias y precios exportados por la receta",
    'description': """
Carga única de lo que sale de la receta de migración (Cowork) al ERP nuevo:

* Clientes (clientes.csv): una ficha por cliente, con su número del sistema anterior; respeta el candado
  de contactos (un celular, un correo, un RUC: una sola ficha) y no los junta ni los pisa.
* Proveedores (proveedores.csv, mismo formato; quien es cliente y proveedor tiene una sola ficha) y sus precios
  por producto (precios_proveedor.csv).
* Productos y existencias (productos.csv + inventario.csv): usa las reglas de la dueña de «Inventario del
  sistema anterior» (la llave es el código; no se pisan nombres ni fotos).
* Combos de cama y colchón (combos.csv, o «Armar los combos desde su nombre»): usa el tipo «Combo» nativo de Odoo; los
  combos ya cargados pasan a ese tipo conservando su id, nombre, precio e historial. Nunca adivina: solo arma lo claro.
* «Revisar» muestra qué pasaría sin cambiar nada; «Cargar» lo hace. Solo para administradores.
* Los archivos viajan por la pantalla de Odoo: nunca por el repositorio ni por GitHub. El módulo no trae
  datos de personas.
""",
    'version': '19.0.1.1.0',
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
