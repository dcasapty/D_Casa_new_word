"""La Guía: el catálogo es coherente, cada atajo existe, cada quien ve solo lo que puede abrir y el buscador sirve."""
import re
from xml.etree import ElementTree

from odoo.addons.dcasa_guia.models import guia as G
from odoo.tests import BaseCase, TransactionCase, tagged
from odoo.tools.misc import file_path

MESES = 'enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre'


def destinos_de(tarea):
    """Todos los destinos de una tarea: el principal y los de sus pasos."""
    destinos = [tarea.get('destino')] if tarea.get('destino') else []
    destinos += [p['destino'] for p in tarea.get('pasos', []) if p.get('destino')]
    return destinos


@tagged('post_install', '-at_install')
class TestCatalogo(BaseCase):
    """El archivo ``data/guia.json`` por sí solo (sin base de datos)."""

    def setUp(self):
        super().setUp()
        self.catalogo = G.cargar_catalogo()
        self.tareas = self.catalogo['tareas']

    def test_normalizar_quita_tildes_y_mayusculas(self):
        self.assertEqual(G.normalizar('Declaración de RENTA'), 'declaracion de renta')
        self.assertEqual(G.palabras_de('¿Cómo hago la declaración de renta?'), ['hago', 'declaracion', 'renta'])
        self.assertEqual(G.palabras_de('el de la para'), [], 'Solo palabras vacías: no busca nada')

    def test_ids_y_categorias_son_validas(self):
        ids = [t['id'] for t in self.tareas]
        self.assertEqual(len(ids), len(set(ids)), 'ids repetidos')
        claves = [c['clave'] for c in self.catalogo['categorias']]
        self.assertEqual(len(claves), len(set(claves)))
        for tarea in self.tareas:
            with self.subTest(tarea['id']):
                self.assertIn(tarea['categoria'], claves)
                for otra in tarea.get('tambien', []):
                    self.assertIn(otra, claves)
                    self.assertNotEqual(otra, tarea['categoria'])

    def test_empieza_por_aqui_son_ids_validos_y_pocos(self):
        ids = {t['id'] for t in self.tareas}
        empezar = self.catalogo['empezar']
        self.assertTrue(set(empezar) <= ids, set(empezar) - ids)
        self.assertEqual(len(empezar), len(set(empezar)))
        self.assertLessEqual(len(empezar), 10, 'Una lista corta: si son muchas, ya no es «empieza por aquí»')

    def test_cada_tarea_esta_escrita_en_palabras_sencillas(self):
        for tarea in self.tareas:
            with self.subTest(tarea['id']):
                self.assertTrue(tarea['titulo'].strip() and tarea['logras'].strip(), 'Falta el título o lo que logra')
                self.assertLessEqual(len(tarea['titulo']), 90)
                self.assertTrue(tarea['logras'].rstrip().endswith('.'), 'Lo que logras es una frase completa')
                self.assertTrue(tarea.get('palabras'), 'Sin palabras de búsqueda no la encuentran con sus palabras')
                if tarea.get('nota'):
                    self.assertTrue(tarea['nota'].rstrip().endswith('.'))

    def test_cada_destino_tiene_una_forma_valida(self):
        for tarea in self.tareas:
            for destino in destinos_de(tarea):
                with self.subTest(tarea['id']):
                    self.assertEqual(sum(1 for k in ('menu', 'nuevo') if destino.get(k)), 1, destino)
                    if destino.get('menu'):
                        self.assertRegex(destino['menu'], r'^[a-z0-9_]+\.[a-zA-Z0-9_]+$')
                    for clave in destino.get('contexto', {}):
                        self.assertTrue(clave.startswith(('search_default_', 'default_')), clave)

    def test_una_tarea_sin_pantalla_dice_que_hacer_con_ella(self):
        """Sin destino, la tarea debe al menos explicar o dejar una pregunta lista para Brian."""
        for tarea in self.tareas:
            if not tarea.get('destino'):
                with self.subTest(tarea['id']):
                    self.assertTrue(tarea.get('brian') or tarea.get('nota'), tarea['id'])

    def test_no_se_inventan_fechas_ni_montos_de_impuestos(self):
        """Las fechas límite y los montos los confirma el contador: el catálogo no los afirma."""
        for tarea in self.tareas:
            texto = ' '.join([tarea['titulo'], tarea['logras'], tarea.get('nota', '')]
                             + [p['texto'] for p in tarea.get('pasos', [])])
            with self.subTest(tarea['id']):
                self.assertIsNone(re.search(rf'\b\d{{1,2}}\s+de\s+({MESES})\b', texto, re.I), texto)
                self.assertIsNone(re.search(r'\$\s*\d', texto), 'Montos en dólares: no se inventan')

    def test_las_tareas_de_impuestos_mandan_a_confirmar_las_fechas(self):
        for clave in ('renta', 'itbms', 'otras-obligaciones', 'decimo-tercer'):
            tarea = next(t for t in self.tareas if t['id'] == clave)
            with self.subTest(clave):
                self.assertIn('contador', (tarea.get('nota') or '') + tarea['logras'])

    def test_un_abono_se_registra_desde_la_factura(self):
        """El abono se anota con «Pagar» en la factura (así queda unido y sale el papel de ABONO); un cobro suelto no
        se une solo a la factura, y la Guía ya no dice que sí."""
        tareas = {t['id']: t for t in self.tareas}
        abono = tareas['registrar-abono']
        self.assertEqual(abono['titulo'], 'Registrar un abono de un cliente')
        self.assertEqual(abono['categoria'], 'vender')
        pasos = ' '.join(p['texto'] for p in abono['pasos'])
        for texto in ('Abre la factura', '«Pagar»', 'monto del abono', 'ABONO', 'saldo'):
            self.assertIn(texto, pasos)
        self.assertIn('La factura es la misma de siempre', abono['logras'])
        self.assertIn('abono', abono['palabras'])
        cobrar = tareas['cobrar-cliente']
        self.assertNotIn('lo une a su factura', cobrar['logras'])
        self.assertIn('no se une solo a su factura', cobrar['logras'])
        self.assertIn('«Pagar»', cobrar['logras'])

    def test_la_declaracion_de_renta_lleva_pasos_con_pantallas(self):
        renta = next(t for t in self.tareas if t['id'] == 'renta')
        self.assertGreaterEqual(len(renta['pasos']), 5)
        self.assertGreaterEqual(sum(1 for p in renta['pasos'] if p['destino']), 5)
        self.assertIn('no presenta la declaración', renta['nota'])


