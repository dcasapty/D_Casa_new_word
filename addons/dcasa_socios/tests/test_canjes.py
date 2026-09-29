from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import SociosCommon


@tagged('post_install', '-at_install')
class TestCanjes(SociosCommon):

    def setUp(self):
        super().setUp()
        self.diez = self.env.ref('dcasa_socios.premio_desc_10')  # 1,000 puntos = $10
        self.env['dcasa.movimiento']._asentar(self.padrino, 'ajuste', 1500, 'test', motivo='Saldo de prueba')

    def test_pedir_reserva_los_puntos(self):
        canje = self.env['dcasa.canje']._pedir(self.padrino, self.diez)
        self.assertEqual(canje.estado, 'solicitado')
        self.assertEqual(len(canje.codigo), 6)
        self.assertEqual(self.padrino.dcasa_saldo, 500)
        self.assertAlmostEqual((canje.expira_en - canje.solicitado_en).total_seconds(), 72 * 3600)

    def test_no_alcanza(self):
        with self.assertRaises(UserError):
            self.env['dcasa.canje']._pedir(self.padrino, self.env.ref('dcasa_socios.premio_desc_25'))

    def test_un_solo_pendiente_del_mismo_premio(self):
        self.env['dcasa.canje']._pedir(self.padrino, self.env.ref('dcasa_socios.premio_desc_5'))
        with self.assertRaises(UserError):
            self.env['dcasa.canje']._pedir(self.padrino, self.env.ref('dcasa_socios.premio_desc_5'))

    def test_canje_minimo(self):
        barato = self.env['dcasa.premio'].create({'name': 'Llavero', 'puntos': 100, 'tipo': 'producto'})
        with self.assertRaises(UserError):
            self.env['dcasa.canje']._pedir(self.padrino, barato)

    def test_stock(self):
        cojin = self.env['dcasa.premio'].create({'name': 'Cojín', 'puntos': 600, 'tipo': 'producto',
                                                 'stock_limitado': True, 'stock': 1})
        canje = self.env['dcasa.canje']._pedir(self.padrino, cojin)
        self.assertEqual(cojin.stock, 0)
        self.assertFalse(cojin._disponible())
        canje._cancelar_por_socio()
        self.assertEqual(cojin.stock, 1)
        self.assertEqual(self.padrino.dcasa_saldo, 1500)

    def test_vence_y_devuelve_los_puntos(self):
        canje = self.env['dcasa.canje']._pedir(self.padrino, self.diez)
        with patch.object(fields.Datetime, 'now', return_value=canje.expira_en + timedelta(minutes=1)):
            self.env['dcasa.canje']._cron_programa()
        self.assertEqual(canje.estado, 'vencido')
        self.assertEqual(self.padrino.dcasa_saldo, 1500)

    def test_suspendido_no_canjea(self):
        self.padrino.action_dcasa_suspender()
        with self.assertRaises(UserError):
            self.env['dcasa.canje']._pedir(self.padrino, self.diez)

    def test_cobrar_premio_en_la_venta(self):
        canje = self.env['dcasa.canje']._pedir(self.padrino, self.diez)
        orden = self.env['sale.order'].create({
            'partner_id': self.padrino.id,
            'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1, 'price_unit': 100})],
        })
        self.env['dcasa.cobrar.premio.wizard'].create({'order_id': orden.id, 'codigo': canje.codigo.lower()}) \
            .action_confirmar()
        self.assertAlmostEqual(orden.amount_untaxed, 90.0, msg='El premio rebaja la base, como un descuento')
        self.assertAlmostEqual(orden.amount_total, 96.30)
        orden.action_confirm()
        self.assertEqual(canje.estado, 'entregado')
        self.assertEqual(canje.sale_order_id, orden)

    def test_el_premio_es_de_quien_lo_gano(self):
        canje = self.env['dcasa.canje']._pedir(self.padrino, self.diez)
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id})
        with self.assertRaises(UserError):
            self.env['dcasa.cobrar.premio.wizard'].create({'order_id': orden.id, 'codigo': canje.codigo}) \
                .action_confirmar()

    def test_no_se_cobra_dos_veces(self):
        canje = self.env['dcasa.canje']._pedir(self.padrino, self.diez)
        ordenes = self.env['sale.order']
        for _i in range(2):
            orden = self.env['sale.order'].create({
                'partner_id': self.padrino.id,
                'order_line': [(0, 0, {'product_id': self.producto.id, 'product_uom_qty': 1})],
            })
            self.env['dcasa.cobrar.premio.wizard'].create({'order_id': orden.id, 'codigo': canje.codigo}) \
                .action_confirmar()
            ordenes |= orden
        ordenes[0].action_confirm()
        with self.assertRaises(UserError):
            ordenes[1].action_confirm()

    # --- Cumpleaños ------------------------------------------------------------

    def test_cumpleanos_una_vez_al_anio_y_con_compra_previa(self):
        self.cliente.dcasa_cumple = '09-29'
        # 29 de septiembre a las 8 p. m. en Panamá = 30 de septiembre 01:00 UTC.
        noche = datetime(2026, 9, 30, 1, 0)
        Canje = self.env['dcasa.canje']
        self.assertFalse(Canje._felicitar_a_los_de_hoy(noche), 'Sin compra previa no hay regalo')
        self.factura()
        self.assertEqual(Canje._felicitar_a_los_de_hoy(noche), self.cliente)
        self.assertFalse(Canje._felicitar_a_los_de_hoy(noche), 'Una vez al año')
        self.assertEqual(self.movimientos(self.cliente, 'cumpleanos').puntos, 500)
