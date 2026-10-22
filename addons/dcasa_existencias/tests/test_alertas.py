"""Alertas diarias por Telegram a Gerencia: apagadas de fábrica, sin umbrales inventados, y solo a Gerencia."""
from datetime import date, datetime, timedelta
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .comun import BodegaComun

ENVIAR = 'odoo.addons.dcasa_brian.models.telegram.BrianTelegramEnlace._enviar'


@tagged('post_install', '-at_install')
class TestAlertas(BodegaComun):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Enlace = cls.env['brian.telegram.enlace']
        Enlace.search([]).write({'activo': False})
        Enlace.create({'user_id': cls.gerencia.id, 'chat_id': '111', 'nombre': 'Gerencia'})
        Enlace.create({'user_id': cls.vendedora.id, 'chat_id': '222', 'nombre': 'Vendedora'})
        cls.Alertas = cls.env['dcasa.existencias.alertas']

    def _correr(self):
        with patch(ENVIAR, autospec=True, return_value={'ok': True}) as enviar:
            self.Alertas._cron_alertas_diarias()
        return [(llamada.args[1], llamada.args[2]) for llamada in enviar.call_args_list]

    def test_de_fabrica_estan_apagadas_y_sin_umbrales(self):
        config = self.config
        self.assertFalse(config.alertas_activas)
        self.assertFalse(config.alerta_stock_bajo or config.alerta_ajustes or config.alerta_cierre
                         or config.alerta_mermas)
        self.assertFalse(config.alerta_ajustes_unidades or config.alerta_ajustes_monto or config.alerta_cierre_dia)
        self._merma()                      # aun con algo que contar, apagadas no mandan nada
        self.assertEqual(self._correr(), [])

    def test_encendidas_sin_ninguna_alerta_elegida_no_mandan_nada(self):
        self.config.alertas_activas = True
        self.assertEqual(self._correr(), [])

    def test_stock_bajo_con_el_umbral_de_la_duena_y_solo_a_gerencia(self):
        self.config.write({'alertas_activas': True, 'alerta_stock_bajo': True, 'alerta_stock_bajo_unidades': 3})
        # Solo los productos de esta prueba (el catálogo instalado trae otros sin existencias).
        self.env['product.product'].search([('id', 'not in', (self.producto | self.sin_costo).ids)]).sale_ok = False
        self.producto.sale_ok = True
        self.sin_costo.sale_ok = True
        enviados = self._correr()
        self.assertEqual([chat for chat, _t in enviados], ['111'], 'solo al Telegram de Gerencia')
        texto = enviados[0][1]
        self.assertIn('SILLA SIN COSTO BODEGA: 3', texto)
        self.assertNotIn('SOFA DE PRUEBA BODEGA', texto)     # tiene 10: no está bajo
        self.assertEqual(self.config.alertas_ultimo_envio, texto)

    def test_ajustes_grandes_desde_el_umbral(self):
        # Solo lo de esta prueba (la carga del catálogo al instalar ya dejó sus «Ajuste del sistema»).
        hace_un_momento = datetime.now() - timedelta(seconds=5)
        self.config.write({'alertas_activas': True, 'alerta_ajustes': True, 'alerta_ajustes_unidades': 3,
                           'alertas_ultima': hace_un_momento})
        Quant = self.env['stock.quant'].with_user(self.gerencia).with_context(inventory_mode=True,
                                                                             inventory_name='Conteo')
        Quant.create({'product_id': self.producto.id, 'location_id': self.ubicacion.id,
                      'inventory_quantity': 9}).action_apply_inventory()                # −1: chico
        self.assertEqual(self._correr(), [])
        self.config.alertas_ultima = hace_un_momento
        Quant.create({'product_id': self.producto.id, 'location_id': self.ubicacion.id,
                      'inventory_quantity': 4}).action_apply_inventory()                # −5: grande
        texto = self._correr()[0][1]
        self.assertIn('ajuste(s) grande(s)', texto)
        self.assertIn('9 → 4', texto)
        self.assertIn('Conteo', texto)

    def test_mes_sin_cerrar_desde_el_dia_que_pone_la_duena(self):
        self.config.write({'alertas_activas': True, 'alerta_cierre': True, 'alerta_cierre_dia': 3})
        self.env.company.sudo().fiscalyear_lock_date = False
        self.assertEqual(self.Alertas._cierre(self.config, date(2030, 4, 2)), [])
        lineas = self.Alertas._cierre(self.config, date(2030, 4, 3))
        self.assertIn('marzo de 2030 sigue sin cerrar', lineas[0])
        self.env.company.sudo().fiscalyear_lock_date = date(2030, 3, 31)
        self.assertEqual(self.Alertas._cierre(self.config, date(2030, 4, 10)), [])

    def test_mermas_sobre_el_tope(self):
        self.config.write({'alertas_activas': True, 'alerta_mermas': True})
        self._merma()
        texto = self._correr()[0][1]
        self.assertIn('pasan del 0.5 %', texto)

    def test_un_umbral_que_falta_no_se_rellena(self):
        with self.assertRaises(ValidationError):
            self.config.write({'alerta_ajustes': True})
        with self.assertRaises(ValidationError):
            self.config.write({'alerta_cierre': True, 'alerta_cierre_dia': 0})
        with self.assertRaises(ValidationError):
            self.config.write({'alerta_stock_bajo_unidades': -1})

    def test_un_telegram_que_falla_no_rompe_nada(self):
        self.config.write({'alertas_activas': True, 'alerta_mermas': True})
        self._merma()
        with patch(ENVIAR, side_effect=RuntimeError('Telegram caído')):
            self.Alertas._cron_alertas_diarias()
        self.assertTrue(self.config.alertas_ultima)
