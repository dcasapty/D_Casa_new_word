"""Tercera revisión, el origen «venta online»: no se fabrica ni con el enlace factura ↔ pedido (hallazgo 1), ni con
valores por defecto, ni con las marcas, ni con ``sudo``, y quien toca un carrito queda anotado aunque escriba directo en
sus líneas (hallazgo 5). Cada prueba dice en su nombre lo que se intentó. Cifras y personas de PRUEBA."""
# ruff: noqa: E501, UP031, B007, B023, F841, PLW0108, RUF012
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import DIA
from .test_comision import ComisionReloj
from .test_endurecimiento import Liquida
from .test_vendedoras import VendedoraCommon


@tagged('post_install', '-at_install')
class TestOrigenSinEnlaceAMano(VendedoraCommon):
    """Hallazgo 1 (bloqueante): el enlace factura ↔ pedido (``sale_line_ids``) lo escribe solo el código de ventas.
    Antes, Caja, Nómina y Gerencia, cada uno solo y sin ``sudo``, creaban, publicaban y cobraban una factura a mano de
    5,000 enlazada a una línea cualquiera de un pedido online de 1,000: al libro iban 500.00 (10 %)."""

    def roles(self):
        return (self.u_caja, self.u_vendedora, self.u_nomina, self.u_gerencia)

    def factura_a_mano(self, usuario, pedido_online, comando=None):
        return self.env['account.move'].with_user(usuario).create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': DIA,
            'invoice_line_ids': [Command.create({
                'name': 'Mueble de mostrador', 'quantity': 1, 'price_unit': 5000.0,
                'tax_ids': [Command.set(self.itbms.ids)],
                'sale_line_ids': [Command.set(pedido_online.order_line.ids)] if comando is None else comando})]})

    def test_una_factura_de_mostrador_enlazada_a_un_pedido_online_no_se_puede_crear_con_ningun_rol(self):
        self.version(10.0)
        pedido_online = self.orden()
        antes = self.env['account.move'].search_count([('partner_id', '=', self.cliente.id)])
        for usuario in self.roles():
            with self.subTest(usuario=usuario.login):
                self.rechaza(lambda: self.factura_a_mano(usuario, pedido_online))
        self.assertEqual(self.env['account.move'].search_count([('partner_id', '=', self.cliente.id)]), antes)
        self.assertFalse(self.env['dcasa.web.venta'].search([]))
        self.assertFalse(self.libro())

    def test_ni_con_sudo_ni_con_la_llave_en_el_contexto_se_crea_ese_enlace(self):
        self.version(10.0)
        pedido_online = self.orden()
        for contexto in ({}, {'dcasa_base_enlace_de_factura': True}, {'include_business_fields': True}):
            with self.subTest(contexto=list(contexto)):
                with self.assertRaisesRegex(UserError, 'lo pone el sistema'), self.env.cr.savepoint():
                    self.env['account.move'].sudo().with_context(**contexto).create({
                        'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': DIA,
                        'invoice_line_ids': [Command.create({
                            'name': 'Mostrador', 'quantity': 1, 'price_unit': 5000.0,
                            'sale_line_ids': [Command.set(pedido_online.order_line.ids)]})]})

    def test_una_venta_de_la_tienda_ya_cobrada_no_pasa_a_ser_del_sitio_editando_el_enlace(self):
        self.version(10.0)
        tienda = self.venta_web(web=False)
        self.assertFalse(self.venta(tienda))
        pedido_online = self.orden()
        for usuario in (*self.roles(), None):
            with self.subTest(usuario=usuario.login if usuario else 'sudo'):
                lineas = tienda.invoice_line_ids.with_user(usuario) if usuario else tienda.invoice_line_ids.sudo()
                self.rechaza(lambda: lineas.write({'sale_line_ids': [Command.link(pedido_online.order_line.id)]}))
        self.env['dcasa.web.venta']._barrido()
        self.assertFalse(self.venta(tienda), 'el barrido de la noche no la anota como venta del sitio')
        self.assertFalse(self.libro())

    def test_enlazar_la_factura_de_una_vendedora_a_un_pedido_online_no_le_quita_su_bono(self):
        self.version(10.0)
        mia = self.vender(web=False, pago='2030-03-05')
        self.assertEqual(self.bono().cobrado, 1000.0)
        online = self.orden()
        for usuario in (self.u_caja, self.u_nomina, self.u_gerencia):
            with self.subTest(usuario=usuario.login):
                self.rechaza(lambda: mia.invoice_line_ids.with_user(usuario).write(
                    {'sale_line_ids': [Command.link(online.order_line.id)]}))
        self.assertEqual(self.bono().cobrado, 1000.0, 'Caja no le quita a la vendedora una venta de la tienda')

    def test_mover_la_linea_facturada_de_la_tienda_a_un_pedido_online_tampoco_la_vuelve_del_sitio(self):
        """El mismo fin por otro lado: el enlace se queda y se cambia el pedido al que pertenece la línea."""
        self.version(10.0)
        tienda_orden = self.orden(web=False, vendedora=self.u_vendedora)
        factura = self.facturar(tienda_orden)
        self.pagar(factura)
        online = self.orden()
        for usuario in (self.u_caja, self.u_gerencia, self.u_vendedora):
            with self.subTest(usuario=usuario.login):
                with self.assertRaisesRegex(UserError, 'no cambia de pedido'), self.env.cr.savepoint():
                    tienda_orden.order_line.with_user(usuario).write({'order_id': online.id})
        self.env['dcasa.web.venta']._barrido()
        self.assertFalse(self.venta(factura))

    def test_lo_que_se_factura_desde_el_pedido_online_sigue_siendo_venta_del_sitio_por_todos_los_caminos(self):
        """Nada legítimo se rompe: facturar el pedido, el anticipo, la nota de crédito y «anular y crear de nuevo»."""
        self.version(10.0)
        # 1. factura normal
        factura = self.venta_web()
        self.assertEqual(self.venta(factura).comision_centavos, 10000)
        # 2. anticipo del 50 % y factura final que lo descuenta
        orden = self.orden(lineas=[(self.mueble, 2000.0, 1, {})])
        wizard = self.env['sale.advance.payment.inv'].with_context(
            active_model='sale.order', active_ids=orden.ids, active_id=orden.id).create({
                'advance_payment_method': 'percentage', 'amount': 50})
        wizard.create_invoices()
        anticipo = orden.invoice_ids
        anticipo.invoice_date = DIA
        anticipo.action_post()
        self.pagar(anticipo)
        self.assertEqual(self.venta(anticipo).comision_centavos, 10000, '10 % de 1,000 del anticipo')
        final = self.env['sale.advance.payment.inv'].with_context(
            active_model='sale.order', active_ids=orden.ids, active_id=orden.id).create({'advance_payment_method': 'delivered'})
        final.create_invoices()
        segunda = orden.invoice_ids - anticipo
        segunda.invoice_date = DIA
        segunda.action_post()
        self.pagar(segunda)
        self.assertEqual(sum(self.venta(f).comision_centavos for f in (anticipo, segunda)), 20000, '10 % de 2,000 en total')
        # 3. nota de crédito por el asistente de Odoo: copia el enlace y resta
        reverso = self.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=factura.ids).create({
                'journal_id': factura.journal_id.id, 'reason': 'devolución de prueba', 'date': DIA})
        reverso.refund_moves()
        nota = factura.reversal_move_ids
        self.assertEqual(nota.invoice_line_ids.sale_line_ids, factura.invoice_line_ids.sale_line_ids)
        # 4. anular y crear una factura nueva: la nueva sigue enlazada al pedido online
        otra = self.venta_web(pagar=False)
        cambio = self.env['account.move.reversal'].with_context(
            active_model='account.move', active_ids=otra.ids).create({
                'journal_id': otra.journal_id.id, 'reason': 'corregir de prueba', 'date': DIA})
        cambio.modify_moves()
        nueva = cambio.new_move_ids.filtered(lambda m: m.move_type == 'out_invoice')
        self.assertTrue(nueva.invoice_line_ids.sale_line_ids.order_id.dcasa_venta_online)
        nueva.invoice_date = DIA
        nueva.action_post()
        self.assertEqual(nueva._dcasa_factor_online()[nueva.id], 1.0)

    def test_una_factura_ya_enlazada_antes_del_arreglo_conserva_su_origen(self):
        """No hay migración ni marca nueva: lo que ya está enlazado por el camino de ventas se queda como está."""
        self.version(10.0)
        factura = self.venta_web()
        self.env.invalidate_all()
        self.assertEqual(factura._dcasa_factor_online()[factura.id], 1.0)
        self.env['dcasa.web.venta']._barrido()
        self.assertEqual(self.venta(factura).comision_centavos, 10000)


