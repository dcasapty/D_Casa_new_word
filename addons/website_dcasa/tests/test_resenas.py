"""Opiniones de productos (lote 2 de la web): reales, de quien compró y pagó, y publicadas solo si Gerencia las aprueba.

* Opina solo quien tiene el producto en una factura suya publicada y pagada por completo; una vez por producto.
* Nadie las crea ni las cambia a mano; un portal, una vendedora o el público no las aprueban ni las leen.
* En la ficha y en ``aggregateRating`` cuentan solo las publicadas: cero publicadas = nada.
"""
import json
import re

from odoo import Command, fields
from odoo.addons.website_dcasa.models.resena import LARGO_MAXIMO, limpiar_texto, nombre_publico
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

CLAVE_BORDE = 'dcasa_tienda_borde.pendientes'


class ResenasComun:

    @classmethod
    def preparar_resenas(cls):
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.website = cls.env.ref('website.default_website')
        Producto = cls.env['product.product']
        cls.sofa = Producto.create({'name': 'SOFÁ OPINIONES PRUEBA', 'type': 'consu', 'list_price': 300.0,
                                    'is_published': True, 'taxes_id': [Command.clear()]})
        cls.mesa = Producto.create({'name': 'MESA OPINIONES PRUEBA', 'type': 'consu', 'list_price': 100.0,
                                    'is_published': True, 'taxes_id': [Command.clear()]})
        cls.oculto = Producto.create({'name': 'MUEBLE NO PUBLICADO', 'type': 'consu', 'list_price': 50.0,
                                      'is_published': False, 'taxes_id': [Command.clear()]})
        cls.flete = Producto.create({'name': 'FLETE OPINIONES', 'type': 'service', 'list_price': 10.0,
                                     'is_published': True, 'taxes_id': [Command.clear()]})
        Partner = cls.env['res.partner']
        cls.lucia = Partner.create({'name': 'LUCÍA MARTÍNEZ PÉREZ', 'phone': '6200-3001',
                                    'email': 'lucia.opiniones@example.com'})
        cls.otro = Partner.create({'name': 'OTRO SIN COMPRAS', 'phone': '6200-3002'})
        # new_test_user le pone su nombre a la ficha si no se le da uno: se le da el de la ficha.
        cls.portal_lucia = new_test_user(cls.env, login='op_lucia', password='op-lucia-123', groups='base.group_portal',
                                         partner_id=cls.lucia.id, name=cls.lucia.name)
        cls.portal_otro = new_test_user(cls.env, login='op_otro', password='op-otro-123', groups='base.group_portal',
                                        partner_id=cls.otro.id, name=cls.otro.name)
        cls.gerente = new_test_user(cls.env, login='op_gerente', groups='base.group_user,dcasa_base.group_gerencia')
        cls.vendedora = new_test_user(cls.env, login='op_vendedora',
                                      groups='base.group_user,sales_team.group_sale_salesman')
        # Lucía: el sofá, el mueble no publicado y el flete pagados por completo; la mesa, en abono (a medias).
        cls.pagada = cls.factura(cls.lucia, [cls.sofa, cls.oculto, cls.flete])
        cls.pagar(cls.pagada)
        cls.a_medias = cls.factura(cls.lucia, [cls.mesa])
        cls.pagar(cls.a_medias, 40.0)

    @classmethod
    def factura(cls, cliente, productos):
        factura = cls.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': p.id, 'quantity': 1, 'price_unit': p.list_price,
                                                 'tax_ids': [Command.clear()]}) for p in productos]})
        factura.action_post()
        return factura

    @classmethod
    def pagar(cls, factura, monto=None):
        valores = {'payment_date': fields.Date.today()}
        if monto is not None:
            valores['amount'] = monto
        cls.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create(valores).action_create_payments()

    def opinar(self, cliente=None, producto=None, estrellas=5, texto='Llegó a tiempo y quedó muy bien.'):
        return self.env['dcasa.resena']._dcasa_crear_del_cliente(
            cliente or self.lucia, (producto or self.sofa).product_tmpl_id.id, estrellas, texto, website=self.website)


