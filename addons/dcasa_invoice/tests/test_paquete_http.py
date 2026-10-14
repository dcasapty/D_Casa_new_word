"""El PDF del «Imprimir documentos» por la web (/dcasa/paquete.pdf) y el botón en el navegador."""
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import HttpCase, tagged

from ..models import paquete
from ..wizard.impresion_paquete import DcasaImpresionPaquete
from .test_paquete import _renderizar_falso, textos

CLAVE = 'Prueba-123456'

# Dentro del navegador: abre la factura, toca «Imprimir documentos» → «Imprimir todo» y comprueba que el iframe
# oculto recibe el PDF y se llama a print() (el Chromium sin pantalla no puede mostrar el cuadro de impresión; lo que
# sí comprueba es que el navegador lo pidió con un PDF de verdad y sin guardar nada en Descargas).
CODIGO_IMPRIMIR = """
(async () => {
    const esperar = async (fn, que, ms = 40000) => {
        const inicio = Date.now();
        while (Date.now() - inicio < ms) {
            const r = fn();
            if (r) { return r; }
            await new Promise((ok) => setTimeout(ok, 100));
        }
        throw new Error("Imprimir documentos: no apareció " + que);
    };
    const llamadas = [];
    const descargas = [];
    const descriptor = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, "contentWindow");
    Object.defineProperty(HTMLIFrameElement.prototype, "contentWindow", {
        configurable: true,
        get() {
            const ventana = descriptor.get.call(this);
            if (!ventana || !this.classList.contains("o_dcasa_paquete_iframe")) { return ventana; }
            return new Proxy(ventana, {
                get: (destino, clave) => {
                    if (clave === "print") { return () => llamadas.push(this.src); }
                    if (clave === "focus") { return () => {}; }
                    const valor = destino[clave];
                    return typeof valor === "function" ? valor.bind(destino) : valor;
                },
            });
        },
    });
    const clic = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function () {
        if (this.download) { descargas.push(this.download); }
        return clic.call(this);
    };
    const boton = await esperar(() => [...document.querySelectorAll(".o_statusbar_buttons button")]
        .find((b) => b.textContent.trim() === "Imprimir documentos"), "el botón «Imprimir documentos»");
    boton.click();
    const imprimir = await esperar(() => [...document.querySelectorAll(".modal-footer button")]
        .find((b) => b.textContent.trim() === "Imprimir todo"), "el cuadro con «Imprimir todo»");
    const casillas = [...document.querySelectorAll(".modal .o_dcasa_paquete input[type=checkbox]")];
    if (casillas.length !== 3 || !casillas.every((c) => c.checked)) {
        throw new Error("Imprimir documentos: las 3 casillas deben venir marcadas");
    }
    const botones = [...document.querySelectorAll(".modal-footer button")].map((b) => b.textContent.trim());
    if (botones.join("|") !== "Imprimir todo|Descargar todo|Cancelar") {
        throw new Error("Imprimir documentos: botones inesperados " + botones.join("|"));
    }
    imprimir.click();
    await esperar(() => llamadas.length, "la llamada a print() del navegador");
    const respuesta = await fetch(llamadas[0]);
    const bytes = new Uint8Array(await respuesta.arrayBuffer());
    if (String.fromCharCode(...bytes.slice(0, 5)) !== "%PDF-") {
        throw new Error("Imprimir documentos: el iframe no recibió un PDF");
    }
    await esperar(() => !document.querySelector(".modal"), "que el cuadro se cierre solo");
    if (descargas.length) { throw new Error("Imprimir documentos: «Imprimir» no debe descargar archivos"); }
    console.log("test successful");
})().catch((e) => console.error(e.message || e));
"""


class PaqueteHttpComun(HttpCase):

    def setUp(self):
        super().setUp()
        self.cliente = self.env['res.partner'].create({
            'name': 'CLIENTE HTTP', 'country_id': self.env.ref('base.pa').id})
        self.mueble = self.env['product.product'].create({
            'name': 'CAMA HTTP', 'type': 'consu', 'is_storable': True, 'list_price': 100.0})
        self.vendedora = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Vendedora Http', 'login': 'paq_http_vendedora', 'password': CLAVE,
            'group_ids': [Command.set(
                [self.env.ref(g).id for g in ('base.group_user', 'dcasa_base.group_vendedora')])]})

    def _venta(self):
        pedido = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1})]})
        pedido.action_confirm()
        factura = pedido._create_invoices()
        factura.action_post()
        return pedido, factura

    def _factura_proveedor(self):
        factura = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.env['res.partner'].create({'name': 'PROVEEDOR HTTP'}).id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': 60.0})]})
        factura.action_post()
        return factura

    def _pedir(self, facturas, docs='cliente,copia,entrega'):
        ids = ','.join(str(f.id) for f in facturas)
        return self.url_open(f'/dcasa/paquete.pdf?facturas={ids}&docs={docs}', allow_redirects=False)


