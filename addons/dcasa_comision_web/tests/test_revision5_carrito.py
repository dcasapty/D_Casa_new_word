"""Quinta revisión adversarial, partes B y C: la llave ``PRECIO_DEL_SISTEMA`` (recálculo de precios de Odoo, cron de la
campaña, pago del visitante), lo que una persona TECLEA en un carrito de la página y las líneas movidas entre pedidos.
Lo tecleado sigue marcado como «lo tocó el equipo» (con cualquier forma de escribirlo); lo que recalcula el servidor no.
El precio de campaña con y sin la llave se prueba en ``website_dcasa``. Datos de PRUEBA."""
# ruff: noqa: E501, B023
import logging

from odoo import Command
from odoo.addons.dcasa_base.models.venta_online import CLAVE_PRECIO
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

_logger = logging.getLogger(__name__)


class Carritos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.publico = cls.env.ref('base.public_user')
        cls.gere = new_test_user(cls.env, login='rev5_gere', groups='base.group_user,dcasa_base.group_gerencia')
        cls.nomi = new_test_user(cls.env, login='rev5_nomi', groups='base.group_user,dcasa_nomina.group_nomina')
        cls.caja = new_test_user(cls.env, login='rev5_caja', groups='base.group_user,dcasa_base.group_caja')
        cls.vend = new_test_user(cls.env, login='rev5_vend', groups='base.group_user,dcasa_base.group_vendedora')
        cls.itbms = cls.env.company.account_sale_tax_id
        cls.mueble = cls.env['product.product'].create({'name': 'MUEBLE carrito 5', 'type': 'consu', 'list_price': 1000.0, 'taxes_id': [Command.set(cls.itbms.ids)]})
        cls.mueble2 = cls.env['product.product'].create({'name': 'MUEBLE2 carrito 5', 'type': 'consu', 'list_price': 700.0})
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente carrito 5'})
        cls.cliente2 = cls.env['res.partner'].create({'name': 'Otro cliente carrito'})

    def carrito(self, web=True, lineas=None, **extra):
        o = self.env['sale.order'].create({'partner_id': self.cliente.id, 'order_line': [Command.create({
            'product_id': (p or self.mueble).id, 'product_uom_qty': q}) for p, q in (lineas or [(self.mueble, 1)])], **extra})
        if web:
            o._dcasa_escribir_marca(dcasa_nacio_en_web=True, dcasa_creada_por_id=self.publico.id)
        return o

    def roles(self):
        # la vendedora no escribe en pedidos que no son suyos (regla de registro): se prueba aparte
        return {'gerencia': self.gere, 'nomina': self.nomi, 'caja': self.caja}

    def marca(self, o):
        o.invalidate_recordset(['dcasa_tocada_por_id'])
        return o.dcasa_tocada_por_id


