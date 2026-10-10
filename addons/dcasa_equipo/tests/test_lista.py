"""Lectura de la lista pegada (sin base de datos). Todo con nombres y correos inventados."""
from odoo.addons.dcasa_equipo.models.alta import leer_lista, leer_rol, revisar_fila
from odoo.tests import TransactionCase, tagged

LISTA = """
# equipo de prueba
Ana Prueba | ana@equipo-prueba.test | Gerencia | Directora | Gerencia
Beto Prueba ; beto@EQUIPO-prueba.test ; Ventas ; Vendedor/a ; vendedor
Cata   Prueba\tcata@equipo-prueba.test\tTecnología\tProgramadora\tAdministrador

"""


@tagged('post_install', '-at_install')
class TestLista(TransactionCase):

    def test_tres_formas_de_separar_y_se_ignora_lo_demas(self):
        filas = leer_lista(LISTA)
        self.assertEqual([f['nombre'] for f in filas], ['Ana Prueba', 'Beto Prueba', 'Cata Prueba'])
        self.assertEqual([f['error'] for f in filas], ['', '', ''])
        self.assertEqual([f['rol'] for f in filas], ['gerencia', 'vendedora', 'administrador'])
        # el correo se guarda en minúsculas
        self.assertEqual(filas[1]['correo'], 'beto@equipo-prueba.test')
        self.assertEqual(filas[2]['departamento'], 'Tecnología')
        self.assertEqual(filas[2]['cargo'], 'Programadora')

    def test_roles_con_otras_palabras(self):
        for texto, clave in (('Vendedora', 'vendedora'), ('  VENDEDOR ', 'vendedora'), ('Ventas', 'vendedora'),
                             ('gerente', 'gerencia'), ('Gerencia', 'gerencia'), ('Admin', 'administrador'),
                             ('Control total', 'administrador')):
            self.assertEqual(leer_rol(texto), clave, texto)
        self.assertFalse(leer_rol('dueño'))
        self.assertFalse(leer_rol(''))

    def test_errores_por_fila(self):
        _fila, error = revisar_fila('', 'a@equipo-prueba.test', 'Ventas', 'x', 'vendedora')
        self.assertIn('nombre', error)
        _fila, error = revisar_fila('Ana', 'sin-arroba', 'Ventas', 'x', 'vendedora')
        self.assertIn('correo', error)
        _fila, error = revisar_fila('Ana', 'a@equipo-prueba.test', 'Ventas', 'x', 'jefa suprema')
        self.assertIn('rol', error)
        fila, error = revisar_fila('  Ana   María ', 'A@Equipo-Prueba.test', ' Ventas ', ' Cargo ', 'Vendedora')
        self.assertEqual(error, '')
        self.assertEqual((fila['nombre'], fila['correo'], fila['departamento'], fila['cargo']),
                         ('Ana María', 'a@equipo-prueba.test', 'Ventas', 'Cargo'))

    def test_linea_con_otra_cantidad_de_datos(self):
        filas = leer_lista("Solo nombre | solo@equipo-prueba.test | Ventas\n"
                           "Ana | ana@equipo-prueba.test | Ventas | Cargo | Vendedora | sobra")
        self.assertEqual(len(filas), 2)
        for fila in filas:
            self.assertIn('cinco datos', fila['error'])

    def test_correo_repetido_en_la_lista(self):
        filas = leer_lista("Ana | ana@equipo-prueba.test | Ventas | x | Vendedora\n"
                           "Otra | ANA@equipo-prueba.test | Ventas | x | Vendedora")
        self.assertEqual(filas[0]['error'], '')
        self.assertIn('repetido', filas[1]['error'])

    def test_lista_vacia(self):
        self.assertEqual(leer_lista(''), [])
        self.assertEqual(leer_lista(False), [])
        self.assertEqual(leer_lista('# solo un comentario\n\n'), [])
