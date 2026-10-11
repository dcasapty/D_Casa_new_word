{
    'name': "D'CASA Panamá — Equipo",
    'summary': "El equipo en Odoo: ícono de marca para Empleados (el esquema de organización llegará después)",
    'description': """
Lo que toca a las personas del equipo (Empleados) y no es de nómina ni de ventas:

* El menú «Empleados» deja el ícono a colores de Odoo por uno azul D'CASA con trazo blanco.
* Aquí vivirá el esquema de organización del equipo cuando la dueña lo defina. Las personas y sus datos se
  crean y se cambian dentro de Odoo, como cualquier ficha; nada de eso se guarda en el repositorio.
""",
    'version': '19.0.2.0.0',
    'category': 'Human Resources',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'hr'],
    'data': [
        'data/iconos_data.xml',
    ],
    'installable': True,
}