@tagged('post_install', '-at_install')
class TestLoTecleadoSigueMarcado(Carritos):
    """C: lo que una persona TECLEA sigue marcado, con cualquier forma de escribirlo."""

    def casos(self, o, linea):
        return {
            'price_unit': lambda: linea.write({'price_unit': 500.0}),
            'price_unit y technical': lambda: linea.write({'price_unit': 500.0, 'technical_price_unit': 500.0}),
            'discount solo': lambda: linea.write({'discount': 20.0}),
            'discount 100': lambda: linea.write({'discount': 100.0}),
            'discount y price iguales': lambda: linea.write({'discount': 0.0, 'price_unit': linea.price_unit}),
            'qty': lambda: linea.write({'product_uom_qty': 3}),
            'producto': lambda: linea.write({'product_id': self.mueble2.id}),
            'tax_ids': lambda: linea.write({'tax_ids': [Command.clear()]}),
            'order.write order_line update price': lambda: o.write({'order_line': [Command.update(linea.id, {'price_unit': 1.0})]}),
            'order.write order_line update discount': lambda: o.write({'order_line': [Command.update(linea.id, {'discount': 10.0})]}),
            'order.write order_line create': lambda: o.write({'order_line': [Command.create({'product_id': self.mueble2.id, 'product_uom_qty': 1})]}),
            'order.write order_line create con precio': lambda: o.write({'order_line': [Command.create({'product_id': self.mueble2.id, 'product_uom_qty': 1, 'price_unit': 5.0})]}),
            'order.write order_line unlink': lambda: o.write({'order_line': [Command.delete(linea.id)]}),
            'line.create': lambda: o.env['sale.order.line'].create({'order_id': o.id, 'product_id': self.mueble2.id, 'product_uom_qty': 1}),
            'line.create con precio': lambda: o.env['sale.order.line'].create({'order_id': o.id, 'product_id': self.mueble2.id, 'product_uom_qty': 1, 'price_unit': 9000.0}),
            'line.create default_price_unit': lambda: o.env['sale.order.line'].with_context(default_price_unit=9000.0).create({'order_id': o.id, 'product_id': self.mueble2.id, 'product_uom_qty': 1}),
            'line.copy': lambda: linea.copy({'order_id': o.id, 'price_unit': 800.0}),
            'line.unlink': linea.unlink,
            'ctx sale_write_from_compute': lambda: linea.with_context(sale_write_from_compute=True).write({'price_unit': 400.0}),
            'ctx force_price_recomputation': lambda: linea.with_context(force_price_recomputation=True).write({'price_unit': 400.0}),
            'ctx clave como True (JSON)': lambda: linea.with_context(**{CLAVE_PRECIO: True}).write({'price_unit': 400.0}),
            'ctx clave como texto (JSON)': lambda: linea.with_context(**{CLAVE_PRECIO: 'dcasa_base_precio_del_sistema'}).write({'price_unit': 400.0}),
            'order pricelist': lambda: o.write({'pricelist_id': self.lista().id}),
            'order pricelist asignado': lambda: setattr(o, 'pricelist_id', self.lista()),
            'order fiscal position': lambda: o.write({'fiscal_position_id': self.posicion().id}),
            'order partner': lambda: o.write({'partner_id': self.cliente2.id}),
        }

    def lista(self):
        return self.env['product.pricelist'].sudo().search([('name', '=', 'Lista carrito 5')], limit=1) or self.env['product.pricelist'].sudo().create({'name': 'Lista carrito 5', 'item_ids': [Command.create({
            'applied_on': '3_global', 'compute_price': 'percentage', 'percent_price': 50})]})

    def posicion(self):
        return self.env['account.fiscal.position'].sudo().search([('name', '=', 'Posicion carrito 5')], limit=1) or self.env['account.fiscal.position'].sudo().create({'name': 'Posicion carrito 5'})

    def test_revision5_c01_lo_tecleado_por_alguien_interno_deja_marca(self):
        sin_marca = []
        for rol, usuario in self.roles().items():
            for nombre in self.casos(self.carrito(), self.carrito().order_line):
                o = self.carrito()
                linea = o.order_line[0]
                self.assertFalse(self.marca(o))
                try:
                    with self.env.cr.savepoint():
                        self.casos(o.with_user(usuario), linea.with_user(usuario))[nombre]()
                except (UserError, AccessError, ValidationError) as e:
                    _logger.info('c01 [%s] %s: bloqueado %s', rol, nombre, str(e)[:60].replace('\n', ' '))
                    continue
                m = self.marca(o)
                _logger.info('c01 [%s] %s: marca=%s', rol, nombre, m.login)
                if not m:
                    sin_marca.append((rol, nombre))
        _logger.info('c01 SIN MARCA: %s', sin_marca)
        self.assertFalse(sin_marca, sin_marca)


@tagged('post_install', '-at_install')
class TestRecalculoDelServidor(Carritos):
    """El recalculo del servidor no marca; el de una persona que antes tecleo, sigue marcado."""

    def test_revision5_c02_actualizar_precios_sin_cambios_previos_no_marca_a_nadie(self):
        for rol, usuario in self.roles().items():
            o = self.carrito()
            o.with_user(usuario).action_update_prices()
            _logger.info('c02 [%s] action_update_prices solo: marca=%s', rol, self.marca(o).login)
            self.assertFalse(self.marca(o))

    def test_revision5_c03_teclear_y_luego_actualizar_precios_la_marca_se_queda(self):
        for usuario in self.roles().values():
            o = self.carrito()
            o.order_line.with_user(usuario).write({'price_unit': 5000.0})
            self.assertEqual(self.marca(o), usuario)
            o.with_user(usuario).action_update_prices()
            self.assertEqual(self.marca(o), usuario)
            self.assertEqual(o.order_line.price_unit, 1000.0, 'recalcular reinicia el precio tecleado')

    def test_revision5_c04_cambiar_la_lista_o_la_posicion_y_actualizar_marca(self):
        lista = self.env['product.pricelist'].create({'name': 'Lista carrito c04', 'item_ids': [Command.create({
            'applied_on': '3_global', 'compute_price': 'percentage', 'percent_price': 50})]})
        for rol, usuario in self.roles().items():
            o = self.carrito()
            o.with_user(usuario).write({'pricelist_id': lista.id})
            o.with_user(usuario).action_update_prices()
            self.assertEqual(self.marca(o), usuario, rol)
            o2 = self.carrito()
            fp = self.env['account.fiscal.position'].create({'name': 'Pos carrito c04 ' + rol})
            o2.with_user(usuario).write({'fiscal_position_id': fp.id})
            self.assertEqual(self.marca(o2), usuario, rol)

    def test_revision5_c05_quien_cambia_el_precio_de_lista_y_actualiza_no_deja_marca_pero_solo_gerencia_puede(self):
        """Menor 3 (consecuencia buscada de «lo que recalcula el servidor no cuenta»; ver ``docs/COMISION_WEB.md``):
        quien tiene permiso de precios (Gerencia) cambia el precio de lista de un producto y toca «Actualizar precios» en
        el carrito de un visitante: lo recalcula el servidor con la llave y no queda marca (el cambio queda en el chatter
        del producto). Nómina y Caja ni siquiera pueden cambiar precios."""
        carrito = self.carrito()
        self.mueble.with_user(self.gere).write({'list_price': 5000.0})
        carrito.with_user(self.gere).action_update_prices()
        self.assertEqual(carrito.order_line.price_unit, 5000.0, 'el servidor recalculó con el precio nuevo')
        self.assertFalse(self.marca(carrito))
        for usuario in (self.nomi, self.caja):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.mueble.with_user(usuario).write({'list_price': 1.0})

    def test_revision5_c06_solo_gerencia_crea_reglas_de_la_lista_de_precios(self):
        lista = self.env['product.pricelist'].search([], limit=1)
        valores = {'pricelist_id': lista.id, 'applied_on': '1_product', 'product_tmpl_id': self.mueble.product_tmpl_id.id,
                   'compute_price': 'fixed', 'fixed_price': 7777.0}
        self.env['product.pricelist.item'].with_user(self.gere).create(valores)
        for usuario in (self.nomi, self.caja):
            with self.subTest(usuario=usuario.login), self.assertRaises(AccessError):
                self.env['product.pricelist.item'].with_user(usuario).create(valores)


