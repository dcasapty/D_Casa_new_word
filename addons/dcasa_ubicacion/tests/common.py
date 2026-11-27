"""Lo común de las pruebas de la ubicación: la tabla de lugares inventados de envíos (su fixture, con precios de
juguete), la tarifa aprobada y un cliente. Nada de aquí es la tabla ni la tarifa de la tienda."""
from odoo.addons.dcasa_conversaciones.tests.common import JuanCase
from odoo.addons.dcasa_envios.tests.common import importar
from odoo.tests import new_test_user

# Junto a «Villa Prueba II» del fixture (La Chorrera): el lugar más cercano, a unos 10 m.
CERCA = (8.9012, -79.8013)
# Lejos de todo lo del fixture (en el Caribe, dentro del recuadro de Panamá): no se acepta.
LEJOS = (9.6, -82.8)


class UbicacionCase(JuanCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gerencia_envios = new_test_user(cls.env, login='ger_ubicacion', name='Gerencia Ubicación',
                                            groups='base.group_user,dcasa_base.group_gerencia')
        importar(cls.env, cls.gerencia_envios)
        cls.tarifa = cls.env['dcasa.envio.tarifa'].search([], limit=1)
        cls.tarifa.with_user(cls.gerencia_envios).action_aprobar()
        cls.cliente = cls.env['res.partner'].create({'name': 'Ana Prueba', 'phone': '+507 6123-4567'})
        cls.villa = cls.env['dcasa.envio.lugar'].search([('name', '=', 'Villa Prueba II')], limit=1)

    def precio_de(self, lugar):
        return self.env['dcasa.envio.tarifa'].sudo().cotizar_lugar(lugar)['total_txt']
