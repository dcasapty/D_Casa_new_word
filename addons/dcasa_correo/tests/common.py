"""Lo común de las pruebas del correo. NUNCA se llama a Resend de verdad: ``requests.post`` está sustituido en todas
(si algo lo llamara sin que la prueba lo pida, la prueba falla)."""
import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user

from ..models.correo import P_A_CLIENTES, P_AL_PAGAR, P_BIENVENIDA, P_BIENVENIDA_DESDE

CLAVE = 're_prueba_123'
PDF = (b'%PDF-1.4 prueba', 'pdf')
RUTA_PDF = 'odoo.addons.base.models.ir_actions_report.IrActionsReport._render_qweb_pdf'


def respuesta(estado=200, cuerpo=None):
    """Una respuesta falsa de Resend."""
    r = MagicMock()
    r.status_code = estado
    r.json.return_value = {'id': 'resend-1'} if cuerpo is None else cuerpo
    r.text = ''
    return r


class CorreoCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.company = cls.env.company
        cls.mueble = cls.env['product.product'].create({
            'name': 'SOFÁ CORREO', 'type': 'consu', 'list_price': 200.0, 'taxes_id': [Command.clear()]})
        cls.diario = cls.env['account.journal'].search(
            [('code', '=', 'EFE'), ('company_id', '=', cls.company.id)], limit=1)
        Partner = cls.env['res.partner']
        cls.ana = Partner.create({'name': 'ANA PRUEBA CORREO', 'phone': '6000-0001', 'email': 'ana@example.com'})
        cls.beto = Partner.create({'name': 'Beto Prueba', 'phone': '6000-0002', 'email': 'beto@example.com'})
        cls.sin_correo = Partner.create({'name': 'Carla Sin Correo', 'phone': '6000-0003'})
        cls.vendedora = new_test_user(
            cls.env, login='correo_vendedora', name='Vendedora Correo', email='vendedora.correo@example.com',
            groups='base.group_user,sales_team.group_sale_salesman')
        cls.admin = new_test_user(
            cls.env, login='correo_admin', name='Admin Correo', email='admin.correo@example.com',
            groups='base.group_user,base.group_system,sales_team.group_sale_manager,account.group_account_manager')

    def setUp(self):
        super().setUp()
        entorno = patch.dict(os.environ, {'DCASA_ENTORNO': 'produccion', 'DCASA_PIN_PEPPER': 'pimienta-de-prueba'})
        entorno.start()
        self.addCleanup(entorno.stop)
        os.environ.pop('RESEND_API_KEY', None)
        self.post = MagicMock(side_effect=AssertionError('requests.post no debe llamarse en esta prueba'))
        parche = patch('requests.post', self.post)
        parche.start()
        self.addCleanup(parche.stop)
        # Los parámetros como quedan al instalar (el interruptor general apagado).
        self.ICP.set_param(P_AL_PAGAR, 'True')
        self.ICP.set_param(P_BIENVENIDA, 'True')
        self.ICP.set_param(P_A_CLIENTES, False)
        self.ICP.set_param(P_BIENVENIDA_DESDE, '2020-01-01 00:00:00')

    # ------------------------------------------------------------------
    # Interruptores
    # ------------------------------------------------------------------

    def con_clave(self):
        parche = patch.dict(os.environ, {'RESEND_API_KEY': CLAVE})
        parche.start()
        self.addCleanup(parche.stop)

    def encender(self):
        """Clave puesta e interruptor encendido."""
        self.con_clave()
        self.ICP.set_param(P_A_CLIENTES, 'True')

    def apagar(self):
        self.ICP.set_param(P_A_CLIENTES, False)

    @contextmanager
    def transporte(self, *respuestas):
        """Odoo «envía de verdad» (sin el freno de las pruebas) y Resend contesta lo que se le pida."""
        mail_server = type(self.env['ir.mail_server'])
        self.post.side_effect = None
        if respuestas:
            self.post.side_effect = list(respuestas)
        else:
            self.post.return_value = respuesta()
        with patch.object(mail_server, '_disable_send', return_value=False):
            yield self.post
        self.post.side_effect = AssertionError('requests.post no debe llamarse en esta prueba')

    def errores_de_envio(self):
        """Odoo registra como ERROR cada correo que Resend no recibió: en estas pruebas es a propósito."""
        return self.assertLogs('odoo.addons.mail.models.mail_mail', level='ERROR')

    # ------------------------------------------------------------------
    # Facturas y pagos
    # ------------------------------------------------------------------

    def factura(self, partner=None, precio=200.0, publicar=True, **valores):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': (partner or self.ana).id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': self.mueble.id, 'quantity': 1, 'price_unit': precio,
                                                 'tax_ids': [Command.clear()]})],
            **valores})
        if publicar:
            factura.action_post()
        return factura

    def pagar(self, factura, monto=None, contexto=None, usuario=None):
        """El botón «Pagar» de la factura (el asistente), con el diario de Efectivo."""
        Asistente = self.env['account.payment.register']
        if usuario:
            Asistente = Asistente.with_user(usuario)
        valores = {'payment_date': fields.Date.today(), 'journal_id': self.diario.id}
        if monto is not None:
            valores['amount'] = monto
        asistente = Asistente.with_context(active_model='account.move', active_ids=factura.ids,
                                           **(contexto or {})).create(valores)
        return asistente.action_create_payments()

    def envios(self, **filtro):
        dominio = [(campo, '=', valor) for campo, valor in filtro.items()]
        return self.env['dcasa.correo.envio'].sudo().search(dominio, order='id')

    def procesar(self):
        with patch(RUTA_PDF, return_value=PDF):
            return self.env['dcasa.correo.envio'].sudo()._procesar()

    def correos_de(self, registro):
        """Los mail.mail que dejó en la cola un registro (factura, venta, ficha)."""
        return self.env['mail.mail'].sudo().search(
            [('model', '=', registro._name), ('res_id', '=', registro.id)], order='id')
