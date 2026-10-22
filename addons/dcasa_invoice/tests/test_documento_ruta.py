"""``/dcasa/doc/<TIPO>/<REFERENCIA>``: lo que abre el QR de uso interno (con la cámara del teléfono).

Se comprueba de punta a punta con HTTP de verdad: con sesión y permiso redirige al documento; sin sesión manda a la
pantalla de entrada y vuelve; sin permiso o si no existe, un aviso claro (403 / 404) que no revela NADA del documento.
"""
import re
from urllib.parse import parse_qs, quote, urlsplit

from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged

from .documentos import DocumentosDePrueba

GRUPOS_DEL_EQUIPO = ('account.group_account_invoice,sales_team.group_sale_manager,purchase.group_purchase_user,'
                     'stock.group_stock_user')
ACCIONES = {
    'FAC': 'account.action_move_out_invoice_type', 'COT': 'sale.action_quotations_with_onboarding',
    'COM': 'purchase.purchase_form_action', 'ENT': 'stock.action_picking_tree_all',
}


@tagged('post_install', '-at_install')
class TestDocumentoRuta(DocumentosDePrueba, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.equipo = new_test_user(cls.env, login='qr_equipo', groups=GRUPOS_DEL_EQUIPO)
        cls.vendedora_b = new_test_user(cls.env, login='qr_vendedora_b', groups='sales_team.group_sale_salesman')
        cls.sin_permisos = new_test_user(cls.env, login='qr_sin_permisos', groups='base.group_user')
        cls.portal = new_test_user(cls.env, login='qr_portal', groups='base.group_portal')
        proveedor = cls.env['res.partner'].create({'name': 'PROVEEDOR SECRETO, S.A.'})
        cls.compra = cls.env['purchase.order'].create({
            'partner_id': proveedor.id,
            'order_line': [Command.create({'product_id': cls.colchon.id, 'product_qty': 3, 'price_unit': 60.0})]})
        cls.compra.button_confirm()
        cls.factura = cls.factura_completa()
        cls.pedido = cls.cotizacion()
        cls.entrega_doc = cls.entrega()
        cls.todos = {'FAC': cls.factura, 'COT': cls.pedido, 'COM': cls.compra, 'ENT': cls.entrega_doc}

    def ir(self, tipo, referencia, **kw):
        kw.setdefault('allow_redirects', False)
        return self.url_open(f'/dcasa/doc/{tipo}/{referencia}', **kw)

    def assertNoRevelaNada(self, respuesta, con_numeros=True):
        """Ni el cliente, ni el proveedor, ni los importes, ni los números del documento salen en el aviso."""
        secretos = ['CLIENTE DE PRUEBA', 'PROVEEDOR SECRETO', 'Casa de Karen', '8-000-0000', '352.63', '81.99']
        if con_numeros:    # (al mandar al login, la dirección que pidió quien escaneó vuelve en la redirección)
            secretos += [self.factura.name, self.pedido.name, self.compra.name, self.entrega_doc.name]
        for secreto in secretos:
            self.assertNotIn(secreto, respuesta.text, secreto)

    # --- Con sesión y permiso ------------------------------------------------------------------------------

    def test_con_permiso_redirige_al_formulario_de_cada_documento(self):
        self.authenticate('qr_equipo', 'qr_equipo')
        for tipo, registro in self.todos.items():
            respuesta = self.ir(tipo, registro.name)
            self.assertEqual(respuesta.status_code, 302, tipo)
            destino = f'/odoo/action-{self.env.ref(ACCIONES[tipo]).id}/{registro.id}'
            if tipo == 'ENT' and 'dcasa.bodega' in self.env:
                # Con dcasa_barras instalado, la nota de entrega se abre en el panel de Bodega para quien usa
                # Inventario (decisión de la dueña, 2026-10-22); qr_equipo lo usa. Sin dcasa_barras, su formulario.
                destino = f'/odoo/bodega/{registro.id}'
            self.assertEqual(urlsplit(respuesta.headers['Location']).path, destino, tipo)
            self.assertIn('no-store', respuesta.headers['Cache-Control'])

    def test_las_referencias_con_barras_y_distintas_formas_de_escribirlas(self):
        self.authenticate('qr_equipo', 'qr_equipo')
        destino = f'/odoo/action-{self.env.ref(ACCIONES["FAC"]).id}/{self.factura.id}'
        self.assertIn('/', self.factura.name)
        for ruta in (self.factura.name, quote(self.factura.name, safe=''), self.factura.name + '/'):
            respuesta = self.ir('FAC', ruta)
            self.assertEqual(respuesta.status_code, 302, ruta)
            self.assertEqual(urlsplit(respuesta.headers['Location']).path, destino, ruta)
        # El tipo en minúsculas y la referencia sin distinguir mayúsculas (un lector puede invertirlas).
        self.assertEqual(self.ir('fac', self.factura.name.lower()).status_code, 302)
        self.assertEqual(self.ir('ent', self.entrega_doc.name).status_code, 302)

    def test_se_abre_de_verdad_la_pantalla_del_documento(self):
        self.authenticate('qr_equipo', 'qr_equipo')
        respuesta = self.ir('COT', self.pedido.name, allow_redirects=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(urlsplit(respuesta.url).path,
                         f'/odoo/action-{self.env.ref(ACCIONES["COT"]).id}/{self.pedido.id}')

    def test_un_pedido_confirmado_abre_en_pedidos(self):
        self.authenticate('qr_equipo', 'qr_equipo')
        confirmado = self.cotizacion()
        confirmado.action_confirm()
        respuesta = self.ir('COT', confirmado.name)
        self.assertEqual(urlsplit(respuesta.headers['Location']).path,
                         f'/odoo/action-{self.env.ref("sale.action_orders").id}/{confirmado.id}')

    def test_una_nota_de_credito_abre_en_notas_de_credito(self):
        self.authenticate('qr_equipo', 'qr_equipo')
        nota = self.factura_completa(abono=0)._reverse_moves([{'invoice_date': '2026-10-14', 'date': '2026-10-14'}])
        nota.action_post()
        respuesta = self.ir('FAC', nota.name)
        self.assertEqual(urlsplit(respuesta.headers['Location']).path,
                         f'/odoo/action-{self.env.ref("account.action_move_out_refund_type").id}/{nota.id}')

    # --- Sin sesión: login y vuelve --------------------------------------------------------------------------

    def test_sin_sesion_manda_al_login_y_vuelve(self):
        ruta = f'/dcasa/doc/FAC/{self.factura.name}'
        respuesta = self.url_open(ruta, allow_redirects=False)
        self.assertIn(respuesta.status_code, (302, 303))
        destino = urlsplit(respuesta.headers['Location'])
        self.assertEqual(destino.path, '/web/login')
        self.assertEqual(parse_qs(destino.query)['redirect'][0].rstrip('?'), ruta)
        # Al entrar, vuelve al documento y lo abre.
        pantalla = self.url_open('/web/login?' + destino.query)
        token = re.search(r'name="csrf_token" value="([^"]+)"', pantalla.text).group(1)
        entrada = self.url_open('/web/login?' + destino.query, data={
            'login': 'qr_equipo', 'password': 'qr_equipo', 'csrf_token': token})
        self.assertEqual(entrada.status_code, 200)
        self.assertEqual(urlsplit(entrada.url).path,
                         f'/odoo/action-{self.env.ref(ACCIONES["FAC"]).id}/{self.factura.id}')

    def test_sin_sesion_no_se_ve_nada_del_documento(self):
        respuesta = self.url_open(f'/dcasa/doc/COT/{self.pedido.name}', allow_redirects=False)
        self.assertNoRevelaNada(respuesta, con_numeros=False)

    # --- Sin permiso -----------------------------------------------------------------------------------------

    def test_sin_permiso_sobre_el_documento_es_403_y_no_revela_nada(self):
        """Una vendedora ve sus propias cotizaciones: la de otra existe, pero ella no puede abrirla."""
        self.authenticate('qr_vendedora_b', 'qr_vendedora_b')
        respuesta = self.ir('COT', self.pedido.name)
        self.assertEqual(respuesta.status_code, 403)
        self.assertIn('No tienes permiso', respuesta.text)
        self.assertIn('no-store', respuesta.headers['Cache-Control'])
        self.assertNoRevelaNada(respuesta)

    def test_sin_permiso_sobre_el_tipo_de_documento_es_403_exista_o_no(self):
        """Quien no puede leer ese tipo de documento recibe lo mismo, exista la referencia o no."""
        self.authenticate('qr_sin_permisos', 'qr_sin_permisos')
        for tipo, registro in self.todos.items():
            existe, no_existe = self.ir(tipo, registro.name), self.ir(tipo, 'NO-EXISTE-999')
            self.assertEqual((existe.status_code, no_existe.status_code), (403, 403), tipo)
            self.assertEqual(existe.text, no_existe.text, tipo)
            self.assertNoRevelaNada(existe)

    def test_un_cliente_del_portal_no_abre_nada_por_aqui(self):
        self.authenticate('qr_portal', 'qr_portal')
        existe, no_existe = self.ir('FAC', self.factura.name), self.ir('FAC', 'INV/2099/99999')
        self.assertEqual((existe.status_code, no_existe.status_code), (403, 403))
        self.assertEqual(existe.text, no_existe.text)
        self.assertNoRevelaNada(existe)

    # --- No existe -----------------------------------------------------------------------------------------------

    def test_si_no_existe_es_404_con_aviso_claro(self):
        self.authenticate('qr_equipo', 'qr_equipo')
        for tipo, referencia in (('FAC', 'INV/2099/99999'), ('COT', 'S99999'), ('COM', 'P99999'),
                                 ('ENT', 'WH/OUT/99999'), ('XXX', 'S00001'), ('FAC', 'x' * 200)):
            respuesta = self.ir(tipo, referencia)
            self.assertEqual(respuesta.status_code, 404, (tipo, referencia))
            self.assertIn('No encontramos el documento', respuesta.text)
            self.assertIn('Ir al sistema', respuesta.text)
            self.assertNoRevelaNada(respuesta)

    def test_una_factura_de_proveedor_no_se_abre_con_el_tipo_factura(self):
        """FAC es solo factura o nota de crédito de CLIENTE: las de proveedores no llevan QR."""
        self.authenticate('qr_equipo', 'qr_equipo')
        proveedor = self.env['res.partner'].create({'name': 'OTRO PROVEEDOR'})
        compra = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': proveedor.id, 'invoice_date': '2026-10-14',
            'invoice_line_ids': [Command.create({'name': 'Mercancía', 'quantity': 1, 'price_unit': 50})]})
        compra.action_post()
        self.assertEqual(self.ir('FAC', compra.name).status_code, 404)

    def test_lo_escrito_en_la_ruta_no_se_repite_en_la_pagina(self):
        self.authenticate('qr_equipo', 'qr_equipo')
        respuesta = self.ir('FAC', quote('<script>alert(1)</script>', safe=''))
        self.assertEqual(respuesta.status_code, 404)
        self.assertNotIn('<script>alert', respuesta.text)
        self.assertNotIn('alert(1)', respuesta.text)
        self.assertTrue(re.search(r'<title>[^<]+</title>', respuesta.text))

    def test_solo_se_pide_con_get(self):
        self.authenticate('qr_equipo', 'qr_equipo')
        respuesta = self.url_open(f'/dcasa/doc/FAC/{self.factura.name}', data={'x': '1'}, allow_redirects=False)
        self.assertEqual(respuesta.status_code, 405)
