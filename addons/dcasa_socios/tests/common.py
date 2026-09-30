import os
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase

from ..models import reglas as R


class SociosCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.company = cls.env.ref('base.main_company')
        # ITBMS que se suma al precio (como en la factura real): el de la tienda ya lo incluye.
        cls.itbms = cls.env['account.tax'].search([
            ('company_id', '=', cls.company.id), ('type_tax_use', '=', 'sale'),
            ('amount', '=', 7), ('price_include', '=', False)], limit=1)
        cls.producto = cls.env['product.product'].create({
            'name': 'CAMA QUEEN GREY CON ESTANTES', 'type': 'consu', 'invoice_policy': 'order',
            'list_price': 100.0, 'taxes_id': [(6, 0, cls.itbms.ids)],
        })
        Partner = cls.env['res.partner']
        cls.padrino = Partner.create({'name': 'Ana Pérez', 'phone': '+507 6000-0001'})
        cls.padrino._dcasa_asegurar_ficha()
        cls.cliente = Partner.create({'name': 'Eric Gómez', 'phone': '6000-0002'})

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def reglas_con(self, **cambios):
        """Reglas reales con algunos valores cambiados (p. ej. topes más bajos)."""
        reglas = R.cargar_reglas()
        for ruta, valor in cambios.items():
            seccion, clave = ruta.split('__')
            reglas[seccion][clave] = valor
        return patch('odoo.addons.dcasa_socios.models.reglas.cargar_reglas', return_value=reglas)

    def factura(self, partner=None, precio=100.0, pagar=True):
        """Factura de cliente con ITBMS; pagada por defecto."""
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': (partner or self.cliente).id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {'product_id': self.producto.id, 'quantity': 1, 'price_unit': precio})],
        })
        factura.action_post()
        if pagar:
            self.pagar(factura)
        return factura

    def pagar(self, factura):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids,
        ).create({'payment_date': factura.invoice_date})._create_payments()

    def movimientos(self, partner, tipo=None):
        dominio = [('partner_id', '=', partner.id)] + ([('tipo', '=', tipo)] if tipo else [])
        return self.env['dcasa.movimiento'].search(dominio)
