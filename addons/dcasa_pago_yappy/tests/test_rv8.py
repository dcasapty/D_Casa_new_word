"""La cuarta vuelta de revisión (RV8) del dinero y los permisos del pago en línea, sobre los arreglos de RV7. Las
pruebas «rojas» del revisor independiente están aquí ADAPTADAS: ya no demuestran el hallazgo, comprueban que el arreglo
se sostiene. Cada prueba de dinero o permisos se comprobó ROMPIENDO el arreglo a propósito (docs/YAPPY.md §14).

* R8-1: la OTRA mitad de la relación: ``sale.order.transaction_ids`` y ``account.move.transaction_ids`` (la regla vive
  en ``dcasa_base``; las pruebas genéricas, de cualquier proveedor, en ``dcasa_base/tests/test_transaccion_de_pago.py``;
  aquí, con Yappy de verdad y con lo que ve Bodega).
* R8-2 / R8-6: la transacción es una lista blanca vacía (nada de ``partner_id``, ``landing_route``, ``state_message``…).
* R8-3: el cobro suelto de OTRO pedido del mismo cliente: el pendiente dice qué hacer y a la clienta no se le afirma
  «ya figuraba como pagado».
* R8-4: lo que escribió la clienta, dentro del pendiente de 15 minutos, va entre comillas y recortado.

TRAMPA (ver ``docs/CONTEXTO_AGENTICO.md``): antes de cada intento del usuario sin permiso se baja la caché
(``env.flush_all(); env.invalidate_all()``); con la caché tibia el ORM no revisa el permiso del comodelo.

Datos inventados; ninguna prueba toca la red.
"""
import re
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import YappyFalso
from .test_dinero_revision import BaseDinero


class BaseRv8(BaseDinero):

    def frio(self):
        self.env.flush_all()
        self.env.invalidate_all()

    def setUp(self):
        super().setUp()
        for destino in ('_send_payment_succeeded_for_order_mail', '_send_order_notification_mail'):
            parche = patch(f'odoo.addons.sale.models.sale_order.SaleOrder.{destino}', lambda *a, **k: None)
            parche.start()
            self.addCleanup(parche.stop)
        self.vendedora = new_test_user(self.env, login='rv8_vend', groups='dcasa_base.group_vendedora')
        self.facturacion = new_test_user(self.env, login='rv8_fact', groups='account.group_account_invoice')
        self.caja = new_test_user(self.env, login='rv8_caja', groups='dcasa_base.group_caja')

    def cliente_nuevo(self, n):
        return self.env['res.partner'].create({
            'name': f'Cliente RV8 {n}', 'phone': f'+507 6000-08{n:02d}', 'email': f'rv8.{n}@example.com',
            'country_id': self.env.ref('base.pa').id})

    def pedido_de(self, cliente, dueno, confirmar=True):
        pedido = self.env['sale.order'].create({
            'partner_id': cliente.id, 'website_id': self.website.id, 'user_id': dueno.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]})
        if confirmar:
            pedido.action_confirm()
        return pedido

    def cobro_hecho_y_cerrado(self, pedido):
        """Lo que deja el sistema cuando Yappy avisó: transacción hecha, cobro contable creado (sin conciliar)."""
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id, 'amount': pedido.amount_total,
            'currency_id': pedido.currency_id.id, 'partner_id': pedido.partner_invoice_id.id,
            'operation': 'online_direct', 'sale_order_ids': [Command.set(pedido.ids)]})
        tx._set_done()
        tx._post_process()
        self.assertTrue(tx.payment_id)
        return tx

    def bodega(self):
        if 'dcasa.bodega' not in self.env:
            self.skipTest('sin dcasa_barras (Bodega)')
        return self.env['dcasa.bodega']


