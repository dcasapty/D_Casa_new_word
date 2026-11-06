"""Camila, etapa 2 (decisiones de la dueña, 2026-11-06): varias campañas con un tope de 15 días POR CLIENTE, el público
con chips del CRM, «Nueva campaña» (y desde el tablero de Marketing), el redactor con IA, los botones y las redes del
correo con UTM, y Juan que sabe que el cliente vino del correo. Datos inventados (ZZCM, @example.com); Resend siempre es
el falso en memoria de ``comun.py``."""
import json
import os
from datetime import timedelta
from unittest.mock import patch

from lxml import html as lxml_html

from odoo import Command, fields
from odoo.addons.dcasa_brian.models import proveedores as P
from odoo.addons.dcasa_conversaciones.models import crm_reglas as CRM
from odoo.addons.dcasa_conversaciones.models import horario as H
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged

from ..models import reglas as R
from .comun import CamilaComun

TOKEN_JUAN = 'token-juan-zzcm-de-prueba-0123456789abcdef'


class Etapa2Comun(CamilaComun):

    def enviar(self, campana, usuario=None):
        return self.Camila.with_user(usuario or self.marketing).enviar(campana['id'], campana['huella'])

    def guardar(self, campana, cambios, usuario=None):
        return self.Camila.with_user(usuario or self.marketing).guardar(campana['id'], cambios)

    def campana(self, datos):
        return self.env['dcasa.camila.campana'].browse(datos['id'])


# ----------------------------------------------------------------------
# 5. Varias campañas y el tope POR CLIENTE
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestTopePorCliente(Etapa2Comun):

    def test_el_registro_de_a_quien_le_salio(self):
        self.con_clave()
        self.permiso(self.ana, self.beto)
        campana = self.armar()['campana']
        self.assertTrue(self.enviar(campana)['ok'])
        registro = self.campana(campana).destinatario_ids
        self.assertEqual(sorted(registro.mapped('correo')), ['ana.zzcm@example.com', 'beto.zzcm@example.com'])
        self.assertEqual(registro.partner_id, self.ana | self.beto)
        self.assertEqual(self.Camila._correos_recientes(), {'ana.zzcm@example.com', 'beto.zzcm@example.com'})

    def test_si_se_llamo_a_send_el_registro_se_queda(self):
        """Revisión 2: si se llamó a «send», el registro se queda aunque Resend conteste un error (pudo salir y su
        estado tardar en cambiar). Solo se suelta si nunca se llamó (``test_revision2``)."""
        self.con_clave()
        self.permiso(self.ana, self.beto)
        campana = self.armar()['campana']
        self.resend.fallar.append(('POST', r'/send$', 503, 'Unavailable'))
        self.assertFalse(self.enviar(campana)['ok'])
        self.assertEqual(len(self.campana(campana).destinatario_ids), 2)
        otra = self.armar()['campana']
        self.assertEqual(otra['publico']['total'], 0, 'Mejor no mandarles otra que mandarles dos')
        self.resend.fallar.clear()
        self.assertTrue(self.enviar(campana)['ok'], 'El reintento de la misma campaña sí sale')

    def test_una_campana_a_la_vez_toca_el_segmento(self):
        self.con_clave()
        self.permiso(self.ana, self.beto)
        primera = self.armar()['campana']
        segunda = self.armar()['campana']
        self.campana(primera).sudo().write({'estado': 'aprobada', 'enviando_desde': fields.Datetime.now()})
        with self.assertRaisesRegex(UserError, 'Otra campaña se está enviando'):
            self.enviar(segunda)
        self.assertFalse(self.resend.llamadas, 'Ni siquiera habló con Resend')

    def test_si_la_anterior_sigue_saliendo_en_resend_espera(self):
        self.con_clave()
        self.permiso(self.ana, self.beto)
        self.resend.estado_al_enviar = 'queued'
        self.assertTrue(self.enviar(self.armar()['campana'])['ok'])
        self.permiso(self.carla)
        segunda = self.armar()['campana']
        resultado = self.enviar(segunda)
        self.assertFalse(resultado['ok'])
        self.assertIn('todavía está saliendo en Resend', resultado['mensaje'])
        for broadcast in self.resend.broadcasts.values():
            broadcast['status'] = 'sent'
        segunda = self.Camila.with_user(self.marketing).panel(segunda['id'])['campana']
        self.assertTrue(self.enviar(segunda)['ok'])

    def test_el_segmento_de_envio_queda_con_los_de_esta_campana(self):
        self.con_clave()
        self.permiso(self.ana, self.beto, self.carla)
        campana = self.armar()['campana']
        self.guardar(campana, {'publico': ['calientes']})
        lead = self.env['crm.lead'].create({'name': 'ZZCM interés', 'type': 'opportunity', 'partner_id': self.carla.id,
                                            'dcasa_temperatura': CRM.CALIENTE})
        self.assertTrue(lead)
        segmento = self.Camila._segmento(self.Camila._cliente())
        self.resend.contacto('ana.zzcm@example.com', segmentos=[segmento])   # quedó de una campaña anterior
        campana = self.Camila.with_user(self.marketing).panel(campana['id'])['campana']
        self.assertEqual(campana['publico']['total'], 1)
        self.assertTrue(self.enviar(campana)['ok'])
        (broadcast,) = self.resend.broadcasts.values()
        self.assertEqual(broadcast['enviado_a'], ['carla.zzcm@example.com'])
        self.assertEqual(self.resend.en_segmento(segmento), {'carla.zzcm@example.com': False})