@tagged('post_install', '-at_install')
class TestPaqueteHttp(PaqueteHttpComun):

    def test_la_vendedora_recibe_un_pdf_con_las_paginas_esperadas(self):
        pedido, factura = self._venta()
        _otro, factura2 = self._venta()
        self.authenticate('paq_http_vendedora', CLAVE)
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            respuesta = self._pedir(factura)
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.headers['Content-Type'], 'application/pdf')
            self.assertTrue(respuesta.headers['Content-Disposition'].startswith('inline'), 'se abre en el visor')
            self.assertIn('Documentos-', respuesta.headers['Content-Disposition'])
            self.assertEqual(respuesta.headers['Cache-Control'], 'no-store')
            self.assertTrue(respuesta.content.startswith(b'%PDF'))
            paginas = textos(respuesta.content)
            self.assertEqual(len(paginas), 3)
            self.assertIn(pedido.picking_ids.name, paginas[2])
            # Varias ventas: tres documentos por cada una.
            lote = self._pedir(factura | factura2)
            self.assertEqual((lote.status_code, len(textos(lote.content))), (200, 6))
            # Solo lo que se pide.
            self.assertEqual(len(textos(self._pedir(factura, 'cliente').content)), 1)

    def test_la_vendedora_no_recibe_la_factura_de_un_proveedor(self):
        proveedor = self._factura_proveedor()
        self.authenticate('paq_http_vendedora', CLAVE)
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            respuesta = self._pedir(proveedor, 'cliente,copia')
        self.assertEqual(respuesta.status_code, 403)
        self.assertNotEqual(respuesta.headers['Content-Type'], 'application/pdf')
        self.assertIn('No tienes permiso', respuesta.text)

    def test_un_usuario_del_portal_no_obtiene_el_paquete_ni_de_su_propia_factura(self):
        _pedido, factura = self._venta()
        self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Portal Http', 'login': 'paq_http_portal', 'password': CLAVE,
            'partner_id': self.cliente.id, 'group_ids': [Command.set([self.env.ref('base.group_portal').id])]})
        self.authenticate('paq_http_portal', CLAVE)
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            respuesta = self._pedir(factura)
        self.assertEqual(respuesta.status_code, 403)
        self.assertNotEqual(respuesta.headers['Content-Type'], 'application/pdf')

    def test_sin_iniciar_sesion_no_sale_nada(self):
        _pedido, factura = self._venta()
        self.authenticate(None, None)
        respuesta = self._pedir(factura)
        self.assertNotEqual(respuesta.status_code, 200)
        self.assertNotEqual(respuesta.headers.get('Content-Type'), 'application/pdf')

    def test_pedidos_mal_hechos_dan_un_mensaje_claro(self):
        _pedido, factura = self._venta()
        self.authenticate('paq_http_vendedora', CLAVE)
        for url, texto in (
                ('/dcasa/paquete.pdf?facturas=abc&docs=cliente', 'no son válidos'),
                ('/dcasa/paquete.pdf?docs=cliente', 'ninguna factura'),
                (f'/dcasa/paquete.pdf?facturas={factura.id}&docs=', 'Marca al menos un documento'),
                (f'/dcasa/paquete.pdf?facturas={factura.id}&docs=otra_cosa', 'Marca al menos un documento'),
        ):
            respuesta = self.url_open(url, allow_redirects=False)
            self.assertEqual(respuesta.status_code, 400, url)
            self.assertIn(texto, respuesta.text)

    def test_el_tope_responde_con_un_mensaje_y_no_arma_nada(self):
        facturas = self.env['account.move']
        for _n in range(3):
            facturas |= self._venta()[1]
        self.authenticate('paq_http_vendedora', CLAVE)
        with patch.object(paquete, 'MAX_FACTURAS', 2), \
                patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            respuesta = self._pedir(facturas)
            self.assertEqual(respuesta.status_code, 400)
            self.assertIn('el máximo por paquete es 2', respuesta.text)
            self.assertEqual(self._pedir(facturas[:2]).status_code, 200)

    def test_una_factura_en_borrador_o_inexistente_no_se_imprime(self):
        pedido = self.env['sale.order'].create({
            'partner_id': self.cliente.id,
            'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1})]})
        pedido.action_confirm()
        borrador = pedido._create_invoices()
        self.authenticate('paq_http_vendedora', CLAVE)
        respuesta = self._pedir(borrador)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('No hay facturas de clientes publicadas', respuesta.text)
        respuesta = self.url_open('/dcasa/paquete.pdf?facturas=999999999&docs=cliente', allow_redirects=False)
        self.assertEqual(respuesta.status_code, 400)


@tagged('post_install', '-at_install')
class TestPaqueteEnElNavegador(PaqueteHttpComun):

    def test_imprimir_pide_el_pdf_y_llama_a_print_sin_guardar_nada(self):
        _pedido, factura = self._venta()
        with patch.object(DcasaImpresionPaquete, '_pdfs_por_registro', _renderizar_falso):
            self.browser_js(f'/odoo/action-account.action_move_out_invoice_type/{factura.id}', CODIGO_IMPRIMIR,
                            ready='odoo.isReady', login='admin', timeout=120)