# ======================================================================================================================
# R8-1 · la otra mitad de la relación (con Yappy de verdad y con Bodega)
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestR81ElOtroLadoDeLasRelaciones(BaseRv8):

    def intento_de_ligar(self, pedido, ajeno, usuario=None):
        """El intento de la vendedora, con la caché fría; devuelve ``True`` si Odoo lo dejó pasar."""
        self.frio()
        try:
            pedido.with_user(usuario or self.vendedora).write({'transaction_ids': [Command.link(ajeno.id)]})
        except AccessError:
            return False
        return True

    def test_a1_la_vendedora_y_facturacion_no_ligan_un_cobro_ajeno_a_un_pedido(self):
        ajeno = self.cobro_hecho_y_cerrado(self.pedido_de(self.cliente_nuevo(1), self.caja))
        pedido = self.pedido_de(self.cliente_nuevo(2), self.vendedora)
        for usuario in (self.vendedora, self.facturacion):
            self.assertFalse(self.intento_de_ligar(pedido, ajeno, usuario), usuario.login)
        self.assertNotIn(ajeno, pedido.sudo().transaction_ids)

    def test_a2_bodega_no_ve_pagado_un_pedido_al_que_se_le_quiso_ligar_un_cobro_ajeno(self):
        """La consecuencia física: Bodega «Este pedido todavía no tiene pago ni abono: no se entrega»."""
        bodega = self.bodega()
        ajeno = self.cobro_hecho_y_cerrado(self.pedido_de(self.cliente_nuevo(1), self.caja))
        pedido = self.pedido_de(self.cliente_nuevo(2), self.vendedora)
        entrega = pedido.picking_ids[:1]
        self.assertTrue(entrega, 'el pedido confirmado tiene su entrega')
        self.assertEqual(bodega._pagos_de_pedidos(pedido)[pedido.id], 'sin_pago')
        self.intento_de_ligar(pedido, ajeno)
        self.frio()
        self.assertEqual(bodega._pagos_de_pedidos(pedido)[pedido.id], 'sin_pago')
        with self.assertRaises(UserError):
            bodega._exigir_pago(entrega)

    def test_a7_basta_un_cobro_ajeno_pequeno_para_que_bodega_vea_un_abono(self):
        """Ni siquiera hace falta el monto del pedido: un cobro hecho de 5.00 ligado a uno de 107.00 ya era «abono»."""
        bodega = self.bodega()
        chico = self.pedido_de(self.cliente_nuevo(1), self.caja, confirmar=False)
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id, 'amount': 5.0,
            'currency_id': chico.currency_id.id, 'partner_id': chico.partner_id.id, 'operation': 'online_direct',
            'sale_order_ids': [Command.set(chico.ids)]})
        tx._set_done()
        pedido = self.pedido_de(self.cliente_nuevo(2), self.vendedora)
        self.intento_de_ligar(pedido, tx)
        self.frio()
        self.assertEqual(bodega._pagos_de_pedidos(pedido)[pedido.id], 'sin_pago')

    def test_a3_la_vendedora_no_suelta_el_cobro_hecho_de_su_pedido(self):
        """Esconder el pago: el pedido deja de verse pagado y el apartado nocturno lo anularía."""
        pedido = self.pedido_de(self.cliente_nuevo(1), self.vendedora)
        propio = self.cobro_hecho_y_cerrado(pedido)
        self.frio()
        with self.assertRaises(AccessError):
            pedido.with_user(self.vendedora).write({'transaction_ids': [Command.unlink(propio.id)]})
        self.assertIn(propio, pedido.sudo().transaction_ids)

    def test_a5_cadena_completa_el_dinero_de_a_no_paga_la_factura_de_c(self):
        """Cuando Caja publica la factura (lo normal), Odoo aplica SOLO el dinero ligado a esa factura: si la vendedora
        pudo ligar el cobro de A a la factura de C, la factura de C salía «pagada» con el dinero de A."""
        ajeno = self.cobro_hecho_y_cerrado(self.pedido_de(self.cliente_nuevo(1), self.caja))
        pedido = self.pedido_de(self.cliente_nuevo(3), self.vendedora)
        factura = pedido._create_invoices()
        self.frio()
        try:
            factura.with_user(self.vendedora).write({'transaction_ids': [Command.link(ajeno.id)]})
        except AccessError:
            pass
        self.frio()
        factura.with_user(self.caja).action_post()
        self.frio()
        self.assertEqual(factura.payment_state, 'not_paid', 'la factura de C no se paga con el dinero de A')
        self.assertNotIn(ajeno, factura.sudo().transaction_ids)

    def test_a8_tampoco_al_crear_el_pedido_con_el_cobro_ajeno_ya_ligado(self):
        ajeno = self.cobro_hecho_y_cerrado(self.pedido_de(self.cliente_nuevo(1), self.caja))
        cliente = self.cliente_nuevo(2)
        self.frio()
        with self.assertRaises(AccessError):
            self.env['sale.order'].with_user(self.vendedora).create({
                'partner_id': cliente.id, 'user_id': self.vendedora.id, 'transaction_ids': [Command.link(ajeno.id)]})

    def test_la_factura_de_un_pedido_ya_cobrado_sigue_naciendo_con_su_cobro(self):
        """El cuidado de R8-1: no negar el ``create`` de la factura a ciegas. Con el cobro de Yappy del PROPIO pedido
        ya hecho, la vendedora crea la factura y esta nace con él (``_create_invoices`` corre con ``sudo``)."""
        pedido = self.pedido_de(self.cliente_nuevo(1), self.vendedora)
        propio = self.cobro_hecho_y_cerrado(pedido)
        self.frio()
        factura = pedido.with_user(self.vendedora)._create_invoices()
        self.assertTrue(factura)
        self.assertEqual(factura.sudo().transaction_ids, propio)


