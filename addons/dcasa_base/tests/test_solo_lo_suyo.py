"""Cada vendedora ve solo lo suyo (pedido de la dueña, 2026-10-16) y su interruptor (2026-10-17).

Pruebas «de ataque»: la Vendedora A intenta ver lo de la Vendedora B por todos los caminos que da Odoo (search,
search_count, read_group, name_search, leer por número, imprimir, adjuntos, mensajes) y no encuentra nada; sí ve lo
suyo y lo que no tiene vendedora. Caja ve, factura y cobra todo; Gerencia y contabilidad ven todo (desde el 2026-10-17
la nota de crédito la hace Gerencia y el cobro solo Caja: test_reglas_gerencia.py). Y el interruptor
«Cada vendedora ve solo sus documentos»: encendido de fábrica; apagado, todas ven todo como antes, sin tocar a nadie;
y el ida y vuelta deja todo como estaba. Explicación: docs/PERMISOS.md.
"""
from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import convert_file

from .test_permisos_vendedora import menus_visibles
from .test_roles import crear_usuario

TODOS = 'sales_team.group_sale_salesman_all_leads'
CLAVE = 'Prueba-solo-lo-suyo-123'


class SoloLoSuyoComun(TransactionCase):
    """Una tienda de prueba: A y B Vendedoras, C Caja, G Gerencia, K contador y un lector contable.

    B vende; C (Caja) le factura el pedido y lo cobra, y Gerencia le hace una nota de crédito: todo eso es de B,
    aunque lo hayan hecho otros. Hay además un pedido sin vendedora (como uno de la web o de Juan) y un cliente cuya
    ficha dice «B»."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.company = env.ref('base.main_company')
        cls.a = crear_usuario(env, 'sls_vendedora_a', 'dcasa_base.group_vendedora')
        cls.b = crear_usuario(env, 'sls_vendedora_b', 'dcasa_base.group_vendedora')
        cls.caja = crear_usuario(env, 'sls_caja', 'dcasa_base.group_caja')
        cls.gerencia = crear_usuario(env, 'sls_gerencia', 'dcasa_base.group_gerencia')
        cls.contador = crear_usuario(env, 'sls_contador', 'account.group_account_user')
        cls.lector = crear_usuario(env, 'sls_lector', 'account.group_account_readonly')

        # Celular y correo: sin ellos la vendedora no confirma ni publica (puertas de dcasa_contactos).
        cls.cliente = env['res.partner'].create({
            'name': 'Cliente Solo Lo Suyo', 'phone': '+507 6555-0101', 'email': 'cliente.solo.lo.suyo@example.com'})
        cls.cliente_de_b = env['res.partner'].create({
            'name': 'Cliente Ficha De B', 'user_id': cls.b.id, 'phone': '+507 6555-0102',
            'email': 'cliente.ficha.de.b@example.com'})
        cls.producto = env['product.product'].create({
            'name': 'Mesa Solo Lo Suyo', 'type': 'consu', 'list_price': 100.0})
        Diario = env['account.journal']
        cls.efectivo = Diario.search([('type', '=', 'cash'), ('company_id', '=', cls.company.id)], limit=1)
        cls.banco = Diario.search([('type', '=', 'bank'), ('company_id', '=', cls.company.id)], limit=1)
        plan = env['account.analytic.plan'].create({'name': 'Plan Solo Lo Suyo'})
        cls.canal = env['account.analytic.account'].create({'name': 'Canal Solo Lo Suyo', 'plan_id': plan.id})

        # Lo de B: ella cotiza y confirma; Caja factura, publica y cobra; la nota la hace Gerencia (A7).
        cls.pedido_b = cls._pedido(cls.b, cls.cliente)
        cls.pedido_b.action_confirm()
        cls.factura_b = cls.pedido_b.with_user(cls.caja)._create_invoices()
        cls.factura_b.with_user(cls.caja).action_post()
        cls.cobro_b = cls._cobrar(cls.caja, cls.factura_b, cls.efectivo)
        cls.nota_b = cls._nota(cls.gerencia, cls.factura_b)
        cls.factura_b.message_post(body='Mensaje interno de la factura de B')
        cls.pedido_b.message_post(body='Mensaje interno del pedido de B')
        cls.adjunto_b = env['ir.attachment'].create({
            'name': 'factura-de-b.pdf', 'res_model': 'account.move', 'res_id': cls.factura_b.id,
            'raw': b'%PDF-1.4 factura de B', 'mimetype': 'application/pdf'})

        # Sin vendedora (web, Juan sin asignar): lo ven todas para que alguien lo atienda.
        cls.pedido_libre = env['sale.order'].create({
            'partner_id': cls.cliente.id, 'user_id': False,
            'order_line': [Command.create({'product_id': cls.producto.id, 'product_uom_qty': 1})]})

    # --- ayudas -----------------------------------------------------------------------------------------------
    @classmethod
    def _pedido(cls, usuario, cliente, **valores):
        return cls.env['sale.order'].with_user(usuario).create({
            'partner_id': cliente.id, **valores,
            'order_line': [Command.create({
                'product_id': cls.producto.id, 'product_uom_qty': 1,
                'analytic_distribution': {str(cls.canal.id): 100}})],
        })

    @classmethod
    def _cobrar(cls, usuario, factura, diario, **valores):
        registro = cls.env['account.payment.register'].with_user(usuario).with_context(
            active_model='account.move', active_ids=factura.ids).create(
            {'payment_date': fields.Date.today(), 'journal_id': diario.id, **valores})
        return registro._create_payments()

    @classmethod
    def _nota(cls, usuario, factura):
        reversa = cls.env['account.move.reversal'].with_user(usuario).with_context(
            active_model='account.move', active_ids=factura.ids).create(
            {'reason': 'Devolución de prueba', 'journal_id': factura.journal_id.id})
        nota = cls.env['account.move'].browse(reversa.refund_moves()['res_id'])
        nota.with_user(usuario).action_post()
        return nota

    @classmethod
    def _de_b(cls):
        """Todo lo de B como (etiqueta, registros): lo que A no debe encontrar por ningún camino."""
        asientos = cls.factura_b | cls.nota_b | cls.cobro_b.move_id
        apuntes = asientos.line_ids
        conciliaciones = apuntes.matched_debit_ids | apuntes.matched_credit_ids
        analitica = cls.env['account.analytic.line'].search([('move_line_id', 'in', cls.factura_b.line_ids.ids)])
        analisis_ventas = cls.env['sale.report'].search(
            [('order_reference', '=', f'sale.order,{cls.pedido_b.id}')])
        analisis_facturas = cls.env['account.invoice.report'].search(
            [('move_id', 'in', (cls.factura_b | cls.nota_b).ids)])
        return (
            ('pedido', cls.pedido_b), ('líneas del pedido', cls.pedido_b.order_line),
            ('factura', cls.factura_b), ('nota de crédito', cls.nota_b), ('cobro', cls.cobro_b),
            ('asiento del cobro', cls.cobro_b.move_id), ('apuntes', apuntes), ('conciliaciones', conciliaciones),
            ('analítica', analitica), ('análisis de ventas', analisis_ventas),
            ('análisis de facturas', analisis_facturas),
            # Los mensajes y notas del documento (los avisos personales, «te asignaron…», son solo de quien los recibe).
            ('mensajes', cls.env['mail.message'].search([
                ('message_type', '!=', 'user_notification'),
                '|', '&', ('model', '=', 'account.move'), ('res_id', 'in', asientos.ids),
                '&', ('model', '=', 'sale.order'), ('res_id', '=', cls.pedido_b.id)])),
            ('adjunto', cls.adjunto_b),
        )

    def _cerrado(self, registros, usuario, etiqueta):
        """Para ``usuario`` esos registros no existen: ni se buscan, ni se cuentan, ni se agrupan, ni se leen."""
        self.assertTrue(registros, f'{etiqueta}: el dato de prueba no se creó')
        dominio = [('id', 'in', registros.ids)]
        Modelo = registros.browse().with_user(usuario)
        self.assertFalse(Modelo.search(dominio), f'{etiqueta}: aparece en search')
        self.assertEqual(Modelo.search_count(dominio), 0, f'{etiqueta}: cuenta en search_count')
        self.assertFalse(Modelo.search_read(dominio, ['id']), f'{etiqueta}: aparece en search_read')
        self.assertEqual(Modelo._read_group(dominio, [], ['__count']), [(0,)], f'{etiqueta}: cuenta en read_group')
        if Modelo._rec_name in Modelo._fields:
            self.assertFalse(Modelo.name_search('', dominio, limit=None), f'{etiqueta}: aparece en name_search')
        for registro in registros:
            with self.assertRaises(AccessError, msg=f'{etiqueta}: se lee por su número'):
                Modelo.browse(registro.id).read(['display_name'])

    def _visible(self, registros, usuario, etiqueta=''):
        Modelo = registros.browse().with_user(usuario)
        self.assertEqual(Modelo.search([('id', 'in', registros.ids)]), registros, f'{etiqueta}: {usuario.login}')
        self.assertTrue(registros.with_user(usuario).read(['display_name']))


@tagged('post_install', '-at_install')
class TestSoloLoSuyo(SoloLoSuyoComun):

    def test_el_interruptor_viene_encendido(self):
        self.assertTrue(self.env['res.users']._dcasa_restriccion_activa())
        self.assertNotIn(self.env.ref(TODOS), self.env.ref('dcasa_base.group_vendedora').all_implied_ids)
        self.assertTrue(self.a._dcasa_solo_lo_suyo())
        for usuario in (self.caja, self.gerencia, self.contador, self.lector):
            self.assertFalse(usuario._dcasa_solo_lo_suyo(), usuario.login)

    def test_a_no_encuentra_nada_de_b_por_ningun_camino(self):
        for etiqueta, registros in self._de_b():
            with self.subTest(etiqueta):
                self._cerrado(registros, self.a, etiqueta)

    def test_a_no_busca_lo_de_b_por_su_nombre(self):
        for registro in (self.pedido_b, self.factura_b, self.nota_b, self.cobro_b):
            with self.subTest(registro.display_name):
                encontrados = registro.browse().with_user(self.a).name_search(registro.name)
                self.assertNotIn(registro.id, [rid for rid, _nombre in encontrados])

    def test_a_no_imprime_lo_de_b(self):
        Informe = self.env['ir.actions.report'].with_user(self.a)
        for informe, registro in (('account.report_invoice', self.factura_b), ('sale.report_saleorder', self.pedido_b)):
            with self.subTest(informe), self.assertRaises(AccessError):
                Informe._render_qweb_pdf(informe, registro.ids)

    def test_b_ve_lo_suyo_aunque_lo_haya_hecho_caja(self):
        for etiqueta, registros in (('pedido', self.pedido_b), ('factura', self.factura_b), ('nota', self.nota_b),
                                    ('cobro', self.cobro_b), ('asiento del cobro', self.cobro_b.move_id),
                                    ('adjunto', self.adjunto_b)):
            with self.subTest(etiqueta):
                self._visible(registros, self.b, etiqueta)
        # La factura y la nota quedan a nombre de B (no de Caja, que las hizo).
        self.assertEqual(self.factura_b.invoice_user_id, self.b)
        self.assertEqual(self.nota_b.invoice_user_id, self.b)
        # Abre su factura con el detalle de pagos y la imprime.
        self.assertTrue(self.factura_b.with_user(self.b).invoice_payments_widget)
        self.assertTrue(self.env['ir.actions.report'].with_user(self.b)._render_qweb_pdf(
            'account.report_invoice', self.factura_b.ids)[0])
        mensajes = self.env['mail.message'].with_user(self.b).search(
            [('model', '=', 'account.move'), ('res_id', '=', self.factura_b.id)])
        self.assertTrue(mensajes)

    def test_lo_sin_vendedora_lo_ven_todas_y_confirmarlo_es_tomarlo(self):
        for usuario in (self.a, self.b):
            self._visible(self.pedido_libre, usuario, 'pedido sin vendedora')
        self.pedido_libre.with_user(self.a).action_confirm()
        self.assertEqual(self.pedido_libre.user_id, self.a, 'quien confirma lo sin dueña se lo queda')
        self._cerrado(self.pedido_libre, self.b, 'pedido que tomó A')
        self._visible(self.pedido_libre, self.a)

    def test_un_pedido_web_sin_vendedora_facturado_por_caja_queda_en_la_bolsa_comun(self):
        web = self.env['sale.order'].sudo().create({
            'partner_id': self.cliente.id, 'user_id': False,
            'order_line': [Command.create({'product_id': self.producto.id, 'product_uom_qty': 1})]})
        web.action_confirm()
        self.assertFalse(web.user_id)
        factura = web.with_user(self.caja)._create_invoices()
        factura.with_user(self.caja).action_post()
        self.assertFalse(factura.invoice_user_id)
        for usuario in (self.a, self.b):
            self._visible(factura, usuario, 'factura sin vendedora')

    def test_ficha_que_dice_b_a_cotiza_y_factura_a_su_nombre(self):
        cotizacion = self._pedido(self.a, self.cliente_de_b)
        self.assertEqual(cotizacion.user_id, self.a)
        factura = self.env['account.move'].with_user(self.a).create({
            'move_type': 'out_invoice', 'partner_id': self.cliente_de_b.id,
            'invoice_line_ids': [Command.create({'product_id': self.producto.id, 'quantity': 1})]})
        self.assertEqual(factura.invoice_user_id, self.a)
        factura.action_post()
        # Desde la oportunidad de B («Nueva cotización» trae default_user_id = B): igual queda a nombre de A.
        oportunidad = self.env['crm.lead'].create({
            'name': 'Oportunidad de B', 'type': 'opportunity', 'partner_id': self.cliente_de_b.id,
            'user_id': self.b.id})
        desde_oportunidad = self.env['sale.order'].with_user(self.a).with_context(
            default_user_id=self.b.id, default_opportunity_id=oportunidad.id).create({
                'partner_id': self.cliente_de_b.id})
        self.assertEqual(desde_oportunidad.user_id, self.a)
        # Caja no está limitada: Odoo pone a la vendedora de la ficha, como siempre.
        de_caja = self._pedido(self.caja, self.cliente_de_b)
        self.assertEqual(de_caja.user_id, self.b)

    def test_a_factura_caja_cobra_y_b_no_lo_ve(self):
        for diario in (self.efectivo, self.banco):
            with self.subTest(diario=diario.name):
                pedido = self._pedido(self.a, self.cliente)
                pedido.action_confirm()
                factura = pedido._create_invoices()
                factura.action_post()
                self.assertEqual(factura.invoice_user_id, self.a)
                cobro = self._cobrar(self.caja, factura, diario)  # el cobro solo en Caja (A5)
                self.assertIn(factura.payment_state, ('paid', 'in_payment'))
                por_cobrar = factura.with_user(self.a).line_ids.filtered(
                    lambda linea: linea.account_id.account_type == 'asset_receivable')
                self.assertTrue(por_cobrar.matched_credit_ids | por_cobrar.matched_debit_ids)
                self._visible(cobro, self.a)
                self._cerrado(cobro, self.b, 'cobro de A')
                self._cerrado(factura, self.b, 'factura de A')

    def test_a_despacha_el_pedido_de_b(self):
        entrega = self.pedido_b.picking_ids
        self.assertTrue(entrega, 'el pedido de B debe tener su entrega')
        como_a = entrega.with_user(self.a)
        como_a.move_ids.quantity = 1
        como_a.button_validate()
        self.assertEqual(entrega.state, 'done')
        self.assertEqual(self.pedido_b.order_line.qty_delivered, 1)
        # Despachar no le abrió el pedido.
        self._cerrado(self.pedido_b, self.a, 'pedido de B después de despachar')

    def test_caja_ve_factura_y_cobra_de_todas_y_gerencia_hace_la_nota(self):
        for etiqueta, registros in self._de_b():
            with self.subTest(etiqueta):
                self._visible(registros, self.caja, etiqueta)
        pedido = self._pedido(self.a, self.cliente)
        pedido.action_confirm()
        factura = pedido.with_user(self.caja)._create_invoices()
        factura.with_user(self.caja).action_post()
        self._cobrar(self.caja, factura, self.banco)
        with self.assertRaises(AccessError, msg='la nota de crédito es de Gerencia (A7)'):
            self._nota(self.caja, factura)
        nota = self._nota(self.gerencia, factura)
        self.assertEqual((factura.invoice_user_id, nota.invoice_user_id), (self.a, self.a), 'la vendedora no cambia')
        Informe = self.env['ir.actions.report'].with_user(self.caja)
        self.assertTrue(Informe._render_qweb_pdf('account.report_invoice', factura.ids)[0])
        self.assertTrue(Informe._render_qweb_pdf('sale.report_saleorder', self.pedido_b.ids)[0])

    def test_gerencia_contador_y_lector_ven_todo(self):
        # Contabilidad pura (contador, lector) no entra a Ventas: lo suyo es lo contable, y lo ve como hoy.
        contable = ('factura', 'nota de crédito', 'cobro', 'asiento del cobro', 'apuntes', 'conciliaciones',
                    'analítica', 'adjunto')
        for usuario in (self.gerencia, self.contador, self.lector):
            for etiqueta, registros in self._de_b():
                if usuario != self.gerencia and etiqueta not in contable:
                    continue
                with self.subTest(usuario=usuario.login, que=etiqueta):
                    self._visible(registros, usuario, etiqueta)

    def test_guardianes_de_los_roles(self):
        vendedora = self.env.ref('dcasa_base.group_vendedora')
        caja = self.env.ref('dcasa_base.group_caja')
        todos = self.env.ref(TODOS)
        self.assertNotIn(todos, vendedora.all_implied_ids)
        self.assertIn(vendedora, caja.all_implied_ids)
        self.assertIn(todos, caja.all_implied_ids)
        for xmlid in ('sales_team.group_sale_manager', 'account.group_account_user', 'account.group_account_readonly'):
            self.assertNotIn(self.env.ref(xmlid), caja.all_implied_ids, xmlid)
        self.assertIn(caja, self.env.ref('dcasa_base.group_gerencia').all_implied_ids)
        # Nadie que sea solo Vendedora ve los documentos de toda la tienda.
        respetar = caja | self.env.ref('sales_team.group_sale_manager') | self.env.ref('account.group_account_readonly')
        usuarios = self.env['res.users'].with_context(active_test=False).search([('share', '=', False)])
        colados = usuarios.filtered(lambda u: vendedora in u.all_group_ids and todos in u.all_group_ids
                                    and not (respetar & u.all_group_ids))
        self.assertFalse(colados, f'Vendedoras que ven todo: {colados.mapped("login")}')

    def test_la_migracion_quita_todos_los_documentos_puesto_a_mano(self):
        todos = self.env.ref(TODOS)
        a_mano = crear_usuario(self.env, 'sls_a_mano', 'dcasa_base.group_vendedora', TODOS)
        caja_a_mano = crear_usuario(self.env, 'sls_caja_a_mano', 'dcasa_base.group_caja', TODOS)
        archivada = crear_usuario(self.env, 'sls_archivada', 'dcasa_base.group_vendedora', TODOS)
        archivada.active = False
        cambiadas = self.env['res.users']._dcasa_quitar_todos_los_documentos()
        self.assertGreaterEqual(cambiadas, 2)
        self.assertNotIn(todos, a_mano.group_ids)
        self.assertNotIn(todos, archivada.group_ids)
        self.assertIn(todos, caja_a_mano.group_ids, 'a la Caja no se le quita')
        self.assertTrue(a_mano._dcasa_solo_lo_suyo())

    def test_la_migracion_enciende_el_interruptor_una_sola_vez(self):
        vendedora = self.env.ref('dcasa_base.group_vendedora')
        todos = self.env.ref(TODOS)
        vendedora.write({'implied_ids': [Command.link(todos.id)]})  # la base de antes
        Users = self.env['res.users']
        self.assertTrue(Users._dcasa_encender_restriccion_al_migrar())
        self.assertNotIn(todos, vendedora.all_implied_ids)
        self.assertTrue(Users._dcasa_restriccion_activa())
        self.assertFalse(Users._dcasa_encender_restriccion_al_migrar(), 'repetirla no cambia nada')

    def test_nadie_con_caja_deja_el_aviso(self):
        Users = self.env['res.users']
        caja = self.env.ref('dcasa_base.group_caja')
        gerencia = self.env.ref('dcasa_base.group_gerencia')
        con_caja = Users.search([('share', '=', False), ('all_group_ids', 'in', caja.ids)]).filtered(
            lambda u: gerencia not in u.all_group_ids)
        self.assertTrue(con_caja, 'en esta prueba hay una Caja')
        self.assertFalse(Users._dcasa_avisar_si_nadie_tiene_caja())
        con_caja.write({'group_ids': [Command.unlink(caja.id)]})
        with self.assertLogs('odoo.addons.dcasa_base.models.res_users', level='WARNING') as registro:
            self.assertTrue(Users._dcasa_avisar_si_nadie_tiene_caja())
        self.assertIn('Caja', registro.output[0])


@tagged('post_install', '-at_install')
class TestInterruptorSoloLoSuyo(SoloLoSuyoComun):
    """«Cada vendedora ve solo sus documentos»: las dos posiciones y el ida y vuelta."""

    def _grupos_de_todos(self):
        usuarios = self.env['res.users'].with_context(active_test=False).search([])
        return {u.id: set(u.group_ids.ids) for u in usuarios}

    def _apagar_desde_ajustes(self, valor):
        ajustes = self.env['res.config.settings'].create({'dcasa_solo_lo_suyo': valor})
        ajustes.execute()

    def _todo_cerrado_para_a(self):
        self.assertTrue(self.a._dcasa_solo_lo_suyo())
        for etiqueta, registros in self._de_b():
            with self.subTest(etiqueta):
                self._cerrado(registros, self.a, etiqueta)

    def _todo_abierto_para_a(self):
        self.assertFalse(self.a._dcasa_solo_lo_suyo())
        for etiqueta, registros in self._de_b():
            with self.subTest(etiqueta):
                self._visible(registros, self.a, etiqueta)

    def test_ajustes_muestra_la_posicion_actual(self):
        self.assertTrue(self.env['res.config.settings'].create({}).dcasa_solo_lo_suyo)
        self._apagar_desde_ajustes(False)
        self.assertFalse(self.env['res.config.settings'].create({}).dcasa_solo_lo_suyo)
        self.assertFalse(self.env['dcasa.permisos.vendedoras'].with_user(self.gerencia).create({}).solo_lo_suyo)

    def test_apagado_las_vendedoras_ven_todo_como_antes(self):
        antes = self._grupos_de_todos()
        self._apagar_desde_ajustes(False)
        self.assertFalse(self.env['res.users']._dcasa_restriccion_activa())
        self.assertIn(self.env.ref(TODOS), self.env.ref('dcasa_base.group_vendedora').all_implied_ids)
        self._todo_abierto_para_a()
        # Como antes: «Cobros de hoy (caja)» vuelve a estar en su menú y la ficha del cliente vuelve a mandar.
        self.assertIn('dcasa_base.menu_dcasa_cobros_hoy', menus_visibles(self.env, self.a))
        self.assertEqual(self._pedido(self.a, self.cliente_de_b).user_id, self.b)
        # Caja, Gerencia y contabilidad siguen igual, y no se tocó la ficha de nadie.
        for etiqueta, registros in self._de_b():
            self._visible(registros, self.caja, etiqueta)
        self.assertEqual(self._grupos_de_todos(), antes, 'el interruptor no cambia los grupos de ninguna persona')

    def test_ida_y_vuelta_deja_todo_como_estaba(self):
        antes = self._grupos_de_todos()
        menus_a = menus_visibles(self.env, self.a)
        menus_caja = menus_visibles(self.env, self.caja)
        self._todo_cerrado_para_a()
        self.assertNotIn('dcasa_base.menu_dcasa_cobros_hoy', menus_a)
        self.assertIn('dcasa_base.menu_dcasa_cobros_hoy', menus_caja)
        for valor in (False, True, False, True):
            self._apagar_desde_ajustes(valor)
            self.assertEqual(self.env['res.users']._dcasa_restriccion_activa(), valor)
            if valor:
                self._todo_cerrado_para_a()
            else:
                self._todo_abierto_para_a()
            # Caja y Gerencia ven todo en las dos posiciones.
            for usuario in (self.caja, self.gerencia):
                self.assertFalse(usuario._dcasa_solo_lo_suyo())
                self._visible(self.factura_b | self.nota_b, usuario)
                self._visible(self.cobro_b, usuario)
        self.assertEqual(self._grupos_de_todos(), antes)
        self.assertEqual(menus_visibles(self.env, self.a), menus_a)
        self.assertEqual(menus_visibles(self.env, self.caja), menus_caja)
        self.assertNotIn(self.env.ref(TODOS), self.env.ref('dcasa_base.group_vendedora').implied_ids)
        self.assertIn(self.env.ref(TODOS), self.env.ref('dcasa_base.group_caja').implied_ids)
        # Y la vendedora sigue cotizando y quedando como dueña de lo suyo (cobrar, no: eso es de Caja).
        pedido = self._pedido(self.a, self.cliente_de_b)
        self.assertEqual(pedido.user_id, self.a)

    def test_gerencia_lo_mueve_desde_su_pantalla(self):
        Pantalla = self.env['dcasa.permisos.vendedoras'].with_user(self.gerencia)
        pantalla = Pantalla.create({'solo_lo_suyo': False})
        respuesta = pantalla.action_guardar()
        self.assertEqual(respuesta['tag'], 'display_notification')
        self.assertFalse(self.env['res.users']._dcasa_restriccion_activa())
        self._todo_abierto_para_a()
        Pantalla.create({'solo_lo_suyo': True}).action_guardar()
        self.assertTrue(self.env['res.users']._dcasa_restriccion_activa())
        self._todo_cerrado_para_a()
        self.assertIn('dcasa_base.menu_dcasa_permisos_vendedoras', menus_visibles(self.env, self.gerencia))

    def test_vendedora_y_caja_no_mueven_el_interruptor(self):
        for usuario in (self.a, self.caja):
            with self.subTest(usuario.login):
                with self.assertRaises(AccessError):
                    self.env['res.users'].with_user(usuario)._dcasa_poner_restriccion(False)
                with self.assertRaises(AccessError):
                    self.env['dcasa.permisos.vendedoras'].with_user(usuario).create({'solo_lo_suyo': False})
                with self.assertRaises(AccessError):
                    self.env['res.config.settings'].with_user(usuario).create({'dcasa_solo_lo_suyo': False})
                self.assertNotIn('dcasa_base.menu_dcasa_permisos_vendedoras', menus_visibles(self.env, usuario))
        self.assertTrue(self.env['res.users']._dcasa_restriccion_activa())

    def test_guardar_otro_ajuste_no_lo_mueve(self):
        self._apagar_desde_ajustes(False)
        self.env['res.config.settings'].create({'dcasa_descuento_max_vendedora': 12}).execute()
        self.assertFalse(self.env['res.users']._dcasa_restriccion_activa())
        self._apagar_desde_ajustes(True)
        self.env['res.config.settings'].create({'dcasa_descuento_max_vendedora': 10}).execute()
        self.assertTrue(self.env['res.users']._dcasa_restriccion_activa())

    def test_un_despliegue_no_lo_mueve(self):
        """Cada despliegue actualiza el módulo (-u): el rol se vuelve a cargar y el interruptor queda donde estaba."""
        for valor in (False, True):
            with self.subTest(apagado=not valor):
                self._apagar_desde_ajustes(valor)
                for archivo in ('security/dcasa_roles.xml', 'security/dcasa_reglas_ventas.xml',
                                'security/dcasa_reglas_contables.xml'):
                    convert_file(self.env, 'dcasa_base', archivo, {}, mode='update', noupdate=False)
                self.env.registry.clear_cache()
                self.env.invalidate_all()
                self.assertEqual(self.env['res.users']._dcasa_restriccion_activa(), valor)


@tagged('post_install', '-at_install')
class TestSoloLoSuyoHttp(HttpCase):
    """Por la web: el PDF de un informe y un archivo adjunto de lo de B no le llegan a A."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        grupos = [env.ref(g).id for g in ('base.group_user', 'dcasa_base.group_vendedora')]
        Users = env['res.users'].with_context(no_reset_password=True)
        cls.a = Users.create({'name': 'Sls Http A', 'login': 'sls_http_a', 'password': CLAVE,
                              'group_ids': [Command.set(grupos)]})
        cls.b = Users.create({'name': 'Sls Http B', 'login': 'sls_http_b', 'password': CLAVE,
                              'group_ids': [Command.set(grupos)]})
        cliente = env['res.partner'].create({'name': 'Cliente Http Solo Lo Suyo'})
        producto = env['product.product'].create({'name': 'Silla Http Solo Lo Suyo', 'list_price': 50.0})
        cls.pedido_b = env['sale.order'].create({
            'partner_id': cliente.id, 'user_id': cls.b.id,
            'order_line': [Command.create({'product_id': producto.id, 'product_uom_qty': 1})]})
        cls.pedido_b.action_confirm()
        cls.factura_b = cls.pedido_b._create_invoices()
        cls.factura_b.action_post()
        cls.adjunto_b = env['ir.attachment'].create({
            'name': 'factura-http-de-b.pdf', 'res_model': 'account.move', 'res_id': cls.factura_b.id,
            'raw': b'%PDF-1.4 factura http de B', 'mimetype': 'application/pdf'})

    def test_a_no_recibe_el_pdf_ni_el_adjunto_de_b(self):
        self.authenticate('sls_http_a', CLAVE)
        for url in (f'/report/pdf/account.report_invoice/{self.factura_b.id}',
                    f'/report/pdf/sale.report_saleorder/{self.pedido_b.id}',
                    f'/web/content/{self.adjunto_b.id}?download=true'):
            with self.subTest(url):
                respuesta = self.url_open(url, allow_redirects=False)
                self.assertNotEqual(respuesta.status_code, 200, url)
                self.assertNotIn(b'%PDF', respuesta.content)
                self.assertNotIn(self.factura_b.name.encode(), respuesta.content)

    def test_b_si_recibe_lo_suyo(self):
        self.authenticate('sls_http_b', CLAVE)
        respuesta = self.url_open(f'/web/content/{self.adjunto_b.id}?download=true', allow_redirects=False)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.content.startswith(b'%PDF'))
        respuesta = self.url_open(f'/report/pdf/account.report_invoice/{self.factura_b.id}', allow_redirects=False)
        self.assertEqual(respuesta.status_code, 200)
