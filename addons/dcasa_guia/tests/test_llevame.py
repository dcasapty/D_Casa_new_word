"""«Llévame ahí» y lo más usado según el puesto: listas curadas válidas, cada quien ve solo lo que puede abrir, el uso
es de cada persona (nadie ve ni escribe el de otra), el registro nunca falla y la pantalla trae los botones."""
import re
from unittest import mock

from psycopg2 import IntegrityError

from odoo import Command
from odoo.addons.dcasa_guia.models import guia as G
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import BaseCase, TransactionCase, tagged
from odoo.tools import mute_logger
from odoo.tools.misc import file_path

from .test_guia import destinos_de

# Lo que solo ven Gerencia y Contabilidad (una vendedora no).
SOLO_CONTROL = {'resumen', 'itbms', 'cierre-mes', 'banco-conciliar', 'ganancias', 'facturas-vencidas', 'por-pagar',
                'entregar-contador', 'factura-proveedor'}


def leer(ruta):
    with open(file_path(ruta), encoding='utf-8') as archivo:
        return archivo.read()


@tagged('post_install', '-at_install')
class TestListasPorPuesto(BaseCase):
    """El archivo ``data/guia_roles.json`` por sí solo."""

    def setUp(self):
        super().setUp()
        self.roles = G.cargar_roles()
        self.ids = {t['id'] for t in G.cargar_catalogo()['tareas']}

    def listas(self):
        return [*self.roles['roles'], self.roles['porDefecto']]

    def test_cada_puesto_tiene_de_6_a_8_tareas_que_existen_y_sin_repetir(self):
        for rol in self.listas():
            with self.subTest(rol['clave']):
                self.assertTrue(6 <= len(rol['tareas']) <= 8, f"{rol['clave']}: {len(rol['tareas'])} tareas")
                self.assertEqual(len(rol['tareas']), len(set(rol['tareas'])), 'tareas repetidas')
                self.assertFalse(set(rol['tareas']) - self.ids, set(rol['tareas']) - self.ids)

    def test_los_puestos_tienen_clave_unica_y_grupos_con_forma_de_xmlid(self):
        claves = [r['clave'] for r in self.listas()]
        self.assertEqual(len(claves), len(set(claves)))
        self.assertEqual(claves[0], 'gerencia', 'Gerencia va primero: quien tiene varios puestos cuenta como Gerencia')
        for rol in self.roles['roles']:
            self.assertTrue(rol['titulo'].strip() and rol['grupos'])
            for grupo in rol['grupos']:
                self.assertRegex(grupo, r'^[a-z0-9_]+\.[a-zA-Z0-9_]+$')

    def test_la_vendedora_trae_lo_que_pidio_la_duena(self):
        vendedora = next(r for r in self.roles['roles'] if r['clave'] == 'vendedora')
        # cotizar · facturar · cobrar · ver mis ventas · buscar producto por código · conversaciones · cliente nuevo
        self.assertEqual(vendedora['tareas'], ['cotizacion-nueva', 'por-facturar', 'cobrar-cliente', 'ventas-hoy',
                                               'codigo-publico', 'conversaciones', 'cliente-nuevo'])
        self.assertFalse(SOLO_CONTROL & set(vendedora['tareas']), 'La lista de la vendedora no lleva lo de Gerencia')

    def test_gerencia_y_contabilidad_traen_resumen_cobros_impuestos_cierre_y_banco(self):
        for clave in ('gerencia', 'contabilidad'):
            tareas = next(r for r in self.roles['roles'] if r['clave'] == clave)['tareas']
            with self.subTest(clave):
                for esperada in ('resumen', 'facturas-vencidas', 'itbms', 'cierre-mes', 'banco-conciliar'):
                    self.assertIn(esperada, tareas)

    def test_los_numeros_de_lo_que_tu_mas_usas_son_razonables(self):
        reglas = self.roles['masUsadas']
        self.assertGreaterEqual(reglas['minimoTareas'], 1)
        self.assertGreaterEqual(reglas['minimoVeces'], 2, 'Con una sola vez no hay costumbre')
        self.assertGreaterEqual(reglas['maximo'], reglas['minimoTareas'])
        self.assertLessEqual(reglas['maximo'], 8)