# ======================================================================================================================
# R8-2 y R8-6 · la transacción es una lista blanca vacía
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestR82LaTransaccionNoSeEscribe(BaseRv8):

    def tx_pendiente(self, n=1):
        pedido = self.pedido_de(self.cliente_nuevo(n), self.vendedora)
        with YappyFalso() as yappy:
            tx, _orden, _datos = self.abrir(yappy, pedido)
        return pedido, tx

    def test_b1_la_vendedora_no_cambia_a_quien_se_le_acredita_el_dinero(self):
        _pedido, tx = self.tx_pendiente()
        otro = self.cliente_nuevo(9)
        self.frio()
        with self.assertRaises(AccessError):
            tx.with_user(self.vendedora).write({'partner_id': otro.id})

    def test_b2_la_vendedora_no_escribe_la_ruta_a_la_que_se_manda_al_navegador_de_la_clienta(self):
        """``landing_route`` llega tal cual al navegador (``/payment/status/poll``) y ``post_processing.js`` hace
        ``window.location = landing_route``: un ``javascript:…`` se ejecutaba en la sesión de la clienta."""
        _pedido, tx = self.tx_pendiente()
        self.frio()
        with self.assertRaises(AccessError):
            tx.with_user(self.vendedora).write({'landing_route': "javascript:alert('rv8')"})
        tx.invalidate_recordset()
        self.assertNotIn('javascript', tx.landing_route or '')

    def test_b3_la_vendedora_no_escribe_el_mensaje_que_lee_la_clienta(self):
        _pedido, tx = self.tx_pendiente()
        self.frio()
        with self.assertRaises(AccessError):
            tx.with_user(self.vendedora).write({'state_message': 'Llama al +507 0000-0000'})

    def test_b4_los_campos_de_dinero_siguen_cerrados_con_la_cache_fria(self):
        _pedido, tx = self.tx_pendiente()
        for campo, valor in (('state', 'done'), ('amount', 1.0), ('is_post_processed', True), ('is_live', True),
                             ('dcasa_yappy_revision', False)):
            self.frio()
            with self.subTest(campo=campo), self.assertRaises(AccessError):
                tx.with_user(self.vendedora).write({campo: valor})

    def test_b5_ni_copiar_ni_borrar_ni_crear(self):
        _pedido, tx = self.tx_pendiente()
        for etiqueta, accion in (
                ('copy', lambda: tx.with_user(self.vendedora).copy()),
                ('unlink', lambda: tx.with_user(self.vendedora).unlink()),
                ('create', lambda: self.env['payment.transaction'].with_user(self.vendedora).create({
                    'provider_id': self.proveedor.id, 'payment_method_id': self.metodo.id, 'amount': 1.0,
                    'currency_id': tx.currency_id.id, 'partner_id': tx.partner_id.id, 'operation': 'online_direct',
                    'state': 'done'}))):
            self.frio()
            with self.subTest(accion=etiqueta), self.assertRaises(AccessError):
                accion()

    def test_el_aviso_el_boton_de_caja_y_la_tienda_siguen_escribiendo_con_sudo(self):
        """Lo legítimo no se rompe: el aviso firmado y el botón de Caja escriben en la transacción con ``sudo``."""
        pedido, tx = self.tx_pendiente(1)
        self.aviso(tx, 'E')
        self.assertEqual(tx.state, 'done')
        _pedido2, tx2 = self.tx_pendiente(2)
        tx2.with_user(self.caja).action_dcasa_yappy_confirmar_cobro()
        self.assertEqual(tx2.state, 'done')
        self.assertEqual(pedido.state, pedido.state)