# ----------------------------------------------------------------------
# 4. A quién va: los chips del CRM
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestPublico(Etapa2Comun):

    def factura(self, partner, dias=0):
        factura = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': partner.id,
            'invoice_date': fields.Date.today() - timedelta(days=dias),
            'invoice_line_ids': [Command.create({'product_id': self.productos[0].product_variant_id.id, 'quantity': 1,
                                                 'price_unit': 100.0, 'tax_ids': [Command.clear()]})]})
        factura.action_post()
        return factura

    def test_los_chips_cuentan_y_se_suman(self):
        self.permiso(self.ana, self.beto, self.carla)
        self.factura(self.ana)
        self.factura(self.beto, dias=200)
        variante = self.productos[1].product_variant_id
        self.env['sale.order'].create({'partner_id': self.carla.id,
                                       'order_line': [Command.create({'product_id': variante.id})]})
        self.env['crm.lead'].create({'name': 'ZZCM tibio', 'type': 'opportunity', 'partner_id': self.beto.id,
                                     'dcasa_temperatura': CRM.TIBIO})
        self.env.cr.execute("UPDATE res_partner SET create_date = now() - interval '2 years' WHERE id = %s",
                            [self.ana.id])
        self.env.invalidate_all()
        publico = self.Camila._publico(['compraron'])
        chips = {chip['clave']: chip['n'] for chip in publico['chips']}
        self.assertEqual(chips['todos'], 3)
        self.assertEqual(chips['compraron'], 1)
        self.assertEqual(chips['volver'], 1)
        self.assertEqual(chips['cotizaron'], 2, 'Carla cotizó y Beto preguntó (su oportunidad) sin comprar en 90 días')
        self.assertEqual(chips['tibios'], 1)
        self.assertEqual(chips['calientes'], 0)
        self.assertEqual(chips['antiguos'], 1)
        self.assertEqual(set(publico['incluidos']), {'ana.zzcm@example.com'})
        sumados = self.Camila._publico(['compraron', 'cotizaron'])
        self.assertEqual(set(sumados['incluidos']),
                         {'ana.zzcm@example.com', 'carla.zzcm@example.com', 'beto.zzcm@example.com'})

    def test_quienes_quedan_fuera_y_por_que(self):
        self.con_clave()
        self.permiso(self.ana, self.beto)
        sin_permiso = self.env['res.partner'].create({'name': 'Dora Zzcm', 'email': 'dora.zzcm@example.com',
                                                      'phone': '6000-1030'})
        con_baja = self.env['res.partner'].create({'name': 'Eva Zzcm', 'email': 'eva.zzcm@example.com',
                                                   'phone': '6000-1031'})
        con_baja.sudo()._dcasa_promos_baja('ficha')
        sin_correo = self.env['res.partner'].create({'name': 'Fito Zzcm', 'phone': '6000-1032'})
        self.assertTrue(self.enviar(self.armar()['campana'])['ok'])   # Ana y Beto: recibieron una hoy
        for ficha in (self.ana, sin_permiso, con_baja, sin_correo):
            self.factura(ficha)
        fuera = {f['motivo']: f['n'] for f in self.Camila._publico(['compraron'])['fuera']}
        self.assertEqual(fuera, {'reciente': 1, 'sin_permiso': 1, 'baja': 1, 'sin_correo': 1})
        self.assertFalse(self.Camila._publico(['compraron'])['incluidos'])

    def test_el_publico_se_guarda_validado(self):
        campana = self.armar()['campana']
        datos = self.guardar(campana, {'publico': ['tibios', 'inventado', 'calientes']})
        self.assertEqual(datos['campana']['publico']['elegidos'], ['tibios', 'calientes'])
        self.assertEqual(self.guardar(campana, {'publico': []})['campana']['publico']['elegidos'], ['todos'])
        with self.assertRaisesRegex(UserError, 'No entendí a quién va'):
            self.guardar(campana, {'publico': 'todos'})
        self.assertEqual(R.leer_chips('nuevos,antiguos'), ['nuevos', 'antiguos'])


