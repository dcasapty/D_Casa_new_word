{
    'name': "D'CASA Panamá — Guía del negocio",
    'summary': "«¿Qué necesitas hacer hoy?»: atajos en palabras sencillas a lo que hay que hacer en el negocio",
    'description': """
La Guía para quien administra el negocio sin ser contador:

* Un menú «Guía» con la pregunta «¿Qué necesitas hacer hoy?»: categorías (vender y cobrar, facturas y pagos, bancos,
  cómo va el negocio, impuestos y obligaciones, personal y nómina, productos e inventario, compras, clientes y
  vendedores, tienda en línea, administrar el sistema).
* Cada tarea dice, en palabras sencillas, qué quiere hacer la persona y qué logra al llegar a la pantalla, y lleva un
  atajo hasta ella. Las hay con pasos (declaración de renta, pasarle los números al contador).
* Solo se muestran las tareas que la persona puede abrir: los mismos permisos del menú de la izquierda.
* Buscador sin tildes, y botón «Preguntarle a Brian» en cada tarea.
* «Llévame ahí»: abre la pantalla justa en un clic, desde la tarjeta, el detalle, los pasos y el buscador; deja una
  cinta discreta y descartable que recuerda lo que estás haciendo.
* Lo más usado: «En tu puesto lo que más se usa» (lista curada por puesto) y «Lo que tú más usas» (el uso real de cada
  persona; nadie ve el de otra).
* Nada se inventa: las fechas límite de impuestos se confirman con el contador.
* La misma lista alimenta la herramienta ``buscar_en_guia`` de Brian (módulo dcasa_brian).
""",
    'version': '19.0.1.0.0',
    'category': 'Hidden',
    'author': "D'CASA Panamá",
    'website': 'https://dcasapty.com',
    'license': 'LGPL-3',
    'depends': ['dcasa_interfaz'],
    'data': [
        'security/ir.model.access.csv',
        'security/guia_security.xml',
        'views/guia_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dcasa_guia/static/src/scss/*.scss',
            'dcasa_guia/static/src/js/*.js',
            'dcasa_guia/static/src/xml/*.xml',
        ],
    },
    'installable': True,
}