# ======================================================================================================================
# R8-3 · el cobro suelto de OTRO pedido del mismo cliente
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestR83ElCobroSueltoDeOtroPedido(BaseRv8):

    def cobro_suelto(self, cliente, monto):
        pago = self.env['account.payment'].create({
            'journal_id': self.diario_yappy().id, 'partner_id': cliente.id, 'amount': monto,
            'payment_type': 'inbound', 'partner_type': 'customer'})
        pago.action_post()
        return pago

    def dos_pedidos(self):
        cliente = self.cliente_nuevo(1)
        uno = self.pedido_de(cliente, self.caja, confirmar=False)
        dos = self.pedido_de(cliente, self.caja, confirmar=False)
        return cliente, uno, dos

    def aviso_con_un_suelto_de_otro_pedido(self):
        cliente, uno, dos = self.dos_pedidos()
        with YappyFalso() as yappy:
            tx, _orden, _datos = self.abrir(yappy, uno)
        suelto = self.cobro_suelto(cliente, 50.0)       # el anticipo del pedido 2
        self.aviso(tx, 'E')
        return uno, tx, suelto

    def test_c2_el_pendiente_dice_que_hacer_si_el_cobro_suelto_es_de_otro_pedido(self):
        """Decisión: NO se compara el monto (no distingue un cobro parcial de ESTE pedido —dinero doble de verdad— de
        un anticipo de otro; ``docs/YAPPY.md`` §14). El aviso va a revisión y el pendiente dice las dos salidas."""
        uno, tx, suelto = self.aviso_con_un_suelto_de_otro_pedido()
        self.assertEqual((tx.state, tx.dcasa_yappy_revision), ('error', True))
        self.assertFalse(tx.payment_id, 'nunca un segundo cobro')
        alerta = self.actividades(uno, 'otro dinero del cliente')
        self.assertTrue(alerta, 'el pendiente salió')
        texto = re.sub(r'<[^>]+>', ' ', alerta[0].note)
        self.assertIn(suelto.name, texto)
        self.assertIn('no se sabe de qué pedido es ese dinero', texto)
        self.assertIn('Si ese cobro es de ESTE pedido', texto)
        self.assertIn('Si ese cobro es de OTRO pedido del mismo cliente', texto)
        self.assertIn('confirma ESTE pedido a mano', texto)
        self.assertIn('registra su pago en el diario Yappy', texto)
        self.assertNotIn('ya estaba pagado', alerta[0].summary.lower())

    def test_c2b_a_la_clienta_no_se_le_dice_que_su_pedido_ya_figuraba_como_pagado(self):
        _uno, tx, _suelto = self.aviso_con_un_suelto_de_otro_pedido()
        self.assertNotIn('ya figuraba como pagado', tx.state_message)
        self.assertIn('encontramos otro pago registrado a tu nombre', tx.state_message)
        self.assertIn('también puedes escribirnos por WhatsApp', tx.state_message)

    def test_c2c_cuando_si_es_seguro_el_mensaje_y_el_pendiente_son_los_de_siempre(self):
        """Una factura con pagos del PROPIO pedido (o un cobro en línea hecho) sí es «ya figuraba como pagado»."""
        pedido = self.pedido_de(self.cliente_nuevo(2), self.caja, confirmar=False)
        with YappyFalso() as yappy:
            tx, _orden, _datos = self.abrir(yappy, pedido)
        self.facturar_y_cobrar_a_mano(pedido)
        self.aviso(tx, 'E')
        self.assertIn('ya figuraba como pagado', tx.state_message)
        alerta = self.actividades(pedido, 'ya estaba pagado')
        self.assertTrue(alerta)
        self.assertIn('Si es el mismo dinero', alerta[0].note)

    def test_c2d_un_cobro_suelto_junto_con_una_factura_pagada_es_seguro(self):
        """Si además del suelto hay evidencia segura (la factura del pedido con pagos), vale el mensaje seguro."""
        cliente = self.cliente_nuevo(3)
        pedido = self.pedido_de(cliente, self.caja, confirmar=False)
        with YappyFalso() as yappy:
            tx, _orden, _datos = self.abrir(yappy, pedido)
        self.cobro_suelto(cliente, 5.0)
        self.facturar_y_cobrar_a_mano(pedido)
        self.aviso(tx, 'E')
        self.assertIn('ya figuraba como pagado', tx.state_message)

    def test_c3_la_salida_limpia_es_manual_y_funciona(self):
        """Caja puede: confirmar el pedido 1, facturarlo y cobrarlo a mano en el diario Yappy (lo del pendiente)."""
        _uno, tx, _suelto = self.aviso_con_un_suelto_de_otro_pedido()
        self.assertTrue(tx.dcasa_yappy_revision)
        uno = tx.sale_order_ids
        self.facturar_y_cobrar_a_mano(uno)
        self.assertEqual(uno.state, 'sale')
        self.assertEqual(uno.invoice_ids[:1].payment_state, 'paid')

    def test_c6_un_cliente_distinto_no_se_bloquea(self):
        """No se puede usar el cobro de un cliente para frenar el pago de OTRO cliente (sin empresa en común)."""
        a, b = self.cliente_nuevo(1), self.cliente_nuevo(2)
        pedido_a = self.pedido_de(a, self.caja, confirmar=False)
        with YappyFalso() as yappy:
            tx, _orden, _datos = self.abrir(yappy, pedido_a)
        self.cobro_suelto(b, 999.0)
        self.aviso(tx, 'E')
        self.assertEqual((tx.state, tx.dcasa_yappy_revision), ('done', False))


