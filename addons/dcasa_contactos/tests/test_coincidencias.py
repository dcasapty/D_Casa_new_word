"""Encontrar al cliente que ya existe y corregir sus datos sin salir de la venta (pedido de la dueña, 2026-11-04).

«Los clientes escriben por WhatsApp y el sistema los guarda con lo que tengan en su perfil. Cuando llegan a la tienda,
la vendedora pone el nombre y el celular, el celular ya estaba y le sale un error; por evitarlo crea otro cliente con
otro número. Debe ser fácil verificar si es la misma persona y actualizar sus datos sin perder lo que se factura.»"""
from odoo import Command
from odoo.addons.dcasa_base.tests.test_roles import crear_usuario
from odoo.exceptions import ValidationError
from odoo.tests import Form, TransactionCase, tagged

from ..models.coincidencias import parece_telefono


@tagged('post_install', '-at_install')
class TestCoincidencias(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = crear_usuario(cls.env, 'coinc_vendedora', 'dcasa_base.group_vendedora')
        cls.portal = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Portal Coincidencias', 'login': 'coinc_portal',
            'group_ids': [Command.set([cls.env.ref('base.group_portal').id])]})
        Partner = cls.env['res.partner'].sudo()
        # Como la crea el chat: con lo que traiga el perfil de WhatsApp (aquí, una frase).
        cls.del_chat = Partner.create({'name': 'Bendiciones 🙏', 'phone': '+507 6000-1101', 'dcasa_creado_por': 'juan'})
        cls.otra = Partner.create({'name': 'Rosa Otra Coincidencia', 'phone': '+507 6000-1102',
                                   'email': 'rosa.coincidencia@example.com', 'vat': '8-700-1102', 'customer_rank': 1})
        cls.socia = Partner.create({'name': 'Socia Solo Programa', 'dcasa_celular': '60001103'})

    # ------------------------------------------------------------------
    # Buscar por celular
    # ------------------------------------------------------------------

    def test_que_parece_un_telefono(self):
        for texto in ('6000-1101', '60001101', '+507 6000 1101', '(507) 6000-1101', '6000'):
            self.assertTrue(parece_telefono(texto), texto)
        for texto in ('Bendiciones', 'Calle 50', '600', 'ana@gmail.com', None):
            self.assertFalse(parece_telefono(texto), texto)

    def test_el_selector_encuentra_por_celular_escrito_de_cualquier_forma(self):
        Partner = self.env['res.partner'].with_user(self.vendedora).with_context(res_partner_search_mode='customer')
        for texto in ('6000-1101', '60001101', '+507 6000 1101', '+50760001101', '6000-11'):
            ids = [i for i, _ in Partner.name_search(texto, limit=20)]
            self.assertIn(self.del_chat.id, ids, texto)
        ids = [i for i, _ in Partner.name_search('6000-1103')]
        self.assertIn(self.socia.id, ids, 'el celular de Socios también cuenta')
        ids = [i for i, _ in Partner.name_search('6000-1109')]
        self.assertNotIn(self.del_chat.id, ids)

    def test_la_lista_del_selector_muestra_el_celular(self):
        Partner = self.env['res.partner'].with_user(self.vendedora)
        fila = next(r for r in Partner.with_context(res_partner_search_mode='customer').web_name_search(
            '6000-1101', {'display_name': {}}) if r['id'] == self.del_chat.id)
        self.assertIn('--+507 6000-1101--', fila['__formatted_display_name'])
        self.assertNotIn('6000-1101', fila['display_name'], 'el nombre que queda en la cotización no cambia')
        fila = next(r for r in Partner.web_name_search('Bendiciones', {'display_name': {}})
                    if r['id'] == self.del_chat.id)
        self.assertNotIn('6000-1101', fila['__formatted_display_name'], 'solo al elegir un cliente')

    def test_crear_y_editar_despues_de_buscar_un_celular(self):
        Partner = self.env['res.partner'].with_user(self.vendedora)
        valores = Partner.with_context(default_name='6000-1199').default_get(['name', 'phone', 'email'])
        self.assertEqual((valores.get('name'), valores.get('phone')), (False, '6000-1199'))
        valores = Partner.with_context(default_name='nueva@example.com').default_get(['name', 'phone', 'email'])
        self.assertEqual((valores.get('name'), valores.get('email')), (False, 'nueva@example.com'))
        valores = Partner.with_context(default_name='Ana Nueva').default_get(['name', 'phone', 'email'])
        self.assertEqual(valores.get('name'), 'Ana Nueva')

    # ------------------------------------------------------------------
    # «Ya existe esta persona»
    # ------------------------------------------------------------------

    def test_al_crear_sale_la_ficha_con_el_mismo_celular(self):
        with Form(self.env['res.partner'].with_user(self.vendedora).with_context(
                res_partner_search_mode='customer')) as ficha:
            ficha.name = 'María Nueva Coincidencia'
            self.assertFalse(ficha.dcasa_coincidencias)
            ficha.phone = '6000-1101'
            coincidencias = ficha.dcasa_coincidencias
            self.assertEqual([c['id'] for c in coincidencias], [self.del_chat.id])
            c = coincidencias[0]
            self.assertTrue(c['fuerte'])
            self.assertEqual(c['por'], ['el celular'])
            self.assertEqual(c['nombre'], 'Bendiciones 🙏')
            self.assertIn(['Celular', '+507 6000-1101'], c['datos'])
            self.assertTrue(c['origen'].startswith('Llegó por el chat'))
            # Cambia a un celular libre: ya no hay coincidencia (y se puede crear).
            ficha.phone = '6000-1198'
            ficha.email = 'maria.nueva@example.com'
            self.assertFalse(ficha.dcasa_coincidencias)

    def test_por_correo_y_cedula_y_luego_nombre_parecido(self):
        with Form(self.env['res.partner'].with_user(self.vendedora)) as ficha:
            ficha.name = 'Rosa Otra Coincidencia'
            parecida = ficha.dcasa_coincidencias
            self.assertEqual([c['id'] for c in parecida], [self.otra.id])
            self.assertFalse(parecida[0]['fuerte'], 'un nombre parecido no es la misma persona: se pregunta')
            ficha.email = 'ROSA.coincidencia@example.com'
            ficha.vat = '8 700 1102'
            c = ficha.dcasa_coincidencias[0]
            self.assertTrue(c['fuerte'])
            self.assertEqual(c['por'], ['el correo', 'la cédula o RUC'])
            ficha.email = 'rosa.distinta@example.com'
            ficha.vat = '8-700-1199'
            ficha.phone = '6000-1197'
            ficha.name = 'Otra Persona Distinta'

    def test_solo_al_crear_y_solo_al_equipo(self):
        self.assertFalse(self.del_chat.with_user(self.vendedora).dcasa_coincidencias, 'una ficha guardada no avisa')
        nueva = self.env['res.partner'].with_user(self.portal).new({'name': 'X', 'phone': '6000-1101'})
        self.assertFalse(nueva.dcasa_coincidencias, 'quien viene del sitio no ve fichas ajenas')

    # ------------------------------------------------------------------
    # Corregir los datos dentro de la cotización y la factura
    # ------------------------------------------------------------------

    def test_corregir_los_datos_en_la_cotizacion(self):
        orden = self.env['sale.order'].with_user(self.vendedora).create({'partner_id': self.del_chat.id})
        with Form(orden) as f:
            self.assertEqual(f.dcasa_cliente_nombre, 'Bendiciones 🙏')
            self.assertEqual(f.dcasa_cliente_celular, '+507 6000-1101')
            f.dcasa_cliente_nombre = 'María Corregida'
            f.dcasa_cliente_correo = 'Maria.Corregida@Example.com '
            f.dcasa_cliente_cedula = '8-700-1104'
        ficha = self.del_chat
        self.assertEqual((ficha.name, ficha.email, ficha.vat),
                         ('María Corregida', 'maria.corregida@example.com', '8-700-1104'))
        self.assertEqual(ficha.write_uid, self.vendedora, 'se guarda como quien corrige (sin sudo)')
        self.assertEqual(orden.partner_id, ficha)
        self.assertEqual(self.env['res.partner'].search_count([('name', '=', 'María Corregida')]), 1)

    def test_en_la_cotizacion_el_celular_de_otra_ficha_avisa_y_no_se_guarda(self):
        orden = self.env['sale.order'].with_user(self.vendedora).create({'partner_id': self.del_chat.id})
        with self.assertLogs('odoo.tests.form.onchange', level='WARNING') as avisos:
            f = Form(orden)
            f.dcasa_cliente_celular = '6000-1102'
        self.assertIn('Rosa Otra Coincidencia', avisos.output[0])
        self.assertIn('cambia el Cliente', avisos.output[0])
        with self.assertRaises(ValidationError):
            f.save()

    def test_en_la_cotizacion_un_correo_mal_escrito_avisa(self):
        orden = self.env['sale.order'].with_user(self.vendedora).create({'partner_id': self.del_chat.id})
        with self.assertLogs('odoo.tests.form.onchange', level='WARNING') as avisos:
            f = Form(orden)
            f.dcasa_cliente_correo = 'maria@gmial.com'
        self.assertIn('gmail.com', avisos.output[0])

    def test_corregir_los_datos_en_la_factura_borrador(self):
        """La factura sale del pedido y la publica Caja: en el borrador, Caja corrige los datos."""
        caja = crear_usuario(self.env, 'coinc_caja', 'dcasa_base.group_caja')
        factura = self.env['account.move'].create({'move_type': 'out_invoice', 'partner_id': self.del_chat.id})
        with Form(factura.with_user(caja)) as f:
            f.dcasa_cliente_nombre = 'María Factura'
            f.dcasa_cliente_correo = 'maria.factura@example.com'
        self.assertEqual((self.del_chat.name, self.del_chat.email), ('María Factura', 'maria.factura@example.com'))
