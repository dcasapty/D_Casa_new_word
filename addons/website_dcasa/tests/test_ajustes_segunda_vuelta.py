# ruff: noqa: E501
"""rv_web, segunda vuelta (2026-11-20): ataques al modelo nuevo ``dcasa.portada.ajustes`` (los segundos de cada foto del
hero) y a la lista del carrusel que cuelga de él por ``ajustes_id`` (models/portada.py).

Tras quitarle a Gerencia el ACL sobre ``website``: ¿corre acciones de servidor del sitio?, ¿se puede forjar ``ajustes_id``
para colgar diapositivas del sitio de otro?, ¿crear ajustes de otro sitio?, ¿un sitio sin registro?, ¿puertas para quien
no es Gerencia?, ¿la regeneración del borde?, ¿valores raros por RPC?
"""
from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.service.model import call_kw
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


def _usuario(env, login, *grupos):
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login.replace('_', ' ').title(), 'login': login, 'password': login,
        'group_ids': [Command.set([env.ref('base.group_user').id, *(env.ref(g).id for g in grupos)])],
    })


@tagged('post_install', '-at_install')
class TestRvWeb2Ajustes(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sitio = cls.env.ref('website.default_website')
        cls.otro = cls.env['website'].create({'name': 'Sitio rv_web2'})
        cls.Ajustes = cls.env['dcasa.portada.ajustes']
        cls.Diapositiva = cls.env['dcasa.portada.diapositiva']
        cls.propios = cls.Ajustes._dcasa_del_sitio(cls.sitio, crear=True)
        cls.del_otro = cls.Ajustes._dcasa_del_sitio(cls.otro, crear=True)
        cls.gerente = _usuario(cls.env, 'rvw2_gerente', 'dcasa_base.group_gerencia')
        cls.vendedora = _usuario(cls.env, 'rvw2_vendedora', 'dcasa_base.group_vendedora')
        cls.portal = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Rvw2 Portal', 'login': 'rvw2_portal', 'password': 'rvw2_portal',
            'group_ids': [Command.set([cls.env.ref('base.group_portal').id])]})
        cls.publico = cls.env.ref('base.public_user')
        base = {'type': 'consu', 'sale_ok': True, 'is_published': True, 'list_price': 10.0}
        cls.p1 = cls.env['product.template'].create({**base, 'name': 'ZZRVW2 UNO'})
        cls.p2 = cls.env['product.template'].create({**base, 'name': 'ZZRVW2 DOS'})
        cls.Diapositiva.search([]).unlink()

    # ------------------------------------------------------------------ Gerencia ya no toca el sitio

    def test_gerencia_ya_no_escribe_en_el_sitio_ni_corre_sus_acciones_de_servidor(self):
        sitio = self.sitio.with_user(self.gerente)
        self.assertEqual([sitio.has_access(op) for op in ('read', 'write', 'create', 'unlink')], [True, False, False, False])
        with self.assertRaises(AccessError), self.cr.savepoint():
            sitio.write({'name': 'x'})
        acciones = self.env['ir.actions.server'].sudo().search([('model_id.model', '=', 'website'), ('group_ids', '=', False)])
        self.assertTrue(acciones)
        contexto = {'active_model': 'website', 'active_id': self.sitio.id, 'active_ids': self.sitio.ids}
        for accion in acciones:
            with self.subTest(accion=accion.name), self.assertRaises(AccessError), self.cr.savepoint():
                accion.with_user(self.gerente).with_context(**contexto).run()
        # Ni siquiera con el contexto de la acción propia: la acción del menú es de los ajustes, no del sitio.
        propia = self.env.ref('website_dcasa.action_dcasa_portada_carrusel')
        self.assertEqual(propia.model_id.model, 'dcasa.portada.ajustes')
        # Ninguna otra acción de servidor sin grupo, de ningún modelo, quedó abierta a Gerencia por el modelo nuevo.
        sin_grupo = self.env['ir.actions.server'].sudo().search([
            ('model_id.model', '=', 'dcasa.portada.ajustes'), ('group_ids', '=', False)])
        self.assertFalse(sin_grupo, 'una acción de servidor sin grupo sobre los ajustes la correría quien pueda escribirlos')

    def test_el_modelo_nuevo_no_abre_otra_puerta_de_acl(self):
        """Los únicos ACL de los ajustes y de la lista son los de Gerencia y los administradores (nada para empleados,
        portal ni público) y no hay reglas de registro que cambien eso."""
        for modelo in ('dcasa.portada.ajustes', 'dcasa.portada.diapositiva'):
            accesos = self.env['ir.model.access'].sudo().search([('model_id.model', '=', modelo)])
            grupos = {a.group_id.full_name if a.group_id else 'TODOS' for a in accesos}
            self.assertNotIn('TODOS', grupos, f'{modelo}: un ACL sin grupo abre el modelo a todos')
            for acceso in accesos:
                self.assertTrue(acceso.group_id.id in (self.env.ref('dcasa_base.group_gerencia').id,
                                                        self.env.ref('base.group_system').id),
                                f'{modelo}: ACL de otro grupo: {acceso.name}')
            self.assertFalse(self.env['ir.rule'].sudo().search([('model_id.model', '=', modelo)]),
                             f'{modelo}: regla de registro que no estaba pensada')
        for usuario in (self.vendedora, self.portal, self.publico):
            for modelo in ('dcasa.portada.ajustes', 'dcasa.portada.diapositiva'):
                M = self.env[modelo].with_user(usuario)
                self.assertEqual([M.has_access(op) for op in ('read', 'write', 'create', 'unlink')], [False] * 4,
                                 f'{usuario.login} {modelo}')

    def test_los_metodos_privados_del_modelo_no_se_llaman_por_rpc(self):
        for usuario in (self.gerente, self.vendedora, self.portal):
            for metodo, args in (('_dcasa_del_sitio', [self.sitio.id]), ('_dcasa_normalizar_segundos', [3])):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    call_kw(self.Ajustes.with_user(usuario), metodo, args, {})

    def test_action_abrir_solo_para_gerencia_y_nunca_crea_ajustes_de_otro_sitio(self):
        for usuario in (self.vendedora, self.portal):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.Ajustes.with_user(usuario).action_abrir()
        antes = self.Ajustes.sudo().search_count([])
        accion = self.Ajustes.with_user(self.gerente).action_abrir()
        self.assertEqual(accion['res_id'], self.propios.id)
        self.assertEqual(self.Ajustes.sudo().search_count([]), antes, 'abrir la pantalla no crea ajustes de más')

    # ------------------------------------------------------------------ ajustes_id forjado

    def _crear(self, usuario, **vals):
        return self.Diapositiva.with_user(usuario).create({'product_tmpl_id': self.p1.id, **vals})

    def test_ajustes_id_de_otro_sitio_con_el_sitio_propio_no_cuelga(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._crear(self.gerente, website_id=self.sitio.id, ajustes_id=self.del_otro.id)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._crear(self.gerente, website_id=self.otro.id, ajustes_id=self.propios.id)
        self.assertFalse(self.Diapositiva.sudo().search([]), 'ninguna diapositiva quedó a medias')

    def test_cambiar_ajustes_id_o_el_sitio_deja_la_diapositiva_coherente(self):
        d = self._crear(self.gerente, website_id=self.sitio.id)
        self.assertEqual(d.ajustes_id, self.propios)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            d.with_user(self.gerente).write({'ajustes_id': self.del_otro.id})
        d.with_user(self.gerente).write({'website_id': self.otro.id})
        self.assertEqual(d.ajustes_id, self.del_otro, 'al cambiar de sitio, cuelga de los ajustes del sitio nuevo')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            d.with_user(self.gerente).write({'website_id': self.sitio.id, 'ajustes_id': self.del_otro.id})

    def test_ajustes_id_inexistente_o_basura_da_error_y_no_deja_filas(self):
        antes = self.Diapositiva.sudo().search_count([])
        for basura in (10 ** 9, -1, 'abc', [1], {'a': 1}, 1.5):
            with self.subTest(ajustes_id=repr(basura)), self.assertRaises(Exception) as error, self.cr.savepoint(), \
                    mute_logger('odoo.sql_db', 'odoo.models'):
                self._crear(self.gerente, ajustes_id=basura)
            self.assertNotIsInstance(error.exception, (KeyboardInterrupt, SystemExit))
        self.assertEqual(self.Diapositiva.sudo().search_count([]), antes)

    def test_quien_no_es_gerencia_no_sabe_si_un_ajuste_existe(self):
        """El ``create`` de la diapositiva lee el sitio de los ajustes con sudo ANTES de que el ACL pare a quien no debe:
        con un ``ajustes_id`` que no existe, un portal recibe un error distinto al de uno que sí existe."""
        resultados = {}
        for nombre, valor in (('existe', self.propios.id), ('no_existe', 10 ** 9)):
            with self.assertRaises(Exception) as error, self.cr.savepoint(), mute_logger('odoo.sql_db', 'odoo.models'):
                self._crear(self.portal, ajustes_id=valor)
            resultados[nombre] = type(error.exception).__name__
        self.assertEqual(resultados['existe'], 'AccessError')
        self.assertEqual(resultados['no_existe'], 'AccessError', f'distingue si el id existe: {resultados}')

    def test_gerencia_puede_cambiar_el_sitio_de_unos_ajustes_sin_dejar_diapositivas_sueltas(self):
        """Mover los ajustes de un sitio a otro (``website_id``) no puede dejar diapositivas de un sitio colgando de los
        ajustes de otro."""
        sitio_c = self.env['website'].create({'name': 'Sitio rv_web2 C'})
        propios_c = self.Ajustes._dcasa_del_sitio(sitio_c, crear=True)
        d = self.Diapositiva.create({'website_id': sitio_c.id, 'product_tmpl_id': self.p2.id})
        self.assertEqual(d.ajustes_id, propios_c)
        sitio_d = self.env['website'].create({'name': 'Sitio rv_web2 D'})
        try:
            with self.cr.savepoint():
                propios_c.with_user(self.gerente).write({'website_id': sitio_d.id})
        except Exception as error:  # noqa: BLE001
            self.assertIsInstance(error, (ValidationError, AccessError), type(error))
            return
        d.invalidate_recordset()
        self.assertEqual(d.ajustes_id.website_id, d.website_id,
                         'la diapositiva del sitio C quedó colgando de ajustes de otro sitio')

    # ------------------------------------------------------------------ crear ajustes de otro sitio, sin registro

    def test_un_juego_de_ajustes_por_sitio_y_gerencia_no_los_borra(self):
        with self.assertRaises(IntegrityError), self.cr.savepoint(), mute_logger('odoo.sql_db'):
            self.Ajustes.with_user(self.gerente).create({'website_id': self.sitio.id})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.propios.with_user(self.gerente).unlink()
        # Gerencia sí puede crear los de un sitio nuevo (solo guarda sus segundos): nada más cambia en ese sitio.
        nuevo = self.env['website'].create({'name': 'Sitio rv_web2 nuevo'})
        creados = self.Ajustes.with_user(self.gerente).create({'website_id': nuevo.id, 'segundos': 5})
        self.assertEqual(nuevo._dcasa_hero_tiempo(), '5s')
        self.assertEqual(creados.website_id, nuevo)

    def test_un_sitio_sin_registro_trae_los_3_segundos_y_su_firma_no_falla(self):
        sin = self.env['website'].create({'name': 'Sitio rv_web2 sin ajustes'})
        self.assertEqual(sin._dcasa_hero_tiempo(), '3s')
        self.assertEqual(sin._dcasa_hero_firma(), ((), 3.0))
        self.assertFalse(self.Ajustes.sudo().search([('website_id', '=', sin.id)]), 'leer no crea registros')

    def test_borrar_los_ajustes_los_administradores_vuelve_a_los_3_segundos(self):
        self.del_otro.sudo().segundos = 8
        self.assertEqual(self.otro._dcasa_hero_tiempo(), '8s')
        self.del_otro.with_user(self.env.ref('base.user_admin')).unlink()
        self.assertEqual(self.otro._dcasa_hero_tiempo(), '3s')

    # ------------------------------------------------------------------ la regeneración del borde

    def _marcas(self):
        self.env.flush_all()
        self.env.cr.flush()
        return self.env['dcasa.tienda.pendiente'].sudo().search([]).mapped('producto_id')

    def test_cada_cambio_de_ajustes_o_de_la_lista_marca_regenerar_todo(self):
        Pendiente = self.env['dcasa.tienda.pendiente'].sudo()

        def limpio():
            self._marcas()
            Pendiente.search([]).unlink()

        limpio()
        self.propios.with_user(self.gerente).write({'segundos': 6})
        self.assertIn(0, self._marcas(), 'cambiar los segundos')
        limpio()
        self.propios.with_user(self.gerente).write({'segundos': 6})
        self.assertIn(0, self._marcas(), 'escribir el mismo valor también marca (el borde se entera igual)')
        limpio()
        d = self._crear(self.gerente, website_id=self.sitio.id)
        self.assertIn(0, self._marcas(), 'agregar un producto')
        limpio()
        d.with_user(self.gerente).write({'sequence': 99})
        self.assertIn(0, self._marcas(), 'reordenar')
        limpio()
        d.with_user(self.gerente).unlink()
        self.assertIn(0, self._marcas(), 'quitar un producto')
        limpio()
        creados = self.Ajustes.with_user(self.gerente).create({'website_id': self.env['website'].create({'name': 'S'}).id})
        self.assertIn(0, self._marcas(), 'crear ajustes')
        limpio()
        creados.sudo().unlink()
        self.assertIn(0, self._marcas(), 'quitar ajustes')
        limpio()
        # Lo que el visitante no ve no marca nada: leer, abrir la pantalla, normalizar.
        self.Ajustes.with_user(self.gerente).action_abrir()
        self.propios.with_user(self.gerente).read(['segundos'])
        self.assertEqual(self._marcas(), [], 'abrir la pantalla no regenera nada')

    def test_la_regeneracion_masiva_repetida_queda_en_una_marca_por_lote(self):
        """Quien guarda 50 veces seguidas deja marcas de «todo» (una por guardado), pero el aviso al Worker sale una sola
        vez por lote: lo que cuesta es el aviso, no las marcas."""
        Pendiente = self.env['dcasa.tienda.pendiente'].sudo()
        self._marcas()
        Pendiente.search([]).unlink()
        for i in range(50):
            self.propios.with_user(self.gerente).write({'segundos': 3 + (i % 2)})
        self.assertEqual(self._marcas().count(0), 1, 'dentro de una misma transacción, una sola marca de «todo»')

    # ------------------------------------------------------------------ valores raros por RPC

    def test_valores_raros_por_rpc_son_siempre_un_error_claro_o_un_numero_en_rango(self):
        valores = [0, 1, 1.9, 1.94, 1.95, 1.99, 2, 2.04, 2.05, 15, 15.01, 15.04, 15.05, 15.1, -2, -0.0, 1e9, 1e400,
                   float('nan'), float('inf'), float('-inf'), '2.5', ' 3 ', '3,5', '1e1', 'abc', '', None, False, True,
                   [3], {'a': 1}, (3,), {3}, b'3', '3; background:red', '3s}</style>', '١٠', '٣', '0x10', '1_0']
        sitio_valores = self.env['website'].create({'name': 'Sitio valores'})
        for via in ('write', 'create', 'web_save'):
            for valor in valores:
                with self.subTest(via=via, valor=repr(valor)[:30]):
                    try:
                        with self.cr.savepoint():
                            if via == 'write':
                                self.propios.with_user(self.gerente).write({'segundos': valor})
                                self.propios.flush_recordset()
                            elif via == 'create':
                                creado = self.Ajustes.with_user(self.gerente).create({
                                    'website_id': sitio_valores.id, 'segundos': valor})
                                self.assertTrue(2.0 <= creado.segundos <= 15.0, f'create con {valor!r}: {creado.segundos!r}')
                                creado.sudo().unlink()   # un solo juego por sitio: se quita para la siguiente vuelta
                            else:
                                self.propios.with_user(self.gerente).web_save({'segundos': valor}, {'segundos': {}})
                    except ValidationError:
                        continue
                    except Exception as error:  # noqa: BLE001
                        self.fail(f'{via} con {valor!r}: {type(error).__name__}: {str(error)[:120]}')
                    if via == 'create':
                        continue
                    self.propios.invalidate_recordset()
                    self.assertTrue(2.0 <= self.propios.segundos <= 15.0, f'{via} con {valor!r} dejó {self.propios.segundos!r}')
                    self.assertRegex(self.sitio._dcasa_hero_tiempo(), r'^\d{1,2}(\.\d)?s$')

    def test_la_plantilla_solo_escribe_un_numero_aunque_la_base_tenga_basura(self):
        for sql in ("'NaN'::numeric", "'Infinity'::float8", "'-Infinity'::float8", '0', '1.99', '15.01', '1e300::float8',
                    '-5', '2'):
            try:
                with self.cr.savepoint():
                    self.cr.execute(f'UPDATE dcasa_portada_ajustes SET segundos = {sql} WHERE id = %s', (self.propios.id,))
            except Exception:  # noqa: BLE001 — la columna no admite ese valor
                continue
            self.propios.invalidate_recordset()
            with self.subTest(sql=sql):
                self.assertRegex(self.sitio._dcasa_hero_tiempo(), r'^\d{1,2}(\.\d)?s$')
