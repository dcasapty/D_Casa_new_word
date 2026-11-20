"""«Qué compró»: la API de Yappy no manda el detalle de la compra, así que tiene que vivir en Odoo y ser fácil de ver.

Un pedido con varias líneas y variantes, pagado por Yappy (servidor falso), queda confirmado con sus líneas intactas y
visibles en la transacción, en el pedido y en la nota que se le deja al equipo; uno que no se pagó conserva sus líneas
para que una vendedora lo retome. Datos inventados."""
import re

from odoo import Command
from odoo.addons.dcasa_base.models.venta_online import CLAVE_CONTEXTO, ESCRIBIR
from odoo.addons.dcasa_pago_yappy.models import resumen
from odoo.tests import TransactionCase, new_test_user, tagged

from .common import CELULAR_LIMPIO, ComunYappy, YappyFalso


class BaseCompra(ComunYappy, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Atributo = cls.env['product.attribute']
        color = Atributo.create({'name': 'Color', 'value_ids': [Command.create({'name': 'Gris humo'}),
                                                                 Command.create({'name': 'Azul noche'})]})
        medida = Atributo.create({'name': 'Medida', 'value_ids': [Command.create({'name': 'Queen'}),
                                                                   Command.create({'name': 'King'})]})
        cls.sofa = cls.env['product.template'].create({
            'name': 'Sofá Roma de prueba', 'type': 'consu', 'is_storable': True, 'list_price': 250.0,
            'taxes_id': [Command.set(cls.env.company.account_sale_tax_id.ids)],
            'attribute_line_ids': [
                Command.create({'attribute_id': color.id, 'value_ids': [Command.set(color.value_ids.ids)]}),
                Command.create({'attribute_id': medida.id, 'value_ids': [Command.set(medida.value_ids.ids)]})]})
        cls.variantes = cls.sofa.product_variant_ids
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        for variante in cls.variantes:
            cls.env['stock.quant']._update_available_quantity(variante, almacen.lot_stock_id, 20.0)
        cls.entrega = cls.env['delivery.carrier'].search([('name', '=', 'Retiro en tienda (La Chorrera)')], limit=1)

    def valores(self, variante, atributo):
        return variante.product_template_attribute_value_ids.filtered(lambda v: v.attribute_id.name == atributo).name

    def variante(self, color, medida):
        return self.variantes.filtered(
            lambda v: self.valores(v, 'Color') == color and self.valores(v, 'Medida') == medida)

    def pedido_grande(self):
        gris = self.variante('Gris humo', 'Queen')
        azul = self.variante('Azul noche', 'King')
        pedido = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'website_id': self.website.id,
            'order_line': [
                Command.create({'product_id': gris.id, 'product_uom_qty': 2, 'discount': 10.0}),
                Command.create({'product_id': azul.id, 'product_uom_qty': 1}),
                Command.create({'product_id': self.producto.id, 'product_uom_qty': 3}),
            ]})
        if self.entrega:
            pedido.set_delivery_line(self.entrega, 0.0)
        return pedido

    def lineas_de(self, pedido):
        return [(ln.product_id.id, ln.product_uom_qty, ln.price_unit, ln.discount, ln.price_total)
                for ln in pedido.order_line.sorted('id')]

    def texto(self, html):
        return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', str(html or ''))).strip()


