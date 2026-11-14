"""Sitio web › Busca con una foto: solo Gerencia y los administradores cambian el interruptor y los topes; la limpieza
de las huellas y de las búsquedas viejas."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models.buscar_foto import PARAM_ACTIVO, PARAM_TOPE_MES, PARAM_TOPES, TOPE_MES_DE_FABRICA, TOPES_DE_FABRICA


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
        # El techo del gasto de IA de la foto en el mes: 5 USD de fábrica; un valor raro tampoco lo quita.
        self.assertEqual(TOPE_MES_DE_FABRICA, 5.0)
        for valor, esperado in (('', 5.0), ('mucho', 5.0), ('-3', 0.0), ('2.5', 2.5), ('99999', 1000.0)):
            self.Param.set_param(PARAM_TOPE_MES, valor)
            self.assertEqual(self.Foto._dcasa_tope_mes(), esperado, valor)

    def test_gerencia_y_administradores_la_cambian(self):
        for usuario in (self.gerente, self.admin):
            with self.subTest(usuario.login):
                ajustes = self.env['dcasa.buscar.foto.ajustes'].with_user(usuario).create({})
                self.assertTrue(ajustes.activo)
                self.assertEqual(ajustes.tope_mes_usd, 5.0)
                ajustes.write({'activo': False, 'tope_visitante_hora': 5, 'tope_conexion_hora': 15, 'tope_dia': 50,
                               'tope_mes_usd': 7.5})
                accion = ajustes.execute()
                self.assertEqual(accion['tag'], 'reload')
                self.assertFalse(self.Foto._dcasa_activa())
                self.assertEqual(self.Foto._dcasa_topes(), {'visitante': 5, 'conexion': 15, 'dia': 50})
                self.assertEqual(self.Foto._dcasa_tope_mes(), 7.5)
                self.Param.set_param(PARAM_TOPE_MES, '')
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
        for cambio in ({'tope_dia': -1}, {'tope_mes_usd': -1}, {'tope_mes_usd': 1000.01}):
            with self.subTest(cambio):
                ajustes = self.env['dcasa.buscar.foto.ajustes'].with_user(self.gerente).create(cambio)
                with self.assertRaises(UserError):
                    ajustes.execute()
        self.assertEqual(self.Foto._dcasa_tope_mes(), 5.0, 'No cambió nada')

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
        # «No encontraron nada parecido» es solo de muebles; lo que no era un mueble va aparte.
        self.assertEqual((ajustes.con_resultado_mes, ajustes.sin_resultado_mes, ajustes.no_mueble_mes,
                          ajustes.documentos_mes, ajustes.no_leidas_mes), (2, 1, 1, 1, 1))

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
        Sal = self.env['dcasa.buscar.foto.sal'].sudo()
        Sal.search([]).unlink()
        hoy = self.Foto._dcasa_ahora_local(ahora).date()
        sales = {dias: Sal.create({'fecha': hoy - timedelta(days=dias), 'valor': f'sal-{dias}'})
                 for dias in (0, 1, 2, 9)}
        Uso._cron_limpiar()
        self.assertEqual((reciente.huella_visitante, reciente.huella_conexion), ('a', 'b'))
        self.assertEqual((de_ayer.huella_visitante, de_ayer.huella_conexion), (False, False))
        self.assertFalse(vieja.exists())
        # La sal de hoy y la de ayer se quedan (las huellas de la última hora pueden ser de antes de la medianoche); las
        # de antes, no: sin la sal, una huella vieja ya no se puede volver a calcular.
        self.assertEqual([dias for dias, sal in sales.items() if sal.exists()], [0, 1])

    def test_la_sal_del_dia_nace_al_azar_una_sola_vez(self):
        Sal = self.env['dcasa.buscar.foto.sal'].sudo()
        Sal.search([]).unlink()
        hoy, ayer = self.Foto._dcasa_sales()
        self.assertIsNone(ayer)
        self.assertEqual(len(hoy), 64)
        self.assertEqual(self.Foto._dcasa_sales(), (hoy, None), 'La misma todo el día')
        self.assertEqual(Sal.search_count([]), 1)
        manana = fields.Datetime.now() + timedelta(days=1)
        nueva, de_ayer = self.Foto._dcasa_sales(manana)
        self.assertEqual(de_ayer, hoy)
        self.assertNotEqual(nueva, hoy)
