"""La promoción de envío en Odoo (quién la cambia, una sola vigente, la de noviembre precargada) y el envío dentro de
una cotización (el mismo camino que «Agregar envío», la línea de la promoción, reemplazar, lo que no se toca)."""
from datetime import date
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from ..models import venta
from .common import EnviosComun

HOY = 'odoo.addons.dcasa_envios.models.promocion.EnvioPromocion._hoy'


class PromocionComun(EnviosComun):
    """«Hoy» (la fecha de Panamá con que se ofrece y se suma la promoción, y con la que se mira si una cotización
    venció) es el 12 de noviembre de 2026 (``self.hoy`` lo cambia). Con ``FIJAR_FECHA = False``, el reloj de verdad."""

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
        self.hoy = date(2026, 11, 12)
        if self.FIJAR_FECHA:
            self.startPatcher(patch(HOY, side_effect=lambda: self.hoy))

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
        """Suma el envío como Juan (``fecha``: desde ahí, «hoy» es ese día)."""
        if fecha:
            self.hoy = fecha
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

    def test_el_itbms_del_envio_es_el_del_transportista_con_la_posicion_fiscal_de_la_venta(self):
        """Revisión adversarial (M2): Juan dice «al envío se le suma el ITBMS» solo si de verdad se le suma."""
        Orden = self.env['sale.order']
        self.assertFalse(Orden._dcasa_envio_lleva_itbms(), 'el de la tienda no lleva impuestos')
        itbms = self.env.company.account_sale_tax_id
        self.transportista.product_id.taxes_id = [Command.set(itbms.ids)]
        orden = self.orden((self.sofa, 1))
        self.assertTrue(Orden._dcasa_envio_lleva_itbms())
        self.assertTrue(orden._dcasa_envio_lleva_itbms())
        exenta = self.env['account.fiscal.position'].create({'name': 'Exenta de prueba'})
        self.env['account.tax'].create({
            'name': 'Exento de prueba', 'amount': 0.0, 'type_tax_use': 'sale',
            'fiscal_position_ids': [Command.set(exenta.ids)], 'original_tax_ids': [Command.set(itbms.ids)]})
        orden.fiscal_position_id = exenta
        self.assertFalse(orden._dcasa_envio_lleva_itbms(), 'con la posición fiscal de la venta, el envío va exento')

    def test_la_marca_de_la_promocion_solo_la_pone_el_sistema(self):
        orden = self.orden((self.sofa, 2))
        orden.user_id = self.vendedora
        terminos = {'promocion_id': self.noviembre.id, 'zona': 'gratis', 'minimo': 0}
        for usuario in (self.vendedora, self.gerencia):
            linea = orden.order_line.with_user(usuario)
            for valores in ({'dcasa_promocion_envio_id': self.noviembre.id}, {'dcasa_promocion_terminos': terminos}):
                with self.subTest(usuario=usuario.login, valores=valores), self.assertRaises(AccessError):
                    linea.write(valores)
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.env['sale.order.line'].with_user(usuario).create({
                    'order_id': orden.id, 'product_id': self.mesa.id, 'price_unit': -50,
                    'dcasa_promocion_envio_id': self.noviembre.id})

    def test_i3_el_lugar_del_envio_lo_marca_solo_el_servidor(self):
        """Segunda vuelta (I-3/R11): por RPC, cambiarle el lugar a la línea del envío a Colón ($105, abono $20) no la
        vuelve gratis: deja de ser del sistema, se quita la promoción y lo rebajado contaría contra el tope."""
        orden = self.de_la_vendedora((self.sofa, 2))                        # $300
        self.poner(orden, 'Barrio Simulado')
        envio = orden.order_line.filtered('dcasa_envio_lugar_id')
        envio.with_user(self.vendedora).write({'dcasa_envio_lugar_id': self.lugar('Costa Inventada').id})
        self.assertFalse(envio.dcasa_envio_lugar_id, 'ya no es del sistema')
        self.assertFalse(self.promocion_de(orden))
        self.assertAlmostEqual(orden.amount_untaxed, 405.0)
        self.assertIn('ya no tiene el envío a domicilio que sumó el sistema', self.notas(orden))
        # Ni creando una línea con la marca: la línea es de quien la crea.
        nueva = self.env['sale.order.line'].with_user(self.vendedora).create({
            'order_id': orden.id, 'product_id': self.transportista.product_id.id, 'price_unit': 10.0,
            'dcasa_envio_lugar_id': self.lugar('Costa Inventada').id})
        self.assertFalse(nueva.dcasa_envio_lugar_id)

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

    def test_la_promocion_sigue_al_envio_impuestos_y_repetidas_con_los_terminos_guardados(self):
        orden = self.de_la_vendedora((self.sofa, 2))
        self.poner(orden, 'Barrio Simulado')                                # $105 − $20 de abono
        promocion = self.promocion_de(orden)
        self.assertEqual(promocion.dcasa_promocion_terminos, {
            'promocion_id': self.noviembre.id, 'nombre': 'Envío Gratis Todo Noviembre', 'desde': '2026-11-01',
            'hasta': '2026-11-30', 'minimo': 200.0, 'mide': 'sin_itbms', 'zona': 'abono', 'abono': 20.0,
            'excluye_colchon': True, 'sumada_el': '2026-11-12',
            'vale_hasta': min(orden.validity_date or date(2026, 12, 12), date(2026, 12, 12)).isoformat()})
        envio = orden.order_line.filtered('dcasa_envio_lugar_id')
        impuesto = self.env.company.account_sale_tax_id
        envio.sudo().write({'tax_ids': [Command.set(impuesto.ids)]})        # el sistema (su) no le quita la marca
        self.assertEqual(promocion.tax_ids, impuesto, 'los mismos impuestos que el envío')
        self.env['sale.order.line'].sudo().create({
            'order_id': orden.id, 'product_id': envio.product_id.id, 'price_unit': -20.0, 'is_delivery': True,
            'tax_ids': [Command.set(impuesto.ids)], 'dcasa_promocion_envio_id': self.noviembre.id})
        self.assertEqual(self.promocion_de(orden), promocion, 'una sola promoción: la que tiene sus términos')
        self.assertTrue(promocion._dcasa_promocion_coherente())

    def test_i2_si_gerencia_cambia_o_archiva_la_promocion_lo_ya_sumado_se_respeta(self):
        """Segunda vuelta (I-2/R2/R3): lo sumado guarda sus términos; la sincronización mira la COMPRA contra ellos."""
        colon = self.de_la_vendedora((self.sofa, 2))                        # $300 a Colón: abono de $20
        self.poner(colon, 'Barrio Simulado')
        costa = self.de_la_vendedora((self.sofa, 2))                        # $300 a Costa: gratis
        self.poner(costa, 'Costa Inventada')
        mesas = self.de_la_vendedora((self.mesa, 5))                        # $300, −$45
        self.poner(mesas, 'Costa Inventada')
        self.assertEqual(self.noviembre.cotizaciones_abiertas, 3)
        self.noviembre.with_user(self.gerencia).write({'abono': 25, 'minimo': 300})
        for orden in (colon, costa):
            orden.with_user(self.vendedora).action_confirm()
        self.assertEqual(self.promocion_de(colon).price_unit, -20.0, 'lo que decía el PDF')
        self.assertEqual(self.promocion_de(costa).price_unit, -45.0, 'el mínimo de cuando se sumó: $200')
        # Confirmada, archivar la promoción no la vuelve incoherente (R3): devolver una de las mesas sigue pasando.
        mesas.with_user(self.vendedora).action_confirm()
        self.noviembre.with_user(self.gerencia).write({'active': False})
        self.assertTrue(self.promocion_de(mesas)._dcasa_promocion_coherente())
        mesas.order_line.filtered(lambda ln: ln.product_id == self.mesa).with_user(self.vendedora).write(
            {'product_uom_qty': 4})                                         # $240: sigue pasando de $200
        self.assertTrue(self.promocion_de(mesas))

    def test_i2_la_ficha_avisa_cuantas_cotizaciones_abiertas_la_tienen(self):
        arch = self.env['dcasa.envio.promocion'].with_user(self.gerencia).get_view(view_type='form')['arch']
        self.assertIn('o_dcasa_promocion_abiertas', arch)
        self.assertIn('los cambios valen solo para las nuevas', arch)
        self.assertEqual(self.noviembre.cotizaciones_abiertas, 0)
        orden = self.de_la_vendedora((self.sofa, 2))
        self.poner(orden, 'Costa Inventada')
        self.noviembre.invalidate_recordset(['cotizaciones_abiertas'])
        self.assertEqual(self.noviembre.cotizaciones_abiertas, 1)
        orden.with_user(self.vendedora).action_confirm()
        self.noviembre.invalidate_recordset(['cotizaciones_abiertas'])
        self.assertEqual(self.noviembre.cotizaciones_abiertas, 0, 'las confirmadas ya no son cotizaciones abiertas')

    def test_m1_guardar_la_venta_con_varias_lineas_a_la_vez(self):
        """Segunda vuelta (M-1/R4): la ficha manda los comandos juntos; la promoción se revisa una vez al final."""
        for segundo in ({'sequence': 99}, {'name': 'Promoción (nota de la vendedora)'}):
            with self.subTest(segundo=segundo):
                orden = self.de_la_vendedora((self.sofa, 2))
                self.poner(orden, 'Costa Inventada')
                sofa = orden.order_line.filtered(lambda linea: linea.product_id == self.sofa)
                orden.with_user(self.vendedora).write({'order_line': [
                    Command.update(sofa.id, {'product_uom_qty': 1}),
                    Command.update(self.promocion_de(orden).id, segundo)]})
                self.assertFalse(self.promocion_de(orden), 'con $150 ya no aplica: se quita al final del guardado')
                self.assertIn('ya no pasa de $200 sin ITBMS (ahora suma $150)', self.notas(orden))
        # Y si el guardado deja la compra igual, la promoción sigue (exenta del tope durante el guardado).
        orden = self.de_la_vendedora((self.mesa, 4))                        # $240, −$45 (más del 10 %)
        self.poner(orden, 'Costa Inventada')
        mesa = orden.order_line.filtered(lambda linea: linea.product_id == self.mesa)
        orden.with_user(self.vendedora).write({'order_line': [
            Command.update(mesa.id, {'product_uom_qty': 5}), Command.update(self.promocion_de(orden).id,
                                                                           {'sequence': 99})]})
        self.assertEqual(self.promocion_de(orden).price_unit, -45.0)

    def test_m2_una_cotizacion_grande_no_dispara_las_consultas(self):
        """Segunda vuelta (M-2/R5): 150 líneas; cambiar una cantidad con la promoción cuesta casi lo mismo que sin."""
        productos = [self.sofa, self.mesa] * 75
        con = self.de_la_vendedora(*[(p, 1) for p in productos])
        sin = self.de_la_vendedora(*[(p, 1) for p in productos])
        self.poner(con, 'Costa Inventada')
        self.assertTrue(self.promocion_de(con))
        consultas = {}
        for nombre, orden in (('sin', sin), ('con', con)):
            linea = orden.order_line.filtered(lambda ln: ln.product_id == self.mesa)[:1].with_user(self.vendedora)
            self.env.flush_all()
            self.env.invalidate_all()
            antes = self.env.cr.sql_log_count
            linea.write({'product_uom_qty': 2})
            self.env.flush_all()
            consultas[nombre] = self.env.cr.sql_log_count - antes
        self.assertLess(consultas['con'], consultas['sin'] + 60, consultas)

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

    def test_i1_decide_el_dia_en_que_se_suma_y_lo_prometido_vale_hasta_que_vence(self):
        """Segunda vuelta (I-1/R6/R7/R8): se respeta lo YA prometido, no se dan promesas nuevas después."""
        # Sumada el 28 de noviembre, vence el 10 de diciembre: el 2 de diciembre (con la promoción ya archivada)
        # se confirma con lo prometido.
        orden = self.de_la_vendedora((self.sofa, 2))
        orden.validity_date = date(2026, 12, 10)
        self.poner(orden, 'Costa Inventada', fecha=date(2026, 11, 28))
        self.assertEqual(self.promocion_de(orden).dcasa_promocion_terminos['sumada_el'], '2026-11-28')
        self.hoy = date(2026, 12, 2)
        self.noviembre.with_user(self.gerencia).write({'active': False})
        orden.with_user(self.vendedora).action_confirm()
        self.assertTrue(self.promocion_de(orden), 'se respeta lo prometido en el PDF')
        self.assertAlmostEqual(orden.amount_untaxed, 300.0)
        self.noviembre.with_user(self.gerencia).write({'active': True})
        # Vencida (venció el 30 de noviembre): el 2 de diciembre se vuelve a mirar con la promoción de hoy (ninguna).
        vencida = self.de_la_vendedora((self.sofa, 2))
        vencida.validity_date = date(2026, 11, 30)
        self.poner(vencida, 'Costa Inventada', fecha=date(2026, 11, 28))
        self.hoy = date(2026, 12, 2)
        vencida.with_user(self.vendedora).action_confirm()
        self.assertFalse(self.promocion_de(vencida))
        self.assertIn('porque lo prometido valía hasta el 30/11/2026 y hoy (02/12/2026) no hay una promoción de envío '
                      'vigente', self.notas(vencida))
        # Una cotización de octubre a la que se le suma el envío en noviembre sí la recibe (R8)…
        de_octubre = self.de_la_vendedora((self.sofa, 2))
        de_octubre.validity_date = date(2026, 12, 31)
        _puesto, resultado = self.poner(de_octubre, 'Costa Inventada', fecha=date(2026, 11, 12))
        self.assertTrue(resultado['aplica'])
        # …y una de noviembre a la que se le suma (o se le vuelve a calcular) en enero, no (R6).
        enero = self.de_la_vendedora((self.sofa, 2))
        enero.validity_date = date(2027, 2, 1)
        _puesto, resultado = self.poner(enero, 'Costa Inventada', fecha=date(2027, 1, 15))
        self.assertEqual(resultado['motivo'], 'sin_promocion')
        self.assertFalse(self.promocion_de(enero))

    def test_i1_volver_a_sumar_el_mismo_envio_no_pierde_lo_prometido(self):
        orden = self.de_la_vendedora((self.sofa, 2))
        orden.validity_date = date(2026, 12, 10)
        self.poner(orden, 'Costa Inventada', fecha=date(2026, 11, 28))
        lineas = orden.order_line.filtered('is_delivery')
        puesto, resultado = self.poner(orden, 'Costa Inventada', fecha=date(2026, 12, 2))
        self.assertTrue(puesto['ya_estaba'])
        self.assertTrue(resultado['aplica'])
        self.assertEqual(orden.order_line.filtered('is_delivery'), lineas, 'no se tocó')
        # Otro lugar sí se calcula con la promoción de hoy (ninguna en diciembre).
        puesto, resultado = self.poner(orden, 'Barrio Simulado')
        self.assertFalse(puesto['ya_estaba'])
        self.assertEqual(resultado['motivo'], 'sin_promocion')

    def test_ib_lo_prometido_tiene_fin_y_cambiar_vence_el_no_lo_alarga_ni_lo_revive(self):
        """Tercera vuelta (I-B): vale hasta el «Vence el» que tenía la cotización al sumarse, nunca más de 30 días
        después de sumada (sin «Vence el», 30 días). Cambiarlo después no lo alarga ni lo revive."""
        def sumada(vence, fecha=date(2026, 11, 12)):
            orden = self.de_la_vendedora((self.sofa, 2))                 # $300: gratis a Costa Inventada
            orden.validity_date = vence
            self.poner(orden, 'Costa Inventada', fecha=fecha)
            self.assertTrue(self.promocion_de(orden))
            return orden

        def confirmar_el(orden, dia):
            self.hoy = dia
            orden.with_user(self.vendedora).action_confirm()
            return self.promocion_de(orden)

        # Sin «Vence el» al sumarse: 30 días (hasta el 12/12). El 12/12 vale; el 13/12, no (y queda el porqué).
        sin_fecha = sumada(False)
        self.assertEqual(self.promocion_de(sin_fecha).dcasa_promocion_terminos['vale_hasta'], '2026-12-12')
        self.assertTrue(confirmar_el(sin_fecha, date(2026, 12, 12)))
        tarde = sumada(False)
        self.assertFalse(confirmar_el(tarde, date(2026, 12, 13)))
        self.assertIn('porque lo prometido valía hasta el 12/12/2026 y hoy (13/12/2026) no hay una promoción de envío '
                      'vigente', self.notas(tarde))
        # Un «Vence el» más allá de los 30 días no los alarga.
        lejos = sumada(date(2027, 3, 31))
        self.assertEqual(self.promocion_de(lejos).dcasa_promocion_terminos['vale_hasta'], '2026-12-12')
        self.assertFalse(confirmar_el(lejos, date(2027, 3, 1)))
        # Vaciarlo o alargarlo después de sumada no cambia nada.
        vaciada = sumada(date(2026, 12, 5))
        vaciada.with_user(self.vendedora).write({'validity_date': False})
        alargada = sumada(date(2026, 12, 5))
        alargada.with_user(self.vendedora).write({'validity_date': date(2027, 12, 31)})
        self.assertFalse(confirmar_el(vaciada, date(2026, 12, 6)))
        self.assertFalse(confirmar_el(alargada, date(2026, 12, 6)))
        # Vencida y «revivida» por la vendedora: no vuelve.
        revivida = sumada(date(2026, 12, 5))
        self.hoy = date(2026, 12, 20)
        revivida.with_user(self.vendedora).write({'validity_date': date(2027, 1, 31)})
        self.assertFalse(confirmar_el(revivida, date(2026, 12, 20)))
        # Vencida con la promoción todavía vigente: se vuelve a revisar con la de hoy y la nota dice hasta cuándo valía.
        noviembre = sumada(date(2026, 11, 5), fecha=date(2026, 11, 2))
        self.assertEqual(self.promocion_de(noviembre).dcasa_promocion_terminos['vale_hasta'], '2026-11-05')
        self.assertTrue(confirmar_el(noviembre, date(2026, 11, 20)))
        self.assertEqual(self.promocion_de(noviembre).dcasa_promocion_terminos['sumada_el'], '2026-11-20')
        self.assertIn('Lo prometido valía hasta el 05/11/2026: la promoción de envío se volvió a revisar con la de '
                      'hoy: −$45 (antes −$45).', self.notas(noviembre))

    def test_ma_copiar_con_las_lineas_de_quien_copia_no_trae_marcas_del_servidor(self):
        """Tercera vuelta (M-a): ``copy(default={'order_line': …})`` por RPC: esas líneas son de quien copia."""
        orden = self.de_la_vendedora((self.mesa, 1))                          # $60
        lugar = self.lugar('Barrio Simulado')
        producto = self.transportista.product_id
        terminos = {'promocion_id': self.noviembre.id, 'nombre': 'X', 'desde': '2026-11-01', 'hasta': '2026-11-30',
                    'minimo': 0.0, 'mide': 'sin_itbms', 'zona': 'gratis', 'abono': 0.0, 'excluye_colchon': False,
                    'sumada_el': '2026-11-12', 'vale_hasta': '2026-12-12'}
        envio = {'product_id': producto.id, 'price_unit': 500.0, 'is_delivery': True, 'name': 'Envío'}
        with self.assertRaises(AccessError):
            orden.with_user(self.vendedora).copy({'order_line': [
                Command.create({'product_id': self.mesa.id, 'product_uom_qty': 1}),
                Command.create(dict(envio, dcasa_envio_lugar_id=lugar.id)),
                Command.create({'product_id': producto.id, 'price_unit': -500.0, 'is_delivery': True, 'name': 'Promo',
                                'dcasa_promocion_envio_id': self.noviembre.id,
                                'dcasa_promocion_terminos': terminos})]})
        copia = orden.with_user(self.vendedora).copy({'order_line': [
            Command.create({'product_id': self.mesa.id, 'product_uom_qty': 1}),
            Command.create(dict(envio, dcasa_envio_lugar_id=lugar.id))]})
        self.assertFalse(copia.order_line.filtered('dcasa_envio_lugar_id'), 'el lugar solo lo marca el servidor')
        self.assertFalse(self.promocion_de(copia))
        # Sin ``default``, la copia sí trae el envío del sistema (test_h17).

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
        self.hoy = date(2026, 12, 1)
        diciembre = orden.with_user(self.vendedora).copy()
        self.assertFalse(self.promocion_de(diciembre))
        self.assertAlmostEqual(diciembre.amount_untaxed, 285.0)
        self.assertIn('no se copió porque hoy (01/12/2026) no hay una promoción de envío vigente',
                      self.notas(diciembre))

    def test_m6_la_compra_se_mide_despues_de_descuentos_y_premios(self):
        """Decisión de la dueña (2026-11-12): los $200 se cuentan DESPUÉS de descuentos y premios de Socios."""
        orden = self.orden((self.sofa, 1), (self.mesa, 1), (self.mesa, 1))  # 150 + 60 + 60 = 270
        orden.order_line[-1].price_unit = -80.0                             # una rebaja (descuento o premio)
        self.assertEqual(orden._dcasa_envio_compra()['subtotal_sin_itbms'], 130.0)
        _puesto, resultado = self.poner(orden, 'Costa Inventada')
        self.assertEqual(resultado['motivo'], 'monto')