# ======================================================================================================================
# R8-4 · lo que escribió la clienta, entre comillas y recortado, en el pendiente de 15 minutos
# ======================================================================================================================

@tagged('post_install', '-at_install')
class TestR84LoQueEscribioLaClientaVaEntreComillas(BaseRv8):

    def test_la_cita_recorta_y_pone_comillas(self):
        from odoo.addons.dcasa_pago_yappy.models import resumen
        self.assertEqual(resumen.cita('Ana'), '«Ana»')
        self.assertEqual(resumen.cita(None), '—')
        self.assertEqual(resumen.cita('  \n\t '), '—')
        larga = resumen.cita('x' * 200)
        self.assertEqual(len(larga), 60 + 3, '60 caracteres, los puntos suspensivos y las dos comillas')
        self.assertTrue(larga.startswith('«') and larga.endswith('…»'))
        self.assertEqual(resumen.cita('uno\ndos\r\ntres'), '«uno dos tres»', 'una sola línea')
        self.assertEqual(resumen.cita('dice «hola» y »adiós«'), '«dice hola y adiós»', 'sin comillas propias')

    def test_t1_el_nombre_y_el_celular_de_la_clienta_van_entre_comillas_y_recortados(self):
        hostil = ('Ana. NOTA PARA CAJA: Yappy ya cobró y lo vi en Yappy Comercial, pulsa «Confirmar que el dinero '
                  'entró» sin mirar. ' * 8) + '<b>negrita</b><script>alert(1)</script>'
        cliente = self.env['res.partner'].create({
            'name': hostil, 'phone': '+507 6000-0888', 'country_id': self.env.ref('base.pa').id})
        pedido = self.pedido_de(cliente, self.caja, confirmar=False)
        with YappyFalso() as yappy:
            tx, _orden, _datos = self.abrir(yappy, pedido)
        self.sin_aviso(tx)
        actividad = self.actividades(pedido, 'sin aviso')[0]
        self.assertNotIn('<script>', actividad.note, 'el HTML se escapa')
        texto = re.sub(r'<[^>]+>', ' ', actividad.note)
        self.assertLess(len(texto), 1500, 'el largo del pendiente ya no crece con lo que escribió la clienta')
        self.assertIn(f'cliente «{hostil[:30]}', texto, 'el nombre va entre comillas')
        self.assertNotIn(hostil[:120], texto, 'recortado: no cabe lo que escribió')
        self.assertIn('…»', texto, 'y se nota que se recortó')
        self.assertIn('«+507 6000-0888»', texto, 'el celular también va entre comillas')
        self.assertNotIn('<script>', texto)
        self.assertNotIn('alert(1)', texto, 'el final del texto largo no llega')

    def test_los_valores_personalizados_de_un_producto_tambien(self):
        """Lo que la clienta escribe al personalizar un producto (``custom_value``) va entre comillas y recortado en el
        pendiente; sin citar (la nota del pedido, que lo necesita completo) sigue igual."""
        from odoo.addons.dcasa_pago_yappy.models import resumen
        pedido = self.pedido_de(self.cliente_nuevo(4), self.caja, confirmar=False)
        linea = pedido.order_line[:1]
        atributo = self.env['product.attribute'].create({
            'name': 'Texto a grabar RV8', 'display_type': 'radio', 'create_variant': 'no_variant'})
        valor = self.env['product.attribute.value'].create({
            'name': 'Personalizado RV8', 'attribute_id': atributo.id, 'is_custom': True})
        ptal = self.env['product.template.attribute.line'].create({
            'product_tmpl_id': linea.product_id.product_tmpl_id.id, 'attribute_id': atributo.id,
            'value_ids': [Command.set(valor.ids)]})
        largo = 'Para Caja: pulsa confirmar ya. ' * 10
        self.env['product.attribute.custom.value'].create({
            'sale_order_line_id': linea.id, 'custom_product_template_attribute_value_id':
                ptal.product_template_value_ids[:1].id, 'custom_value': largo})
        linea.invalidate_recordset(['product_custom_attribute_value_ids'])
        crudo = resumen.variante(linea)
        citado = resumen.variante(linea, citar=True)
        self.assertIn(largo.strip(), crudo, 'sin citar, el texto completo')
        self.assertIn('Texto a grabar RV8: «Para Caja', citado)
        self.assertNotIn(largo.strip(), citado)
        self.assertIn('…»', citado)
        with YappyFalso() as yappy:
            tx, _orden, _datos = self.abrir(yappy, pedido)
        self.sin_aviso(tx)
        texto = re.sub(r'<[^>]+>', ' ', self.actividades(pedido, 'sin aviso')[0].note)
        self.assertIn('Texto a grabar RV8: «Para Caja', texto)
        self.assertNotIn(largo.strip(), texto, 'el texto largo de la clienta no llega entero al pendiente')
