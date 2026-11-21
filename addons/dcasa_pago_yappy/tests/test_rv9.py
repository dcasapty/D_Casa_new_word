"""La quinta vuelta (RV8b, R9-1 a R9-4) del dinero y los permisos del pago en línea, sobre los arreglos de RV8. Las
pruebas «rojas» del revisor independiente están aquí ADAPTADAS: ya no demuestran el hallazgo, comprueban que el arreglo
se sostiene. Las genéricas (de cualquier proveedor, sin Yappy ni Bodega) viven en
``dcasa_base/tests/test_transaccion_de_pago.py``; aquí, con Yappy de verdad y con lo que ve Bodega.

* R9-1: el pedido no nace con un cobro ajeno puesto por ``default_transaction_ids`` del contexto (y con él, Bodega
  soltaba la entrega sin cobrar).
* R9-2: crear a mano un recibo con el cobro de otro, volverlo factura y que Caja lo publique (el dinero de A pagaba la
  factura suelta de C).
* R9-4: la cita de lo que escribió la clienta no deja caracteres de formato (los bidireccionales reordenan el párrafo).

Datos inventados; ninguna prueba toca la red. Los errores a propósito se capturan con ``assertLogs`` (el CI cuenta como
falla toda línea de registro ERROR).
"""
import unicodedata

from odoo import Command
from odoo.addons.dcasa_pago_yappy.models import resumen
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .test_rv8 import BaseRv8


@tagged('post_install', '-at_install')
class TestR91ElContextoNoLigaCobros(BaseRv8):

    def ajeno(self, n=1):
        return self.cobro_hecho_y_cerrado(self.pedido_de(self.cliente_nuevo(n), self.caja))

    def crear_con_contexto(self, comando, usuario=None, **extra):
        self.frio()
        return self.env['sale.order'].with_user(usuario or self.vendedora).with_context(
            default_transaction_ids=[comando]).create({
                'partner_id': self.cliente_nuevo(2).id, 'user_id': (usuario or self.vendedora).id,
                'website_id': self.website.id, **extra})

    def test_r1_el_pedido_no_nace_con_un_cobro_ajeno_puesto_por_el_contexto(self):
        ajeno = self.ajeno()
        for comando in (Command.link(ajeno.id), Command.set([ajeno.id])):
            for usuario in (self.vendedora, self.facturacion):
                with self.subTest(usuario=usuario.login, comando=comando[0]), self.assertRaises(AccessError):
                    self.crear_con_contexto(comando, usuario)

    def test_r1b_con_ese_pedido_bodega_ya_no_suelta_la_entrega_sin_cobrar(self):
        """La consecuencia física del hallazgo: el pedido nacía «pagado» con el cobro de otro y Bodega validaba la
        entrega sin cobrar. Ahora el pedido ni nace."""
        bodega = self.bodega()
        ajeno = self.ajeno()
        nuevo = self.env['sale.order']
        try:
            nuevo = self.crear_con_contexto(
                Command.set([ajeno.id]),
                order_line=[Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})])
        except AccessError:
            pass
        self.assertFalse(nuevo, 'el pedido no nació')
        pedido = self.pedido_de(self.cliente_nuevo(3), self.vendedora)
        self.assertEqual(bodega._pagos_de_pedidos(pedido)[pedido.id], 'sin_pago')
        with self.assertRaises(UserError):
            bodega._exigir_pago(pedido.picking_ids[:1])

    def test_quien_cobra_si_puede(self):
        ajeno = self.ajeno()
        pedido = self.crear_con_contexto(Command.link(ajeno.id), self.caja)
        self.assertIn(ajeno, pedido.sudo().transaction_ids)


