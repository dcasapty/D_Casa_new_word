"""El horario del sitio (Visítanos y el pie) sale de los Ajustes de Juan: un solo lugar (lote 2 de la web)."""
import importlib.util

from odoo.tests import tagged
from odoo.tools.misc import file_path

from .common import JuanCase

CLAVE_BORDE = 'dcasa_tienda_borde.pendientes'


def _migracion():
    ruta = file_path('dcasa_conversaciones/migrations/19.0.1.5.0/post-migrate.py')
    spec = importlib.util.spec_from_file_location('dcasa_conversaciones_horario_19_0_1_5_0', ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@tagged('post_install', '-at_install')
class TestHorarioDelSitio(JuanCase):

    def setUp(self):
        super().setUp()
        self.website = self.env['website'].get_current_website()

    def test_el_sitio_lee_los_ajustes_de_juan(self):
        self.ajustes.write({'horario_inicio': 9.0, 'horario_fin': 18.0, 'horario_fin_domingo': 17.0})
        self.assertEqual(self.website._dcasa_horario_tienda(), [
            {'dias': 'Lunes a sábado', 'horas': '9:00 a. m. a 6:00 p. m.',
             'corto': 'Lun. a sáb. 9:00 a. m. a 6:00 p. m.'},
            {'dias': 'Domingo', 'horas': '9:00 a. m. a 5:00 p. m.', 'corto': 'Dom. 9:00 a. m. a 5:00 p. m.'},
        ])

    def test_un_dia_apagado_sale_cerrado(self):
        self.ajustes.write({'horario_inicio': 9.0, 'horario_fin': 18.0, 'horario_fin_domingo': 0.0,
                            'dia_domingo': False})
        self.assertEqual(self.website._dcasa_horario_tienda()[-1],
                         {'dias': 'Domingo', 'horas': 'Cerrado', 'corto': 'Dom. cerrado'})

    def test_visitante_anonimo_lo_ve(self):
        """El sitio lo arma para el público: los ajustes no son legibles para el anónimo, el gancho sí."""
        publico = self.website.with_user(self.env.ref('base.public_user'))
        self.assertTrue(publico._dcasa_horario_tienda())

    def test_cambiar_el_horario_renueva_la_tienda_del_borde(self):
        if 'dcasa.tienda.pendiente' not in self.env:
            self.skipTest('dcasa_tienda_borde no está instalado')
        self.env.cr.precommit.data.pop(CLAVE_BORDE, None)
        self.ajustes.write({'horario_fin': 18.0})
        self.assertEqual(self.env.cr.precommit.data.get(CLAVE_BORDE, {}).get(0), 'horario de la tienda',
                         'El pie sale en todas las páginas: se renueva todo')

    def test_otro_ajuste_no_toca_el_borde(self):
        self.env.cr.precommit.data.pop(CLAVE_BORDE, None)
        self.ajustes.write({'pausa_por_defecto_minutos': 90})
        self.assertNotIn(0, self.env.cr.precommit.data.get(CLAVE_BORDE, {}))

    def test_migracion_pone_el_horario_de_la_duena_si_seguia_de_fabrica(self):
        self.ajustes.write({'horario_inicio': 8.0, 'horario_fin': 17.0, 'horario_fin_domingo': 0.0})
        _migracion().migrate(self.env.cr, '19.0.1.4.0')
        self.assertEqual((self.ajustes.horario_inicio, self.ajustes.horario_fin, self.ajustes.horario_fin_domingo),
                         (9.0, 18.0, 17.0))

    def test_migracion_respeta_un_horario_ya_puesto(self):
        self.ajustes.write({'horario_inicio': 10.0, 'horario_fin': 19.0, 'horario_fin_domingo': 0.0})
        _migracion().migrate(self.env.cr, '19.0.1.4.0')
        self.assertEqual((self.ajustes.horario_inicio, self.ajustes.horario_fin), (10.0, 19.0))
        self.ajustes.write({'horario_inicio': 8.0, 'horario_fin': 17.0, 'dia_domingo': False})
        _migracion().migrate(self.env.cr, '19.0.1.4.0')
        self.assertEqual(self.ajustes.horario_fin, 17.0, 'Con un día apagado ya no es el de fábrica')
