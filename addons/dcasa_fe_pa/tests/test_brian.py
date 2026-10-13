from odoo.tests import tagged

from .common import FeComun


@tagged('post_install', '-at_install')
class TestBrianFe(FeComun):
    """Brian solo consulta la factura electrónica (si dcasa_brian está instalado)."""

    def setUp(self):
        super().setUp()
        if 'brian.herramientas' not in self.env:
            self.skipTest('dcasa_brian no está instalado')

    def test_estado_de_solo_lectura(self):
        self._activar('rechazar')
        doc = self._factura().l10n_pa_fe_documento_ids
        doc._procesar()
        Herramientas = self.env['brian.herramientas'].with_user(self.admin)
        spec = Herramientas._todas()['estado_factura_electronica']
        self.assertEqual(spec['nivel'], 'lectura')
        resultado = Herramientas.ejecutar('estado_factura_electronica', {})
        self.assertTrue(resultado['ok'], resultado)
        datos = resultado['datos']
        self.assertTrue(datos['activa'])
        self.assertEqual(datos['por_estado']['rechazado'], 1)
        self.assertEqual(datos['piden_atencion'][0]['factura'], doc.move_id.name)
        self.assertIn('SIM-99', datos['piden_atencion'][0]['error'])
        self.assertEqual(doc.estado, 'rechazado', 'Consultar no cambia nada')
