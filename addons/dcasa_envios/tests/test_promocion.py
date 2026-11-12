"""La promoción de envío en Odoo (quién la cambia, una sola vigente, la de noviembre precargada) y el envío dentro de
una cotización (el mismo camino que «Agregar envío», la línea de la promoción, reemplazar, lo que no se toca)."""
from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import EnviosComun


class PromocionComun(EnviosComun):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.importar()
        cls.env['dcasa.envio.tarifa'].search([], limit=1).with_user(cls.gerencia).action_aprobar()
        cls.noviembre = cls.env.ref('dcasa_envios.promocion_noviembre_2026')
        impuesto = cls.env.company.account_sale_tax_id
        base = {'type': 'consu', 'sale_ok': True, 'taxes_id': [Command.set(impuesto.ids)]}
        Producto = cls.env['product.product']
        cls.sofa = Producto.create({**base, 'name': 'ZZENV SOFA GRIS', 'list_price': 150.0})
        cls.mesa = Producto.create({**base, 'name': 'ZZENV MESA PINO', 'list_price': 60.0})
        cls.colchon = Producto.create({**base, 'name': 'ZZENV COLCHÓN FIRME QUEEN', 'list_price': 300.0})
        cls.combo = Producto.create({**base, 'name': 'COMBO ZZENV CAMA QUEEN + COLCHÓN', 'list_price': 500.0})
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente Envío Prueba'})
        cls.transportista = cls.env['sale.order']._dcasa_envio_transportista()

    def orden(self, *pares, estado=None):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': p.id, 'product_uom_qty': c}) for p, c in pares]})
        if estado == 'sale':
            orden.action_confirm()
        return orden

    def aplicar(self, orden, lugar, fecha=date(2026, 11, 12)):
        precio = self.env['dcasa.envio.tarifa'].cotizar_lugar(lugar)['total']
        resultado, promocion = self.env['dcasa.envio.promocion']._aplicar(
            precio, lugar.prov, lugar.dist, orden._dcasa_envio_compra(), fecha=fecha)
        return precio, resultado, promocion

    def poner(self, orden, nombre, fecha=date(2026, 11, 12)):
        lugar = self.lugar(nombre)
        precio, resultado, promocion = self.aplicar(orden, lugar, fecha)
        return orden.sudo()._dcasa_envio_poner(lugar, precio, resultado, promocion), resultado


