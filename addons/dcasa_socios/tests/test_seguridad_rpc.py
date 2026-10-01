"""S-01 y S-02: los botones del programa se comprueban en el servidor, no en la vista.

Se llama por ``odoo.service.model.call_kw``, la misma puerta que ``/web/dataset/call_kw``.
"""
from odoo.exceptions import AccessError
from odoo.service.model import call_kw
from odoo.tests import new_test_user, tagged

from .common import SociosCommon


@tagged('post_install', '-at_install')
class TestSeguridadRpcSocios(SociosCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.interno = new_test_user(cls.env, login='rpc_bodega', groups='base.group_user', name='Bodega')
        cls.vendedora = new_test_user(cls.env, login='rpc_vendedora', name='Vendedora',
                                      groups='base.group_user,sales_team.group_sale_salesman')
        cls.gerente = new_test_user(cls.env, login='rpc_gerente', name='Gerente Socios',
                                    groups='base.group_user,sales_team.group_sale_manager')
        cls.portal = new_test_user(cls.env, login='rpc_portal', groups='base.group_portal', name='Portal')

    def setUp(self):
        super().setUp()
        self.padrino._dcasa_guardar_pin('482915')

    def rpc(self, usuario, modelo, metodo, ids, *args):
        return call_kw(self.env(user=usuario)[modelo], metodo, [ids, *args], {})

    # ------------------------------------------------------------------
    # S-01: ficha del socio
    # ------------------------------------------------------------------

    def test_vendedora_no_toca_pin_ni_candado(self):
        for metodo in ('action_dcasa_reiniciar_pin', 'action_dcasa_desbloquear', 'action_dcasa_suspender',
                       'action_dcasa_activar', 'action_dcasa_ajustar'):
            for usuario in (self.interno, self.vendedora):
                with self.subTest(metodo=metodo, usuario=usuario.login), self.assertRaises(AccessError):
                    self.rpc(usuario, 'res.partner', metodo, self.padrino.ids)
        self.assertFalse(self.padrino.dcasa_pin_temporal)
        self.assertEqual(self.padrino.dcasa_socio_estado, 'activo')

    def test_crear_ficha_solo_ventas(self):
        with self.assertRaises(AccessError):
            self.rpc(self.interno, 'res.partner', 'action_dcasa_crear_ficha', self.cliente.ids)
        self.assertFalse(self.cliente.dcasa_socio_codigo)
        self.assertTrue(self.rpc(self.vendedora, 'res.partner', 'action_dcasa_crear_ficha', self.cliente.ids))
        self.assertTrue(self.cliente.dcasa_socio_codigo)

    def test_gerente_reinicia_pin_y_queda_rastro(self):
        accion = self.rpc(self.gerente, 'res.partner', 'action_dcasa_reiniciar_pin', self.padrino.ids)
        temporal = accion['params']['title'].split(': ')[1]
        self.assertTrue(self.padrino.dcasa_pin_temporal)
        self.assertTrue(self.padrino._dcasa_pin_correcto(temporal))
        nota = self.padrino.message_ids[:1]
        self.assertIn('PIN reiniciado por Gerente Socios', nota.body)
        self.assertNotIn(temporal, nota.body, 'El PIN nunca va al chatter')
        self.assertEqual(nota.author_id, self.gerente.partner_id)

    def test_gerente_desbloquea_y_queda_rastro(self):
        for _i in range(5):
            self.padrino._dcasa_registrar_fallo()
        self.assertTrue(self.padrino._dcasa_bloqueada())
        self.assertTrue(self.rpc(self.gerente, 'res.partner', 'action_dcasa_desbloquear', self.padrino.ids))
        self.assertFalse(self.padrino._dcasa_bloqueada())
        self.assertEqual(self.padrino.dcasa_intentos_fallidos, 0)
        self.assertIn('desbloqueada por Gerente Socios', self.padrino.message_ids[:1].body)

    def test_gerente_suspende_y_reactiva(self):
        self.rpc(self.gerente, 'res.partner', 'action_dcasa_suspender', self.padrino.ids)
        self.assertEqual(self.padrino.dcasa_socio_estado, 'suspendido')
        self.rpc(self.gerente, 'res.partner', 'action_dcasa_activar', self.padrino.ids)
        self.assertEqual(self.padrino.dcasa_socio_estado, 'activo')

    def test_desbloqueo_del_login_es_privado(self):
        with self.assertRaises(AccessError):
            self.rpc(self.gerente, 'res.partner', '_dcasa_desbloquear', self.padrino.ids)

    # ------------------------------------------------------------------
    # S-02: canjes
    # ------------------------------------------------------------------

    def canje(self):
        self.env['dcasa.movimiento']._asentar(self.padrino, 'ajuste', 1500, 'test', motivo='Saldo de prueba')
        return self.env['dcasa.canje']._pedir(self.padrino, self.env.ref('dcasa_socios.premio_desc_10'))

    def test_portal_e_interno_no_tocan_canjes(self):
        canje = self.canje()
        for usuario in (self.portal, self.interno):
            for metodo in ('action_entregar', 'action_cancelar'):
                with self.subTest(usuario=usuario.login, metodo=metodo), self.assertRaises(AccessError):
                    self.rpc(usuario, 'dcasa.canje', metodo, canje.ids)
        self.assertEqual(canje.estado, 'solicitado')
        self.assertEqual(self.padrino.dcasa_saldo, 500)

    def test_vendedora_entrega_y_cancela(self):
        canje = self.canje()
        self.assertTrue(self.rpc(self.vendedora, 'dcasa.canje', 'action_entregar', canje.ids))
        self.assertEqual(canje.estado, 'entregado')
        self.assertEqual(canje.entregado_por, 'rpc_vendedora')
        otro = self.env['dcasa.canje']._pedir(self.padrino, self.env.ref('dcasa_socios.premio_desc_5'))
        self.assertTrue(self.rpc(self.vendedora, 'dcasa.canje', 'action_cancelar', otro.ids))
        self.assertEqual(otro.estado, 'cancelado')
