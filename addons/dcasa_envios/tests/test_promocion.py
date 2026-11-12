"""La promoción de envío en Odoo (quién la cambia, una sola vigente, la de noviembre precargada) y el envío dentro de
una cotización (el mismo camino que «Agregar envío», la línea de la promoción, reemplazar, lo que no se toca)."""
from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from ..models import venta
from .common import EnviosComun

FECHA_COTIZACION = 'odoo.addons.dcasa_envios.models.venta.SaleOrder._dcasa_promocion_fecha'


class PromocionComun(EnviosComun):
    """Las cotizaciones de estas pruebas se tienen por creadas el 12 de noviembre de 2026 (``fechas`` cambia la de una
    cotización y ``fecha_cotizacion`` la de las que no están ahí). La fecha real de creación se prueba aparte."""

    FIJAR_FECHA = True

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

    def setUp(self):
        super().setUp()
        self.fecha_cotizacion = date(2026, 11, 12)
        self.fechas = {}
        if self.FIJAR_FECHA:
            self.startPatcher(patch(FECHA_COTIZACION, autospec=True,
                                    side_effect=lambda orden: self.fechas.get(orden.id, self.fecha_cotizacion)))

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

    def poner(self, orden, nombre, fecha=None):
        """Suma el envío como Juan (``fecha``: la cotización se tiene por creada ese día)."""
        if fecha:
            self.fechas[orden.id] = fecha
        lugar = self.lugar(nombre)
        precio = self.env['dcasa.envio.tarifa'].cotizar_lugar(lugar)['total']
        puesto = orden.sudo()._dcasa_envio_poner(lugar, precio)
        return puesto, puesto.get('resultado')

    def de_la_vendedora(self, *pares):
        self.cliente.write({'phone': '+507 6000-0000', 'email': 'cliente.envio@example.com'})
        orden = self.orden(*pares)
        orden.user_id = self.vendedora
        return orden

    def promocion_de(self, orden):
        return orden.order_line.filtered('dcasa_promocion_envio_id')

    def notas(self, orden):
        return ' '.join(orden.message_ids.mapped('body'))


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
        promocion = self.promocion_de(orden)
        self.assertTrue(promocion._dcasa_promocion_coherente())
        # Cambiada a mano deja de ser la promoción EN ESE MISMO CAMBIO: lo que rebaje cuenta contra su tope desde cero
        # (−$40 sobre $300 pasa del 10 %; antes de la revisión adversarial se colaba porque la marca se quitaba antes).
        with self.assertRaises(ValidationError):
            promocion.with_user(self.vendedora).write({'price_unit': -40.0})
        self.assertEqual((promocion.price_unit, promocion.dcasa_promocion_envio_id), (-45.0, self.noviembre))
        promocion.with_user(self.vendedora).write({'price_unit': -25.0})          # dentro del 10 %
        self.assertEqual(promocion.price_unit, -25.0)
        self.assertFalse(promocion.dcasa_promocion_envio_id, 'cambiada a mano, ya es una rebaja de la vendedora')
        self.assertTrue(promocion._dcasa_es_rebaja())


