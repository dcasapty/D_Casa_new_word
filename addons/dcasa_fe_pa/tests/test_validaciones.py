from odoo.addons.dcasa_fe_pa.models import catalogos as C
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import FeComun


@tagged('post_install', '-at_install')
class TestValidaciones(FeComun):

    def test_tipo_de_receptor_se_deduce(self):
        self.assertEqual(self.contribuyente._l10n_pa_fe_tipo_receptor(), C.RECEPTOR_CONTRIBUYENTE)
        self.assertEqual(self.consumidor._l10n_pa_fe_tipo_receptor(), C.RECEPTOR_CONSUMIDOR_FINAL)
        turista = self.env['res.partner'].create({'name': 'John', 'country_id': self.env.ref('base.us').id})
        self.assertEqual(turista._l10n_pa_fe_tipo_receptor(), C.RECEPTOR_EXTRANJERO)
        self.consumidor.l10n_pa_tipo_receptor = C.RECEPTOR_GOBIERNO
        self.assertEqual(self.consumidor._l10n_pa_fe_tipo_receptor(), C.RECEPTOR_GOBIERNO)

    def test_tasa_itbms_del_impuesto(self):
        itbms = self.company.account_sale_tax_id
        self.assertEqual(itbms._l10n_pa_fe_codigo_itbms(), '01')
        itbms.l10n_pa_tasa_itbms = '00'
        self.assertEqual(itbms._l10n_pa_fe_codigo_itbms(), '00')

    def test_faltan_datos_del_cliente_no_publica(self):
        self._activar()
        cliente = self.env['res.partner'].create({'name': 'Mueblería X', 'vat': '8-NT-2-1', 'l10n_pa_dv': '3',
                                                  'country_id': self.env.ref('base.pa').id})
        factura = self._factura(cliente, publicar=False)
        with self.assertRaises(UserError) as error:
            factura.action_post()
        mensaje = str(error.exception)
        self.assertIn('no tiene dirección', mensaje)
        self.assertIn('ubicación DGI', mensaje)
        self.assertEqual(factura.state, 'draft')
        self.assertFalse(factura.l10n_pa_fe_documento_ids)

    def test_falta_dv_de_la_empresa(self):
        self._activar()
        self.company.l10n_pa_dv = False
        factura = self._factura(publicar=False)
        self.assertIn('La empresa no tiene DV.', factura._l10n_pa_fe_problemas())

    def test_linea_sin_itbms(self):
        self._activar()
        factura = self._factura(publicar=False)
        factura.invoice_line_ids.tax_ids = False
        problemas = factura._l10n_pa_fe_problemas()
        self.assertTrue(any('exactamente un impuesto ITBMS' in p for p in problemas), problemas)

    def test_gobierno_exige_cpbs(self):
        self._activar()
        self.contribuyente.l10n_pa_tipo_receptor = C.RECEPTOR_GOBIERNO
        factura = self._factura(self.contribuyente, publicar=False)
        self.assertTrue(any('CPBS' in p for p in factura._l10n_pa_fe_problemas()))
        self.cama.l10n_pa_cpbs = '5612'
        self.assertFalse(factura._l10n_pa_fe_problemas())
        factura.action_post()
        self.assertIn('<dCodCPBScmp>5612</dCodCPBScmp>', factura.l10n_pa_fe_documento_ids.payload)

    def test_extranjero_sin_identificacion(self):
        self._activar()
        turista = self.env['res.partner'].create({'name': 'John', 'country_id': self.env.ref('base.us').id})
        factura = self._factura(turista, publicar=False)
        self.assertTrue(any('pasaporte' in p for p in factura._l10n_pa_fe_problemas()))
        turista.vat = 'X1234567'
        factura.action_post()
        self.assertIn('<dIdExt>X1234567</dIdExt>', factura.l10n_pa_fe_documento_ids.payload)

    def test_consumidor_final_sin_datos_si_publica(self):
        self._activar()
        factura = self._factura()
        self.assertEqual(factura.state, 'posted')
        self.assertEqual(factura.l10n_pa_fe_documento_ids.estado, 'por_enviar')

    def test_formatos_de_campos(self):
        with self.assertRaises(ValidationError):
            self.diario.l10n_pa_fe_punto = '000'
        with self.assertRaises(ValidationError):
            self.company.l10n_pa_fe_sucursal = '12'
        with self.assertRaises(ValidationError):
            self.cama.l10n_pa_cpbs = 'AB12'

    def test_descuento_y_forma_de_pago(self):
        self._activar()
        factura = self._factura(publicar=False)
        factura.invoice_line_ids.discount = 10
        factura.action_post()
        payload = factura.l10n_pa_fe_documento_ids.payload
        self.assertIn('<dPrUnitDesc>15.802</dPrUnitDesc>', payload)
        self.assertIn('<dTotDesc>15.80</dTotDesc>', payload)
        self.assertIn('<iFormaPago>02</iFormaPago>', payload)
