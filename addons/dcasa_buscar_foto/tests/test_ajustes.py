"""Sitio web › Busca con una foto: solo Gerencia y los administradores cambian el interruptor y los topes; la limpieza
de las huellas y de las búsquedas viejas."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models.buscar_foto import PARAM_ACTIVO, PARAM_TOPES, TOPES_DE_FABRICA


@tagged('post_install', '-at_install')
class TestAjustesBuscarFoto(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerente = new_test_user(cls.env, login='foto_gerente', groups='base.group_user,dcasa_base.group_gerencia')
        cls.admin = new_test_user(cls.env, login='foto_admin', groups='base.group_user,base.group_system')
        cls.vendedora = new_test_user(cls.env, login='foto_vendedora',
                                      groups='base.group_user,sales_team.group_sale_salesman')
        cls.Param = cls.env['ir.config_parameter'].sudo()
        cls.Foto = cls.env['dcasa.buscar.foto']
        # Las cuentas empiezan en cero (una base usada para capturas ya trae búsquedas).
        cls.env['dcasa.buscar.foto.uso'].sudo().search([]).unlink()

    def test_nace_encendida_con_los_topes_de_fabrica(self):
        self.assertEqual(self.Param.get_param(PARAM_ACTIVO), 'True')
        self.assertTrue(self.Foto._dcasa_activa())
        self.assertTrue(self.env.ref('website.default_website')._dcasa_buscar_foto_activa())
        for clave in PARAM_TOPES.values():
            self.Param.set_param(clave, '')
        self.assertEqual(self.Foto._dcasa_topes(), TOPES_DE_FABRICA)
        self.Param.set_param(PARAM_TOPES['dia'], 'mucho')
        self.assertEqual(self.Foto._dcasa_topes()['dia'], TOPES_DE_FABRICA['dia'], 'Un valor raro no deja sin tope')

    def test_gerencia_y_administradores_la_cambian(self):
        for usuario in (self.gerente, self.admin):
            with self.subTest(usuario.login):
                ajustes = self.env['dcasa.buscar.foto.ajustes'].with_user(usuario).create({})
                self.assertTrue(ajustes.activo)
                ajustes.write({'activo': False, 'tope_visitante_hora': 5, 'tope_conexion_hora': 15, 'tope_dia': 50})
                accion = ajustes.execute()
                self.assertEqual(accion['tag'], 'reload')
                self.assertFalse(self.Foto._dcasa_activa())
                self.assertEqual(self.Foto._dcasa_topes(), {'visitante': 5, 'conexion': 15, 'dia': 50})
                self.Param.set_param(PARAM_ACTIVO, 'True')

    def test_la_vendedora_no_la_ve_ni_la_cambia(self):
        with self.assertRaises(AccessError):
            self.env['dcasa.buscar.foto.ajustes'].with_user(self.vendedora).create({})
        ajustes = self.env['dcasa.buscar.foto.ajustes'].create({'activo': False})
        with self.assertRaises(AccessError):
            ajustes.with_user(self.vendedora).execute()
        self.assertTrue(self.Foto._dcasa_activa(), 'No cambió nada')
        menu = self.env.ref('dcasa_buscar_foto.menu_dcasa_buscar_foto')
        visibles = self.env['ir.ui.menu'].with_user(self.vendedora)._visible_menu_ids()
        self.assertNotIn(menu.id, visibles)
        self.assertIn(menu.id, self.env['ir.ui.menu'].with_user(self.gerente)._visible_menu_ids())

    def test_descartar_vuelve_a_la_pantalla(self):
        accion = self.env['dcasa.buscar.foto.ajustes'].with_user(self.gerente).create({}).cancel()
        self.assertEqual(accion['res_model'], 'dcasa.buscar.foto.ajustes')

    def test_un_tope_fuera_de_rango_no_se_guarda(self):
        ajustes = self.env['dcasa.buscar.foto.ajustes'].with_user(self.gerente).create({'tope_dia': -1})
        with self.assertRaises(UserError):
            ajustes.execute()

    def test_apagar_o_encender_rehace_las_paginas_del_borde(self):
        if 'dcasa.tienda.pendiente' not in self.env:
            self.skipTest('dcasa_tienda_borde no está instalado')
        Pendiente = type(self.env['dcasa.tienda.pendiente'])
        with patch.object(Pendiente, '_dcasa_marcar', autospec=True) as marcar:
            self.env['dcasa.buscar.foto.ajustes'].with_user(self.gerente).create({'activo': True}).execute()
            marcar.assert_not_called()   # no cambió: no hace falta rehacer nada
            self.env['dcasa.buscar.foto.ajustes'].with_user(self.gerente).create({'activo': False}).execute()
            marcar.assert_called_once()

    def test_cuantas_hubo(self):
        Uso = self.env['dcasa.buscar.foto.uso'].sudo()
        ahora = fields.Datetime.now()
        for resultado in ('resultados', 'resultados', 'nada', 'documento', 'no_ahora', 'otra'):
            Uso.create({'resultado': resultado})
        Uso.create({'resultado': 'resultados', 'fecha': ahora - timedelta(days=40)})
        ajustes = self.env['dcasa.buscar.foto.ajustes'].with_user(self.gerente).create({})
        self.assertEqual((ajustes.busquedas_hoy, ajustes.busquedas_mes), (6, 6))
        self.assertEqual((ajustes.con_resultado_mes, ajustes.sin_resultado_mes, ajustes.documentos_mes,
                          ajustes.no_leidas_mes), (2, 2, 1, 1))

    def test_los_estilos_del_sitio_compilan(self):
        """Un error de SCSS (p. ej. ``min(22rem, 100%)``, que libsass no entiende) deja TODO el sitio sin estilos."""
        paquete = self.env['ir.qweb']._get_asset_bundle('web.assets_frontend', css=True, js=False)
        paquete.css()
        self.assertFalse(paquete.css_errors, paquete.css_errors)

    def test_la_limpieza_borra_huellas_y_busquedas_viejas(self):
        Uso = self.env['dcasa.buscar.foto.uso'].sudo()
        ahora = fields.Datetime.now()
        reciente = Uso.create({'resultado': 'nada', 'huella_visitante': 'a', 'huella_conexion': 'b'})
        de_ayer = Uso.create({'resultado': 'nada', 'huella_visitante': 'a', 'huella_conexion': 'b',
                              'fecha': ahora - timedelta(hours=30)})
        vieja = Uso.create({'resultado': 'nada', 'fecha': ahora - timedelta(days=91)})
        Uso._cron_limpiar()
        self.assertEqual((reciente.huella_visitante, reciente.huella_conexion), ('a', 'b'))
        self.assertEqual((de_ayer.huella_visitante, de_ayer.huella_conexion), (False, False))
        self.assertFalse(vieja.exists())