@tagged('post_install', '-at_install')
class TestPantalla(BaseCase):
    """La pantalla (JS y plantillas) existe y es coherente con el catálogo."""

    def test_la_plantilla_y_la_accion_cliente_estan_registradas(self):
        with open(file_path('dcasa_guia/static/src/xml/guia.xml'), encoding='utf-8') as archivo:
            raiz = ElementTree.fromstring(archivo.read())
        nombres = {t.get('t-name') for t in raiz.iter('t')}
        self.assertTrue({'dcasa_guia.Guia', 'dcasa_guia.Tarea'} <= nombres, nombres)
        with open(file_path('dcasa_guia/static/src/js/guia.js'), encoding='utf-8') as archivo:
            js = archivo.read()
        self.assertIn('registry.category("actions").add("dcasa_guia", DcasaGuia)', js)
        self.assertIn('static template = "dcasa_guia.Guia"', js)
        self.assertIn('"dcasa.guia", "obtener"', js)
        self.assertIn('"dcasa.guia", "buscar"', js)

    def test_la_pantalla_tiene_las_preguntas_y_botones_clave(self):
        with open(file_path('dcasa_guia/static/src/xml/guia.xml'), encoding='utf-8') as archivo:
            xml = archivo.read()
        # «Ir ahora» pasó a ser «Llévame ahí»; test_llevame.py vigila el botón nuevo.
        for texto in ('¿Qué necesitas hacer hoy?', 'Qué vas a lograr', 'Preguntarle a Brian', 'Llévame ahí',
                      'Escoge un tema', 'Lo que más se necesita', 'Todos los temas', 'Dónde queda'):
            with self.subTest(texto):
                self.assertIn(texto, xml)

    def test_el_inicio_ofrece_la_guia_solo_si_esta_instalada(self):
        with open(file_path('dcasa_interfaz/static/src/xml/inicio.xml'), encoding='utf-8') as archivo:
            self.assertIn('t-if="d.guia"', archivo.read())