# ----------------------------------------------------------------------
# 6. «Nueva campaña» y el tablero de Marketing
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestNuevaCampana(Etapa2Comun):

    def nueva(self, **opciones):
        return self.Camila.with_user(self.marketing).nueva(opciones)

    def test_desde_lo_que_mas_hay_en_stock(self):
        mucho = self.producto('ZZCM ROPERO CON MUCHO STOCK', stock=40)
        datos = self.nueva(tema='stock')
        campana = datos['campana']
        self.assertEqual(campana['lineas'][0]['producto_id'], mucho.id)
        self.assertEqual(campana['tema'], 'stock')
        self.assertIn('Lo que más hay en stock', campana['nombre'])

    def test_desde_el_tablero_solo_van_los_que_se_pueden_ofrecer(self):
        agotado = self.producto('ZZCM MESA AGOTADA DEL TABLERO', stock=0)
        sin_foto = self.producto('ZZCM MESA SIN FOTO DEL TABLERO', con_foto=False)
        datos = self.nueva(tema='quietos', productos=[agotado.id, self.productos[2].id, sin_foto.id,
                                                      self.productos[5].id])
        self.assertEqual([linea['producto_id'] for linea in datos['campana']['lineas']],
                         [self.productos[2].id, self.productos[5].id])
        with self.assertRaisesRegex(UserError, 'No hay productos'):
            self.nueva(tema='quietos', productos=[agotado.id])
        with self.assertRaisesRegex(UserError, 'no es válida'):
            self.nueva(tema='quietos', productos=['1'])

    def test_desde_una_idea_la_ia_sugiere_los_productos(self):
        uno, dos = self.productos[3], self.productos[6]
        P.fijar_guion([json.dumps({'ids': [dos.id, 999999, uno.id]}),
                       json.dumps({'asunto': 'Para dormir mejor', 'entrada': 'Lo que tu recámara necesita.',
                                   'lineas': {}})])
        datos = self.nueva(tema='idea', idea='Todo para dormir mejor')
        campana = datos['campana']
        self.assertEqual([linea['producto_id'] for linea in campana['lineas']], [dos.id, uno.id])
        self.assertEqual((campana['idea'], campana['asunto']), ('Todo para dormir mejor', 'Para dormir mejor'))
        self.assertIn('Todo para dormir mejor', json.dumps(P.LLAMADAS[0]['mensajes'], ensure_ascii=False))
        with self.assertRaisesRegex(UserError, 'Escribe la idea'):
            self.nueva(tema='idea', idea='  ')

    def test_si_la_ia_no_sugiere_quedan_los_de_siempre_y_lo_dice(self):
        datos = self.nueva(tema='idea', idea='Algo para la terraza')
        self.assertTrue(datos['campana']['lineas'])
        self.assertIn('La IA no devolvió', datos['campana']['nota'])

    def test_en_blanco_y_temas_que_no_existen(self):
        datos = self.nueva(tema='blanco')
        self.assertFalse(datos['campana']['lineas'])
        self.assertTrue(any('no tiene productos' in b for b in datos['bloqueos']))
        with self.assertRaisesRegex(UserError, 'No entendí'):
            self.nueva(tema='remate')
        with self.assertRaises(AccessError):
            self.Camila.with_user(self.vendedora).nueva({'tema': 'stock'})


