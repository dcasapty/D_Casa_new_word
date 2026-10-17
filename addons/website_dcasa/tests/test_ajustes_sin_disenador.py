"""Guardar Ajustes sin el grupo «Editor y diseñador» del sitio (models/res_config_settings.py).

En producción nadie tiene ese grupo (el sitio se edita por código: dcasa_interfaz, ``dcasa.sitio._sitio_por_codigo``).
«Google Merchant Center» (``group_gmc_feed``, de website_sale) llegaba como valor por defecto al crear los Ajustes y se
escribía en el sitio como el usuario: una administradora no podía guardar ninguna pantalla de Ajustes («No tienes
permiso para modificar registros "Sitio web"»). Se prueba por las mismas llamadas que hace el navegador al pulsar
«Guardar».
"""
from unittest.mock import patch

from odoo.tests import tagged

from .ajustes_navegador import GRUPOS_EDITOR, GuardarAjustesComoElNavegador


@tagged('post_install', '-at_install')
class TestAjustesSinDisenador(GuardarAjustesComoElNavegador):

    def test_la_duena_es_administradora_sin_disenador(self):
        self.assertTrue(self.duena.has_group('base.group_system'))
        for xmlid in GRUPOS_EDITOR:
            self.assertFalse(self.duena.has_group(xmlid), xmlid)

    def test_guardar_ajustes_no_escribe_en_el_sitio_como_la_duena(self):
        sitio = self.env['website'].get_current_website()
        Website = type(sitio)
        original = Website.write
        escrituras = []

        def espia(registros, valores):
            escrituras.append((registros.env.su, sorted(valores)))
            return original(registros, valores)

        with patch.object(Website, 'write', espia):
            self.guardar_ajustes('ajustes_duena')   # sin el arreglo: «No tienes permiso … "Sitio web"»
        # Solo website_sale.set_values copia el interruptor a todos los sitios, y lo hace con sudo().
        self.assertEqual([e for e in escrituras if not e[0]], [])
        sitio.invalidate_recordset()
        self.assertFalse(sitio.enabled_gmc_src)

    def test_google_merchant_center_se_sigue_encendiendo(self):
        """Si sí cambia, se escribe como en Odoo (en el sitio y en el grupo); y después se sigue pudiendo guardar."""
        sitio = self.env['website'].get_current_website()
        feed = self.env.ref('website_sale.group_product_feed')
        self.assertFalse(sitio.enabled_gmc_src)
        self.env['res.config.settings'].create({'group_gmc_feed': True}).execute()
        self.assertTrue(sitio.enabled_gmc_src)
        self.assertIn(feed, self.env.ref('base.group_user').all_implied_ids)
        self.guardar_ajustes('ajustes_duena')
        sitio.invalidate_recordset()
        self.assertTrue(sitio.enabled_gmc_src)
        self.assertIn(feed, self.env.ref('base.group_user').all_implied_ids)