@tagged('post_install', '-at_install')
class TestResenasReglas(ResenasComun, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_resenas()

    def test_solo_lo_comprado_y_pagado_por_completo(self):
        self.assertIn(self.pagada.payment_state, ('paid', 'in_payment'))
        self.assertEqual(self.a_medias.payment_state, 'partial')
        por = self.env['dcasa.resena']._dcasa_por_resenar(self.lucia, website=self.website)
        self.assertEqual(list(por), [self.sofa.product_tmpl_id],
                         'Ni la mesa (en abono), ni lo que no está en la tienda, ni el flete')
        self.assertEqual(por[self.sofa.product_tmpl_id], self.pagada)
        self.assertEqual(self.env['dcasa.resena']._dcasa_por_resenar(self.otro, website=self.website), {})

    def test_queda_por_revisar_y_una_sola_vez(self):
        resena = self.opinar()
        self.assertEqual((resena.estado, resena.partner_id, resena.factura_id, resena.estrellas),
                         ('pendiente', self.lucia, self.pagada, 5))
        with self.assertRaises(UserError):
            self.opinar(estrellas=1)
        self.assertEqual(self.env['dcasa.resena']._dcasa_por_resenar(self.lucia, website=self.website), {})

    def test_quien_no_compro_o_no_pago_no_opina(self):
        for cliente, producto in ((self.otro, self.sofa), (self.lucia, self.mesa), (self.lucia, self.oculto),
                                  (self.lucia, self.flete)):
            with self.subTest(cliente=cliente.name, producto=producto.name), self.assertRaises(UserError):
                self.opinar(cliente, producto)
        with self.assertRaises(UserError):   # sin sesión
            self.env['dcasa.resena']._dcasa_crear_del_cliente(self.env['res.partner'], self.sofa.product_tmpl_id.id, 5)
        self.assertFalse(self.env['dcasa.resena'].sudo().search([]).filtered(
            lambda r: r.product_tmpl_id in (self.sofa | self.mesa | self.oculto | self.flete).product_tmpl_id))

    def test_un_contacto_de_la_empresa_opina_por_su_ficha(self):
        empresa = self.env['res.partner'].create({'name': 'Hotel Opiniones S.A.', 'is_company': True})
        contacto = self.env['res.partner'].create({'name': 'Marta Compras', 'parent_id': empresa.id})
        self.pagar(self.factura(empresa, [self.mesa]))
        resena = self.opinar(contacto, self.mesa)
        self.assertEqual(resena.partner_id, empresa)

    def test_estrellas_y_texto(self):
        for malas in (0, 6, 'x', None):
            with self.subTest(estrellas=malas), self.assertRaises(UserError):
                self.opinar(estrellas=malas)
        with self.assertRaises(UserError):
            self.opinar(texto='a' * (LARGO_MAXIMO + 1))
        resena = self.opinar(texto='  Muy   buena\x00 calidad.\r\n\n  La recomiendo  ')
        self.assertEqual(resena.texto, 'Muy buena calidad.\n\nLa recomiendo')
        self.assertEqual(limpiar_texto('\t\x07hola'), 'hola')

    def test_nombre_publico(self):
        self.assertEqual(nombre_publico('LUCÍA MARTÍNEZ PÉREZ'), 'Lucía M.')
        self.assertEqual(nombre_publico('ana'), 'Ana')
        self.assertEqual(nombre_publico(''), 'Cliente')
        self.assertEqual(self.opinar().nombre_publico, 'Lucía M.')

    def test_nadie_la_escribe_ni_la_cambia_a_mano(self):
        resena = self.opinar(estrellas=2)
        valores = {'partner_id': self.lucia.id, 'product_tmpl_id': self.mesa.product_tmpl_id.id, 'estrellas': 5}
        for usuario in (self.env.ref('base.user_admin'), self.gerente):
            Resena = self.env['dcasa.resena'].with_user(usuario)
            with self.subTest(usuario=usuario.login):
                with self.assertRaises(AccessError):
                    Resena.create(valores)
                # (AccessError es un UserError en Odoo: vale cualquiera de los dos)
                with self.assertRaises(UserError):
                    resena.with_user(usuario).write({'estrellas': 5})
                with self.assertRaises(UserError):
                    resena.with_user(usuario).write({'estado': 'aprobada'})
        self.assertEqual((resena.estrellas, resena.estado), (2, 'pendiente'))

    def test_portal_vendedora_y_publico_no_aprueban_ni_leen(self):
        resena = self.opinar()
        for usuario in (self.portal_lucia, self.portal_otro, self.vendedora, self.env.ref('base.public_user')):
            with self.subTest(usuario=usuario.login):
                with self.assertRaises(AccessError):
                    resena.with_user(usuario).action_aprobar()
                with self.assertRaises(AccessError):
                    self.env['dcasa.resena'].with_user(usuario).search([])
        self.assertEqual(resena.estado, 'pendiente')

    def test_gerencia_publica_y_esconde(self):
        resena = self.opinar(estrellas=4)
        self.env.cr.precommit.data.pop(CLAVE_BORDE, None)
        resena.with_user(self.gerente).action_aprobar()
        self.assertEqual((resena.estado, resena.revisado_por_id), ('aprobada', self.gerente))
        self.assertTrue(resena.revisado_el)
        if 'dcasa.tienda.pendiente' in self.env:
            self.assertIn(self.sofa.product_tmpl_id.id, self.env.cr.precommit.data.get(CLAVE_BORDE, {}),
                          'La ficha guardada en el borde se renueva')
        resena.with_user(self.env.ref('base.user_admin')).action_rechazar()
        self.assertEqual(resena.estado, 'rechazada')

    def test_lo_no_aprobado_no_se_ve(self):
        plantilla = self.sofa.product_tmpl_id
        resena = self.opinar(estrellas=4)
        self.assertEqual(plantilla._dcasa_opiniones()['total'], 0, 'Por revisar: no se publica')
        self.assertIsNone(self.env['dcasa.resena']._dcasa_valoracion_google(plantilla))
        resena.with_user(self.gerente).action_aprobar()
        opiniones = plantilla._dcasa_opiniones()
        self.assertEqual((opiniones['total'], opiniones['promedio_texto'], opiniones['redondeo']), (1, '4.0', 4))
        self.assertEqual(opiniones['opiniones'][0]['autor'], 'Lucía M.')
        self.assertEqual(self.env['dcasa.resena']._dcasa_valoracion_google(plantilla), {
            '@type': 'AggregateRating', 'ratingValue': 4.0, 'reviewCount': 1, 'bestRating': 5, 'worstRating': 1})
        resena.with_user(self.gerente).action_rechazar()
        self.assertEqual(plantilla._dcasa_opiniones()['total'], 0)
        self.assertIsNone(self.env['dcasa.resena']._dcasa_valoracion_google(plantilla))


@tagged('post_install', '-at_install')
class TestResenasEnLaFicha(ResenasComun, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.preparar_resenas()

    def _datos_google(self, html):
        bloques = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        return [json.loads(b) for b in bloques]

    def _producto_en_google(self, html):
        for datos in self._datos_google(html):
            for item in datos if isinstance(datos, list) else [datos]:
                if item.get('@type') in ('Product', 'ProductGroup'):
                    return item
        self.fail('La ficha no trae los datos del producto para Google')

    def test_sin_publicadas_no_hay_estrellas_ni_aggregate_rating(self):
        self.opinar()   # por revisar
        html = self.url_open(self.sofa.website_url).text
        self.assertNotIn('dcasa-opiniones', html)
        self.assertNotIn('o_dcasa_ficha_valoracion', html)
        self.assertNotIn('aggregateRating', self._producto_en_google(html))
        self.assertNotIn('Llegó a tiempo', html)

    def test_publicada_se_ve_con_nombre_corto_y_cuenta_para_google(self):
        self.opinar(estrellas=5).with_user(self.gerente).action_aprobar()
        html = self.url_open(self.sofa.website_url).text
        self.assertIn('Opiniones de quienes lo compraron', html)
        self.assertIn('Llegó a tiempo y quedó muy bien.', html)
        self.assertIn('Lucía M.', html)
        self.assertNotIn('MARTÍNEZ', html)
        self.assertNotIn('6200-3001', html)
        self.assertNotIn('lucia.opiniones@example.com', html)
        self.assertIn('href="#dcasa-opiniones"', html, 'Las estrellas debajo del nombre llevan a la sección')
        self.assertEqual(self._producto_en_google(html)['aggregateRating'], {
            '@type': 'AggregateRating', 'ratingValue': 5.0, 'reviewCount': 1, 'bestRating': 5, 'worstRating': 1})
        # la de otro producto no se cuela
        self.assertNotIn('Llegó a tiempo', self.url_open(self.mesa.website_url).text)

    def test_editor_del_sitio_abre_la_ficha_con_opiniones(self):
        """Con la marca del editor (data-oe-*) la ficha sigue armándose: lección del lote 1."""
        self.opinar().with_user(self.gerente).action_aprobar()
        self.authenticate('admin', 'admin')
        respuesta = self.url_open(self.sofa.website_url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('Opiniones de quienes lo compraron', respuesta.text)
