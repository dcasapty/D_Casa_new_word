"""Un combo de cama + colchón (tipo «Combo» de Odoo) en la factura electrónica de la DGI.

La línea del combo es un título de sección (display_type «line_section»): la DGI nunca la ve. Lo que se declara son
las piezas (la cama y el colchón), cada una con su parte del precio del combo y su ITBMS: no hay líneas en cero.
"""
from lxml import etree

from odoo.addons.dcasa_fe_pa.models import catalogos as C
from odoo.tests import tagged

from .common import FeComun

NS = {'d': C.NAMESPACE}


@tagged('post_install', '-at_install')
class TestComboEnLaFacturaElectronica(FeComun):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        itbms = cls.company.account_sale_tax_id
        cls.colchon = cls.env['product.product'].create({
            'name': 'COLCHON KING DE PRUEBA FE', 'default_code': 'FE-COL', 'type': 'consu', 'list_price': 200.0,
            'taxes_id': [(6, 0, itbms.ids)]})
        cls.cama.write({'list_price': 150.0, 'taxes_id': [(6, 0, itbms.ids)]})
        grupos = cls.env['product.combo'].create([
            {'name': 'Cama', 'combo_item_ids': [(0, 0, {'product_id': cls.cama.id})]},
            {'name': 'Colchón', 'combo_item_ids': [(0, 0, {'product_id': cls.colchon.id})]}])
        cls.combo = cls.env['product.template'].create({
            'name': 'COMBO CAMA KING DE PRUEBA FE', 'type': 'combo', 'list_price': 320.0,
            'taxes_id': [(6, 0, itbms.ids)], 'combo_ids': [(6, 0, grupos.ids)]})

    def _factura_de_combo(self, cliente=None):
        Linea = self.env['sale.order.line']
        orden = self.env['sale.order'].create({'partner_id': (cliente or self.contribuyente).id})
        combo = Linea.create({'order_id': orden.id, 'product_id': self.combo.product_variant_id.id,
                              'product_uom_qty': 1})
        for item in self.combo.combo_ids.combo_item_ids:
            Linea.create({'order_id': orden.id, 'product_id': item.product_id.id, 'product_uom_qty': 1,
                          'combo_item_id': item.id, 'linked_line_id': combo.id})
        orden.action_confirm()
        factura = orden._create_invoices()
        factura.action_post()
        return factura

    def test_la_dgi_recibe_las_piezas_con_su_precio_y_su_itbms_y_nunca_una_linea_en_cero(self):
        factura = self._factura_de_combo()
        self.assertEqual(factura.invoice_line_ids.mapped('display_type'), ['line_section', 'product', 'product'])
        items = factura._l10n_pa_fe_items('01')
        self.assertEqual(len(items), 2, 'El título del combo no es una línea de la factura electrónica')
        self.assertEqual(sorted((i['codigo'], i['precio_item']) for i in items),
                         [('1062010735N', 137.14), ('FE-COL', 182.86)])
        self.assertTrue(all(i['valor_total'] > 0 and i['tasa'] == '01' for i in items))
        self.assertAlmostEqual(sum(i['precio_item'] for i in items), 320.0)
        self.assertAlmostEqual(sum(i['valor_total'] for i in items), factura.amount_total)
        self.assertEqual(factura._l10n_pa_fe_problemas_lineas(), [])

    def test_el_xml_lleva_dos_items_y_el_total_de_la_factura(self):
        self._activar('autorizar')
        factura = self._factura_de_combo()
        (doc,) = factura.l10n_pa_fe_documento_ids
        raiz = etree.fromstring(doc.payload.encode())
        self.assertEqual(len(raiz.findall('d:gItem', namespaces=NS)), 2)
        self.assertEqual(raiz.findtext('d:gTot/d:dVTot', namespaces=NS), '342.40')
        self.assertEqual(raiz.findtext('d:gTot/d:dNroItems', namespaces=NS), '2')
        self.assertNotIn('COMBO CAMA KING', doc.payload, 'El nombre del combo no viaja a la DGI: solo sus piezas')
        self.env['dcasa.fe.documento']._cron_procesar()
        self.assertEqual(doc.estado, 'autorizado')