@tagged('post_install', '-at_install')
class TestPromocionDeEnvio(PromocionComun):

    def test_viene_cargada_la_de_noviembre_con_las_decisiones_de_la_duena(self):
        promocion = self.noviembre
        self.assertEqual((promocion.name, promocion.desde, promocion.hasta, promocion.minimo, promocion.mide,
                          promocion.abono, promocion.excluye_colchon, promocion.active),
                         ('Envío Gratis Todo Noviembre', date(2026, 11, 1), date(2026, 11, 30), 200.0, 'sin_itbms',
                          20.0, True, True))
        self.assertEqual(promocion._como_motor()['provincias_gratis'], ['Panamá', 'Panamá Oeste'])
        self.assertEqual(self.env['dcasa.envio.promocion']._vigente(date(2026, 11, 30)), promocion)
        self.assertFalse(self.env['dcasa.envio.promocion']._vigente(date(2026, 12, 1)))
        self.assertIn("El envío a ese lugar cuesta normalmente $100. Con la promoción de noviembre, en compras de más "
                      "de $200 sin ITBMS, D'CASA te regala el envío: te sale gratis (te ahorras $100).",
                      promocion.resumen)
        self.assertIn("D'CASA te abona $20 del envío: te queda en $80.", promocion.resumen)
        self.assertIn('La promoción es hasta el 30 de noviembre; después, el envío vuelve a su precio normal.',
                      promocion.resumen)

    def test_solo_gerencia_la_cambia_y_queda_quien_cambio_que(self):
        with self.assertRaises(AccessError):
            self.noviembre.with_user(self.vendedora).write({'minimo': 1})
        with self.assertRaises(AccessError):
            self.env['dcasa.envio.promocion'].with_user(self.vendedora).create(
                {'name': 'X', 'desde': date(2027, 1, 1), 'hasta': date(2027, 1, 2), 'minimo': 1, 'abono': 5})
        self.assertTrue(self.noviembre.with_user(self.vendedora).read(['name']), 'el equipo la puede ver')
        self.noviembre.with_user(self.gerencia).write({'abono': 25})
        self.env.flush_all()
        self.env.cr.precommit.run()          # el historial se escribe al confirmar la transacción
        cambio = self.noviembre.message_ids.tracking_value_ids.filtered(lambda t: t.field_id.name == 'abono')
        self.assertEqual(len(cambio), 1)
        self.assertEqual((cambio.old_value_float, cambio.new_value_float), (20.0, 25.0))
        self.assertEqual(cambio.mail_message_id.author_id, self.gerencia.partner_id)

    def test_una_sola_vigente_a_la_vez(self):
        Promocion = self.env['dcasa.envio.promocion'].with_user(self.gerencia)
        valores = {'name': 'Otra', 'minimo': 100, 'mide': 'sin_itbms', 'provincias_gratis': 'Colón', 'abono': 0}
        with self.assertRaises(ValidationError):
            Promocion.create(dict(valores, desde=date(2026, 11, 30), hasta=date(2026, 12, 5)))
        archivada = Promocion.create(dict(valores, desde=date(2026, 11, 30), hasta=date(2026, 12, 5), active=False))
        with self.assertRaises(ValidationError):
            archivada.write({'active': True})
        diciembre = Promocion.create(dict(valores, desde=date(2026, 12, 1), hasta=date(2026, 12, 31)))
        self.assertEqual(self.env['dcasa.envio.promocion']._vigente(date(2026, 12, 2)), diciembre)

    def test_valores_que_no_sirven(self):
        Promocion = self.env['dcasa.envio.promocion'].with_user(self.gerencia)
        base = {'name': 'Prueba', 'desde': date(2027, 2, 1), 'hasta': date(2027, 2, 28), 'minimo': 100,
                'mide': 'sin_itbms', 'provincias_gratis': 'Panamá'}
        for malo in ({'hasta': date(2027, 1, 1)}, {'minimo': -1}, {'abono': -5},
                     {'provincias_gratis': False, 'distritos_gratis': False, 'abono': 0},
                     {'provincias_gratis': 'Panamá Oste'}, {'distritos_gratis': 'Chorrera Vieja'}):
            with self.subTest(malo=malo), self.assertRaises(ValidationError):
                Promocion.create(dict(base, **malo))
        buena = Promocion.create(dict(base, provincias_gratis='panama oeste\nPANAMÁ', distritos_gratis='Colón'))
        self.assertEqual(buena._como_motor()['provincias_gratis'], ['panama oeste', 'PANAMÁ'])

    def test_la_calculadora_y_brian_siguen_dando_el_precio_normal(self):
        lugar = self.lugar('Costa Inventada')
        self.assertEqual(self.env['dcasa.envio.tarifa'].cotizar_lugar(lugar)['total'], 45.0)
        brian = self.env['brian.herramientas'].with_user(self.vendedora).ejecutar(
            'cotizar_envio', {'lugar': 'Costa Inventada'})
        self.assertTrue(brian['ok'], brian)
        costa = brian['datos']['lugares'][0]
        self.assertEqual(costa['total'], '$45', 'el precio de Brian no cambia')
        self.assertEqual(costa['texto_para_el_cliente'], 'Envío a Costa Inventada (Santa Prueba, Panamá): $45.')
        self.assertEqual(costa['con_la_promocion'],
                         "El envío a Costa Inventada (Santa Prueba, Panamá) cuesta normalmente $45. Con la promoción "
                         "de noviembre, en compras de más de $200 sin ITBMS, D'CASA te regala el envío: te sale gratis "
                         "(te ahorras $45). La promoción es hasta el 30 de noviembre; después, el envío vuelve a su "
                         "precio normal. No aplica si la compra lleva colchón.", 'la promoción va aparte')
        with patch('odoo.addons.dcasa_envios.models.promocion.EnvioPromocion._hoy', return_value=date(2026, 12, 1)):
            diciembre = self.env['brian.herramientas'].with_user(self.vendedora).ejecutar(
                'cotizar_envio', {'lugar': 'Costa Inventada'})
        self.assertNotIn('con_la_promocion', diciembre['datos']['lugares'][0])


