"""«Hoy» para Brian es la fecha de Panamá, no la del servidor (UTC). Auditoría 2026-11-06: desde las 7 p. m. de
Panamá, «hoy» y «ayer» caían un día después (pagos, cortes, rangos de fechas)."""
from datetime import date

from freezegun import freeze_time

from odoo.addons.dcasa_brian.models import herramientas_comun as c
from odoo.tests import new_test_user, tagged

from .common import BrianCase

# 01:30 UTC del 6 de noviembre = 8:30 p. m. del 5 de noviembre en Panamá.
NOCHE_EN_PANAMA = '2026-11-06 01:30:00'


@tagged('post_install', '-at_install')
class TestFechasDePanama(BrianCase):

    @freeze_time(NOCHE_EN_PANAMA)
    def test_hoy_y_ayer_en_la_noche_de_panama(self):
        self.assertEqual(c.leer_fecha('hoy'), date(2026, 11, 5))
        self.assertEqual(c.leer_fecha('ayer'), date(2026, 11, 4))
        self.assertEqual(c.leer_fecha('hoy', hoy=date(2026, 1, 2)), date(2026, 1, 2),
                         'manda la fecha de quien pregunta')

    @freeze_time(NOCHE_EN_PANAMA)
    def test_hoy_de_brian_sin_zona_horaria_es_panama(self):
        usuario = new_test_user(self.env, login='brian_sin_zona', groups='base.group_user')
        usuario.tz = False   # Telegram y MCP: usuarios sin zona horaria
        Herramientas = self.env['brian.herramientas'].with_user(usuario).with_context(tz=False)
        self.assertEqual(Herramientas._b_hoy(), date(2026, 11, 5))
        desde, hasta, _etiqueta = Herramientas._b_rango(desde='ayer', hasta='hoy')
        self.assertEqual((desde, hasta), (date(2026, 11, 4), date(2026, 11, 5)))