# ----------------------------------------------------------------------
# 3. El redactor con IA
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestRedactor(Etapa2Comun):

    def setUp(self):
        super().setUp()
        self.permiso(self.ana)
        self.datos = self.armar()['campana']
        self.linea = self.datos['lineas'][0]
        self.plantilla = self.env['product.template'].browse(self.linea['producto_id'])
        self.plantilla.write({'description_sale': 'Sofá de tres puestos con tela antimanchas color arena.',
                              'dcasa_medidas': 'Ancho × Fondo × Alto: 210 × 90 × 85 cm'})

    def escribir(self, que, producto_id=False):
        return self.Camila.with_user(self.marketing).escribir(self.datos['id'], que, producto_id)

    def test_la_linea_de_un_producto_con_sus_datos_reales(self):
        P.fijar_guion([json.dumps({'linea': 'Tela que aguanta el día a día, en un tono que combina con todo.'})])
        resultado = self.escribir('linea', self.plantilla.id)
        self.assertTrue(resultado['ok'], resultado)
        linea = resultado['panel']['campana']['lineas'][0]
        self.assertEqual(linea['texto'], 'Tela que aguanta el día a día, en un tono que combina con todo.')
        pedido = json.dumps(P.LLAMADAS[0]['mensajes'], ensure_ascii=False)
        self.assertIn('antimanchas', pedido)
        self.assertIn('210 × 90 × 85', pedido)
        self.assertNotIn('ana.zzcm@example.com', pedido, 'A la IA solo le llegan datos de productos')
        self.assertNotIn('Ana Zzcm', pedido)

    def test_lo_que_no_pasa_la_revision_no_se_guarda_y_se_dice(self):
        P.fijar_guion([json.dumps({'linea': 'Llévate dos por uno, sin costo de envío.'})])
        resultado = self.escribir('linea', self.plantilla.id)
        self.assertFalse(resultado['ok'])
        self.assertIn('revisión de marca', resultado['mensaje'])
        self.assertNotIn('dos por uno', self.campana(self.datos).linea_ids[0].texto)

    def test_si_la_ia_falla_lo_dice(self):
        resultado = self.escribir('asunto')   # sin guion, la IA de prueba contesta algo que no es JSON
        self.assertEqual(resultado, {'ok': False, 'mensaje': 'La IA no devolvió un texto que se pudiera leer.'})

    def test_todo_con_la_idea(self):
        self.guardar(self.datos, {'idea': 'Renovar la sala para diciembre'})
        lineas = {str(linea['producto_id']): 'Listo para tu sala.' for linea in self.datos['lineas']}
        lineas[str(self.plantilla.id)] = 'Precio de fábrica, solo hoy.'   # no pasa: queda como estaba
        P.fijar_guion([json.dumps({'asunto': 'Tu sala lista para diciembre',
                                   'entrada': 'Ideas para recibir a la familia.', 'lineas': lineas})])
        resultado = self.escribir('todo')
        self.assertTrue(resultado['ok'], resultado)
        campana = resultado['panel']['campana']
        self.assertEqual((campana['asunto'], campana['entrada']),
                         ('Tu sala lista para diciembre', 'Ideas para recibir a la familia.'))
        self.assertIn('No pasó la revisión de marca', campana['nota'])
        self.assertNotEqual(campana['lineas'][0]['texto'], 'Precio de fábrica, solo hoy.')
        self.assertIn('Renovar la sala para diciembre', json.dumps(P.LLAMADAS[0]['mensajes'], ensure_ascii=False))

    def test_sugerir_productos_solo_de_lo_que_se_puede_ofrecer(self):
        fuera = self.producto('ZZCM LÁMPARA PARA SUGERIR', precio=60.0)
        agotado = self.producto('ZZCM LÁMPARA AGOTADA', stock=0)
        P.fijar_guion([json.dumps({'ids': [agotado.id, fuera.id, self.plantilla.id, str(fuera.id)]})])
        resultado = self.Camila.with_user(self.marketing).sugerir_productos(self.datos['id'], 'Luz para la sala')
        self.assertTrue(resultado['ok'], resultado)
        self.assertEqual([p['id'] for p in resultado['productos']], [fuera.id],
                         'Ni el agotado ni el que ya está en la campaña')