@tagged('post_install', '-at_install')
class TestMoverLineasEntrePedidos(Carritos):

    def mover(self, forma, usuario, origen, objetivo):
        """Pasa una línea (o varias) de ``origen`` a ``objetivo`` de la forma ``forma``, como ``usuario``."""
        l1, l2 = origen.order_line
        L1, L2, T = l1.with_user(usuario), l2.with_user(usuario), objetivo.with_user(usuario)
        Linea = self.env['sale.order.line'].with_user(usuario)
        formas = {
            'write order_id': lambda: L1.write({'order_id': objetivo.id}),
            'order.write link': lambda: T.write({'order_line': [Command.link(l1.id)]}),
            'order.write set': lambda: T.write({'order_line': [Command.set(T.order_line.ids + l1.ids)]}),
            'copy+unlink': lambda: (L1.copy({'order_id': objetivo.id}), L1.unlink()),
            'varias lineas': lambda: (L1 | L2).write({'order_id': objetivo.id}),
            'write mezclado': lambda: (L1 | Linea.browse(objetivo.order_line.ids)).write({'order_id': objetivo.id}),
            'create+write': lambda: (Linea.create({'order_id': objetivo.id, 'product_id': self.mueble.id, 'product_uom_qty': 1}),
                                     L1.write({'order_id': objetivo.id})),
            'con precio': lambda: L1.write({'order_id': objetivo.id, 'price_unit': 4000.0}),
        }
        formas[forma]()

    def test_revision5_c10_mover_lineas_entre_pedidos_marca_ambos_con_todas_las_formas(self):
        faltan = []
        for rol, usuario in self.roles().items():
            for forma in ('write order_id', 'order.write link', 'order.write set', 'copy+unlink', 'varias lineas',
                          'write mezclado', 'create+write', 'con precio'):
                for objetivo, nombre in ((self.carrito(web=False), 'mostrador'), (self.carrito(), 'online')):
                    origen = self.carrito(lineas=[(self.mueble, 1), (self.mueble2, 1)])
                    try:
                        with self.env.cr.savepoint():
                            self.mover(forma, usuario, origen, objetivo)
                    except (UserError, AccessError, ValidationError) as e:
                        _logger.info('c10 [%s] %s -> %s: bloqueado %s', rol, forma, nombre, str(e)[:60])
                        continue
                    ok_origen = self.marca(origen) == usuario
                    ok_destino = (self.marca(objetivo) == usuario) if nombre == 'online' else True
                    if not (ok_origen and ok_destino):
                        faltan.append((rol, forma, nombre))
        self.assertFalse(faltan, faltan)


@tagged('post_install', '-at_install')
class TestLlaveDePrecioDelSistema(Carritos):
    """B: la llave no se filtra (no es un valor de JSON) y no sobrevive al recálculo."""

    def test_revision5_b01_la_llave_no_sobrevive_al_recalculo(self):
        o = self.carrito()
        o.with_user(self.gere).action_update_prices()
        # despues de recalcular, una persona que teclea deja marca
        o.order_line.with_user(self.gere).write({'price_unit': 777.0})
        self.assertEqual(self.marca(o), self.gere)

    def test_revision5_b02_la_llave_no_es_un_valor_de_json(self):
        from odoo.addons.dcasa_base.models import venta_online as vo
        self.assertIsNot(vo.PRECIO_DEL_SISTEMA, True)
        self.assertFalse(isinstance(vo.PRECIO_DEL_SISTEMA, (bool, int, str, dict, list)))
        import json
        with self.assertRaises(TypeError):
            json.dumps({CLAVE_PRECIO: vo.PRECIO_DEL_SISTEMA})
