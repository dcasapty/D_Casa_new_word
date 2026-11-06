"""Los resultados por campaña: los chats que llegaron con la marca, sus ventas (la atribución de Conversaciones), lo
que da Resend y la herramienta de Brian."""
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import tagged

from ..models import reglas as R
from .comun import CamilaComun


@tagged('post_install', '-at_install')
class TestResultados(CamilaComun):

    def setUp(self):
        super().setUp()
        self.con_clave()
        self.permiso(self.ana)
        campana = self.armar()['campana']
        self.Camila.with_user(self.marketing).enviar(campana['id'], campana['huella'])
        self.campana = self.env['dcasa.camila.campana'].browse(campana['id'])

    def llega(self, texto, numero='50760003001', id_mensaje='w1', minutos=10, nombre='Cliente Zzcm Chat'):
        return self.env['dcasa.conversacion'].sudo()._registrar_mensaje({
            'canal': 'whatsapp_cloud', 'id_externo': numero, 'id_mensaje': id_mensaje, 'direccion': 'entrante',
            'autor': 'cliente', 'texto': texto, 'nombre': nombre,
            'ts': fields.Datetime.now() + timedelta(minutes=minutos)})

    def test_el_chat_con_la_marca_cuenta_una_vez(self):
        conv, _mensaje, _creado = self.llega(R.texto_whatsapp(self.campana.id))
        self.assertEqual(len(self.campana.llegada_ids), 1)
        self.assertEqual(self.campana.llegada_ids.conversacion_id, conv)
        self.llega(R.texto_whatsapp(self.campana.id), id_mensaje='w2', minutos=20)
        self.assertEqual(len(self.campana.llegada_ids), 1, 'El mismo chat cuenta una sola vez')
        self.llega('Hola, ¿tienen camas?', numero='50760003002', id_mensaje='w3')
        self.assertEqual(len(self.campana.llegada_ids), 1, 'Sin la marca no cuenta')

    def test_solo_cuentan_campanas_enviadas(self):
        borrador = self.env['dcasa.camila.campana'].sudo().create({'name': 'Otra'})
        self.llega(R.texto_whatsapp(borrador.id), numero='50760003003')
        self.assertFalse(borrador.llegada_ids)
        self.llega(R.texto_whatsapp(99999), numero='50760003004', id_mensaje='w9')
        self.assertFalse(self.env['dcasa.camila.llegada'].search([('campana_id', '=', 99999)]))

    def test_un_error_al_contar_nunca_frena_el_mensaje(self):
        with patch('odoo.addons.dcasa_camila.models.envio.DcasaCamila._anotar_llegada', side_effect=RuntimeError()), \
                self.assertLogs('odoo.addons.dcasa_camila.models.conversacion', level='WARNING'):
            _conv, mensaje, creado = self.llega(R.texto_whatsapp(self.campana.id), numero='50760003005')
        self.assertTrue(creado and mensaje.exists())

    def test_las_ventas_de_los_que_llegaron_y_el_dinero_solo_para_gerencia(self):
        conv, _mensaje, _creado = self.llega(R.texto_whatsapp(self.campana.id))
        cliente = conv.partner_id
        producto = self.productos[0].product_variant_id
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': cliente.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'product_id': producto.id, 'quantity': 1, 'price_unit': 300.0,
                                                 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        self.assertEqual(self.Camila._ventas(self.campana), (0, 0.0), 'Sin pagar todavía no cuenta')
        diario = self.env['account.journal'].search([('type', '=', 'cash'), ('company_id', '=', self.env.company.id)],
                                                    limit=1)
        self.env['account.payment.register'].with_context(active_model='account.move', active_ids=factura.ids).create(
            {'journal_id': diario.id, 'payment_date': fields.Date.today()}).action_create_payments()
        self.assertEqual(self.Camila._ventas(self.campana), (1, 300.0))
        de_marketing = self.Camila.with_user(self.marketing).panel()['historial'][0]
        self.assertEqual((de_marketing['chats'], de_marketing['ventas'], de_marketing['monto']), (1, 1, None))
        de_gerencia = self.Camila.with_user(self.gerencia).panel()['historial'][0]
        self.assertEqual(de_gerencia['monto'], '$300.00')

    def test_aperturas_y_clics_los_da_resend(self):
        bid = self.campana.resend_broadcast_id
        self.resend.destinatarios.update({(bid, 'delivered'): 1, (bid, 'opened'): 1, (bid, 'clicked'): 0,
                                          (bid, 'unsubscribed'): 0})
        datos = self.Camila.with_user(self.marketing).actualizar_resultados(self.campana.id)
        fila = datos['historial'][0]
        self.assertEqual(fila['resend']['entregados'], 1)
        self.assertEqual(fila['resend']['abiertos'], 1)
        self.assertEqual(fila['enviados'], 1)


@tagged('post_install', '-at_install')
class TestBrianCamila(CamilaComun):

    def ejecutar(self, usuario, **argumentos):
        return self.env['brian.herramientas'].with_user(usuario).ejecutar('estado_campanas', argumentos)

    def test_contrato_para_modelos_pequenos(self):
        spec = self.env['brian.herramientas']._todas()['estado_campanas']
        self.assertLess(len(spec['descripcion']), 260)
        self.assertLessEqual(len(spec['parametros']), 5)
        self.assertEqual(spec['nivel'], 'lectura')

    def test_dice_como_va_y_solo_al_equipo_de_marketing(self):
        self.permiso(self.ana)
        self.armar()
        respuesta = self.ejecutar(self.marketing)
        self.assertTrue(respuesta['ok'], respuesta)
        datos = respuesta['datos']
        self.assertEqual(datos['clientes_con_permiso'], 1)
        self.assertEqual(len(datos['borrador']['productos']), R.PRODUCTOS_POR_CAMPANA)
        self.assertEqual(datos['clave_de_resend'], 'falta (no se puede enviar)')
        self.assertFalse(self.ejecutar(self.vendedora)['ok'])
