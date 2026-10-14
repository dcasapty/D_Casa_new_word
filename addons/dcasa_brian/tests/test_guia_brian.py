"""Brian conoce la Guía del negocio: dice la ruta del menú para lo que la persona quiere hacer."""
from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestBrianGuia(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupos):
            ids = [cls.env.ref(g).id for g in ('base.group_user', *grupos)]
            return Usuarios.create({'name': login.replace('_', ' ').title(), 'login': login,
                                    'group_ids': [Command.set(ids)]})

        cls.gerencia = usuario('brian_g_gerencia', ('dcasa_base.group_gerencia', 'account.group_account_manager'))
        cls.caja = usuario('brian_g_caja', ('sales_team.group_sale_salesman',))

    def ejecutar(self, usuario, consulta):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar('buscar_en_guia', {'consulta': consulta})

    def test_la_herramienta_esta_en_el_catalogo_de_lectura(self):
        esquema = next(e for e in self.env['brian.herramientas'].catalogo() if e['name'] == 'buscar_en_guia')
        self.assertEqual((esquema['nivel'], esquema['categoria']), ('lectura', 'general'))

    def test_gerencia_pregunta_por_la_renta_y_recibe_la_ruta_y_los_pasos(self):
        respuesta = self.ejecutar(self.gerencia, 'no sé por dónde empezar con la declaración de renta')
        self.assertTrue(respuesta.get('ok'), respuesta)
        primero = respuesta['datos']['resultados'][0]
        self.assertIn('renta', primero['tarea'].lower())
        self.assertIn('Estado de resultados', primero['donde'])
        self.assertGreaterEqual(len(primero['pasos']), 5)
        self.assertIn('contador', primero['nota'])
        self.assertIn('contador', respuesta['datos']['nota'])

    def test_la_caja_no_recibe_rutas_de_contabilidad(self):
        respuesta = self.ejecutar(self.caja, 'declaración de renta')
        self.assertTrue(respuesta.get('ok'), respuesta)
        rutas = ' '.join(r['donde'] for r in respuesta['datos']['resultados'])
        self.assertNotIn('Facturación › Reportes contables', rutas)

    def test_sin_coincidencias_orienta_a_la_guia(self):
        respuesta = self.ejecutar(self.gerencia, 'zzzzqqqq')
        self.assertTrue(respuesta.get('ok'), respuesta)
        self.assertEqual(respuesta['datos']['resultados'], [])
        self.assertIn('Guía', respuesta['datos']['nota'])

    def test_un_menu_de_lista_trae_boton_abrir(self):
        respuesta = self.ejecutar(self.gerencia, 'ver las facturas de los clientes')
        self.assertTrue(respuesta.get('ok'), respuesta)
        con_boton = [r for r in respuesta['datos']['resultados'] if r.get('abrir')]
        self.assertTrue(con_boton, respuesta)
        self.assertTrue(all(r['abrir']['modelo'] for r in con_boton))

    def test_el_panel_de_brian_sabe_recibir_una_pregunta_escrita(self):
        """La Guía deja la pregunta en la caja de Brian (servicio.preguntar) y el panel la recoge sin enviarla."""
        from odoo.tools.misc import file_path
        with open(file_path('dcasa_brian/static/src/js/brian_servicio.js'), encoding='utf-8') as archivo:
            servicio = archivo.read()
        self.assertIn('preguntar(texto)', servicio)
        self.assertIn('pregunta: ""', servicio)
        with open(file_path('dcasa_brian/static/src/js/brian_panel.js'), encoding='utf-8') as archivo:
            panel = archivo.read()
        self.assertIn('this.abierto.pregunta', panel)
        self.assertIn('this.state.texto = pregunta', panel)
