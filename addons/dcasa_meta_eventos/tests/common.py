"""Lo común de las pruebas de Meta. NUNCA se llama a Meta de verdad: ``requests.post`` está sustituido en todas (si
algo lo llamara sin que la prueba lo pida, la prueba falla). Las personas, correos y celulares son inventados."""
import os
from unittest.mock import MagicMock, patch

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user

from ..models import meta_api

TOKEN = 'EAAprueba-token-de-meta-0000000000000000000000'
PIXEL = '123456789012345'
CODIGO = 'TEST12345'
CORREO = 'Cliente.Prueba@Example.COM'
CELULAR = '6000-1234'
VISTA_PRIVACIDAD = """
<xpath expr="." position="inside">
    <h2 id="privacidad-meta">Anuncios y medición con Meta</h2>
    <p>Texto de prueba.</p>
</xpath>
"""


def respuesta(estado=200, cuerpo=None, texto=''):
    """Una respuesta falsa de la Graph API."""
    r = MagicMock()
    r.status_code = estado
    r.json.return_value = {'events_received': 1, 'fbtrace_id': 'AbCdEfTrace'} if cuerpo is None else cuerpo
    r.text = texto
    return r


def publicar_privacidad(env):
    """Una vista de prueba agrega la sección de Meta a la política (en la vida real lo hace el paso del abogado)."""
    return env['ir.ui.view'].create({
        'name': 'Prueba: sección de Meta en la política',
        'type': 'qweb',
        'inherit_id': env.ref('website_dcasa.privacidad_cuerpo').id,
        'arch': VISTA_PRIVACIDAD,
    })


def entorno(**variables):
    """``patch.dict`` de os.environ: produccion por defecto y SIN token salvo que se pida."""
    valores = {'DCASA_ENTORNO': 'produccion', 'DCASA_PIN_PEPPER': 'pimienta-de-prueba'}
    valores.update(variables)
    parche = patch.dict(os.environ, valores)
    return parche


class MetaCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.company = cls.env.company
        cls.website = cls.env.ref('website.default_website')
        cls.mueble = cls.env['product.product'].create({
            'name': 'SOFÁ META PRUEBA', 'type': 'consu', 'list_price': 300.0, 'taxes_id': [Command.clear()]})
        cls.silla = cls.env['product.product'].create({
            'name': 'SILLA META PRUEBA', 'type': 'consu', 'list_price': 50.0, 'taxes_id': [Command.clear()]})
        cls.flete = cls.env['product.product'].create({
            'name': 'FLETE META PRUEBA', 'type': 'service', 'list_price': 20.0, 'taxes_id': [Command.clear()]})
        cls.diario = cls.env['account.journal'].search(
            [('code', '=', 'EFE'), ('company_id', '=', cls.company.id)], limit=1) or cls.env['account.journal'].search(
            [('type', '=', 'cash'), ('company_id', '=', cls.company.id)], limit=1)
        Partner = cls.env['res.partner']
        cls.panama = cls.env.ref('base.pa')
        cls.cliente = Partner.create({'name': 'CLIENTE META PRUEBA', 'phone': CELULAR, 'email': CORREO,
                                      'country_id': cls.panama.id})
        cls.otro = Partner.create({'name': 'OTRO CLIENTE META', 'phone': '6000-5678',
                                   'email': 'otro.meta@example.com'})
        cls.vendedora = new_test_user(
            cls.env, login='meta_vendedora', name='Vendedora Meta', email='vendedora.meta@example.com',
            groups='base.group_user,sales_team.group_sale_salesman,account.group_account_invoice')
        cls.gerencia = new_test_user(
            cls.env, login='meta_gerencia', name='Gerencia Meta', email='gerencia.meta@example.com',
            groups='base.group_user,dcasa_base.group_gerencia')
        cls.admin = new_test_user(
            cls.env, login='meta_admin', name='Admin Meta', email='admin.meta@example.com',
            groups='base.group_user,base.group_system,dcasa_base.group_gerencia,account.group_account_manager')

    def setUp(self):
        super().setUp()
        parche = entorno()
        parche.start()
        self.addCleanup(parche.stop)
        os.environ.pop(meta_api.VARIABLE_TOKEN, None)
        self.post = MagicMock(side_effect=AssertionError('requests.post no debe llamarse en esta prueba'))
        parche_post = patch('requests.post', self.post)
        parche_post.start()
        self.addCleanup(parche_post.stop)
        # De fábrica: todo apagado y vacío.
        for clave in ('pixel_id', 'pixel_activo', 'capi_web', 'capi_tienda', 'test_event_code', 'graph_version'):
            self.ICP.set_param(f'dcasa_meta.{clave}', False)
        self.Evento = self.env['dcasa.meta.evento'].sudo()

    # ------------------------------------------------------------------
    # Interruptores
    # ------------------------------------------------------------------

    def con_token(self):
        parche = patch.dict(os.environ, {meta_api.VARIABLE_TOKEN: TOKEN})
        parche.start()
        self.addCleanup(parche.stop)

    def en_staging(self):
        parche = patch.dict(os.environ, {'DCASA_ENTORNO': 'staging'})
        parche.start()
        self.addCleanup(parche.stop)

    def encender(self, web=True, tienda=True, token=True, privacidad=True):
        """Lo que quedaría tras el visto bueno del abogado: política publicada, ID, token e interruptores."""
        if privacidad:
            publicar_privacidad(self.env)
        if token:
            self.con_token()
        self.ICP.set_param('dcasa_meta.pixel_id', PIXEL)
        self.ICP.set_param('dcasa_meta.capi_web', 'True' if web else False)
        self.ICP.set_param('dcasa_meta.capi_tienda', 'True' if tienda else False)

    def responder(self, *respuestas):
        """Meta contesta lo que se le pida (por defecto, 200)."""
        self.post.side_effect = list(respuestas) if respuestas else None
        if not respuestas:
            self.post.return_value = respuesta()
        return self.post

    # ------------------------------------------------------------------
    # Consentimiento
    # ------------------------------------------------------------------

    def aceptar(self, partner=None, usuario=None):
        """La vendedora marca la casilla de la ficha (consentimiento B)."""
        ficha = (partner or self.cliente).with_user(usuario or self.vendedora)
        ficha.dcasa_meta_consentimiento = True
        return ficha

    # ------------------------------------------------------------------
    # Facturas, pedidos web y pagos
    # ------------------------------------------------------------------

    def factura(self, partner=None, lineas=None, publicar=True, tipo='out_invoice'):
        lineas = lineas or [(self.mueble, 1, 300.0)]
        factura = self.env['account.move'].create({
            'move_type': tipo, 'partner_id': (partner or self.cliente).id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': p.id, 'quantity': q, 'price_unit': precio,
                                                 'tax_ids': [Command.clear()]}) for p, q, precio in lineas]})
        if publicar:
            factura.action_post()
        return factura

    def pedido_web(self, partner=None, lineas=None):
        """Un pedido de la tienda en línea ya confirmado (como el que queda al terminar el checkout)."""
        lineas = lineas or [(self.mueble, 1)]
        pedido = self.env['sale.order'].create({
            'partner_id': (partner or self.cliente).id, 'website_id': self.website.id,
            'order_line': [Command.create({'product_id': p.id, 'product_uom_qty': q, 'tax_ids': [Command.clear()]})
                           for p, q in lineas]})
        pedido.action_confirm()
        return pedido

    def facturar(self, pedido):
        factura = pedido._create_invoices()
        factura.action_post()
        return factura

    def pagar(self, factura, monto=None):
        """El botón «Pagar» de la factura (el asistente), con el diario de efectivo."""
        valores = {'payment_date': fields.Date.today(), 'journal_id': self.diario.id}
        if monto is not None:
            valores['amount'] = monto
        asistente = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=factura.ids).create(valores)
        return asistente.action_create_payments()

    def fila(self, factura):
        return self.Evento.search([('event_id', '=', f'factura-{factura.id}')])