@tagged('post_install', '-at_install')
class TestServidor(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupos):
            ids = [cls.env.ref(g).id for g in ('base.group_user', *grupos)]
            return Usuarios.create({'name': login.title(), 'login': login, 'group_ids': [(6, 0, ids)]})

        cls.gerencia = usuario('guia_gerencia', ('dcasa_base.group_gerencia', 'account.group_account_manager'))
        cls.vendedora = usuario('guia_vendedora', ('sales_team.group_sale_salesman',))
        cls.interno = usuario('guia_interno', ())

    def obtener(self, usuario=None):
        return self.env['dcasa.guia'].with_user(usuario or self.env.user).obtener()

    def ids_de(self, usuario):
        return {t['id'] for c in self.obtener(usuario)['categorias'] for t in c['tareas']}

    def test_cada_atajo_del_catalogo_existe(self):
        """Si un módulo instalado cambia o quita un menú, esta prueba lo dice (la Guía no manda a ningún lado roto)."""
        instalados = set(self.env['ir.module.module'].sudo().search([('state', '=', 'installed')]).mapped('name'))
        for tarea in G.cargar_catalogo()['tareas']:
            for destino in destinos_de(tarea):
                menu = destino.get('menu')
                if not menu or menu.split('.')[0] not in instalados:
                    continue
                with self.subTest(f"{tarea['id']} → {menu}"):
                    registro = self.env.ref(menu, raise_if_not_found=False)
                    self.assertTrue(registro and registro._name == 'ir.ui.menu', f'No existe el menú {menu}')
                    self.assertTrue(registro.action, f'El menú {menu} no abre ninguna pantalla')

    def test_los_filtros_del_atajo_existen_en_la_vista_de_busqueda(self):
        for tarea in G.cargar_catalogo()['tareas']:
            for destino in destinos_de(tarea):
                filtros = [k for k in destino.get('contexto', {}) if k.startswith('search_default_')]
                if not filtros or not destino.get('menu'):
                    continue
                accion = self.env.ref(destino['menu']).action
                vista = self.env[accion.res_model].get_views([(accion.search_view_id.id or False, 'search')])
                arch = vista['views']['search']['arch']
                for clave in filtros:
                    with self.subTest(f"{tarea['id']} → {clave}"):
                        self.assertIn(f'name="{clave.removeprefix("search_default_")}"', arch)

    def test_gerencia_ve_las_categorias_con_sus_tareas(self):
        datos = self.obtener(self.gerencia)
        claves = [c['clave'] for c in datos['categorias']]
        for esperada in ('vender', 'facturar', 'reportes', 'impuestos', 'personal', 'productos'):
            self.assertIn(esperada, claves)
        self.assertEqual(datos['total'], len({t['id'] for c in datos['categorias'] for t in c['tareas']}))
        self.assertTrue(datos['empezar'])
        for categoria in datos['categorias']:
            self.assertTrue(categoria['tareas'], 'Una categoría vacía no sale')
            for tarea in categoria['tareas']:
                self.assertTrue(tarea['titulo'] and tarea['logras'])

    def test_cada_quien_ve_solo_lo_que_puede_abrir(self):
        gerencia, vendedora, interno = (self.ids_de(u) for u in (self.gerencia, self.vendedora, self.interno))
        self.assertIn('renta', gerencia)
        self.assertIn('cierre-mes', gerencia)
        self.assertIn('cotizacion-nueva', vendedora)
        for solo_contabilidad in ('renta', 'ganancias', 'balance', 'banco-conciliar', 'cierre-mes'):
            self.assertNotIn(solo_contabilidad, vendedora, 'Una vendedora no ve contabilidad')
            self.assertNotIn(solo_contabilidad, interno)
        self.assertNotIn('colaborador-nuevo', vendedora, 'Nómina es de quien la administra')
        self.assertLess(len(interno), len(vendedora))
        self.assertLess(len(vendedora), len(gerencia))

    def test_comparar_las_ventas_es_solo_de_gerencia(self):
        """La pantalla (el Inicio) la abren todos, pero el bloque «Comparar» es de Gerencia: la tarea trae
        ``grupos``."""
        self.assertIn('comparar-ventas', self.ids_de(self.gerencia))
        for usuario in (self.vendedora, self.interno):
            with self.subTest(usuario.login):
                self.assertNotIn('comparar-ventas', self.ids_de(usuario))
                self.assertNotIn('comparar-ventas', self.buscar('comparar ventas', usuario))
        self.assertEqual(self.buscar('cómo vamos contra el mes pasado')[0], 'comparar-ventas')
        self.assertFalse(self.env['dcasa.guia'].with_user(self.vendedora).registrar_uso('comparar-ventas'))
        # Un grupo que no existe en esta instalación no abre la tarea a nadie más.
        Guia = self.env['dcasa.guia'].with_user(self.vendedora)
        self.assertFalse(Guia._tiene_algun_grupo(['modulo_que_no_esta.grupo']))
        self.assertTrue(Guia._tiene_algun_grupo([]))

    def test_las_tareas_traen_destino_ruta_y_pasos_resueltos(self):
        tareas = {t['id']: t for c in self.obtener(self.gerencia)['categorias'] for t in c['tareas']}
        itbms = tareas['itbms']
        self.assertEqual(itbms['destino']['tipo'], 'menu')
        self.assertTrue(itbms['destino']['menu_id'])
        self.assertEqual(itbms['destino']['ruta'].split(' › ')[-1], 'Resumen de ITBMS')
        renta = tareas['renta']
        self.assertGreaterEqual(len(renta['pasos']), 5)
        self.assertTrue(all(p['destino']['menu_id'] for p in renta['pasos'] if p['destino']))
        self.assertIsNone(renta['pasos'][-1]['destino'], 'El último paso es entregarle los reportes al contador')
        nueva = tareas['cotizacion-nueva']
        self.assertEqual((nueva['destino']['tipo'], nueva['destino']['modelo']), ('nuevo', 'sale.order'))
        borrador = tareas['factura-borrador']
        self.assertEqual(borrador['destino']['contexto'], {'search_default_draft': 1})

    def test_una_tarea_aparece_tambien_en_su_otra_categoria(self):
        por_categoria = {c['clave']: {t['id'] for t in c['tareas']} for c in self.obtener(self.gerencia)['categorias']}
        self.assertIn('cierre-mes', por_categoria['reportes'])
        self.assertIn('cierre-mes', por_categoria['impuestos'])
        self.assertIn('planilla', por_categoria['personal'])
        self.assertIn('seguro-social', por_categoria['impuestos'])
        self.assertIn('seguro-social', por_categoria['personal'])

    def test_tareas_sin_pantalla_salen_para_todos(self):
        for usuario in (self.gerencia, self.vendedora, self.interno):
            with self.subTest(usuario.login):
                ids = self.ids_de(usuario)
                self.assertIn('otras-obligaciones', ids)
                self.assertIn('precios-en-bloque', ids)

    # --- Buscar ---------------------------------------------------------------------

    def buscar(self, consulta, usuario=None, **kwargs):
        return [t['id'] for t in self.env['dcasa.guia'].with_user(usuario or self.gerencia).buscar(consulta, **kwargs)]

    def test_buscar_la_declaracion_de_renta_con_o_sin_tilde(self):
        self.assertEqual(self.buscar('declaración de renta')[0], 'renta')
        self.assertEqual(self.buscar('declaracion de renta')[0], 'renta')
        self.assertEqual(self.buscar('¿Cómo hago la declaración de RENTA?')[0], 'renta')
        self.assertIn('renta', self.buscar('ISR')[:2])

    def test_buscar_con_palabras_de_la_gente(self):
        casos = {
            'cobrar a un cliente': 'cobrar-cliente',
            'cerrar el mes': 'cierre-mes',
            'ITBMS': 'itbms',
            'quien me debe': 'facturas-vencidas',
            'planilla': 'planilla',
            'conciliar el banco': 'banco-conciliar',
            'crear un producto': 'producto-nuevo',
            'cotizacion': 'cotizacion-nueva',
            'borrador': 'factura-borrador',
        }
        for consulta, esperada in casos.items():
            with self.subTest(consulta):
                self.assertIn(esperada, self.buscar(consulta)[:3], self.buscar(consulta))

    def test_buscar_abono_lleva_a_registrar_un_abono(self):
        for consulta in ('abono', 'registrar un abono', 'el cliente pagó una parte'):
            with self.subTest(consulta):
                self.assertIn('registrar-abono', self.buscar(consulta)[:3], self.buscar(consulta))
        self.assertEqual(self.buscar('abono')[0], 'registrar-abono')
        self.assertIn('registrar-abono', self.ids_de(self.gerencia))
        self.assertNotIn('registrar-abono', self.ids_de(self.interno), 'sin permiso de facturas no sale')

    def test_las_palabras_de_la_gente_pesan_mas_que_una_coincidencia_suelta(self):
        """«ISR» es lo que se dice por «impuesto sobre la renta»: la declaración de renta va primero que la nómina."""
        ranking = self.buscar('isr')
        self.assertLess(ranking.index('renta'), ranking.index('seguro-social'))

    def test_buscar_varias_palabras_no_trae_ruido(self):
        """«declaración de renta» no debe traer «rentabilidad» ni lo que solo coincide con una palabra."""
        ids = self.buscar('declaración de renta')
        self.assertEqual(ids[0], 'renta')
        self.assertNotIn('rentabilidad', ids)
        self.assertLessEqual(len(ids), 3)

    def test_buscar_por_trozo_de_palabra(self):
        self.assertIn('facturas-clientes', self.buscar('factur'))

    def test_buscar_nada_o_basura_da_lista_vacia(self):
        self.assertEqual(self.buscar(''), [])
        self.assertEqual(self.buscar('de la el'), [])
        self.assertEqual(self.buscar('zzzzqqqq'), [])

    def test_buscar_respeta_el_limite_y_los_permisos(self):
        self.assertLessEqual(len(self.buscar('factura', limite=3)), 3)
        self.assertNotIn('renta', self.buscar('declaración de renta', usuario=self.vendedora))
        self.assertNotIn('ganancias', self.buscar('ganancia utilidad perdida', usuario=self.vendedora))