@tagged('post_install', '-at_install')
class TestPuestoYUso(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Usuarios = cls.env['res.users'].with_context(no_reset_password=True)

        def usuario(login, grupos):
            ids = [cls.env.ref(g).id for g in ('base.group_user', *grupos)]
            return Usuarios.create({'name': login.title(), 'login': login, 'group_ids': [Command.set(ids)]})

        cls.gerencia = usuario('llevame_gerencia', ('dcasa_base.group_gerencia',))
        cls.contable = usuario('llevame_contable', ('account.group_account_user',))
        cls.vendedora = usuario('llevame_vendedora', ('dcasa_base.group_vendedora',))
        cls.otra = usuario('llevame_otra', ('dcasa_base.group_vendedora',))
        cls.interno = usuario('llevame_interno', ())
        cls.sistema = usuario('llevame_sistema', ('base.group_system',))
        cls.Uso = cls.env['dcasa.guia.uso']

    def guia(self, usuario):
        return self.env['dcasa.guia'].with_user(usuario)

    def visibles(self, usuario):
        return [t['id'] for c in self.guia(usuario).obtener()['categorias'] for t in c['tareas']]

    def usar(self, usuario, tarea, veces=1):
        return [self.guia(usuario).registrar_uso(tarea) for _ in range(veces)]

    def filas(self, usuario):
        return {f.tarea: f.veces for f in self.Uso.sudo().search([('user_id', '=', usuario.id)])}

    def hay_contabilidad(self):
        return bool(self.env.ref('dcasa_contabilidad.menu_estado_resultados', raise_if_not_found=False))

    # --- El puesto ----------------------------------------------------------------------

    def test_cada_quien_tiene_su_puesto(self):
        esperado = {self.gerencia: 'gerencia', self.sistema: 'gerencia', self.contable: 'contabilidad',
                    self.vendedora: 'vendedora', self.interno: 'equipo'}
        for usuario, clave in esperado.items():
            with self.subTest(usuario.login):
                self.assertEqual(self.guia(usuario).obtener()['rol']['clave'], clave)

    def test_gerencia_gana_aunque_la_persona_tambien_sea_vendedora(self):
        """Gerencia incluye a Vendedora y a Contabilidad: la lista que le toca es la de Gerencia."""
        self.assertEqual(self.guia(self.gerencia).obtener()['rol']['titulo'], 'Gerencia')

    def test_el_puesto_es_la_lista_curada_filtrada_por_lo_que_puede_abrir(self):
        roles = G.cargar_roles()
        listas = {r['clave']: r['tareas'] for r in roles['roles']}
        listas[roles['porDefecto']['clave']] = roles['porDefecto']['tareas']
        for usuario in (self.gerencia, self.contable, self.vendedora, self.interno, self.sistema):
            datos = self.guia(usuario).obtener()
            visibles = set(self.visibles(usuario))
            with self.subTest(usuario.login):
                esperado = [i for i in listas[datos['rol']['clave']] if i in visibles]
                self.assertEqual([t['id'] for t in datos['puesto']], esperado)

    def test_una_vendedora_no_ve_en_su_puesto_nada_de_gerencia(self):
        datos = self.guia(self.vendedora).obtener()
        ids = {t['id'] for t in datos['puesto']}
        self.assertFalse(ids & SOLO_CONTROL, ids & SOLO_CONTROL)
        self.assertIn('cotizacion-nueva', ids)
        self.assertLessEqual(ids, set(self.visibles(self.vendedora)))

    def test_gerencia_y_contabilidad_ven_lo_de_control_si_el_modulo_esta_instalado(self):
        if not self.hay_contabilidad():
            self.skipTest('dcasa_contabilidad no está instalado')
        for usuario in (self.gerencia, self.contable):
            ids = {t['id'] for t in self.guia(usuario).obtener()['puesto']}
            with self.subTest(usuario.login):
                self.assertTrue({'resumen', 'itbms', 'cierre-mes'} <= ids, ids)

    def test_un_interno_sin_puesto_solo_ve_lo_que_puede_abrir(self):
        datos = self.guia(self.interno).obtener()
        ids = {t['id'] for t in datos['puesto']}
        self.assertFalse(ids & SOLO_CONTROL)
        self.assertLessEqual(ids, set(self.visibles(self.interno)))

    def test_obtener_trae_puesto_y_mas_usadas_con_los_destinos_resueltos(self):
        datos = self.guia(self.vendedora).obtener()
        self.assertEqual(set(datos['rol']), {'clave', 'titulo'})
        self.assertEqual(datos['mas_usadas'], [], 'Sin uso todavía solo sale lo curado')
        for tarea in datos['puesto']:
            self.assertTrue(tarea['titulo'] and tarea['logras'])
            if tarea['destino']:
                self.assertIn(tarea['destino']['tipo'], ('menu', 'nuevo'))

    # --- Registrar el uso ---------------------------------------------------------------

    def test_registrar_uso_suma_uno_por_persona_y_tarea(self):
        self.assertEqual(self.usar(self.vendedora, 'cotizacion-nueva', 3), [True, True, True])
        self.assertEqual(self.usar(self.vendedora, 'cliente-nuevo'), [True])
        self.assertEqual(self.usar(self.otra, 'cotizacion-nueva'), [True])
        self.assertEqual(self.filas(self.vendedora), {'cotizacion-nueva': 3, 'cliente-nuevo': 1})
        self.assertEqual(self.filas(self.otra), {'cotizacion-nueva': 1})
        fila = self.Uso.sudo().search([('user_id', '=', self.vendedora.id), ('tarea', '=', 'cotizacion-nueva')])
        self.assertTrue(fila.ultima_vez)

    def test_registrar_uso_tolera_lo_que_no_existe_o_viene_raro(self):
        for raro in (None, '', ' ', 'no-existe', 'RENTA', 123, 1.5, True, [], ['renta'], {}, 'x' * 500, 'a\x00b'):
            with self.subTest(repr(raro)[:30]):
                self.assertIs(self.guia(self.gerencia).registrar_uso(raro), False)
        self.assertFalse(self.filas(self.gerencia), 'No se anotó nada')

    def test_registrar_uso_no_anota_lo_que_la_persona_no_puede_abrir(self):
        if not self.hay_contabilidad():
            self.skipTest('dcasa_contabilidad no está instalado')
        self.assertIn('renta', self.visibles(self.gerencia))
        self.assertNotIn('renta', self.visibles(self.vendedora))
        self.assertEqual(self.usar(self.vendedora, 'renta'), [False])
        self.assertEqual(self.usar(self.interno, 'cierre-mes'), [False])
        self.assertEqual(self.usar(self.gerencia, 'renta'), [True])
        self.assertFalse(self.filas(self.vendedora))
        self.assertEqual(self.filas(self.gerencia), {'renta': 1})

    def test_un_error_al_anotar_nunca_se_nota(self):
        guia = self.guia(self.vendedora)
        with mock.patch.object(type(self.Uso), '_sumar', side_effect=RuntimeError('se cayó')), \
                mute_logger('odoo.addons.dcasa_guia.models.guia'):
            self.assertIs(guia.registrar_uso('cotizacion-nueva'), False)
        self.assertEqual(self.usar(self.vendedora, 'cotizacion-nueva'), [True], 'Después sigue funcionando')

    def test_un_error_de_la_base_al_anotar_tampoco_estorba(self):
        """Un fallo de verdad en SQL (la restricción de «al menos una vez») se queda en el savepoint."""
        original = type(self.Uso)._sumar

        def mal(modelo, tarea):
            modelo.create({'user_id': modelo.env.uid, 'tarea': tarea, 'veces': 0})

        guia = self.guia(self.vendedora)
        with mock.patch.object(type(self.Uso), '_sumar', mal), \
                mute_logger('odoo.addons.dcasa_guia.models.guia', 'odoo.sql_db'):
            self.assertIs(guia.registrar_uso('cotizacion-nueva'), False)
        self.assertFalse(self.filas(self.vendedora))
        with mock.patch.object(type(self.Uso), '_sumar', original):
            self.assertEqual(self.usar(self.vendedora, 'cotizacion-nueva'), [True], 'La transacción sigue sana')

    # --- Cada quien ve y escribe solo lo suyo ----------------------------------------------

    def test_nadie_ve_el_uso_de_otro(self):
        self.usar(self.vendedora, 'cotizacion-nueva', 2)
        self.usar(self.gerencia, 'cliente-nuevo', 5)
        for usuario in (self.vendedora, self.gerencia):
            visibles = self.Uso.with_user(usuario).search([])
            with self.subTest(usuario.login):
                self.assertEqual(visibles.mapped('user_id'), usuario)
        self.assertFalse(self.Uso.with_user(self.otra).search([]), 'Quien no usó nada no ve nada')
        self.assertEqual(self.Uso.with_user(self.sistema).search_count([]), 0, 'Ni un administrador ve el de otros')

    def test_nadie_escribe_el_uso_de_otro(self):
        self.usar(self.gerencia, 'cliente-nuevo', 2)
        ajena = self.Uso.sudo().search([('user_id', '=', self.gerencia.id)])
        with self.assertRaises(AccessError):
            ajena.with_user(self.vendedora).write({'veces': 99})
        with self.assertRaises(AccessError):
            self.Uso.with_user(self.vendedora).create({'user_id': self.gerencia.id, 'tarea': 'clientes-lista'})
        with self.assertRaises(AccessError):
            ajena.with_user(self.vendedora).unlink()
        self.assertEqual(self.filas(self.gerencia), {'cliente-nuevo': 2})

    def test_nadie_borra_su_propio_uso_por_la_pantalla(self):
        self.usar(self.vendedora, 'cliente-nuevo')
        propia = self.Uso.with_user(self.vendedora).search([])
        with self.assertRaises(AccessError):
            propia.unlink()

    def test_la_fila_exige_tarea_valida_una_por_persona_y_al_menos_una_vez(self):
        with self.assertRaises(ValidationError):
            self.Uso.with_user(self.vendedora).create({'user_id': self.vendedora.id, 'tarea': 'no-existe'})
        self.usar(self.vendedora, 'cliente-nuevo')
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.Uso.sudo().create({'user_id': self.vendedora.id, 'tarea': 'cliente-nuevo'})
        with mute_logger('odoo.sql_db'), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.Uso.sudo().create({'user_id': self.vendedora.id, 'tarea': 'clientes-lista', 'veces': 0})

    # --- «Lo que tú más usas» ----------------------------------------------------------------

    def mas_usadas(self, usuario):
        return self.guia(usuario).obtener()['mas_usadas']

    def test_lo_que_tu_mas_usas_sale_solo_con_datos_suficientes(self):
        """Hacen falta 3 tareas con 2 usos o más (``masUsadas`` en guia_roles.json)."""
        propias = [t['id'] for t in self.guia(self.vendedora).obtener()['puesto']]
        self.assertGreaterEqual(len(propias), 4)
        a, b, c, d = propias[:4]
        self.usar(self.vendedora, a, 2)
        self.usar(self.vendedora, b, 3)
        self.assertEqual(self.mas_usadas(self.vendedora), [], 'Con 2 tareas todavía no es costumbre')
        self.usar(self.vendedora, c, 1)
        self.assertEqual(self.mas_usadas(self.vendedora), [], 'Un solo uso no cuenta')
        self.usar(self.vendedora, d, 1)
        self.assertEqual(self.mas_usadas(self.vendedora), [])
        self.usar(self.vendedora, c, 1)
        usadas = self.mas_usadas(self.vendedora)
        self.assertEqual([(t['id'], t['veces']) for t in usadas], [(b, 3), (a, 2), (c, 2)],
                         'Las más usadas primero; a igual uso, la más reciente primero')
        self.assertTrue(all(t['titulo'] and t['logras'] and t['destino'] for t in usadas))

    def test_lo_que_tu_mas_usas_tiene_tope_y_cuenta_solo_lo_real(self):
        maximo = G.cargar_roles()['masUsadas']['maximo']
        propias = [t['id'] for c in self.guia(self.vendedora).obtener()['categorias'] for t in c['tareas']
                   if t['destino']][:maximo + 2]
        self.assertGreaterEqual(len(propias), maximo + 1)
        for i, tarea in enumerate(propias):
            self.usar(self.vendedora, tarea, 2 + (i % 3))
        usadas = self.mas_usadas(self.vendedora)
        self.assertEqual(len(usadas), maximo)
        self.assertEqual([t['veces'] for t in usadas], sorted((t['veces'] for t in usadas), reverse=True))
        # Es lo que hizo, no lo que se supone: los conteos salen de las filas.
        filas = self.filas(self.vendedora)
        self.assertTrue(all(t['veces'] == filas[t['id']] for t in usadas))

    def test_lo_que_tu_mas_usas_no_mezcla_a_las_personas(self):
        for tarea in ('cotizacion-nueva', 'cliente-nuevo', 'clientes-lista'):
            self.usar(self.gerencia, tarea, 4)
        self.assertEqual(len(self.mas_usadas(self.gerencia)), 3)
        self.assertEqual(self.mas_usadas(self.vendedora), [])
        self.assertEqual(self.mas_usadas(self.otra), [])

    def test_lo_que_tu_mas_usas_no_ofrece_lo_que_ya_no_puede_abrir(self):
        """Si la persona perdió el permiso de una pantalla, esa tarea deja de salir (aunque la haya usado)."""
        if not self.hay_contabilidad():
            self.skipTest('dcasa_contabilidad no está instalado')
        for tarea in ('cotizacion-nueva', 'cliente-nuevo'):
            self.usar(self.vendedora, tarea, 2)
        # Historial de un permiso que ya no tiene (se escribe con sudo, como si hubiera tenido el puesto de Gerencia).
        self.Uso.sudo().create({'user_id': self.vendedora.id, 'tarea': 'renta', 'veces': 9})
        self.assertEqual(self.mas_usadas(self.vendedora), [], 'Quedan 2 tareas visibles: no alcanza')
        self.usar(self.vendedora, 'clientes-lista', 2)
        self.assertNotIn('renta', [t['id'] for t in self.mas_usadas(self.vendedora)])
        self.assertEqual(len(self.mas_usadas(self.vendedora)), 3)

    def test_si_no_se_puede_leer_el_uso_la_pantalla_sigue_con_lo_curado(self):
        with mock.patch.object(type(self.Uso), 'search_read', side_effect=ValueError('sin tabla')), \
                mute_logger('odoo.addons.dcasa_guia.models.guia'):
            datos = self.guia(self.vendedora).obtener()
        self.assertEqual(datos['mas_usadas'], [])
        self.assertTrue(datos['puesto'])
        self.assertTrue(datos['categorias'])

    def test_registrar_el_uso_no_cambia_lo_que_se_ofrece(self):
        def buscar():
            return [t['id'] for t in self.guia(self.vendedora).buscar('cotizacion')]

        antes, resultados = self.visibles(self.vendedora), buscar()
        self.assertIn('cotizacion-nueva', resultados)
        self.usar(self.vendedora, 'cotizacion-nueva', 5)
        self.assertEqual(self.visibles(self.vendedora), antes)
        self.assertEqual(buscar(), resultados, 'Usar el botón no mueve el orden de los resultados')


@tagged('post_install', '-at_install')
class TestPantallaLlevame(BaseCase):
    """La pantalla (JS, plantillas y estilos): el botón, los pasos, el uso silencioso y la cinta."""

    def setUp(self):
        super().setUp()
        self.xml = leer('dcasa_guia/static/src/xml/guia.xml')
        self.cinta = leer('dcasa_guia/static/src/xml/guia_cinta.xml')
        self.js = leer('dcasa_guia/static/src/js/guia.js')
        self.ruta = leer('dcasa_guia/static/src/js/guia_ruta.js')
        self.scss = leer('dcasa_guia/static/src/scss/guia.scss') + leer('dcasa_guia/static/src/scss/guia_cinta.scss')

    def test_la_tarjeta_el_detalle_y_cada_paso_tienen_llevame_ahi(self):
        self.assertGreaterEqual(self.xml.count('Llévame ahí'), 3, 'tarjeta, detalle y paso')
        self.assertIn('o_dcasa_guia_llevame_tarea', self.xml)
        self.assertIn('o_dcasa_guia_paso_ir', self.xml)
        self.assertIn('this.llevame(tarea, paso_index)', self.xml)
        self.assertNotIn('Ir ahora', self.xml, 'El botón antiguo se reemplazó por «Llévame ahí»')
        self.assertNotIn('>Abrir<', self.xml)

    def test_el_boton_solo_sale_si_hay_pantalla_a_donde_llevar(self):
        """Lo que la persona no puede abrir llega del servidor sin destino: no se le ofrece botón."""
        self.assertIn('t-if="destinoTarea and !abierta"', self.xml)
        self.assertIn('t-if="paso.destino"', self.xml)
        self.assertIn('t-if="destinoTarea"', self.xml)

    def test_el_boton_se_lee_con_el_nombre_de_la_tarea(self):
        self.assertIn("'Llévame ahí: ' + tarea.titulo", self.xml)
        self.assertIn('aria-expanded', self.xml)

    def test_la_pantalla_muestra_lo_que_tu_mas_usas_y_lo_de_tu_puesto(self):
        for texto in ('Lo que tú más usas', 'En tu puesto lo que más se usa', 'masUsadas', 'delPuesto'):
            with self.subTest(texto):
                self.assertIn(texto, self.xml)
        self.assertLess(self.xml.index('Lo que tú más usas'), self.xml.index('En tu puesto lo que más se usa'))
        self.assertLess(self.xml.index('En tu puesto lo que más se usa'), self.xml.index('Escoge un tema</h2>'))

    def test_el_uso_se_anota_sin_esperar_y_sin_que_un_error_estorbe(self):
        self.assertIn('"dcasa.guia", "registrar_uso"', self.ruta)
        self.assertIn('orm.silent.call', self.ruta)
        self.assertIn('.catch((error) => console.warn("Guía: no se pudo anotar', self.ruta)
        self.assertNotIn('await anotarUso', self.ruta, 'El uso nunca se espera')
        self.assertNotIn('await orm', self.ruta, 'Ninguna llamada de uso se espera')
        # Se anota antes de abrir la pantalla (no depende de que llegue) y una sola vez por clic.
        llevar = self.ruta[self.ruta.index('async function llevar'):]
        self.assertLess(llevar.index('anotarUso(tarea.id)'), llevar.index('await abrir()'))
        self.assertEqual(self.ruta.count('anotarUso(tarea.id)'), 1)

    def test_el_uso_solo_se_anota_si_la_persona_pidio_ir_no_desde_la_cinta(self):
        self.assertIn('{ contar: false }', self.ruta)
        self.assertIn('this.ruta.llevar(this.cinta.tarea, this.actual + 1, { contar: false })', self.ruta)

    def test_la_cinta_es_un_componente_aparte_que_no_se_mete_en_las_pantallas_de_odoo(self):
        self.assertIn('registry.category("main_components").add("dcasa_guia.Cinta"', self.ruta)
        self.assertIn('registry.category("services").add("dcasa_guia_ruta"', self.ruta)
        for prohibido in ('patch(', 'querySelector', 'insertAdjacent', 'innerHTML', 'appendChild'):
            self.assertNotIn(prohibido, self.ruta, 'La cinta no toca el DOM ni los componentes de Odoo')
        self.assertNotIn('xpath', self.cinta)
        # Lo único que escribe fuera de sí misma es la variable de estilo con su propio alto.
        self.assertEqual(set(re.findall(r'document\.(\w+)', self.ruta)), {'documentElement'})
        variables = set(re.findall(r'(?:setProperty|removeProperty)\("(--[\w-]+)"', self.ruta))
        self.assertEqual(variables, {'--dc-cinta-alto'})

    def test_la_cinta_dice_que_haces_el_paso_siguiente_y_deja_volver_o_cerrar(self):
        for texto in ('Estás haciendo:', 'Siguiente:', 'Volver a la Guía', 'Llévame ahí', 'Ya lo hice',
                      'Cerrar este recordatorio', 'role="region"'):
            with self.subTest(texto):
                self.assertIn(texto, self.cinta)
        self.assertIn('ACTION_MANAGER:UI-UPDATED', self.ruta, 'Se va sola al salir de las pantallas de la tarea')

    def test_la_guia_se_abre_con_la_tarea_pedida_al_volver(self):
        self.assertIn('dcasa_guia_tarea', self.js)
        self.assertIn('dcasa_guia_tarea', self.ruta)

    def test_los_estilos_son_planos_y_sin_amarillo(self):
        css = self.scss.lower()
        self.assertNotIn('gradient', css, 'Sistema plano: sin degradados')
        for amarillo in ('#fed00f', 'dc-amarillo', 'yellow'):
            self.assertNotIn(amarillo, css, 'El amarillo nunca toca el blanco')
        self.assertIn('.o_dcasa_guia_cinta', css)

    def test_los_botones_se_dejan_tocar_en_el_celular(self):
        self.assertIn('@media (pointer: coarse) {\n    .o_dcasa_guia_llevame {\n        min-height: 44px;', self.scss)

    def test_los_destinos_del_catalogo_son_los_que_el_boton_sabe_abrir(self):
        """Los dos tipos de destino del catálogo (menú y formulario nuevo) son los que abre el servicio."""
        for tipo in ('"menu"', '"nuevo"'):
            self.assertIn(f'destino.tipo === {tipo}', self.ruta)
        destinos = [d for t in G.cargar_catalogo()['tareas'] for d in destinos_de(t)]
        tipos = {k for d in destinos for k in ('menu', 'nuevo') if d.get(k)}
        self.assertEqual(tipos, {'menu', 'nuevo'})

    def test_el_manifiesto_carga_la_seguridad_el_servicio_la_cinta_y_los_estilos(self):
        manifiesto = leer('dcasa_guia/__manifest__.py')
        for patron in ('static/src/js/*.js', 'static/src/xml/*.xml', 'static/src/scss/*.scss',
                       'security/ir.model.access.csv', 'security/guia_security.xml'):
            self.assertIn(patron, manifiesto)