# ----------------------------------------------------------------------
# Los botones, los enlaces con UTM y las redes del correo
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestBotonesDelCorreo(Etapa2Comun):

    def setUp(self):
        super().setUp()
        self.datos = self.armar()['campana']
        self.marca = R.marca(self.datos['id'])

    def html(self):
        return lxml_html.fromstring(self.campana(self.datos).html)

    def test_de_fabrica_whatsapp_y_los_productos_llevan_a_la_web(self):
        documento = self.html()
        self.assertTrue(documento.xpath("//td[contains(@class, 'o_camila_boton_whatsapp')]"))
        self.assertFalse(documento.xpath("//td[contains(@class, 'o_camila_boton_tienda')]"))
        enlace = documento.xpath("//a[contains(@class, 'o_camila_producto_enlace')]/@href")[0]
        self.assertIn('/shop/', enlace)
        self.assertIn(f'utm_source=correo&utm_medium=email&utm_campaign={self.marca}', enlace)
        whatsapp = documento.xpath("//td[contains(@class, 'o_camila_boton_whatsapp')]/a/@href")[0]
        self.assertIn('vi%20el%20correo%20de%20novedades', whatsapp.replace('+', '%20'))

    def test_la_tienda_en_linea_o_los_dos_y_al_menos_uno(self):
        self.guardar(self.datos, {'botones': {'web': True}})
        tienda = self.html().xpath("//td[contains(@class, 'o_camila_boton_tienda')]/a/@href")[0]
        self.assertEqual(tienda, f'https://tienda.example.com/shop?utm_source=correo&utm_medium=email'
                                 f'&utm_campaign={self.marca}')
        self.assertTrue(self.html().xpath("//td[contains(@class, 'o_camila_boton_whatsapp')]"))
        self.guardar(self.datos, {'botones': {'whatsapp': False}})
        self.assertFalse(self.html().xpath("//td[contains(@class, 'o_camila_boton_whatsapp')]"))
        with self.assertRaisesRegex(UserError, 'al menos un botón'):
            self.guardar(self.datos, {'botones': {'web': False}})
        with self.assertRaisesRegex(UserError, 'No entendí los botones'):
            self.guardar(self.datos, {'botones': {'web': 'sí'}})
        # Aunque llegue por otro lado, sin botones no se deja enviar.
        self.con_clave()
        self.permiso(self.ana)
        self.campana(self.datos).sudo().write({'boton_web': False})
        with self.assertRaisesRegex(UserError, 'al menos un botón'):
            self.Camila.with_user(self.marketing).enviar(self.datos['id'], self.datos['huella'])

    def test_sin_enlaces_en_los_productos(self):
        self.guardar(self.datos, {'botones': {'productos': False}})
        self.assertFalse(self.html().xpath("//a[contains(@class, 'o_camila_producto_enlace')]"))

    def test_las_redes_del_sitio_al_pie(self):
        self.website.write({'social_instagram': 'https://instagram.com/dcasa.zzcm', 'social_facebook': False,
                            'social_tiktok': 'javascript:alert(1)'})
        self.assertFalse(self.html().xpath("//a[contains(@class, 'o_camila_red')]"), 'Apagadas de fábrica')
        datos = self.guardar(self.datos, {'botones': {'redes': True}})
        self.assertEqual(datos['campana']['redes_del_sitio'], ['Instagram'])
        redes = self.html().xpath("//a[contains(@class, 'o_camila_red')]")
        self.assertEqual([(a.text_content(), a.get('href')) for a in redes],
                         [('Instagram', 'https://instagram.com/dcasa.zzcm')])
        self.assertNotIn('fed00f', ''.join(a.get('style') for a in redes).lower(), 'Sin amarillo sobre lo claro')

    def test_las_ventas_de_la_web_con_el_utm_de_la_campana(self):
        self.con_clave()
        self.permiso(self.ana)
        self.assertTrue(self.enviar(self.datos)['ok'])
        utm = self.env['utm.campaign'].create({'name': self.marca})
        orden = self.env['sale.order'].create({
            'partner_id': self.beto.id, 'campaign_id': utm.id,
            'order_line': [Command.create({'product_id': self.productos[0].product_variant_id.id,
                                           'price_unit': 120.0, 'tax_ids': [Command.clear()]})]})
        orden.action_confirm()
        de_marketing = self.Camila.with_user(self.marketing).panel()['historial'][0]
        self.assertEqual((de_marketing['web'], de_marketing['monto_web']), (1, None), 'Marketing no ve montos')
        self.assertEqual(self.Camila.with_user(self.gerencia).panel()['historial'][0]['monto_web'], '$120.00')