@tagged('post_install', '-at_install')
class TestOrigenPorContextoYMarcas(Liquida):
    """Cierre de B1 (segunda revisión), con las variantes de la tercera: lote, ``copy``, ``Form``, ``ir.default``,
    importar, listas de marcas, ``sudo`` y copias."""

    def _crear(self, usuario, contexto=None, n=1, **extra):
        valores = {'partner_id': self.cliente.id, 'company_id': self.company.id, **extra,
                   'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1,
                                                  'price_unit': 1000.0})]}
        return self.env['sale.order'].with_user(usuario).with_context(**(contexto or {})).create([valores] * n)

    def test_create_en_lote_con_default_en_el_contexto(self):
        for usuario in (self.u_vendedora, self.u_gerencia, self.u_caja):
            with self.subTest(usuario=usuario.login):
                ordenes = self._crear(usuario, {'default_dcasa_nacio_en_web': True, 'default_dcasa_venta_online': True,
                                                'default_dcasa_creada_por_id': self.env.ref('base.public_user').id,
                                                'default_dcasa_tocada_por_id': usuario.id,
                                                'default_dcasa_llevada_por_vendedora': True}, n=2)
                for orden in ordenes:
                    self.assertEqual((orden.dcasa_nacio_en_web, orden.dcasa_venta_online, orden.dcasa_llevada_por_vendedora,
                                      orden.dcasa_creada_por_id.id, orden.dcasa_tocada_por_id.id), (False, False, False, 0, 0))

    def test_copy_con_valores_en_el_argumento_y_name_create(self):
        base = self._crear(self.u_gerencia)
        copia = base.with_user(self.u_gerencia).copy(default={
            'dcasa_nacio_en_web': True, 'dcasa_venta_online': True, 'dcasa_creada_por_id': self.u_vendedora.id})
        self.assertEqual((copia.dcasa_nacio_en_web, copia.dcasa_venta_online, copia.dcasa_creada_por_id.id), (False, False, 0))
        nombre = self.env['sale.order'].with_user(self.u_gerencia).with_context(
            default_dcasa_nacio_en_web=True, default_partner_id=self.cliente.id).name_create('Pedido por nombre')
        self.assertFalse(self.env['sale.order'].browse(nombre[0]).dcasa_nacio_en_web)

    def test_formulario_con_default_en_el_contexto(self):
        modelo = self.env['sale.order'].with_user(self.u_gerencia).with_context(default_dcasa_nacio_en_web=True)
        with Form(modelo) as f:
            f.partner_id = self.cliente
            with f.order_line.new() as ln:
                ln.product_id = self.mueble
        self.assertFalse(f.record.dcasa_nacio_en_web)
        self.assertFalse(f.record.dcasa_venta_online)

    def test_un_valor_por_defecto_del_sistema_no_fabrica_el_origen(self):
        self.env['ir.default'].set('sale.order', 'dcasa_nacio_en_web', True)
        orden = self._crear(self.u_gerencia)
        self.assertFalse(orden.dcasa_nacio_en_web)

    def test_importar_con_columnas_de_origen(self):
        resultado = self.env['sale.order'].with_user(self.u_gerencia).load(
            ['partner_id/.id', 'dcasa_nacio_en_web', 'dcasa_venta_online', 'dcasa_creada_por_id/.id',
             'dcasa_llevada_por_vendedora'],
            [[str(self.cliente.id), '1', '1', str(self.u_vendedora.id), '0']])
        ids = [i for i in (resultado.get('ids') or []) if i]
        for orden in self.env['sale.order'].browse(ids):
            self.assertEqual((orden.dcasa_nacio_en_web, orden.dcasa_venta_online, orden.dcasa_creada_por_id.id), (False, False, 0))

    def test_libro_candado_y_ventas_no_se_crean_por_rpc_ni_con_defaults(self):
        for usuario in (self.u_gerencia, self.u_nomina):
            for modelo, vals in (
                    ('dcasa.web.movimiento', {'empleado_id': self.ana.id, 'company_id': self.company.id, 'tipo': 'ajuste',
                                              'concepto': 'comision', 'centavos': 99999, 'mes': '2030-03-01',
                                              'autor': 'x', 'motivo': 'x'}),
                    ('dcasa.web.candado', {'clave': 99}),
                    ('dcasa.web.venta', {'company_id': self.company.id, 'comision_centavos': 5}),
                    ('dcasa.web.liquidacion.linea', {'empleado_id': self.ana.id, 'concepto': 'comision', 'centavos': 99999})):
                with self.subTest(usuario=usuario.login, modelo=modelo):
                    self.rechaza(lambda: self.env[modelo].with_user(usuario).create(vals))

    def test_liquidacion_y_version_con_mas_valores_por_defecto_en_el_contexto(self):
        contexto = {'default_estado': 'pagada', 'default_aprobada_por': self.u_gerencia.id,
                    'default_pagada_por': self.u_gerencia.id, 'default_avisos': 'todo en orden',
                    'default_cancelada_por': self.u_gerencia.id, 'default_name': 'LQW-9999'}
        liq = self.env['dcasa.web.liquidacion'].with_user(self.u_nomina).with_context(**contexto).create({
            'fecha_desde': '2030-03-01', 'fecha_hasta': '2030-03-31'})
        self.assertEqual((liq.estado, liq.aprobada_por.id, liq.pagada_por.id, liq.avisos, liq.cancelada_por.id), ('borrador', 0, 0, False, 0))
        self.assertNotEqual(liq.name, 'LQW-9999')
        version = self.env['dcasa.web.reglas'].with_user(self.u_nomina).with_context(
            default_anulada=True, default_numero=77, default_autor='Gerencia general', default_anulada_por=self.u_gerencia.id,
            default_motivo_anulacion='x').create({'company_id': self.company.id, 'porcentaje': 0, 'tarifa_fija': 0})
        self.assertEqual((version.anulada, version.numero != 77, version.autor, version.anulada_por.id), (False, True, self.u_nomina.name, 0))

    def test_escribir_las_marcas_a_mano(self):
        orden = self.orden(creado_por=self.env.ref('base.public_user'))
        for usuario in (self.u_vendedora, self.u_gerencia, self.u_caja):
            for campo, valor in (('dcasa_nacio_en_web', False), ('dcasa_creada_por_id', usuario.id),
                                 ('dcasa_tocada_por_id', False), ('dcasa_llevada_por_vendedora', True),
                                 ('dcasa_via_andres', True)):
                with self.subTest(usuario=usuario.login, campo=campo):
                    self.rechaza(lambda: orden.with_user(usuario).write({campo: valor}))
            orden.with_user(usuario).write({'dcasa_venta_online': False})
            self.assertTrue(orden.dcasa_venta_online, 'escribir el calculado no cambia nada')

    def test_sudo_no_fabrica_el_origen_ni_cambia_las_marcas(self):
        orden = self.env['sale.order'].sudo().create({
            'partner_id': self.cliente.id, 'company_id': self.company.id, 'dcasa_nacio_en_web': True,
            'dcasa_venta_online': True, 'dcasa_creada_por_id': self.u_vendedora.id,
            'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1, 'price_unit': 1000.0})]})
        self.assertEqual((orden.dcasa_nacio_en_web, orden.dcasa_venta_online, orden.dcasa_creada_por_id.id), (False, False, 0))
        self.rechaza(lambda: orden.sudo().write({'dcasa_nacio_en_web': True}))
        self.rechaza(lambda: orden.sudo().write({'dcasa_tocada_por_id': self.u_vendedora.id}))

    def test_copiar_una_liquidacion_aprobada_o_una_version_no_copia_el_estado(self):
        self.version(10.0)
        self.venta_web()
        self.avanzar('2030-03-05 15:00:00')
        liq = self.liquidar(usuario=self.u_nomina, hasta='2030-03-31')
        liq.with_user(self.u_nomina).action_aprobar()
        self.assertEqual(liq.estado, 'aprobada')
        copia = liq.with_user(self.u_nomina).copy()
        self.assertEqual((copia.estado, len(copia.linea_ids), copia.aprobada_por.id), ('borrador', 0, 0))
        pausa = self.version(0.0)
        otra = pausa.with_user(self.u_nomina).copy()
        self.assertFalse(otra.anulada)


@tagged('post_install', '-at_install')
class TestHuellaDeQuienTocaElCarrito(ComisionReloj):
    """Hallazgo 5: ``dcasa_tocada_por_id`` no se esquiva escribiendo directo en las líneas por RPC. Un usuario interno
    que crea, cambia (producto, cantidad, precio, descuento) o borra una línea de un pedido que nació por un flujo
    digital queda anotado; la llave ``sale_write_from_compute`` del contexto (que por RPC cualquiera manda) no lo
    esquiva."""

    def setUp(self):
        super().setUp()
        self.otro_mueble = self.env['product.product'].create({
            'name': 'OTRO MUEBLE DE PRUEBA COMISION', 'type': 'consu', 'invoice_policy': 'order', 'list_price': 500.0,
            'taxes_id': [Command.set(self.itbms.ids)]})

    def probar(self, accion, creado_por=None, confirmar=False):
        orden = self.orden(creado_por=creado_por or self.env.ref('base.public_user'), confirmar=confirmar)
        with self.env.cr.savepoint():
            accion(orden)
        self.env.flush_all()
        orden.invalidate_recordset()
        return orden.dcasa_tocada_por_id

    def test_cada_cambio_directo_a_las_lineas_de_un_usuario_interno_deja_huella(self):
        vend, gere = self.u_vendedora, self.u_gerencia
        casos = {
            'precio tecleado por Gerencia': lambda o: o.order_line.with_user(gere).write({'price_unit': 1.0}),
            'precio con la llave sale_write_from_compute en el contexto': lambda o: o.order_line.with_user(gere).with_context(
                sale_write_from_compute=True).write({'price_unit': 1.0}),
            'cantidad de una línea (write directo)': lambda o: o.order_line.with_user(vend).write({'product_uom_qty': 5}),
            'descuento de una línea': lambda o: o.order_line.with_user(vend).write({'discount': 5.0}),
            'cambio de producto de una línea': lambda o: o.order_line.with_user(vend).write({'product_id': self.otro_mueble.id}),
            'línea nueva (create directo, sin precio)': lambda o: self.env['sale.order.line'].with_user(vend).create({
                'order_id': o.id, 'product_id': self.mueble.id, 'product_uom_qty': 2}),
            'línea nueva con la llave en el contexto': lambda o: self.env['sale.order.line'].with_user(vend).with_context(
                sale_write_from_compute=True).create({'order_id': o.id, 'product_id': self.mueble.id,
                                                       'product_uom_qty': 2, 'price_unit': 900.0}),
            'borrar una línea': lambda o: o.order_line.with_user(vend).unlink(),
            'mover a este pedido una línea que era de otro': lambda o: self.orden(web=False, confirmar=False).order_line.with_user(
                gere).write({'order_id': o.id}),
            'cambio de cliente': lambda o: o.with_user(vend).write(
                {'partner_id': self.env['res.partner'].create({'name': 'Otro cliente de prueba'}).id}),
            'cantidad por el pedido': lambda o: o.with_user(vend).write(
                {'order_line': [Command.update(o.order_line.id, {'product_uom_qty': 9})]}),
        }
        for nombre, accion in casos.items():
            with self.subTest(caso=nombre):
                self.assertTrue(self.probar(accion), 'este cambio al carrito no dejó huella de quien lo tocó: ' + nombre)

    def test_lo_que_hace_un_visitante_o_el_servidor_no_deja_huella(self):
        publico = self.env.ref('base.public_user')
        portal = self.env['res.users'].sudo().search([('share', '=', True), ('id', '!=', publico.id)], limit=1)
        casos = {
            'visitante cambia cantidad': lambda o: o.order_line.with_user(publico).sudo().write({'product_uom_qty': 3}),
            'visitante agrega línea': lambda o: self.env['sale.order.line'].with_user(publico).sudo().create({
                'order_id': o.id, 'product_id': self.mueble.id, 'product_uom_qty': 1}),
            'el cálculo de precios de Odoo al cambiar la cantidad (sin que nadie teclee el precio)':
                lambda o: o.order_line.with_context(sale_write_from_compute=True).write({'technical_price_unit': 1000.0}),
            'el precio que repone el propio servidor (el combo armable)': lambda o: o.order_line.with_user(
                self.u_vendedora)._dcasa_reponer_precio(),
            'una línea de envío que pone la tienda': lambda o: self.env['sale.order.line'].with_user(self.u_vendedora).create({
                'order_id': o.id, 'product_id': self.envio.id, 'product_uom_qty': 1, 'price_unit': 50.0, 'is_delivery': True}),
            'un premio (precio negativo)': lambda o: self.env['sale.order.line'].with_user(self.u_vendedora).create({
                'order_id': o.id, 'product_id': self.premio.id, 'product_uom_qty': 1, 'price_unit': -50.0}),
        }
        for nombre, accion in casos.items():
            with self.subTest(caso=nombre):
                self.assertFalse(self.probar(accion), 'esto no es alguien del equipo armando el carrito: ' + nombre)

    def test_un_pedido_de_mostrador_no_se_marca_aunque_el_equipo_cambie_sus_lineas(self):
        tienda = self.orden(web=False, confirmar=False)
        tienda.order_line.with_user(self.u_gerencia).write({'product_uom_qty': 4})
        self.assertFalse(tienda.dcasa_tocada_por_id)

    def test_la_venta_del_sitio_muestra_quien_cambio_las_lineas(self):
        self.version(10.0)
        orden = self.orden(creado_por=self.env.ref('base.public_user'), confirmar=False)
        orden.order_line.with_user(self.u_gerencia).write({'product_uom_qty': 2})
        orden.action_confirm()
        factura = self.facturar(orden)
        self.pagar(factura)
        venta = self.venta(factura)
        self.assertEqual((venta.tocada_por_id, venta.creado_por_personal), (self.u_gerencia, True))
