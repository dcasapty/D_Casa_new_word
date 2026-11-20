"""La definición única de «venta online» y su testigo de origen (``models/venta_online.py``), sin depender de ningún
módulo que la use. Los casos de la comisión web (Andrés, Juan, bono, Inicio) se prueban en ``dcasa_comision_web``."""
import importlib.util
from pathlib import Path

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

MIGRACION = Path(__file__).resolve().parent.parent / 'migrations' / '19.0.1.10.0' / 'post-migrate.py'


@tagged('post_install', '-at_install')
class TestVentaOnline(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.website = cls.env['website'].search([], limit=1) if 'website' in cls.env else cls.env['res.partner']
        cls.cliente = cls.env['res.partner'].create({'name': 'Cliente venta online base'})
        cls.producto = cls.env['product.product'].create({'name': 'MUEBLE BASE ONLINE', 'type': 'consu'})

    def orden(self, web, **extra):
        valores = {'partner_id': self.cliente.id, 'order_line': [Command.create(
            {'product_id': self.producto.id, 'product_uom_qty': 1, 'price_unit': 10.0})], **extra}
        if web:
            valores['website_id'] = self.website.id
        return self.env['sale.order'].create(valores)

    def test_tener_website_id_no_basta_para_nacer_en_la_web(self):
        """Revisión adversarial (2026-11-19): ``website_id`` se acepta por RPC, así que quien teclea un pedido de
        mostrador con él no lo vuelve «de la web». El origen lo escribe solo el código del carrito del sitio."""
        if not self.website:
            self.skipTest('Sin tienda en línea instalada')
        con_sitio = self.orden(True)
        self.assertFalse(con_sitio.dcasa_nacio_en_web or con_sitio.dcasa_venta_online)
        con_contexto = self.env['sale.order'].with_context(default_website_id=self.website.id).create({
            'partner_id': self.cliente.id})
        self.assertFalse(con_contexto.dcasa_nacio_en_web or con_contexto.dcasa_venta_online)

    def test_el_origen_se_escribe_con_la_llave_interna_y_vale_la_definicion(self):
        web, tienda = self.orden(False), self.orden(False)
        web._dcasa_escribir_marca(dcasa_nacio_en_web=True, dcasa_creada_por_id=self.env.user.id)
        self.assertTrue(web.dcasa_nacio_en_web and web.dcasa_venta_online)
        self.assertEqual(web.dcasa_creada_por_id, self.env.user)
        self.assertFalse(tienda.dcasa_nacio_en_web or tienda.dcasa_venta_online)

    def test_el_campo_calculado_tampoco_se_escribe_a_mano(self):
        """Escribir ``dcasa_venta_online`` (el campo que lee todo el sistema) no cambia nada, ni al crear ni al
        escribir, ni con ``sudo()``."""
        creada = self.orden(False, dcasa_venta_online=True)
        self.assertFalse(creada.dcasa_venta_online, 'al crear se descarta')
        creada.sudo().write({'dcasa_venta_online': True})
        creada.invalidate_recordset()
        self.assertFalse(creada.dcasa_venta_online, 'escribirlo no lo cambia')
        creada._dcasa_escribir_marca(dcasa_nacio_en_web=True)
        creada.sudo().write({'dcasa_venta_online': False, 'origin': 'otra cosa'})
        creada.invalidate_recordset()
        self.assertTrue(creada.dcasa_venta_online, 'ni lo apaga')
        self.assertEqual(creada.origin, 'otra cosa', 'lo demás del write sí pasa')

    def test_la_definicion_es_la_tabla_de_verdad_de_las_tres_marcas(self):
        orden = self.orden(False)
        casos = [(False, False, False, False), (True, False, False, True), (True, False, True, False),
                 (True, True, True, True), (False, True, False, True)]
        for nacio, andres, vendedora, esperado in casos:
            with self.subTest(nacio=nacio, andres=andres, vendedora=vendedora):
                orden.invalidate_recordset()
                self.env.cr.execute(
                    'UPDATE sale_order SET dcasa_nacio_en_web = %s, dcasa_via_andres = %s, '
                    'dcasa_llevada_por_vendedora = %s WHERE id = %s', [nacio, andres, vendedora, orden.id])
                orden.invalidate_recordset()
                self.env.add_to_compute(orden._fields['dcasa_venta_online'], orden)
                self.assertEqual(orden.dcasa_venta_online, esperado)

    def test_nadie_forja_ni_cambia_las_marcas_ni_con_sudo(self):
        orden = self.orden(False, dcasa_nacio_en_web=True, dcasa_via_andres=True)
        self.assertFalse(orden.dcasa_nacio_en_web or orden.dcasa_via_andres, 'al crear se descartan')
        with self.assertRaisesRegex(UserError, 'lo pone el sistema'):
            orden.sudo().write({'dcasa_nacio_en_web': True})
        orden._dcasa_escribir_marca(dcasa_via_andres=True)
        self.assertTrue(orden.dcasa_via_andres and orden.dcasa_venta_online)

    def test_sin_reglas_de_la_comision_web_la_regla_para_las_vendedoras_no_rige(self):
        Orden = self.env['sale.order']
        if 'dcasa.web.reglas' in self.env and self.env['dcasa.web.reglas'].search_count([]):
            self.skipTest('Hay una versión de reglas en esta base')
        self.assertFalse(Orden._dcasa_online_desde())
        self.assertEqual(Orden._dcasa_dominio_no_online_desde('date_order'), [])

    def test_el_factor_online_de_una_factura_sin_pedido_es_cero(self):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.cliente.id,
            'invoice_line_ids': [Command.create({'name': 'Suelta', 'quantity': 1, 'price_unit': 5.0})]})
        self.assertEqual(factura._dcasa_factor_online(), {factura.id: 0.0})

    def test_el_factor_online_no_crece_con_la_cantidad_de_facturas(self):
        """Constante en consultas: sirve al Inicio y al bono por meta con muchas facturas."""
        def facturas(cuantas):
            lotes = self.env['account.move']
            for _ in range(cuantas):
                lotes |= self.env['account.move'].create({
                    'move_type': 'out_invoice', 'partner_id': self.cliente.id,
                    'invoice_line_ids': [Command.create({'name': 'Suelta', 'quantity': 1, 'price_unit': 5.0})]})
            return lotes
        pocas, muchas = facturas(2), facturas(8)
        for lote in (pocas, muchas):
            lote.invalidate_recordset()
        with _contar(self.env.cr) as pocas_n:
            pocas._dcasa_factor_online()
        with _contar(self.env.cr) as muchas_n:
            muchas._dcasa_factor_online()
        self.assertEqual(pocas_n.cuantas, muchas_n.cuantas)

    def test_la_migracion_marca_una_sola_vez_lo_que_ya_nacio_en_la_web(self):
        if not self.website:
            self.skipTest('Sin tienda en línea instalada')
        orden = self.orden(True)
        self.env.cr.execute('UPDATE sale_order SET dcasa_nacio_en_web = FALSE, dcasa_venta_online = FALSE '
                            'WHERE id = %s', [orden.id])
        orden.invalidate_recordset()
        especificacion = importlib.util.spec_from_file_location('migracion_online', MIGRACION)
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        modulo.migrate(self.env.cr, '19.0.1.9.0')
        orden.invalidate_recordset()
        self.assertTrue(orden.dcasa_nacio_en_web and orden.dcasa_venta_online)
        tienda = self.orden(False)
        modulo.migrate(self.env.cr, '19.0.1.9.0')
        tienda.invalidate_recordset()
        self.assertFalse(tienda.dcasa_nacio_en_web, 'un pedido sin sitio no se marca')


class _contar:
    """Cuenta las consultas que se hacen dentro del bloque."""

    def __init__(self, cr):
        self.cr = cr

    def __enter__(self):
        self.inicio = self.cr.sql_log_count
        return self

    def __exit__(self, *_):
        self.cuantas = self.cr.sql_log_count - self.inicio