@tagged('post_install', '-at_install')
class TestR92LaFacturaNoSeCreaConElCobroDeOtro(BaseRv8):

    def crear_recibo(self, usuario, ajeno, cliente):
        self.frio()
        return self.env['account.move'].with_user(usuario).create({
            'move_type': 'out_receipt', 'partner_id': cliente.id, 'transaction_ids': [Command.link(ajeno.id)],
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1, 'price_unit': 107.0})]})

    def ajeno(self):
        return self.cobro_hecho_y_cerrado(self.pedido_de(self.cliente_nuevo(1), self.caja))

    def test_r2_quien_no_cobra_no_crea_un_recibo_con_el_cobro_de_otro(self):
        ajeno = self.ajeno()
        for usuario in (self.vendedora, self.facturacion):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.crear_recibo(usuario, ajeno, self.cliente_nuevo(2))

    def test_r3_ni_el_recibo_se_vuelve_factura_ni_nota_de_credito(self):
        """El camino completo del revisor: crear (recibo) + cambiar el tipo. Los dos pasos están cerrados: el primero
        por el cobro ligado, el segundo por el tipo (probado sin cobro, que sí se podía crear)."""
        ajeno = self.ajeno()
        cliente = self.cliente_nuevo(3)
        with self.assertRaises(AccessError):
            self.crear_recibo(self.vendedora, ajeno, cliente)
        self.frio()
        recibo = self.env['account.move'].with_user(self.vendedora).create({
            'move_type': 'out_receipt', 'partner_id': cliente.id,
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1, 'price_unit': 107.0})]})
        for tipo in ('out_invoice', 'out_refund'):
            self.frio()
            with self.subTest(tipo=tipo), self.assertRaises(AccessError):
                recibo.with_user(self.vendedora).write({'move_type': tipo})

    def test_r3b_la_cadena_caja_publica_y_el_dinero_de_a_no_paga_ninguna_factura_de_c(self):
        ajeno = self.ajeno()
        cliente = self.cliente_nuevo(3)
        try:
            recibo = self.crear_recibo(self.vendedora, ajeno, cliente)
            self.frio()
            recibo.with_user(self.vendedora).write({'move_type': 'out_invoice'})
        except AccessError:
            return
        self.frio()
        recibo.with_user(self.caja).action_post()
        self.frio()
        self.assertEqual(ajeno.payment_id.sudo().reconciled_invoice_ids, self.env['account.move'],
                         f'el cobro de A quedó aplicado a la factura suelta de C: {recibo.sudo().payment_state}')

    def test_la_factura_de_un_pedido_ya_cobrado_con_yappy_sigue_naciendo_con_su_cobro(self):
        pedido = self.pedido_de(self.cliente_nuevo(1), self.vendedora)
        propio = self.cobro_hecho_y_cerrado(pedido)
        self.frio()
        factura = pedido.with_user(self.vendedora)._create_invoices()
        self.assertEqual(factura.sudo().transaction_ids, propio)


@tagged('post_install', '-at_install')
class TestR94LaCitaNoDejaCaracteresDeFormato(BaseRv8):

    # Los caracteres invisibles se arman con chr(): un archivo con ellos escritos tal cual (o con \uXXXX mal puesto) no
    # se puede revisar a simple vista.
    ZWSP, RLO, LRI, PDI, BOM, SHY = chr(0x200B), chr(0x202E), chr(0x2066), chr(0x2069), chr(0xFEFF), chr(0x00AD)
    HOSTILES = {
        'bidireccional RLO': f'Ana{RLO} etnemalaer odagap',
        'bidireccional aislado': f'Ana{ZWSP}{LRI}pulsa confirmar{PDI}',
        'BOM': f'Ana{BOM} Co',
        'guion suave': f'Con{SHY}fir{SHY}mar',
        'control': 'Ana\x07\x1b[31mroja',
    }

    def test_t3_la_cita_quita_los_caracteres_de_formato_y_de_control(self):
        """Los bidireccionales (U+202E, U+2066…) reordenan en pantalla lo que sigue en el mismo párrafo del pendiente
        (incluida «El sistema no pagó ni canceló nada solo»); los de ancho cero (U+200B, U+FEFF) esconden texto."""
        for nombre, hostil in self.HOSTILES.items():
            salida = resumen.cita(hostil)
            with self.subTest(hostil=nombre):
                raros = [letra for letra in salida if unicodedata.category(letra) in ('Cf', 'Cc')]
                self.assertFalse(raros, f'quedaron caracteres de formato o de control dentro de la cita: {salida!r}')
                self.assertTrue(salida.startswith('«') and salida.endswith('»'))

    def test_el_texto_legible_se_conserva_y_los_acentos_tambien(self):
        self.assertEqual(resumen.cita(f'Ana{self.ZWSP} María{self.RLO} Núñez'), '«Ana María Núñez»')
        self.assertEqual(resumen.cita(f'{self.ZWSP}{self.BOM}'), '—', 'solo había caracteres de formato: queda vacía')
        self.assertEqual(resumen.cita(f'a{self.ZWSP}b'), '«ab»')