@tagged('post_install', '-at_install')
class TestPedidoPagadoConVariantes(BaseCompra):

    def test_el_pedido_pagado_queda_confirmado_con_todas_sus_lineas_intactas(self):
        pedido = self.pedido_grande()
        antes = self.lineas_de(pedido)
        self.assertGreaterEqual(len(antes), 3)
        with YappyFalso() as yappy:
            tx, _orden, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'E')
        tx._post_process()
        self.assertEqual(pedido.state, 'sale')
        self.assertEqual(self.lineas_de(pedido), antes, 'las líneas, sus variantes, cantidades y precios no cambian')
        self.assertEqual(tx.payment_id.amount, pedido.amount_total)

    def test_la_transaccion_muestra_las_lineas_del_pedido_con_su_variante(self):
        pedido = self.pedido_grande()
        with YappyFalso() as yappy:
            tx, _orden, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'E')
        self.assertEqual(tx.dcasa_pedido_id, pedido)
        self.assertEqual(tx.dcasa_lineas_ids, pedido.order_line.filtered(lambda ln: not ln.display_type))
        lectura = tx.dcasa_lineas_ids.read(
            ['product_id', 'name', 'product_uom_qty', 'price_unit', 'discount', 'price_total'])
        gris = next(fila for fila in lectura if fila['product_id'][0] == self.variante('Gris humo', 'Queen').id)
        self.assertEqual(gris['product_uom_qty'], 2.0)
        self.assertEqual(gris['discount'], 10.0)
        self.assertIn('Gris humo', gris['name'] + gris['product_id'][1], 'el color se ve en la línea')
        self.assertIn('Queen', gris['name'] + gris['product_id'][1], 'la medida se ve en la línea')

    def test_quien_cobra_y_quien_vende_lo_ven_sin_buscar(self):
        pedido = self.pedido_grande()
        with YappyFalso() as yappy:
            tx, _orden, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'E')
        for login, grupo in (('caja_compro', 'dcasa_base.group_caja'),
                             ('vendedora_compro', 'dcasa_base.group_vendedora'),
                             ('gerencia_compro', 'dcasa_base.group_gerencia')):
            usuario = new_test_user(self.env, login=login, groups=grupo)
            with self.subTest(grupo=grupo):
                visto = tx.with_user(usuario)
                self.assertEqual(visto.dcasa_pedido_id, pedido)
                self.assertEqual(len(visto.dcasa_lineas_ids), len(pedido.order_line), 've todas las líneas')
                self.assertTrue(visto.dcasa_lineas_ids.read(['product_id', 'name', 'price_unit', 'product_uom_qty']))
                self.assertEqual(visto.dcasa_cliente_celular, '+507 6000-0101')
                orden = pedido.with_user(usuario)
                self.assertIn('Yappy', orden.dcasa_pago_texto)
                self.assertIn('pagado', orden.dcasa_pago_texto)

    def test_el_pedido_dice_como_pago_cliente_entrega_y_origen(self):
        pedido = self.pedido_grande()
        with YappyFalso() as yappy:
            tx, orden, _d = self.abrir(yappy, pedido)
            self.aviso(tx, 'E', confirmationNumber='CONF-12345')
        pedido.invalidate_recordset()
        texto = pedido.dcasa_pago_texto
        self.assertIn('Yappy · pagado', texto)
        self.assertIn(f'${pedido.amount_total:.2f}', texto)
        self.assertIn(orden, texto, 'la orden que se ve en el reporte de Yappy Comercial')
        self.assertIn('CONF-12345', texto)
        self.assertIn('solo informativa', texto, 'el número de confirmación se presenta como informativo')
        self.assertIn('de PRUEBA', texto)
        self.assertEqual(pedido.dcasa_origen_texto, 'Página web')
        if self.entrega:
            self.assertIn('Retiro en tienda', pedido.dcasa_entrega_texto)
        self.assertIn('Calle de prueba 1', pedido.dcasa_entrega_texto)
        self.assertIn('La Chorrera', pedido.dcasa_entrega_texto)

    def test_el_origen_dice_si_llego_por_andres(self):
        pedido = self.pedido()
        pedido.with_context(**{CLAVE_CONTEXTO: ESCRIBIR}).write({'dcasa_via_andres': True})
        self.assertIn('Andrés', pedido.dcasa_origen_texto)
        self.assertIn('Página web', pedido.dcasa_origen_texto)

    def test_un_pedido_sin_pagos_no_inventa_un_pago(self):
        pedido = self.pedido()
        self.assertFalse(pedido.dcasa_pago_texto)
        self.assertEqual(pedido.dcasa_origen_texto, 'Página web')

    def test_la_nota_que_se_le_deja_al_equipo_trae_todo_el_detalle(self):
        pedido = self.pedido_grande()
        with YappyFalso() as yappy:
            tx, orden, _d = self.abrir(yappy, pedido, celular='6123 4567')
            self.aviso(tx, 'E', confirmationNumber='CONF-777')
        notas = [m for m in pedido.message_ids if 'Yappy confirmó el pago' in str(m.body)]
        self.assertEqual(len(notas), 1, 'una sola nota de compra, aunque el aviso se repita')
        nota = notas[0]
        self.assertEqual(nota.subtype_id, self.env.ref('mail.mt_note'), 'es una nota interna: el cliente no la recibe')
        self.assertFalse(nota.partner_ids, 'no se manda a nadie')
        self.assertFalse(self.env['mail.mail'].search_count([('mail_message_id', '=', nota.id)]))
        cuerpo = self.texto(nota.body)
        for esperado in ('Sofá Roma de prueba', 'Gris humo', 'Queen', 'Azul noche', 'King', '2 ×', '−10 %',
                         '$250.00 c/u', 'Sofá de prueba (Yappy)'.upper(), '3 ×', 'Total del pedido',
                         f'${pedido.amount_total:.2f}', 'Ana Prueba Yappy', '+507 6000-0101',
                         'Calle de prueba 1', 'Origen: Página web', orden, 'CONF-777', 'solo informativa'):
            self.assertIn(esperado.lower(), cuerpo.lower(), esperado)
        # H5: el celular de Yappy de quien paga es de Caja y superiores; la nota la lee también la vendedora
        self.assertNotIn('61234567', cuerpo)
        self.assertNotIn('Celular de Yappy', cuerpo)
        if self.entrega:
            self.assertIn('retiro en tienda', cuerpo.lower())
        self.aviso(tx, 'E')
        self.assertEqual(len([m for m in pedido.message_ids if 'Yappy confirmó el pago' in str(m.body)]), 1)

    def test_los_textos_de_las_personas_nunca_se_vuelven_html_en_la_nota(self):
        self.cliente.name = '<img src=x onerror=alert(1)> Ana'
        self.cliente.street = '<script>alert(2)</script> Calle'
        self.producto.name = '<b>Sofá</b> peligroso'
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _orden, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'E')
        nota = next(m for m in pedido.message_ids if 'Yappy confirmó el pago' in str(m.body))
        html = str(nota.body)
        self.assertNotIn('<img', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('<b>Sofá</b>', html)
        self.assertIn('&lt;img', html)

    def test_las_lineas_del_resumen_traen_variante_precio_y_descuento(self):
        pedido = self.pedido_grande()
        filas = resumen.lineas(pedido)
        sofa_gris = next(f for f in filas if 'Gris humo' in f['variante'])
        self.assertEqual(sofa_gris['variante'], 'Color: Gris humo · Medida: Queen')
        self.assertEqual((sofa_gris['cantidad'], sofa_gris['descuento'], sofa_gris['precio']), (2.0, 10.0, 250.0))
        frase = resumen.frase_de_linea(pedido, sofa_gris)
        self.assertIn('2 × SOFÁ ROMA DE PRUEBA (Color: Gris humo · Medida: Queen)'.lower(), frase.lower())
        self.assertIn('−10 %', frase)
        if self.entrega:
            self.assertTrue(any(f['es_envio'] for f in filas), 'el envío viene marcado como envío')

    def test_el_pago_en_modo_de_prueba_lo_dice_en_la_nota(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _orden, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'E')
        self.assertIn('modo de PRUEBA', self.texto(' '.join(pedido.message_ids.mapped('body'))))


@tagged('post_install', '-at_install')
class TestPedidoQueNoSePago(BaseCompra):
    """Si el cliente nunca pagó (R, C, X o sin aviso), el carrito con sus líneas sigue ahí para que una vendedora lo
    retome."""

    def test_rechazo_cancelacion_o_vencimiento_conservan_las_lineas(self):
        for estado in ('R', 'C', 'X'):
            with self.subTest(estado=estado):
                pedido = self.pedido_grande()
                antes = self.lineas_de(pedido)
                with YappyFalso() as yappy:
                    tx, orden, _d = self.abrir(yappy, pedido)
                self.aviso(tx, estado)
                tx._post_process()
                self.assertEqual(tx.state, 'cancel')
                self.assertEqual(pedido.state, 'draft', 'sigue siendo un carrito/cotización')
                self.assertEqual(self.lineas_de(pedido), antes)
                self.assertFalse(pedido.transaction_ids.filtered(lambda t: t.state == 'done'))
                self.assertEqual(
                    tx.dcasa_lineas_ids, pedido.order_line,
                    'la transacción cancelada sigue mostrando qué iba a comprar')
                self.assertIn('cancelado', pedido.dcasa_pago_texto)
                self.assertIn(orden, pedido.dcasa_pago_texto)

    def test_sin_aviso_el_pedido_conserva_sus_lineas_y_alguien_lo_ve_para_retomarlo(self):
        pedido = self.pedido_grande()
        antes = self.lineas_de(pedido)
        with YappyFalso() as yappy:
            tx, orden, _d = self.abrir(yappy, pedido)
        self.envejecer(tx, minutes=30)
        self.env['payment.transaction']._cron_dcasa_yappy_sin_aviso()
        self.assertEqual(self.lineas_de(pedido), antes)
        self.assertEqual(pedido.state, 'draft')
        actividad = self.env['mail.activity'].sudo().search(
            [('res_model', '=', 'sale.order'), ('res_id', '=', pedido.id)])
        self.assertTrue(actividad)
        nota = self.texto(actividad[0].note)
        for esperado in ('Sofá Roma de prueba', 'Gris humo', '2 ×', 'Queen', orden):
            self.assertIn(esperado.lower(), nota.lower(), esperado)

    def test_el_filtro_de_yappy_sin_completar_encuentra_el_pedido_y_el_pagado_no_sale(self):
        sin_pagar = self.pedido_grande()
        pagado = self.pedido()
        with YappyFalso() as yappy:
            tx_sin, _o, _d = self.abrir(yappy, sin_pagar)
            tx_pagado, _o2, _d2 = self.abrir(yappy, pagado)
        self.aviso(tx_sin, 'C')
        self.aviso(tx_pagado, 'E')
        tx_pagado._post_process()
        Pedido = self.env['sale.order']
        sin_completar = Pedido.search([
            ('state', 'in', ('draft', 'sent')), ('transaction_ids.provider_code', '=', 'yappy'),
            ('transaction_ids.state', 'in', ('pending', 'cancel', 'error'))])
        self.assertIn(sin_pagar, sin_completar)
        self.assertNotIn(pagado, sin_completar)
        pagados = Pedido.search(
            [('transaction_ids.provider_code', '=', 'yappy'), ('transaction_ids.state', '=', 'done')])
        self.assertIn(pagado, pagados)
        self.assertNotIn(sin_pagar, pagados)

    def test_despues_de_cancelar_se_puede_volver_a_pagar_el_mismo_pedido(self):
        pedido = self.pedido_grande()
        with YappyFalso() as yappy:
            primera, _o, _d = self.abrir(yappy, pedido)
            self.aviso(primera, 'R')
            segunda, orden2, _d2 = self.abrir(yappy, pedido)
        self.assertNotEqual(primera.dcasa_yappy_orden, orden2)
        self.aviso(segunda, 'E')
        segunda._post_process()
        self.assertEqual(pedido.state, 'sale')
        self.assertEqual(segunda.dcasa_lineas_ids, pedido.order_line)


@tagged('post_install', '-at_install')
class TestCombosYLasVistas(BaseCompra):

    def test_un_combo_se_ve_con_sus_piezas_y_el_pedido_se_paga_con_todo_intacto(self):
        Combo = self.env['product.combo']
        impuestos = [Command.set(self.env.company.account_sale_tax_id.ids)]
        cama = self.env['product.product'].create({
            'name': 'Cama Zeta de prueba', 'type': 'consu', 'list_price': 90.0, 'taxes_id': impuestos})
        colchon = self.env['product.product'].create({
            'name': 'Colchón Imperial de prueba', 'type': 'consu', 'list_price': 60.0, 'taxes_id': impuestos})
        grupo_cama = Combo.create({'name': 'Cama', 'combo_item_ids': [Command.create({'product_id': cama.id})]})
        grupo_colchon = Combo.create({
            'name': 'Colchón', 'combo_item_ids': [Command.create({'product_id': colchon.id})]})
        combo = self.env['product.product'].create({
            'name': 'Combo dormitorio de prueba', 'type': 'combo', 'list_price': 130.0,
            'taxes_id': [Command.set(self.env.company.account_sale_tax_id.ids)],
            'combo_ids': [Command.set((grupo_cama | grupo_colchon).ids)]})
        pedido = self.env['sale.order'].create({'partner_id': self.cliente.id, 'website_id': self.website.id})
        Linea = self.env['sale.order.line']
        base = Linea.create({'order_id': pedido.id, 'product_id': combo.id, 'product_uom_qty': 1})
        for grupo, producto in ((grupo_cama, cama), (grupo_colchon, colchon)):
            Linea.create({'order_id': pedido.id, 'product_id': producto.id, 'product_uom_qty': 1,
                          'linked_line_id': base.id, 'combo_item_id': grupo.combo_item_ids.id})
        filas = resumen.lineas(pedido)
        self.assertEqual(len(filas), 3)
        piezas = [f for f in filas if f['pieza_de']]
        self.assertEqual(len(piezas), 2)
        self.assertEqual({f['pieza_de'].lower() for f in piezas}, {'combo dormitorio de prueba'})
        self.assertTrue(any(f['es_combo'] for f in filas))
        frases = ' '.join(resumen.frase_de_linea(pedido, f) for f in piezas)
        self.assertIn('pieza de: combo dormitorio de prueba', frases.lower())
        antes = self.lineas_de(pedido)
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        self.aviso(tx, 'E')
        tx._post_process()
        self.assertEqual(self.lineas_de(pedido), antes)
        self.assertEqual(len(tx.dcasa_lineas_ids), 3)
        self.assertIn('pieza de', self.texto(' '.join(pedido.message_ids.mapped('body'))))

    def test_las_vistas_del_pedido_y_de_la_transaccion_compilan_y_traen_el_bloque(self):
        from lxml import etree  # noqa: PLC0415
        vista = self.env['sale.order'].get_view(self.env.ref('sale.view_order_form').id)
        arbol = etree.fromstring(vista['arch'])
        campos = {c.get('name') for c in arbol.iter('field')}
        for nombre in ('dcasa_pago_texto', 'dcasa_entrega_texto', 'dcasa_origen_texto'):
            self.assertIn(nombre, campos)
        vista = self.env['payment.transaction'].get_view(self.env.ref('payment.payment_transaction_form').id)
        arbol = etree.fromstring(vista['arch'])
        campos = {c.get('name') for c in arbol.iter('field')}
        for nombre in ('dcasa_pedido_id', 'dcasa_lineas_ids', 'dcasa_origen_texto', 'dcasa_entrega_texto',
                       'dcasa_yappy_orden', 'dcasa_yappy_confirmacion', 'dcasa_yappy_avisos'):
            self.assertIn(nombre, campos)
        lista = self.env['payment.transaction'].get_view(self.env.ref('payment.payment_transaction_list').id)
        columnas = {c.get('name') for c in etree.fromstring(lista['arch']).iter('field')}
        for nombre in ('reference', 'dcasa_pedido_id', 'partner_name', 'amount', 'state', 'dcasa_yappy_orden'):
            self.assertIn(nombre, columnas)

    def test_pagos_con_yappy_tiene_su_pantalla_y_menu_para_caja(self):
        accion = self.env.ref('dcasa_pago_yappy.action_pagos_yappy')
        self.assertEqual(accion.res_model, 'payment.transaction')
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, _d = self.abrir(yappy, pedido)
        caja = new_test_user(self.env, login='caja_pantalla', groups='dcasa_base.group_caja')
        import ast  # noqa: PLC0415
        encontradas = self.env['payment.transaction'].with_user(caja).search(ast.literal_eval(accion.domain))
        self.assertIn(tx, encontradas)
        menu = self.env.ref('dcasa_pago_yappy.menu_pagos_yappy')
        self.assertEqual(
            menu.group_ids, self.env.ref('dcasa_base.group_caja') | self.env.ref('account.group_account_user'))

    def test_el_menu_de_pagos_es_de_caja_y_arriba_no_de_la_vendedora(self):
        """Como «Cobros de hoy (caja)»: es la lista de los pagos de TODA la tienda. La vendedora ve el bloque en su
        pedido, no esta lista (y la guardia de dcasa_base solo deja a la vendedora los menús de clientes de su
        lista)."""
        from odoo.addons.dcasa_base.tests.test_permisos_vendedora import menus_visibles  # noqa: PLC0415
        menu = 'dcasa_pago_yappy.menu_pagos_yappy'
        vendedora = new_test_user(self.env, login='vendedora_menu_yappy', groups='dcasa_base.group_vendedora')
        caja = new_test_user(self.env, login='caja_menu_yappy', groups='dcasa_base.group_caja')
        gerencia = new_test_user(self.env, login='gerencia_menu_yappy', groups='dcasa_base.group_gerencia')
        self.assertNotIn(menu, menus_visibles(self.env, vendedora))
        self.assertIn(menu, menus_visibles(self.env, caja))
        self.assertIn(menu, menus_visibles(self.env, gerencia))

    def test_ninguna_pantalla_nueva_trae_claves(self):
        pedido = self.pedido()
        with YappyFalso() as yappy:
            tx, _o, datos = self.abrir(yappy, pedido)
        self.aviso(tx, 'E', confirmationNumber='CONF-1')
        texto = ' '.join(str(v) for v in (
            pedido.read(['dcasa_pago_texto', 'dcasa_entrega_texto', 'dcasa_origen_texto']),
            tx.read(), self.texto(' '.join(pedido.message_ids.mapped('body')))))
        for secreto in ('COMERCIO-DE-PRUEBA', 'clave-inventada', CELULAR_LIMPIO + 'x', yappy.token, datos['token']):
            self.assertNotIn(secreto, texto)
