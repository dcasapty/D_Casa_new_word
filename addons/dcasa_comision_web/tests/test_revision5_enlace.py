"""Quinta revisión adversarial, parte A: otras entradas al enlace factura ↔ pedido (``sale_line_ids`` e
``invoice_lines``) sin la llave interna, cada rol SOLO y SIN ``sudo``, y de punta a punta (crear → publicar → cobrar →
libro). La puerta del enlace (``dcasa_base/models/enlace_factura.py``) no se desarmó en esta ronda: ninguna de estas
entradas fabrica un enlace, quita uno ni deja una venta del sitio fabricada. Lo que el revisor SÍ encontró en esta parte
(editar el precio o la cantidad de una factura en borrador y un anticipo mayor que el pedido) no es una puerta del
enlace sino la base facturada: ver ``test_revision5_facturado``. Datos de PRUEBA."""
# ruff: noqa: E501, UP031, B007, B023, F841, PLW0108, RUF012
import logging

from odoo import Command
from odoo.addons.dcasa_comision_web.tests.common import DIA
from odoo.addons.dcasa_comision_web.tests.test_vendedoras import VendedoraCommon
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestEnlaceOtrasEntradas(VendedoraCommon):

    def roles(self):
        return {'caja': self.u_caja, 'vendedora': self.u_vendedora, 'nomina': self.u_nomina,
                'gerencia': self.u_gerencia, 'tecnico': self.u_tecnico}

    def intentar(self, nombre, rol, funcion):
        try:
            with self.env.cr.savepoint():
                funcion()
        except (UserError, AccessError, ValidationError) as e:
            _logger.info('%s [%s]: BLOQUEADO %s: %s', nombre, rol, type(e).__name__, str(e)[:90].replace('\n', ' '))
            return 'BLOQ'
        except Exception as e:  # noqa: BLE001
            _logger.info('%s [%s]: ERROR %s: %s', nombre, rol, type(e).__name__, str(e)[:140].replace('\n', ' '))
            return 'ERR'
        _logger.info('%s [%s]: PASO', nombre, rol)
        return 'PASO'

    def borrador_mostrador(self, usuario=None):
        Move = self.env['account.move']
        if usuario:
            Move = Move.with_user(usuario)
        return Move.create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': DIA,
            'invoice_line_ids': [Command.create({'name': 'Mueble de mostrador', 'quantity': 1, 'price_unit': 5000.0,
                                                 'tax_ids': [Command.set(self.itbms.ids)]})]})

    def hay_enlace(self, factura, pedido):
        return bool(factura.invoice_line_ids.sale_line_ids & pedido.order_line)

    def ciclo_completo(self, factura, online):
        """Publica y cobra la factura: ¿entra una venta del sitio?"""
        factura.action_post()
        self.pagar(factura)
        return self.venta(factura)

    def probar(self, nombre, fabricar):
        """``fabricar(usuario, online)`` devuelve la factura de mostrador (con o sin enlace). Se exige que NO termine con
        una venta del sitio ni con enlace."""
        self.version(10.0)
        for rol, usuario in self.roles().items():
            online = self.orden()
            libro_antes = len(self.libro())
            with self.subTest(vector=nombre, rol=rol):
                try:
                    with self.env.cr.savepoint():
                        factura = fabricar(usuario, online)
                        enlace = self.hay_enlace(factura, online)
                        venta = False
                        if factura.state == 'draft':
                            try:
                                with self.env.cr.savepoint():
                                    venta = self.ciclo_completo(factura, online)
                            except (UserError, AccessError, ValidationError) as e:
                                _logger.info('%s [%s]: no se pudo publicar/cobrar: %s', nombre, rol, str(e)[:80])
                        _logger.info('%s [%s]: factura creada enlace=%s venta=%s libro+=%s', nombre, rol, enlace, bool(venta), len(self.libro()) - libro_antes)
                        self.assertFalse(enlace, 'SE FABRICO EL ENLACE (%s por %s)' % (nombre, rol))
                        self.assertFalse(venta, 'ENTRO UNA VENTA DEL SITIO FABRICADA (%s por %s)' % (nombre, rol))
                except (UserError, AccessError, ValidationError) as e:
                    _logger.info('%s [%s]: BLOQUEADO %s', nombre, rol, str(e)[:90].replace('\n', ' '))

    # --- vectores nuevos ---
    def test_revision5_a01_copy_con_include_business_fields(self):
        def f(usuario, online):
            fo = online._create_invoices()          # borrador del pedido online (camino legitimo)
            c = fo.with_user(usuario).with_context(include_business_fields=True).copy()
            for linea in c.invoice_line_ids:
                linea.price_unit = 5000.0   # sin usuario: edita el precio
            return c
        self.probar('a01 move.copy include_business_fields', f)

    def test_revision5_a02_line_copy_con_include_business_fields_hacia_otra_factura(self):
        def f(usuario, online):
            fo = online._create_invoices()
            borrador = self.borrador_mostrador()
            fo.invoice_line_ids.with_user(usuario).with_context(include_business_fields=True).copy(default={'move_id': borrador.id, 'price_unit': 5000.0})
            return borrador
        self.probar('a02 line.copy include_business_fields', f)

    def test_revision5_a03_default_invoice_line_ids_con_enlace_adentro(self):
        def f(usuario, online):
            return self.env['account.move'].with_user(usuario).with_context(
                default_invoice_line_ids=[[0, 0, {'name': 'X', 'quantity': 1, 'price_unit': 5000.0, 'sale_line_ids': [[6, 0, online.order_line.ids]]}]]).create({
                    'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': DIA})
        self.probar('a03 default_invoice_line_ids con enlace', f)

    def test_revision5_a04_ir_default_del_tecnico(self):
        self.version(10.0)
        online = self.orden()
        for rol in ('tecnico', 'gerencia', 'nomina', 'caja'):
            usuario = self.roles()[rol]
            borrador = self.borrador_mostrador()
            def f():
                self.env['ir.default'].with_user(usuario).set('account.move.line', 'sale_line_ids', online.order_line.ids)
                self.env['account.move.line'].with_user(usuario).create({'move_id': borrador.id, 'name': 'Otra', 'quantity': 1, 'price_unit': 5000.0, 'display_type': 'product'})
                if not self.hay_enlace(borrador, online):
                    raise UserError('sin enlace')
            r = self.intentar('a04 ir.default sale_line_ids', rol, f)
            with self.subTest(rol=rol):
                self.assertNotEqual(r, 'PASO')
        # el otro lado
        for rol in ('tecnico', 'gerencia'):
            usuario = self.roles()[rol]
            borrador = self.borrador_mostrador()
            def g():
                self.env['ir.default'].with_user(usuario).set('sale.order.line', 'invoice_lines', borrador.invoice_line_ids.ids)
                self.env['sale.order.line'].with_user(usuario).create({'order_id': online.id, 'product_id': self.mueble.id, 'product_uom_qty': 1, 'price_unit': 1.0})
                if not borrador.invoice_line_ids.sale_line_ids:
                    raise UserError('sin enlace')
            r = self.intentar('a04b ir.default invoice_lines', rol, g)
            with self.subTest(rol=rol, lado='so'):
                self.assertNotEqual(r, 'PASO')

    def test_revision5_a05_quitar_el_enlace_de_una_factura_online(self):
        """El camino inverso: quitar el enlace de una factura online (para que sea de la vendedora)."""
        self.version(10.0)
        for rol, usuario in self.roles().items():
            online = self.orden()
            fo = self.facturar(online)
            self.pagar(fo)
            linea = fo.invoice_line_ids
            sl = online.order_line
            for nombre, f in (
                    ('unlink3', lambda: linea.with_user(usuario).write({'sale_line_ids': [Command.unlink(sl.id)]})),
                    ('clear5', lambda: linea.with_user(usuario).write({'sale_line_ids': [Command.clear()]})),
                    ('set6vacio', lambda: linea.with_user(usuario).write({'sale_line_ids': [Command.set([])]})),
                    ('so_unlink', lambda: sl.with_user(usuario).write({'invoice_lines': [Command.unlink(linea.id)]})),
                    ('so_clear', lambda: sl.with_user(usuario).write({'invoice_lines': [Command.clear()]})),
                    ('so_set', lambda: sl.with_user(usuario).write({'invoice_lines': [Command.set([])]})),
                    ('move_write', lambda: fo.with_user(usuario).write({'line_ids': [Command.update(linea.id, {'sale_line_ids': [Command.clear()]})]})),
                    ('via_update_del_pedido', lambda: online.with_user(usuario).write({'order_line': [Command.update(sl.id, {'invoice_lines': [Command.clear()]})]})),
                    ('via_update_de_la_linea', lambda: linea.with_user(usuario).write({'sale_line_ids': [Command.update(sl.id, {'invoice_lines': [Command.clear()]})]})),
                    ('via_update_de_la_linea_so', lambda: sl.with_user(usuario).write({'invoice_lines': [Command.update(linea.id, {'sale_line_ids': [Command.clear()]})]})),
            ):
                self.intentar('a05 %s' % nombre, rol, f)
                with self.subTest(rol=rol, via=nombre):
                    self.assertEqual(linea.sale_line_ids, sl, 'SE QUITO EL ENLACE por %s [%s]' % (nombre, rol))

    def test_revision5_a06_web_save_y_onchange(self):
        def f(usuario, online):
            borrador = self.borrador_mostrador()
            Line = self.env['account.move.line'].with_user(usuario)
            if hasattr(Line, 'web_save'):
                Line.web_save({'move_id': borrador.id, 'name': 'X', 'quantity': 1, 'price_unit': 5000.0, 'display_type': 'product',
                               'sale_line_ids': [[6, 0, online.order_line.ids]]}, {'id': {}})
            return borrador
        self.probar('a06 line.web_save con enlace', f)

        def g(usuario, online):
            Line = self.env['account.move.line'].with_user(usuario).with_context(default_sale_line_ids=[[6, 0, online.order_line.ids]])
            borrador = self.borrador_mostrador()
            if hasattr(Line, 'web_save'):
                Line.web_save({'move_id': borrador.id, 'name': 'X', 'quantity': 1, 'price_unit': 5000.0, 'display_type': 'product'}, {'id': {}})
            return borrador
        self.probar('a06b line.web_save con default_sale_line_ids', g)

    def test_revision5_a07_move_web_save_con_lineas_y_default(self):
        def f(usuario, online):
            Move = self.env['account.move'].with_user(usuario).with_context(default_sale_line_ids=[[6, 0, online.order_line.ids]])
            r = Move.web_save({'move_type': 'out_invoice', 'partner_id': self.cliente.id, 'invoice_date': DIA,
                               'invoice_line_ids': [[0, 'virtual_1', {'name': 'X', 'quantity': 1, 'price_unit': 5000.0}]]}, {'id': {}})
            return self.env['account.move'].browse(r[0]['id']) if isinstance(r, list) else r
        self.probar('a07 move.web_save lineas + default_sale_line_ids', f)

    def test_revision5_a08_sale_order_lines_anidadas_con_invoice_lines(self):
        self.version(10.0)
        online = self.orden()
        for rol, usuario in self.roles().items():
            borrador = self.borrador_mostrador()
            def f():
                self.env['sale.order'].with_user(usuario).create({
                    'partner_id': self.cliente.id,
                    'order_line': [Command.create({'product_id': self.mueble.id, 'product_uom_qty': 1, 'price_unit': 1.0, 'invoice_lines': [Command.set(borrador.invoice_line_ids.ids)]})]})
                if not borrador.invoice_line_ids.sale_line_ids:
                    raise UserError('sin enlace')
            r = self.intentar('a08 sale.order.create anidado invoice_lines', rol, f)
            with self.subTest(rol=rol):
                self.assertNotEqual(r, 'PASO')
            def g():
                self.env['sale.order'].with_user(usuario).with_context(default_order_line=[[0, 0, {'product_id': self.mueble.id, 'product_uom_qty': 1, 'price_unit': 1.0, 'invoice_lines': [[6, 0, borrador.invoice_line_ids.ids]]}]]).create({'partner_id': self.cliente.id})
                if not borrador.invoice_line_ids.sale_line_ids:
                    raise UserError('sin enlace')
            r = self.intentar('a08b sale.order.create default_order_line', rol, g)
            with self.subTest(rol=rol, v='default_order_line'):
                self.assertNotEqual(r, 'PASO')

    def test_revision5_a09_lista_de_enteros_y_formas_raras_de_comando(self):
        self.version(10.0)
        online = self.orden()
        sl = online.order_line
        for rol, usuario in self.roles().items():
            borrador = self.borrador_mostrador()
            linea = borrador.invoice_line_ids
            for nombre, valor in (('enteros', [sl.id]), ('link2', [[4, sl.id]]), ('link_str', [[4, str(sl.id), 0]]),
                                  ('tupla', [(4, sl.id, 0)]), ('set_str', [[6, 0, [str(sl.id)]]]), ('registro', sl),
                                  ('mezcla', [[5, 0, 0], [4, sl.id, 0]]), ('tipo_str', [['4', sl.id, 0]]),
                                  ('tipo_float', [[4.0, sl.id, 0]]), ('dict', {'a': sl.id})):
                def f():
                    linea.with_user(usuario).write({'sale_line_ids': valor})
                self.intentar('a09 write sale_line_ids %s' % nombre, rol, f)
                with self.subTest(rol=rol, forma=nombre):
                    linea.invalidate_recordset()
                    self.assertFalse(linea.sale_line_ids, 'SE ENLAZO con %s [%s]' % (nombre, rol))
                def g():
                    self.env['account.move.line'].with_user(usuario).create({'move_id': borrador.id, 'name': 'Y', 'quantity': 1, 'price_unit': 1.0, 'display_type': 'product', 'sale_line_ids': valor})
                self.intentar('a09 create sale_line_ids %s' % nombre, rol, g)
                with self.subTest(rol=rol, forma=nombre, v='create'):
                    borrador.invalidate_recordset()
                    self.assertFalse(borrador.invoice_line_ids.sale_line_ids, 'SE ENLAZO en create con %s [%s]' % (nombre, rol))

    def test_revision5_a10_default_get_directo_no_trae_el_enlace(self):
        self.version(10.0)
        online = self.orden()
        for rol, usuario in self.roles().items():
            r = self.env['account.move.line'].with_user(usuario).with_context(default_sale_line_ids=[[6, 0, online.order_line.ids]]).default_get(['sale_line_ids', 'name'])
            with self.subTest(rol=rol):
                self.assertNotIn('sale_line_ids', r)
            r = self.env['sale.order.line'].with_user(usuario).with_context(default_invoice_lines=[[6, 0, [1]]]).default_get(['invoice_lines'])
            with self.subTest(rol=rol, lado='so'):
                self.assertNotIn('invoice_lines', r)

    def test_revision5_a13_campos_calculados_que_reflejan_el_enlace(self):
        """``sale.order.invoice_ids`` (calculado): escribirlo no debe enlazar nada."""
        self.version(10.0)
        online = self.orden()
        for rol, usuario in self.roles().items():
            borrador = self.borrador_mostrador()
            for nombre, f in (('invoice_ids link', lambda: online.with_user(usuario).write({'invoice_ids': [Command.link(borrador.id)]})),
                              ('invoice_ids set', lambda: online.with_user(usuario).write({'invoice_ids': [Command.set(borrador.ids)]})),
                              ('order_line.invoice_lines via sale.order.create', lambda: self.env['sale.order'].with_user(usuario).create({'partner_id': self.cliente.id, 'invoice_ids': [Command.link(borrador.id)]}))):
                r = self.intentar('a13 %s' % nombre, rol, f)
                with self.subTest(rol=rol, via=nombre):
                    borrador.invalidate_recordset()
                    self.assertFalse(borrador.invoice_line_ids.sale_line_ids, 'SE ENLAZO por %s [%s]' % (nombre, rol))
