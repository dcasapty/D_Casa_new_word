"""Fase 0 de Brian: B-01…B-04 y S-09 cerrados por RPC (PoC de la ronda 3, ahora «BLOQUEADO»).

Se llama por ``odoo.service.model.call_kw``, la misma puerta que ``/web/dataset/call_kw``.
"""
import os
from unittest.mock import patch

from odoo.addons.dcasa_brian.models import proveedores
from odoo.exceptions import AccessError
from odoo.service.model import call_kw
from odoo.tests import new_test_user, tagged

from .common import BrianCase


@tagged('post_install', '-at_install')
class TestSeguridadRpcBrian(BrianCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='rpc_brian_ventas', name='Ventas RPC',
                                      groups='base.group_user,sales_team.group_sale_salesman')
        cls.portal = new_test_user(cls.env, login='rpc_brian_portal', groups='base.group_portal', name='Portal')

    def rpc(self, usuario, modelo, metodo, args=(), kwargs=None):
        return call_kw(self.env(user=usuario)[modelo], metodo, list(args), kwargs or {})

    def assertBloqueado(self, usuario, modelo, metodo, args=(), kwargs=None):
        with self.subTest(modelo=modelo, metodo=metodo, usuario=usuario.login), self.assertRaises(AccessError):
            self.rpc(usuario, modelo, metodo, args, kwargs)

    def test_poc_ronda3_todo_bloqueado(self):
        """Los cinco casos de docs/auditoria/ronda3/brian-habilidades/poc_rpc_brian.py."""
        with patch.dict(os.environ, {'BRIAN_API_KEY': 'sk-SECRETO-DE-PRUEBA'}):
            for usuario in (self.vendedora, self.portal):
                # B-02: la clave de IA.
                self.assertBloqueado(usuario, 'brian.proveedores', '_configuracion')
                # B-04: saltarse la confirmación.
                self.assertBloqueado(usuario, 'brian.herramientas', 'ejecutar', ['prueba_sensible', {'nombre': 'X'}],
                                     {'confirmado': True})
                self.assertBloqueado(usuario, 'brian.herramientas', 'ejecutar', ['prueba_leer', {'texto': 'x'}])
                # S-09: el catálogo del abstracto.
                self.assertBloqueado(usuario, 'brian.herramientas', 'catalogo')
                # B-03: auditoría falsa.
                self.assertBloqueado(usuario, 'brian.accion', 'registrar',
                                     [{'nombre': 'cambiar_rol_usuario', 'nivel': 'sensible'}, {'usuario': 'Admin'}])
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'X')]))
        self.assertFalse(self.env['brian.accion'].search([('herramienta', '=', 'cambiar_rol_usuario')]))

    def test_metodos_internos_privados(self):
        accion = self.herramientas().ejecutar('prueba_sensible', {'nombre': 'Pendiente'})
        llamadas = [
            ('brian.herramientas', 'confirmar', [accion['accion_id']]),
            ('brian.herramientas', 'rechazar', [accion['accion_id']]),
            ('brian.herramientas', 'esquema', [{}]),
            ('brian.herramientas', 'seleccionar', [[], 'hola', 3]),
            ('brian.accion', 'marcar', [[accion['accion_id']], 'hecha']),
            ('brian.proveedores', 'estado', []),
            ('brian.proveedores', 'obtener', []),
            ('brian.proveedores', 'probar', []),
            ('brian.proveedores', 'es_grande', ['gpt-4o']),
            ('brian.telegram.enlace', '_procesar_update', [{'message': {}}]),
            ('brian.telegram.enlace', 'notificar_confirmacion', [self.vendedora.id, 1, 'x']),
            ('brian.telegram.enlace', 'generar_codigo', []),
            ('brian.politica', 'verificar', [{}, {}]),
            ('brian.politica', 'resumir', [{}, {}]),
            ('dcasa.reporte.contable', 'balance_general', []),
        ]
        for modelo, metodo, args in llamadas:
            self.assertBloqueado(self.vendedora, modelo, metodo, args)
        self.assertEqual(self.env['brian.accion'].browse(accion['accion_id']).estado, 'por_confirmar')

    def test_probar_y_borrar_clave_solo_administrador(self):
        with self.assertRaises(AccessError):
            self.env['brian.proveedores'].with_user(self.usuario).probar()
        proveedores.fijar_guion(['listo'])
        self.assertTrue(self.env['brian.proveedores'].with_user(self.jefe).probar()['ok'])
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian.api_key', 'sk-no-se-borra')
        # Sin registro (ids=[]) el método igual corría: ahora pide administrador.
        self.assertBloqueado(self.vendedora, 'res.config.settings', 'action_dcasa_brian_borrar_clave', [[]])
        self.assertBloqueado(self.vendedora, 'res.config.settings', 'action_dcasa_brian_probar', [[]])
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param('dcasa_brian.api_key'), 'sk-no-se-borra')

    def test_estado_del_proveedor_sin_clave_y_sin_portal(self):
        with patch.dict(os.environ, {'BRIAN_API_KEY': 'sk-SECRETO-DE-PRUEBA'}):
            estado = self.rpc(self.vendedora, 'brian.conversacion', 'estado_proveedor')
            self.assertNotIn('sk-SECRETO-DE-PRUEBA', str(estado))
            self.assertBloqueado(self.portal, 'brian.conversacion', 'estado_proveedor')

    def test_historial_ajeno(self):
        ajena = self.rpc(self.jefe, 'brian.conversacion', 'nueva')
        self.assertBloqueado(self.usuario, 'brian.conversacion', 'historial', [ajena['id']])
        self.assertTrue(self.rpc(self.jefe, 'brian.conversacion', 'historial', [ajena['id']])['conversacion'])

    def test_confirmar_accion_propia_por_rpc(self):
        """El único camino público para confirmar: brian.conversacion.confirmar_accion, solo el dueño."""
        proveedores.fijar_guion([{'herramientas': [('prueba_sensible', {'nombre': 'Cliente RPC'})]}])
        conv = self.rpc(self.jefe, 'brian.conversacion', 'nueva')
        tarjeta = self.rpc(self.jefe, 'brian.conversacion', 'enviar', [[conv['id']], 'Crea el cliente'])
        accion_id = tarjeta['mensajes'][-1]['confirmacion']['accion_id']
        # Otro usuario no la confirma ni desde su conversación ni desde la ajena.
        otra = self.rpc(self.usuario, 'brian.conversacion', 'nueva')
        self.assertFalse(self.rpc(self.usuario, 'brian.conversacion', 'confirmar_accion',
                                  [[otra['id']], accion_id])['ok'])
        self.assertBloqueado(self.usuario, 'brian.conversacion', 'confirmar_accion', [[conv['id']], accion_id])
        self.assertFalse(self.env['res.partner'].search([('name', '=', 'Cliente RPC')]))
        proveedores.fijar_guion(['Hecho.'])
        confirmado = self.rpc(self.jefe, 'brian.conversacion', 'confirmar_accion', [[conv['id']], accion_id])
        self.assertTrue(confirmado['ok'], confirmado)
        self.assertTrue(self.env['res.partner'].search([('name', '=', 'Cliente RPC')]))
        self.assertEqual(self.env['brian.accion'].browse(accion_id).estado, 'hecha')