@tagged('post_install', '-at_install')
class TestLaPromocionSeVuelveARevisar(PromocionComun):
    """Revisión adversarial del 2026-11-12 (B1, M4, M6, M7): la promoción se revisa cada vez que cambia la cotización y
    antes de confirmarla. Cada prueba es un hueco que el revisor demostró (H1…H17), con la expectativa al revés."""

    def test_h1_bajar_la_compra_quita_la_promocion_con_una_nota(self):
        orden = self.de_la_vendedora((self.sofa, 2))                        # $300
        self.poner(orden, 'Costa Inventada')
        vendedora = orden.with_user(self.vendedora)
        vendedora.order_line.filtered(lambda linea: linea.product_id == self.sofa).write({'product_uom_qty': 1})
        self.assertFalse(self.promocion_de(orden), 'con $150 ya no aplica')
        self.assertAlmostEqual(orden.amount_untaxed, 195.0, msg='$150 + el envío a su precio normal')
        self.assertIn('Se quitó la promoción de envío (−$45) porque la compra ya no pasa de $200 sin ITBMS (ahora '
                      'suma $150).', self.notas(orden))
        self.assertEqual(orden.carrier_id, self.transportista, 'el envío sigue siendo envío para Bodega')
        vendedora.action_confirm()
        self.assertEqual(orden.state, 'sale')
        self.assertFalse(self.promocion_de(orden))

    def test_h1_antes_de_confirmar_tambien_se_revisa(self):
        orden = self.de_la_vendedora((self.sofa, 2))
        self.poner(orden, 'Costa Inventada')
        # Un cambio que no pasa por las líneas (aquí, la compra baja sin escribir en la línea de la promoción).
        sofa = orden.order_line.filtered(lambda linea: linea.product_id == self.sofa)
        sofa.with_context(**{venta.SINCRONIZANDO: True}).write({'product_uom_qty': 1})
        self.assertTrue(self.promocion_de(orden))
        self.assertFalse(self.promocion_de(orden)._dcasa_promocion_coherente(), 'y ya no es exenta')
        orden.with_user(self.vendedora).action_confirm()
        self.assertFalse(self.promocion_de(orden), 'se quita al confirmar')
        self.assertIn('Se quitó la promoción de envío', self.notas(orden))

    def test_h2_agregar_colchon_quita_la_promocion(self):
        orden = self.de_la_vendedora((self.sofa, 2))
        self.poner(orden, 'Costa Inventada')
        self.env['sale.order.line'].with_user(self.vendedora).create(
            {'order_id': orden.id, 'product_id': self.colchon.id, 'product_uom_qty': 1})
        self.assertFalse(self.promocion_de(orden))
        self.assertIn('porque la compra lleva colchón y la promoción no aplica con colchón', self.notas(orden))

    def test_h3_borrar_el_envio_quita_la_promocion(self):
        orden = self.de_la_vendedora((self.mesa, 4))                        # $240
        self.poner(orden, 'Costa Inventada')
        orden.order_line.filtered('dcasa_envio_lugar_id').with_user(self.vendedora).unlink()
        self.assertFalse(self.promocion_de(orden), 'sin envío no queda una rebaja de $45 sobre los productos')
        self.assertAlmostEqual(orden.amount_untaxed, 240.0)
        self.assertIn('ya no tiene el envío a domicilio que sumó el sistema', self.notas(orden))
        # La misma rebaja hecha por la vendedora se sigue bloqueando:
        otra = self.de_la_vendedora((self.mesa, 4))
        with self.assertRaises(ValidationError):
            self.env['sale.order.line'].with_user(self.vendedora).create(
                {'order_id': otra.id, 'product_id': self.mesa.id, 'price_unit': -45.0, 'product_uom_qty': 1})
        orden.with_user(self.vendedora).action_confirm()
        self.assertEqual(orden.state, 'sale')

    def test_h4_mover_la_linea_de_la_promocion_a_otra_cotizacion(self):
        orden = self.de_la_vendedora((self.sofa, 2))
        self.poner(orden, 'Costa Inventada')
        chica = self.de_la_vendedora((self.mesa, 1))                        # $60
        promocion = self.promocion_de(orden)
        with self.assertRaises(ValidationError):                            # −$45 sobre $60: rebaja de la vendedora
            promocion.with_user(self.vendedora).write({'order_id': chica.id})
        self.assertEqual(promocion.order_id, orden)
        promocion.with_user(self.gerencia).write({'order_id': chica.id})   # Gerencia puede, pero ya no es la promoción
        self.assertFalse(promocion.dcasa_promocion_envio_id)
        self.assertFalse(promocion._dcasa_exenta_tope_descuento())

    def test_cambiar_el_envio_a_mano_o_dejarlo_en_cero_quita_la_promocion(self):
        orden = self.de_la_vendedora((self.sofa, 2))
        self.poner(orden, 'Costa Inventada')
        envio = orden.order_line.filtered('dcasa_envio_lugar_id')
        envio.with_user(self.vendedora).write({'price_unit': 0.0})
        self.assertFalse(envio.dcasa_envio_lugar_id, 'el envío ya es de la vendedora')
        self.assertFalse(self.promocion_de(orden))
        self.assertAlmostEqual(orden.amount_untaxed, 300.0)
        # Un envío del sistema que queda en $0 (aunque no lo cambie una persona) tampoco tiene nada que rebajar.
        otra = self.de_la_vendedora((self.sofa, 2))
        self.poner(otra, 'Costa Inventada')
        otra.order_line.filtered('dcasa_envio_lugar_id').sudo().write({'price_unit': 0.0})
        self.assertFalse(self.promocion_de(otra))
        # «Actualizar costo de envío» (el transportista de domicilio cuesta $0 fijo, de website_dcasa) quita las dos.
        tercera = self.de_la_vendedora((self.sofa, 2))
        self.poner(tercera, 'Costa Inventada')
        tercera.set_delivery_line(self.transportista, 0.0)
        self.assertEqual(tercera.order_line.filtered('is_delivery').mapped('price_unit'), [0.0])

    def test_la_promocion_sigue_al_envio_monto_impuestos_y_repetidas(self):
        orden = self.de_la_vendedora((self.sofa, 2))
        self.poner(orden, 'Barrio Simulado')                                # $105 − $20 de abono
        self.noviembre.with_user(self.gerencia).write({'abono': 25})
        self.env['sale.order.line'].with_user(self.vendedora).create(
            {'order_id': orden.id, 'product_id': self.mesa.id, 'product_uom_qty': 1})
        promocion = self.promocion_de(orden)
        self.assertEqual((promocion.price_unit, promocion.name), (-25.0, 'Promoción de envío: abono de $25'))
        self.assertIn('se puso al día con el envío y la compra: −$25 (antes −$20)', self.notas(orden))
        envio = orden.order_line.filtered('dcasa_envio_lugar_id')
        impuesto = self.env.company.account_sale_tax_id
        envio.sudo().write({'tax_ids': [Command.set(impuesto.ids)]})        # el sistema (su) no le quita la marca
        self.assertEqual(promocion.tax_ids, impuesto, 'los mismos impuestos que el envío')
        self.env['sale.order.line'].sudo().create({
            'order_id': orden.id, 'product_id': envio.product_id.id, 'price_unit': -25.0, 'is_delivery': True,
            'tax_ids': [Command.set(impuesto.ids)], 'dcasa_promocion_envio_id': self.noviembre.id})
        self.assertEqual(len(self.promocion_de(orden)), 1, 'una sola promoción')
        self.assertTrue(self.promocion_de(orden)._dcasa_promocion_coherente())

    def test_retiro_en_tienda_no_es_un_envio_que_puso_una_persona(self):
        retiro = self.env['delivery.carrier'].search([('dcasa_por_cotizar', '=', False),
                                                      ('product_id', '=', self.transportista.product_id.id)], limit=1)
        self.assertTrue(retiro, '«Retiro en tienda» de website_dcasa')
        orden = self.orden((self.sofa, 2))
        orden.set_delivery_line(retiro, 0.0)
        puesto, _resultado = self.poner(orden, 'Costa Inventada')
        self.assertTrue(puesto['puesto'], 'el cliente ahora quiere que se lo lleven: se cambia por el envío')
        self.assertEqual(orden.carrier_id, self.transportista)
        self.assertEqual(sorted(orden.order_line.filtered('is_delivery').mapped('price_unit')), [-45.0, 45.0])

    def test_venta_confirmada_no_se_toca_pero_la_promocion_que_ya_no_vale_cuenta_en_el_tope(self):
        orden = self.de_la_vendedora((self.sofa, 2))
        self.poner(orden, 'Costa Inventada')
        orden.with_user(self.vendedora).action_confirm()
        self.assertTrue(self.promocion_de(orden))
        sofa = orden.order_line.filtered(lambda linea: linea.product_id == self.sofa)
        with self.assertRaises(ValidationError):                            # $150 con −$45: 30 % de rebaja
            sofa.with_user(self.vendedora).write({'product_uom_qty': 1})
        self.assertTrue(self.promocion_de(orden), 'lo confirmado no se toca solo')

    def test_la_fecha_que_decide_es_la_de_la_cotizacion(self):
        orden = self.de_la_vendedora((self.sofa, 2))
        self.poner(orden, 'Costa Inventada', fecha=date(2026, 11, 30))     # hecha el último día
        with patch('odoo.addons.dcasa_envios.models.promocion.EnvioPromocion._hoy', return_value=date(2026, 12, 2)):
            orden.with_user(self.vendedora).action_confirm()
        self.assertTrue(self.promocion_de(orden), 'se respeta lo prometido en el PDF')
        self.assertAlmostEqual(orden.amount_untaxed, 300.0)

    def test_h17_duplicar_vuelve_a_calcular_la_promocion(self):
        orden = self.de_la_vendedora((self.mesa, 4))                        # $240
        self.poner(orden, 'Costa Inventada')
        copia = orden.with_user(self.vendedora).copy()                      # no la bloquea el tope
        envio = copia.order_line.filtered('dcasa_envio_lugar_id')
        self.assertEqual((envio.price_unit, envio.dcasa_envio_lugar_id), (45.0, self.lugar('Costa Inventada')))
        promocion = self.promocion_de(copia)
        self.assertEqual((promocion.price_unit, promocion.dcasa_promocion_envio_id), (-45.0, self.noviembre))
        self.assertTrue(promocion._dcasa_promocion_coherente())
        self.assertAlmostEqual(copia.amount_untaxed, 240.0)
        self.assertIn('se volvió a calcular para esta cotización: −$45', self.notas(copia))
        # Duplicada en diciembre: la promoción no se copia y queda el porqué.
        self.fecha_cotizacion = date(2026, 12, 1)
        diciembre = orden.with_user(self.vendedora).copy()
        self.assertFalse(self.promocion_de(diciembre))
        self.assertAlmostEqual(diciembre.amount_untaxed, 285.0)
        self.assertIn('no se copió porque no hay una promoción de envío vigente en la fecha de la cotización '
                      '(01/12/2026)', self.notas(diciembre))

    def test_m6_la_compra_se_mide_despues_de_descuentos_y_premios(self):
        """Decisión de la dueña (2026-11-12): los $200 se cuentan DESPUÉS de descuentos y premios de Socios."""
        orden = self.orden((self.sofa, 1), (self.mesa, 1), (self.mesa, 1))  # 150 + 60 + 60 = 270
        orden.order_line[-1].price_unit = -80.0                             # una rebaja (descuento o premio)
        self.assertEqual(orden._dcasa_envio_compra()['subtotal_sin_itbms'], 130.0)
        _puesto, resultado = self.poner(orden, 'Costa Inventada')
        self.assertEqual(resultado['motivo'], 'monto')


@tagged('post_install', '-at_install')
class TestFechaDeLaCotizacion(PromocionComun):
    """La fecha que decide (sin fijarla): la de creación de la cotización en hora de Panamá, o hoy si se cambia."""

    FIJAR_FECHA = False

    def test_creacion_en_hora_de_panama(self):
        orden = self.orden((self.sofa, 1))
        for momento, esperada in (('2026-12-01 04:59:00', date(2026, 11, 30)),     # 30 nov 23:59 en Panamá
                                  ('2026-12-01 05:00:00', date(2026, 12, 1))):     # 1 dic 00:00 en Panamá
            self.env.cr.execute('UPDATE sale_order SET create_date = %s WHERE id = %s', (momento, orden.id))
            orden.invalidate_recordset(['create_date'])
            self.assertEqual(orden._dcasa_promocion_fecha(), esperada)
        with patch.object(venta, 'FECHA_QUE_DECIDE', 'hoy'), \
                patch('odoo.addons.dcasa_envios.models.promocion.EnvioPromocion._hoy', return_value=date(2027, 1, 5)):
            self.assertEqual(orden._dcasa_promocion_fecha(), date(2027, 1, 5))
