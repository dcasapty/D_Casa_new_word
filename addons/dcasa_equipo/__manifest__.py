{
    'name': "D'CASA Panamá — Equipo",
    'summary': "Alta del equipo en un paso: usuario, empleado, departamento y rol, sin mandar invitaciones",
    'description': """
Dar de alta a las personas del equipo sin pasar por cuatro pantallas de Odoo:

* Empleados › Alta del equipo: se pega la lista (nombre | correo | departamento | cargo | rol), se revisa y se crea.
* Por cada persona: el usuario (con su correo como acceso), su ficha de empleado enlazada al usuario y a su
  contacto, su departamento y su cargo, y el rol de D'CASA (Vendedora, Gerencia o Administrador).
* NO se manda ninguna invitación: la persona no puede entrar hasta que alguien le envíe la invitación desde su ficha
  de usuario. Con el acceso de Odoo, la importación normal sí la manda sola; por eso existe esta pantalla.
* Lo que se pega vive solo en la base de datos de Odoo; nada de esto queda en el repositorio.
* Se puede repetir sin miedo: quien ya existe no se toca (si le faltaba la ficha de empleado, se le crea).
""",
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_base', 'hr', 'auth_signup'],
    'data': [
        'security/ir.model.access.csv',
        'views/alta_views.xml',
        'data/iconos_data.xml',
    ],
    'installable': True,
}