# ----------------------------------------------------------------------
# 7. Juan sabe que el cliente vino del correo; el origen «Correo»
# ----------------------------------------------------------------------

@tagged('post_install', '-at_install')
class TestJuanSabeDelCorreo(Etapa2Comun, HttpCase):

    def setUp(self):
        super().setUp()
        entorno = patch.dict(os.environ, {'JUAN_ODOO_TOKEN': TOKEN_JUAN, 'JUAN_WORKER_TOKEN': '', 'JUAN_URL': ''})
        entorno.start()
        self.addCleanup(entorno.stop)
        self.con_clave()
        self.permiso(self.ana)
        datos = self.armar()['campana']
        self.assertTrue(self.enviar(datos)['ok'])
        self.campana_enviada = self.campana(datos)

    def llega(self, texto, numero='50760005001', id_mensaje='j1'):
        cuerpo = {'canal': 'whatsapp_qr', 'id_externo': numero, 'nombre': 'Cliente Zzcm', 'celular': numero,
                  'id_mensaje': id_mensaje, 'direccion': 'entrante', 'autor': 'cliente', 'texto': texto,
                  'ts': H.a_iso(fields.Datetime.now())}
        respuesta = self.url_open('/dcasa/juan/v1/mensaje', data=json.dumps(cuerpo),
                                  headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {TOKEN_JUAN}'})
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        return respuesta.json()

    def test_juan_recibe_la_campana_y_sus_productos(self):
        cuerpo = self.llega(R.texto_whatsapp(self.campana_enviada.id))
        contexto = cuerpo.get('campana_correo') or ''
        self.assertIn(self.campana_enviada.asunto, contexto)
        self.assertIn(self.campana_enviada.linea_ids[0].nombre, contexto)
        self.assertNotIn('$', contexto, 'Sin precios: si los pregunta, Juan los consulta')
        conversacion = self.env['dcasa.conversacion'].sudo().browse(cuerpo['conversacion_id'])
        self.assertIn(self.env.ref('dcasa_camila.etiqueta_vino_del_correo'), conversacion.etiqueta_ids)
        self.assertEqual(conversacion._estado_para_worker().get('campana_correo'), contexto, 'También en /estado')

    def test_sin_campana_no_va_y_pasados_los_dias_tampoco(self):
        cuerpo = self.llega('Hola, ¿tienen camas?', numero='50760005002', id_mensaje='j2')
        self.assertNotIn('campana_correo', cuerpo)
        cuerpo = self.llega(R.texto_whatsapp(self.campana_enviada.id), numero='50760005003', id_mensaje='j3')
        conversacion = self.env['dcasa.conversacion'].sudo().browse(cuerpo['conversacion_id'])
        conversacion.env['dcasa.camila.llegada'].sudo().search([('conversacion_id', '=', conversacion.id)]).write(
            {'ts': fields.Datetime.now() - timedelta(days=4)})
        self.assertNotIn('campana_correo', conversacion._estado_para_worker())

    def test_la_cotizacion_dice_de_que_campana_vino(self):
        cuerpo = self.llega(R.texto_whatsapp(self.campana_enviada.id), numero='50760005004', id_mensaje='j4')
        cliente = self.env['dcasa.conversacion'].sudo().browse(cuerpo['conversacion_id']).partner_id
        orden = self.env['sale.order'].create({'partner_id': cliente.id})
        self.assertEqual(orden.dcasa_camila_correo,
                         f'{R.marca(self.campana_enviada.id)} · {self.campana_enviada.asunto}')
        otra = self.env['sale.order'].create({'partner_id': self.beto.id})
        self.assertFalse(otra.dcasa_camila_correo)
        self.assertEqual(orden.dcasa_origen, 'vendedora', 'El «Origen» de siempre no cambia: dice quién la armó')