@tagged('post_install', '-at_install')
class TestEnvioEnLaCotizacion(PromocionComun):

    def test_la_compra_sin_el_envio_y_el_colchon(self):
        orden = self.orden((self.sofa, 1), (self.mesa, 1))
        compra = orden._dcasa_envio_compra()
        self.assertEqual(compra, {'subtotal_sin_itbms': 210.0, 'subtotal_con_itbms': 224.7, 'colchon': False})
        self.poner(orden, 'Costa Inventada')
        self.assertEqual(orden._dcasa_envio_compra()['subtotal_sin_itbms'], 210.0, 'el envío no cuenta')
        self.assertTrue(self.orden((self.colchon, 1))._dcasa_envio_compra()['colchon'])
        self.assertTrue(self.orden((self.combo, 1))._dcasa_envio_compra()['colchon'], 'un combo «+ COLCHÓN»')

    def test_suma_el_envio_como_agregar_envio_y_la_promocion_gratis(self):
        self.assertTrue(self.transportista, 'el transportista «Entrega a domicilio» de la tienda')
        orden = self.orden((self.sofa, 1), (self.mesa, 1))
        puesto, resultado = self.poner(orden, 'Costa Inventada')
        self.assertTrue(puesto['puesto'])
        self.assertEqual(resultado['motivo'], 'gratis')
        envio, promocion = puesto['linea_envio'], puesto['linea_promocion']
        self.assertEqual(orden.carrier_id, self.transportista, 'el método de entrega, como «Agregar envío»')
        self.assertTrue(envio.is_delivery)
        self.assertEqual((envio.product_id, envio.price_unit), (self.transportista.product_id, 45.0))
        self.assertEqual(envio.tax_ids, self.transportista.product_id.taxes_id, 'el ITBMS que tenga su producto')
        self.assertIn('Costa Inventada (Santa Prueba, Panamá)', envio.name)
        self.assertEqual(envio.dcasa_envio_lugar_id, self.lugar('Costa Inventada'))
        self.assertEqual((promocion.price_unit, promocion.product_id, promocion.tax_ids, promocion.is_delivery),
                         (-45.0, envio.product_id, envio.tax_ids, True))
        self.assertEqual(promocion.dcasa_promocion_envio_id, self.noviembre)
        self.assertEqual(promocion.name, 'Promoción Envío Gratis Todo Noviembre: envío gratis')
        self.assertAlmostEqual(orden.amount_untaxed, 210.0, msg='el envío gratis no suma nada')
        self.assertTrue(any('Envío a Costa Inventada' in (m.body or '') for m in orden.message_ids))

    def test_abono_en_colon(self):
        orden = self.orden((self.sofa, 2))
        puesto, resultado = self.poner(orden, 'Barrio Simulado')
        self.assertEqual((resultado['motivo'], resultado['precio_final']), ('abono', 85.0))
        self.assertEqual(puesto['linea_envio'].price_unit, 105.0)
        self.assertEqual(puesto['linea_promocion'].price_unit, -20.0)
        self.assertEqual(puesto['linea_promocion'].name, 'Promoción de envío: abono de $20')
        self.assertAlmostEqual(orden.amount_untaxed, 300.0 + 85.0)

    def test_sin_promocion_que_aplique_solo_va_el_envio(self):
        for pares, motivo in ((((self.mesa, 1),), 'monto'), (((self.colchon, 1),), 'colchon')):
            with self.subTest(motivo=motivo):
                orden = self.orden(*pares)
                puesto, resultado = self.poner(orden, 'Costa Inventada')
                self.assertEqual(resultado['motivo'], motivo)
                self.assertTrue(puesto['puesto'])
                self.assertFalse(puesto['linea_promocion'])
                self.assertEqual(orden.order_line.filtered('is_delivery').price_unit, 45.0)
        fuera = self.orden((self.sofa, 2))
        puesto, resultado = self.poner(fuera, 'Costa Inventada', fecha=date(2026, 12, 1))
        self.assertEqual(resultado['motivo'], 'sin_promocion')
        self.assertFalse(puesto['linea_promocion'])

    def test_otro_lugar_reemplaza_el_envio_y_la_promocion(self):
        orden = self.orden((self.sofa, 2))
        self.poner(orden, 'Costa Inventada')
        self.poner(orden, 'Barrio Simulado')
        envios = orden.order_line.filtered('is_delivery')
        self.assertEqual(sorted(envios.mapped('price_unit')), [-20.0, 105.0], 'nada del envío anterior')
        self.assertEqual(envios.dcasa_envio_lugar_id, self.lugar('Barrio Simulado'))

    def test_no_toca_una_venta_confirmada_ni_el_envio_que_puso_una_persona(self):
        confirmada = self.orden((self.sofa, 2), estado='sale')
        puesto, _resultado = self.poner(confirmada, 'Costa Inventada')
        self.assertEqual(puesto, {'puesto': False, 'motivo': 'confirmada'})
        self.assertFalse(confirmada.order_line.filtered('is_delivery'))
        de_la_vendedora = self.orden((self.sofa, 2))
        de_la_vendedora.set_delivery_line(self.transportista, 30.0)
        puesto, _resultado = self.poner(de_la_vendedora, 'Costa Inventada')
        self.assertEqual(puesto, {'puesto': False, 'motivo': 'ajeno'})
        self.assertEqual(de_la_vendedora.order_line.filtered('is_delivery').price_unit, 30.0)
        flete = self.env['product.product'].search([('default_code', '=', 'DCASA-FLETE')], limit=1)
        con_flete = self.orden((self.sofa, 2), (flete, 1))
        self.assertEqual(self.poner(con_flete, 'Costa Inventada')[0], {'puesto': False, 'motivo': 'ajeno'})

    def test_la_marca_de_la_promocion_solo_la_pone_el_sistema(self):
        orden = self.orden((self.sofa, 2))
        orden.user_id = self.vendedora
        linea = orden.order_line.with_user(self.vendedora)
        with self.assertRaises(AccessError):
            linea.write({'dcasa_promocion_envio_id': self.noviembre.id})
        with self.assertRaises(AccessError):
            self.env['sale.order.line'].with_user(self.vendedora).create({
                'order_id': orden.id, 'product_id': self.mesa.id, 'price_unit': -50,
                'dcasa_promocion_envio_id': self.noviembre.id})

    def test_la_promocion_no_cuenta_contra_el_tope_de_la_vendedora_hasta_que_la_cambia(self):
        orden = self.orden((self.mesa, 4))          # $240: pasa de $200
        orden.user_id = self.vendedora
        self.poner(orden, 'Costa Inventada')        # −$45 de promoción: más que el 10 % de $240
        vendedora = orden.with_user(self.vendedora)
        vendedora.order_line.filtered(lambda linea: linea.product_id == self.mesa).write({'product_uom_qty': 5})
        self.assertAlmostEqual(orden.amount_untaxed, 300.0)
        promocion = orden.order_line.filtered('dcasa_promocion_envio_id')
        promocion.with_user(self.vendedora).write({'price_unit': -40.0})
        self.assertEqual(promocion.price_unit, -40.0)
        self.assertFalse(promocion.dcasa_promocion_envio_id, 'cambiada a mano, ya es una rebaja de la vendedora')
        self.assertTrue(promocion._dcasa_es_rebaja())
