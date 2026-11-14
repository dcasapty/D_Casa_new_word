"""Lo común de las pruebas de «Brian de la tienda»: productos de prueba, el Worker conectado (falso) y el CSRF."""
import json
import os
import re
from unittest.mock import patch

from odoo import Command
from odoo.tests import HttpCase

TOKEN_WORKER = 'w' * 40     # JUAN_WORKER_TOKEN de prueba (no es un secreto real)
TOKEN_ODOO = 'o' * 40       # JUAN_ODOO_TOKEN de prueba
URL_WORKER = 'http://127.0.0.1:9'   # válida (local) y nadie contesta: las rutas de Odoo no la llaman
RAIZ = '/dcasa/brian/v1'
RE_CSRF = re.compile(r'[0-9a-f]{40}o\d{6,}')


class TiendaCase(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref('website.default_website')
        cls.website.show_line_subtotals_tax_selection = 'tax_excluded'
        Template = cls.env['product.template']
        impuesto = cls.env['brian.herramientas']._b_itbms_venta()
        base = {'type': 'consu', 'sale_ok': True, 'is_published': True, 'taxes_id': [Command.set(impuesto.ids)]}
        cls.colchon = Template.create({**base, 'name': 'ZZBT COLCHÓN QUEEN', 'list_price': 278.0})
        cls.base_cama = Template.create({**base, 'name': 'ZZBT BASE DE CAMA', 'list_price': 69.99})
        cls.secreto = Template.create({**base, 'name': 'ZZBT SECRETO SIN PUBLICAR', 'list_price': 10.0,
                                       'is_published': False})
        cls.gratis = Template.create({**base, 'name': 'ZZBT SIN PRECIO', 'list_price': 0.0})
        tamano = cls.env['product.attribute'].create({'name': 'ZZBT tamaño', 'create_variant': 'always', 'value_ids': [
            Command.create({'name': 'ZZBT queen'}), Command.create({'name': 'ZZBT king'})]})
        # Con un opcional: hay que elegir en la ficha (las reglas del «Agregar» de un clic de la tienda).
        cls.con_medidas = Template.create({
            **base, 'name': 'ZZBT CAMA CON MEDIDAS', 'list_price': 300.0,
            'optional_product_ids': [Command.set(cls.base_cama.ids)],
            'attribute_line_ids': [Command.create({'attribute_id': tamano.id,
                                                   'value_ids': [Command.set(tamano.value_ids.ids)]})]})
        # Solo se elige la medida: una variante concreta sí se agrega directo (como el color destacado de la portada).
        cls.de_medida = Template.create({
            **base, 'name': 'ZZBT BASE CON MEDIDA', 'list_price': 120.0,
            'attribute_line_ids': [Command.create({'attribute_id': tamano.id,
                                                   'value_ids': [Command.set(tamano.value_ids.ids)]})]})
        cls.website.prevent_zero_price_sale = True

    def setUp(self):
        super().setUp()
        entorno = patch.dict(os.environ, {'JUAN_URL': URL_WORKER, 'JUAN_WORKER_TOKEN': TOKEN_WORKER,
                                          'JUAN_ODOO_TOKEN': TOKEN_ODOO})
        entorno.start()
        self.addCleanup(entorno.stop)
        self.env['ir.config_parameter'].sudo().set_param('dcasa_brian_tienda.activo', 'True')

    # ------------------------------------------------------------------ peticiones como el navegador

    def csrf(self):
        """Un token CSRF de ESTA sesión (el que trae la página que dibuja Odoo para ella)."""
        return RE_CSRF.search(self.url_open('/').text).group(0)

    def post(self, ruta, cuerpo=None, csrf=True, tipo='application/json'):
        cabeceras = {'Content-Type': tipo}
        if csrf:
            cabeceras['X-CSRF-Token'] = self.csrf() if csrf is True else csrf
        datos = cuerpo if isinstance(cuerpo, (str, bytes)) else json.dumps(cuerpo or {})
        return self.url_open(f'{RAIZ}/{ruta}', data=datos, headers=cabeceras)

    def otra_sesion(self):
        """Otro visitante (otro navegador): una sesión anónima nueva."""
        self.authenticate(None, None)
