"""Celular y correo obligatorios y bien escritos: cuándo se exigen, a quién, y la casilla «Cliente no tiene correo».

Pedido de la dueña (2026-10-16) y su decisión del 2026-10-17: el correo es obligatorio por defecto; si el cliente de
verdad no tiene, la vendedora marca «Cliente no tiene correo electrónico» (en la cotización o en su ficha) y ya se
puede registrar. Solo exime del correo: el celular sigue obligatorio. Nada de esto debe romper el guardado automático
del formulario (la nube): se exige al confirmar la venta y al publicar la factura, no mientras se escribe."""
from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged

EXCEPCION = {'dcasa_sin_exigir_contacto': True}
CLIENTE = {'res_partner_search_mode': 'customer'}
AYUDA = ('Si de verdad no tiene correo, marca «Cliente no tiene correo electrónico» en su ficha o junto al cliente en '
         'la cotización.')


class ContactoCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendedora = new_test_user(cls.env, login='vend_contacto', name='Vendedora Contacto',
                                      groups='base.group_user,dcasa_base.group_vendedora')
        cls.gerencia = new_test_user(cls.env, login='ger_contacto', name='Gerencia Contacto',
                                     groups='base.group_user,dcasa_base.group_gerencia')
        Partner = cls.env['res.partner']
        cls.completo = Partner.create({'name': 'Cliente Completo', 'phone': '6000-0001',
                                       'email': 'completo@example.com', 'customer_rank': 1})
        cls.sin_correo = Partner.create({'name': 'Cliente Sin Correo', 'phone': '6000-0002', 'customer_rank': 1})
        cls.sin_nada = Partner.create({'name': 'Cliente Sin Nada', 'customer_rank': 1})
        cls.producto = cls.env['product.product'].create({'name': 'Servicio de armado prueba', 'type': 'service',
                                                          'list_price': 100.0})

    def cotizar(self, cliente, usuario=None):
        Orden = self.env['sale.order'].with_user(usuario or self.vendedora)
        return Orden.create({
            'partner_id': cliente.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})],
        })

    def factura(self, cliente, usuario=None, **valores):
        Factura = self.env['account.move'].with_user(usuario) if usuario else self.env['account.move']
        return Factura.create({
            'move_type': 'out_invoice', 'partner_id': cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1, 'price_unit': 100.0})],
            **valores,
        })

    def rastro_de(self, partner, campo):
        """Los cambios de ``campo`` que quedaron en el historial de la ficha, como ``(autor, antes, después)``."""
        self.env.flush_all()
        self.env.cr.precommit.run()
        valores = partner.message_ids.tracking_value_ids.filtered(lambda t: t.field_id.name == campo)
        return [(t.mail_message_id.author_id, t.old_value_integer, t.new_value_integer) for t in valores]


