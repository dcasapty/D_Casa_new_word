"""El Inicio con las reglas contables de la gerencia (tanda 2, 2026-10-18): lo que ni el Inicio sobre facturas ni las
reglas de permisos podían probar solos, porque cada uno no veía al otro.

* «Registrar cobro» del Inicio sale exactamente a quien el servidor deja cobrar (Caja, Gerencia, contabilidad y
  administradores; A5): ni la Vendedora (con el interruptor encendido o apagado), ni quien solo factura o solo lee la
  contabilidad. Y a quien no le sale, el servidor le niega el cobro.
* Las notas de crédito, que ahora hace solo Gerencia (A7), restan en el Inicio y son de la vendedora de su factura
  (también una nota hecha aparte y aplicada después), no de Gerencia: ni en «Por vendedora» ni en el selector.
* Un pedido de la web sin vendedora sale en «Sin vendedora» en «Por vendedora», aunque lo facture Caja; no es venta de
  Caja.

Fechas fijas de 2025: nada depende del reloj real.
"""
from datetime import date, datetime, time

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .test_facturado import FacturadoCommon
from .test_inicio_por_rol import crear_usuario


@tagged('post_install', '-at_install')
class TestInicioConLasReglasDeLaGerencia(FacturadoCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.caja = crear_usuario(cls.env, 'caja_reglas_inicio', 'dcasa_base.group_caja')
        # Celular y correo: sin ellos, una factura no se publica como persona (dcasa_contactos).
        cls.cliente.write({'phone': '+507 6555-0701', 'email': 'cliente.reglas.inicio@example.com'})

    def test_registrar_cobro_solo_a_quien_el_servidor_deja_cobrar(self):
        usuarios = {
            'vendedora': (self.vendedora, False),
            'caja': (self.caja, True),
            'gerencia': (self.gerencia, True),
            'contador': (crear_usuario(self.env, 'contador_reglas_inicio', 'account.group_account_user'), True),
            'lector contable': (crear_usuario(self.env, 'lector_reglas_inicio', 'account.group_account_readonly'),
                                False),
            'solo facturación': (crear_usuario(self.env, 'facturacion_reglas_inicio', 'account.group_account_invoice'),
                                 False),
        }
        cobro = {'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.cliente.id, 'amount': 10.0,
                 'journal_id': self.banco.id, 'date': date(2025, 4, 1)}
        for encendido in (True, False):
            self.env['res.users']._dcasa_poner_restriccion(encendido)
            for nombre, (usuario, cobra) in usuarios.items():
                with self.subTest(nombre, interruptor=encendido):
                    permisos = self.tablero.with_user(usuario).obtener_datos()['permisos']
                    self.assertEqual(permisos['cobrar'], cobra, '«Registrar cobro» del Inicio')
                    self.assertEqual(usuario._dcasa_puede_cobrar(), cobra, 'la regla del servidor (cobros.py)')
                    if not cobra:
                        with self.assertRaises(AccessError):
                            self.env['account.payment'].with_user(usuario).create(cobro)

    def test_la_nota_de_credito_de_gerencia_resta_y_es_de_la_vendedora(self):
        dia = date(2025, 4, 8)
        ana = self.vendedora.id
        devuelta = self.suelta(dia, precio=1000.0, vendedor=self.vendedora)        # factura directa de Ana
        Reverso = self.env['account.move.reversal'].with_context(active_model='account.move',
                                                                  active_ids=devuelta.ids)
        valores = {'date': dia, 'reason': 'Devolución de prueba', 'journal_id': devuelta.journal_id.id}
        with self.assertRaises(AccessError, msg='Caja no hace notas de crédito (A7)'):
            Reverso.with_user(self.caja).create(valores).refund_moves()
        asistente = Reverso.with_user(self.gerencia).create(valores)
        asistente.refund_moves()
        nota = asistente.new_move_ids.with_user(self.gerencia)
        nota.invoice_line_ids.write({'price_unit': 250.0})
        nota.action_post()
        self.registrar(nota, dia, time(10, 0))
        # Una nota hecha aparte por Gerencia y aplicada después a otra factura de Ana.
        aplicada = self.suelta(dia, precio=500.0, vendedor=self.vendedora)
        aparte = self.env['account.move'].with_user(self.gerencia).create({
            'move_type': 'out_refund', 'partner_id': self.cliente.id, 'invoice_date': dia,
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'price_unit': 100.0})]})
        aparte.action_post()
        self.registrar(aparte, dia, time(11, 0))
        self.assertFalse(aparte.reversed_entry_id)
        (aparte | aplicada).line_ids.filtered(
            lambda linea: linea.account_id.account_type == 'asset_receivable').with_user(self.gerencia).reconcile()
        self.assertEqual(aplicada.payment_state, 'partial')
        self.assertEqual(aparte.invoice_user_id, self.gerencia,
                         'Odoo le pone a la nota hecha aparte el «Vendedor» de quien la hace (Gerencia)')
        # Restan en el Inicio y son de Ana, no de Gerencia.
        de_ana = self.medir(dia, dia, 'facturado', ana)
        self.assertEqual((de_ana['sin_itbms'], de_ana['cuantas'], de_ana['notas']), (1150.0, 2, 2))
        equipo = self.medir(dia, dia, 'facturado')
        self.assertEqual(equipo['sin_itbms'], 1150.0)
        por_vendedora = self.tablero.with_user(self.gerencia)._por_vendedora(equipo)
        self.assertEqual(dict(por_vendedora), {ana: [2, 1150.0]})
        self.assertNotIn(aparte.id, self.ids(self.medir(dia, dia, 'facturado', self.gerencia.id)))
        con_abonos = self.medir(dia, dia, 'con_abonos', ana)
        self.assertNotIn(aparte.id, self.ids(con_abonos), 'una nota aplicada no es un abono')
        vendedoras = [v['id'] for v in self.tablero.with_user(self.gerencia)._vendedoras_para_elegir(date(2025, 4, 30))]
        self.assertIn(ana, vendedoras)
        self.assertNotIn(self.gerencia.id, vendedoras, 'hacer notas de crédito no la vuelve vendedora')

    def test_un_pedido_web_sin_vendedora_va_a_sin_vendedora_aunque_lo_facture_caja(self):
        dia = date(2025, 4, 15)
        sitio = self.env.ref('website.default_website')

        def pedido_web():
            """Como lo arma la tienda: con sudo, del sitio web, sin tocar la vendedora."""
            return self.env['sale.order'].sudo().create({
                'partner_id': self.cliente.id, 'website_id': sitio.id,
                'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1})]})

        web = pedido_web()
        web.action_confirm()                       # la tienda sola (pago en línea), como superusuario
        self.assertFalse(web.user_id)
        factura = web.with_user(self.caja)._create_invoices()
        factura.write({'invoice_date': dia})
        factura.with_user(self.caja).action_post()
        self.registrar(factura, dia, time(9, 0))
        tomado = pedido_web()
        tomado.with_user(self.vendedora).action_confirm()
        self.assertEqual(tomado.user_id, self.vendedora, 'la vendedora que lo confirma se lo queda')
        de_ana = tomado._create_invoices()
        de_ana.write({'invoice_date': dia})
        de_ana.action_post()
        self.registrar(de_ana, dia, time(9, 0))
        equipo = self.medir(dia, dia, 'facturado')
        self.assertEqual(dict(self.tablero.with_user(self.gerencia)._por_vendedora(equipo)),
                         {'sin': [1, 1000.0], self.vendedora.id: [1, 1000.0]})
        self.assertEqual(self.ids(self.medir(dia, dia, 'facturado', 'sin')), factura.ids)
        self.assertFalse(self.ids(self.medir(dia, dia, 'facturado', self.caja.id)), 'no es venta de Caja')
        resultado = self.comparar('rango', datetime(2025, 4, 20, 10, 0), base='facturado', a_desde='2025-04-15',
                                  a_hasta='2025-04-15', b_desde='2025-04-08', por_vendedora=True)
        filas = {fila['vendedor']: fila for fila in resultado['por_vendedora']}
        self.assertEqual((filas['sin']['nombre'], filas['sin']['a']), ('Sin vendedora', 1000.0))
        self.assertEqual(filas[self.vendedora.id]['a'], 1000.0)
        self.assertNotIn(self.caja.id, filas)