@tagged('post_install', '-at_install')
class TestPuertas(ContactoCommon):
    """Puerta A (confirmar la venta) y B (publicar la factura)."""

    def test_sin_correo_no_se_confirma_y_dice_que_falta(self):
        orden = self.cotizar(self.sin_correo)
        with self.assertRaises(UserError) as error:
            orden.action_confirm()
        self.assertEqual(error.exception.args[0], (
            'Para confirmar la venta, a «Cliente Sin Correo» le falta el correo. Escríbelo en su ficha y vuelve a '
            'confirmar: ahí le llegan su factura y cómo ver sus puntos.\n' + AYUDA))
        self.assertEqual(orden.state, 'draft')

    def test_sin_celular_ni_correo_lo_dice_todo(self):
        orden = self.cotizar(self.sin_nada)
        with self.assertRaises(UserError) as error:
            orden.action_confirm()
        self.assertIn('le falta el celular y el correo. Escríbelos en su ficha', error.exception.args[0])

    def test_con_los_dos_datos_se_confirma(self):
        orden = self.cotizar(self.completo)
        orden.action_confirm()
        self.assertEqual(orden.state, 'sale')

    def test_un_dato_mal_escrito_tambien_frena_y_sugiere(self):
        self.sin_correo.with_context(**EXCEPCION).email = 'ana@gmial.com'
        orden = self.cotizar(self.sin_correo)
        with self.assertRaises(UserError) as error:
            orden.action_confirm()
        self.assertIn('¿Quisiste decir ana@gmail.com?', error.exception.args[0])
        self.assertIn('vuelve a confirmar', error.exception.args[0])

    def test_juan_la_tienda_y_la_excepcion_no_pasan_por_la_puerta(self):
        """``sudo`` (Juan, la tienda, Socios) y el contexto de excepción (importador) siguen como antes."""
        self.cotizar(self.sin_nada).sudo().action_confirm()
        self.cotizar(self.sin_nada).with_context(**EXCEPCION).action_confirm()
        portal = new_test_user(self.env, login='portal_contacto', groups='base.group_portal')
        orden = self.env['sale.order'].with_user(portal).sudo().create({
            'partner_id': self.sin_nada.id,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})],
        })
        orden.action_confirm()
        self.assertEqual(orden.state, 'sale')

    def test_el_correo_de_la_direccion_de_factura_cuenta(self):
        direccion = self.env['res.partner'].create({
            'name': 'Factura de Sin Correo', 'parent_id': self.sin_correo.id, 'type': 'invoice',
            'email': 'factura.sincorreo@example.com'})
        orden = self.cotizar(self.sin_correo)
        orden.partner_invoice_id = direccion
        self.assertFalse(orden.dcasa_falta_contacto)
        orden.action_confirm()
        self.assertEqual(orden.state, 'sale')

    def test_el_correo_del_equipo_no_sirve_como_correo_del_cliente(self):
        correo_del_equipo = self.vendedora.partner_id.email
        self.assertTrue(correo_del_equipo)
        self.sin_correo.with_context(**EXCEPCION).email = correo_del_equipo
        with self.assertRaises(UserError) as error:
            self.cotizar(self.sin_correo).action_confirm()
        self.assertIn("es de D'CASA o de alguien del equipo", error.exception.args[0])
        with self.assertRaises(ValidationError):
            self.sin_nada.with_user(self.vendedora).email = correo_del_equipo

    def test_factura_sin_correo_no_se_publica(self):
        factura = self.factura(self.sin_correo, usuario=self.vendedora)
        with self.assertRaises(UserError) as error:
            factura.action_post()
        self.assertTrue(error.exception.args[0].startswith(
            'Para publicar la factura, a «Cliente Sin Correo» le falta el correo.'), error.exception.args[0])
        self.assertEqual(factura.state, 'draft')

    def test_factura_con_los_datos_se_publica(self):
        factura = self.factura(self.completo, usuario=self.vendedora)
        factura.action_post()
        self.assertEqual(factura.state, 'posted')

    def test_nota_de_credito_historica_y_superusuario_pasan(self):
        nota = self.factura(self.sin_nada, usuario=self.vendedora, move_type='out_refund')
        nota.action_post()
        self.assertEqual(nota.state, 'posted')
        historica = self.factura(self.sin_nada, dcasa_historica=True)
        historica.with_user(self.gerencia).action_post()
        self.assertEqual(historica.state, 'posted')
        suya = self.factura(self.sin_nada)
        suya.action_post()
        self.assertEqual(suya.state, 'posted')

    def test_pagar_nunca_se_bloquea(self):
        """Una factura ya publicada de un cliente sin correo ni celular se cobra igual (la vendedora es caja)."""
        factura = self.factura(self.sin_nada)
        factura.action_post()
        efectivo = self.env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', self.env.company.id)], limit=1)
        registro = self.env['account.payment.register'].with_user(self.vendedora).with_context(
            active_model='account.move', active_ids=factura.ids).create(
            {'payment_date': fields.Date.today(), 'journal_id': efectivo.id})
        registro._create_payments()
        self.assertIn(factura.payment_state, ('paid', 'in_payment'))

    def test_la_contabilidad_no_cambia(self):
        """Publicar con los datos completos da las mismas líneas que una factura igual con la excepción."""
        normal = self.factura(self.completo, usuario=self.vendedora)
        normal.action_post()
        otra = self.factura(self.completo).with_context(**EXCEPCION)
        otra.action_post()

        def lineas(factura):
            return sorted((linea.account_id.id, linea.debit, linea.credit, linea.tax_line_id.id)
                          for linea in factura.line_ids)
        self.assertEqual(lineas(normal), lineas(otra))
        self.assertEqual(normal.amount_total, otra.amount_total)


@tagged('post_install', '-at_install')
class TestCasillaSinCorreo(ContactoCommon):
    """«Cliente no tiene correo electrónico»: la marca la vendedora; solo exime del correo."""

    def test_la_vendedora_la_marca_en_la_ficha_y_queda_su_nombre(self):
        self.sin_correo.with_user(self.vendedora).dcasa_sin_correo = True
        self.assertTrue(self.sin_correo.dcasa_sin_correo)
        self.assertEqual(self.rastro_de(self.sin_correo, 'dcasa_sin_correo'),
                         [(self.vendedora.partner_id, 0, 1)])
        orden = self.cotizar(self.sin_correo)
        self.assertFalse(orden.dcasa_falta_contacto)
        orden.action_confirm()
        self.assertEqual(orden.state, 'sale')

    def test_solo_exime_del_correo_el_celular_sigue(self):
        self.sin_nada.with_user(self.vendedora).dcasa_sin_correo = True
        orden = self.cotizar(self.sin_nada)
        self.assertEqual(orden.dcasa_falta_contacto, 'el celular')
        with self.assertRaises(UserError) as error:
            orden.action_confirm()
        self.assertIn('le falta el celular.', error.exception.args[0])
        self.assertNotIn('correo', error.exception.args[0].split('\n')[0].split('le falta')[1])

    def test_se_marca_desde_la_cotizacion_y_se_guarda_en_la_ficha(self):
        orden = self.cotizar(self.sin_correo)
        self.assertEqual(orden.dcasa_falta_contacto, 'el correo')
        self.assertFalse(orden.dcasa_cliente_tiene_correo)
        orden.write({'dcasa_cliente_sin_correo': True})
        self.assertTrue(self.sin_correo.dcasa_sin_correo, 'la casilla vive en la ficha del cliente')
        self.assertFalse(orden.dcasa_falta_contacto)
        self.assertEqual(self.rastro_de(self.sin_correo, 'dcasa_sin_correo'),
                         [(self.vendedora.partner_id, 0, 1)])
        orden.action_confirm()
        self.assertEqual(orden.state, 'sale')
        # Otra cotización del mismo cliente ya la trae marcada.
        self.assertTrue(self.cotizar(self.sin_correo).dcasa_cliente_sin_correo)

    def test_crear_la_cotizacion_con_la_casilla_marcada(self):
        orden = self.env['sale.order'].with_user(self.vendedora).create({
            'partner_id': self.sin_correo.id, 'dcasa_cliente_sin_correo': True,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})],
        })
        self.assertTrue(self.sin_correo.dcasa_sin_correo)
        orden.action_confirm()

    def test_guardar_la_cotizacion_no_toca_la_ficha_de_balde(self):
        orden = self.cotizar(self.completo)
        orden.write({'dcasa_cliente_sin_correo': False, 'note': 'Entrega el sábado'})
        self.assertEqual(self.rastro_de(self.completo, 'dcasa_sin_correo'), [])

    def test_en_el_formulario_de_la_cotizacion(self):
        """Como en la pantalla (Form respeta lo visible y lo editable de la vista): la casilla sale junto al cliente
        sin correo, el aviso amarillo desaparece al marcarla (antes de guardar) y al guardar queda en la ficha."""
        with Form(self.env['sale.order'].with_user(self.vendedora)) as formulario:
            formulario.partner_id = self.sin_correo
            self.assertEqual(formulario.dcasa_falta_contacto, 'el correo')
            formulario.dcasa_cliente_sin_correo = True
            self.assertFalse(formulario.dcasa_falta_contacto, 'el aviso se va al marcar la casilla')
        orden = formulario.record
        self.assertTrue(self.sin_correo.dcasa_sin_correo)
        orden.order_line = [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]
        orden.action_confirm()
        self.assertEqual(orden.state, 'sale')

    def test_con_correo_la_casilla_no_sale_en_la_cotizacion(self):
        with Form(self.env['sale.order'].with_user(self.vendedora)) as formulario:
            formulario.partner_id = self.completo
            self.assertTrue(formulario.dcasa_cliente_tiene_correo)
            with self.assertRaisesRegex(AssertionError, 'invisible'):
                formulario.dcasa_cliente_sin_correo = True

    def test_escribir_un_correo_la_desmarca_sola(self):
        self.sin_correo.with_user(self.vendedora).dcasa_sin_correo = True
        self.sin_correo.with_user(self.vendedora).email = 'Nuevo.Correo@Example.com '
        self.assertFalse(self.sin_correo.dcasa_sin_correo)
        self.assertEqual(self.sin_correo.email, 'nuevo.correo@example.com')
        # Y si se escriben los dos a la vez, manda el correo.
        nueva = self.env['res.partner'].with_user(self.vendedora).with_context(**CLIENTE).create({
            'name': 'Cliente Las Dos', 'phone': '6000-0003', 'email': 'lasdos@example.com',
            'dcasa_sin_correo': True})
        self.assertFalse(nueva.dcasa_sin_correo)
        # Lo de la tienda o de Juan (sudo) igual: un correo escrito desmarca la casilla.
        self.sin_nada.dcasa_sin_correo = True
        self.sin_nada.sudo().write({'email': 'sinnada@example.com'})
        self.assertFalse(self.sin_nada.dcasa_sin_correo)

    def test_en_el_formulario_de_la_ficha_se_desmarca_al_escribir(self):
        self.sin_correo.dcasa_sin_correo = True
        with Form(self.sin_correo.with_user(self.vendedora)) as formulario:
            self.assertTrue(formulario.dcasa_sin_correo)
            formulario.email = 'sincorreo.ya@example.com'
            self.assertFalse(formulario.dcasa_sin_correo, 'la casilla se desmarca al escribir el correo')
        self.assertFalse(self.sin_correo.dcasa_sin_correo)
        self.assertEqual(self.sin_correo.email, 'sincorreo.ya@example.com')

    def test_la_casilla_se_ve_en_la_ficha_para_la_vendedora(self):
        arco = self.env['res.partner'].with_user(self.vendedora).get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('name="dcasa_sin_correo"', arco)
        arco = self.env['sale.order'].with_user(self.vendedora).get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('name="dcasa_cliente_sin_correo"', arco)


@tagged('post_install', '-at_install')
class TestFichaBienEscrita(ContactoCommon):
    """Al escribir en la ficha (puerta D) y al crear un cliente."""

    def test_correo_de_dedo_no_se_guarda_y_sugiere(self):
        with self.assertRaises(ValidationError) as error:
            self.sin_correo.with_user(self.vendedora).email = 'ana@gmial.com'
        self.assertIn('¿Quisiste decir ana@gmail.com?', error.exception.args[0])

    def test_correo_y_celular_se_guardan_limpios_sin_cambiar_la_llave(self):
        ficha = self.sin_nada.with_user(self.vendedora)
        ficha.write({'email': 'ANA.SinNada@Example.com ', 'phone': '6000 0004'})
        self.assertEqual(self.sin_nada.email, 'ana.sinnada@example.com')
        self.assertEqual(self.sin_nada.phone, '+507 6000-0004')
        self.assertEqual(self.sin_nada.dcasa_telefono_llave, 'pa:60000004')

    def test_celular_corto_no_se_guarda(self):
        with self.assertRaises(ValidationError) as error:
            self.sin_nada.with_user(self.vendedora).phone = '6000-000'
        self.assertIn('en Panamá son 8 números', error.exception.args[0])

    def test_una_ficha_vieja_mal_escrita_se_sigue_editando(self):
        """Lo viejo no se toca: cambiarle la calle a una ficha con un correo malo no da error (la nube guarda)."""
        self.sin_nada.with_context(**EXCEPCION).write({'email': 'vieja@gmial.com', 'phone': '345-678'})
        self.sin_nada.with_user(self.vendedora).write({'street': 'Calle Las Mañanitas'})
        self.assertEqual(self.sin_nada.street, 'Calle Las Mañanitas')
        with Form(self.sin_nada.with_user(self.vendedora)) as formulario:
            formulario.city = 'La Chorrera'
        self.assertEqual(self.sin_nada.city, 'La Chorrera')

    def test_al_proveedor_no_se_le_aplica(self):
        proveedor = self.env['res.partner'].create({'name': 'Proveedor Chino', 'supplier_rank': 1})
        proveedor.with_user(self.gerencia).write({'phone': '8613800138000', 'email': 'ventas@fabrica.cn'})
        self.assertEqual(proveedor.phone, '8613800138000', 'al proveedor no se le cambia el número')
        Proveedores = self.env['res.partner'].with_user(self.gerencia).with_context(res_partner_search_mode='supplier')
        nuevo = Proveedores.create({'name': 'Proveedor Nuevo', 'phone': '8613800138001'})
        self.assertEqual(nuevo.phone, '8613800138001')

    def test_crear_un_cliente_exige_celular_y_correo(self):
        Partner = self.env['res.partner'].with_user(self.vendedora).with_context(**CLIENTE)
        with self.assertRaises(ValidationError) as error:
            Partner.create({'name': 'Sin Datos Nuevo', 'phone': False, 'email': False})
        self.assertIn('Escribe el celular y el correo del cliente', error.exception.args[0])
        with self.assertRaises(ValidationError) as error:
            Partner.create({'name': 'Sin Correo Nuevo', 'phone': '6000-0005', 'email': False})
        self.assertIn('Escribe el correo del cliente', error.exception.args[0])
        self.assertIn('Cliente no tiene correo electrónico', error.exception.args[0])
        con_casilla = Partner.create({'name': 'Sin Correo Marcado', 'phone': '6000-0005', 'email': False,
                                      'dcasa_sin_correo': True})
        self.assertTrue(con_casilla.dcasa_sin_correo)
        with self.assertRaises(ValidationError):
            Partner.create({'name': 'Sin Celular Marcado', 'phone': False, 'dcasa_sin_correo': True})
        bien = Partner.create({'name': 'Con Todo Nuevo', 'phone': '6000-0006', 'email': 'contodo@example.com'})
        self.assertEqual(bien.phone, '+507 6000-0006')

    def test_lo_que_no_se_frena_al_crear(self):
        """La creación rápida (nombre y Enter), una empresa (p. ej. la de un contacto, desde su ficha), una dirección y
        un contacto creado sin el modo de clientes no fallan al crear: los frena la venta."""
        Partner = self.env['res.partner'].with_user(self.vendedora).with_context(**CLIENTE)
        rapido_id, _nombre = Partner.name_create('Cliente Rápido')
        self.assertTrue(rapido_id)
        empresa_id, _nombre = Partner.with_context(default_is_company=True).name_create('Empresa Rápida')
        self.assertTrue(self.env['res.partner'].browse(empresa_id).is_company)
        Partner.create({'name': 'Empresa Cliente', 'is_company': True})
        Partner.create({'name': 'Entrega', 'parent_id': self.completo.id, 'type': 'delivery'})
        self.env['res.partner'].with_user(self.vendedora).create({'name': 'Contacto Suelto'})
        with self.assertRaises(UserError):
            self.cotizar(self.env['res.partner'].browse(rapido_id)).action_confirm()

    def test_en_el_formulario_de_cliente_nuevo(self):
        """Como en la pantalla: el celular y el correo son obligatorios; con la casilla, solo el celular."""
        Partner = self.env['res.partner'].with_user(self.vendedora).with_context(**CLIENTE)
        formulario = Form(Partner)
        formulario.name = 'Cliente Formulario'
        with self.assertRaises(AssertionError):
            formulario.save()
        formulario.phone = '6000-0007'
        formulario.dcasa_sin_correo = True
        cliente = formulario.save()
        self.assertTrue(cliente.dcasa_sin_correo)
        self.assertEqual(cliente.phone, '+507 6000-0007')

    def test_la_web_y_juan_crean_sin_correo(self):
        Partner = self.env['res.partner'].with_context(**CLIENTE)
        juan = Partner.with_user(self.vendedora).sudo().create({'name': 'Desde el chat', 'phone': '6000-0008'})
        self.assertFalse(juan.email)
        portal = new_test_user(self.env, login='portal_contacto_crea', groups='base.group_portal')
        web = Partner.with_user(portal).sudo().create({'name': 'Desde la web', 'email': 'web@gmial.com'})
        self.assertEqual(web.email, 'web@gmial.com', 'la tienda tiene su propio aviso; aquí no se toca')

    def test_aviso_quisiste_decir_antes_de_guardar(self):
        ficha = self.env['res.partner'].with_user(self.vendedora).new({'name': 'Aviso', 'email': 'aviso@hotmial.com'})
        aviso = ficha._onchange_dcasa_duplicado()
        self.assertEqual(aviso['warning']['title'], 'Revisa lo que escribiste')
        self.assertIn('¿Quisiste decir aviso@hotmail.com?', aviso['warning']['message'])
        ficha = self.env['res.partner'].with_user(self.vendedora).new({'name': 'Aviso', 'phone': '6000-00'})
        self.assertIn('en Panamá son 8 números', ficha._onchange_dcasa_duplicado()['warning']['message'])

    def test_errores_para_la_tienda(self):
        Partner = self.env['res.partner']
        self.assertEqual(Partner._dcasa_errores_de_contacto('6026-1919', 'ana@gmail.com'), {})
        errores = Partner._dcasa_errores_de_contacto('6026-191', 'ana@gmial.com')
        self.assertIn('¿quisiste decir ana@gmail.com?', errores['email'])
        self.assertIn('8 números', errores['phone'])
        self.assertIn('un solo número', Partner._dcasa_errores_de_contacto('6026-1919 / 2345678', '')['phone'])
        self.assertIn('de verdad', Partner._dcasa_errores_de_contacto('', 'sincorreo@gmail.com')['email'])
