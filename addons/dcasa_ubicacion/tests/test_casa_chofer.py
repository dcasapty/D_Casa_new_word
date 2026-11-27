"""Para que el pedido no vuelva (el dueño, 2026-11-25: «el dolor número uno son los pedidos devueltos»): quién recibe,
el teléfono de respaldo, la foto de la fachada (sin EXIF), «Avisar que llegué» en la página del chofer y la tarjeta
«Marcar mi casa en el mapa» al terminar de pagar.

Las fotos de prueba se hacen con PIL en memoria, con un GPS y una marca de teléfono inventados en su EXIF (el
repositorio es público: ninguna foto ni dato real)."""
import io
import json
import os
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import unquote

from PIL import Image

import odoo
from odoo import fields
from odoo.addons.dcasa_brian.models.registro import BrianError
from odoo.addons.dcasa_conversaciones.models.herramientas_juan import GRUPOS
from odoo.addons.dcasa_envios.controllers.choferes import reiniciar_limite
from odoo.addons.dcasa_envios.tests.common import importar
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import BaseCase, HttpCase, new_test_user, tagged

from ..controllers.checkout import quien_recibe_del_formulario
from ..motor import casa
from .common import CERCA, UbicacionCase

COMENTARIO_CON_GPS = b'GPS 8.9012,-79.8013'
SIN_CLAVES = {'GOOGLE_MAPS_CLAVE_NAVEGADOR': '', 'GOOGLE_MAPS_CLAVE_SERVIDOR': ''}


def foto_de_prueba(ancho=2400, alto=1800, orientacion=None, formato='JPEG', modo='RGB'):
    """Una «foto del teléfono» inventada: con la marca del teléfono y el GPS en el EXIF (y, en JPEG, un comentario)."""
    imagen = Image.new(modo, (ancho, alto), (200, 120, 60, 255) if modo == 'RGBA' else (200, 120, 60))
    exif = Image.Exif()
    exif[0x010F] = 'TelefonoDePrueba'
    exif[0x8825] = {1: 'N', 2: (8.0, 54.0, 4.32), 3: 'W', 4: (79.0, 48.0, 4.68)}
    if orientacion:
        exif[0x0112] = orientacion
    salida = io.BytesIO()
    extra = {'comment': COMENTARIO_CON_GPS} if formato == 'JPEG' else {}
    imagen.save(salida, formato, exif=exif.tobytes(), **extra)
    return salida.getvalue()


def sin_datos_ocultos(prueba, jpeg):
    """Comprueba que es un JPEG sin EXIF, sin comentario, sin XMP ni perfil: nada del archivo original."""
    imagen = Image.open(io.BytesIO(jpeg))
    prueba.assertEqual(imagen.format, 'JPEG')
    prueba.assertFalse(dict(imagen.getexif()), 'sin EXIF (ni el GPS)')
    for clave in ('exif', 'comment', 'xmp', 'icc_profile'):
        prueba.assertNotIn(clave, imagen.info)
    for trozo in (b'Exif', b'TelefonoDePrueba', COMENTARIO_CON_GPS, b'http://ns.adobe.com/xap'):
        prueba.assertNotIn(trozo, jpeg)
    return imagen


@tagged('post_install', '-at_install')
class TestMotorCasa(BaseCase):

    def test_el_telefono_de_respaldo_es_de_panama(self):
        self.assertEqual(casa.telefono_de_respaldo(' 6123 4567 '), {
            'guardar': '+507 6123-4567', 'tel': '+50761234567', 'wa': '50761234567', 'nacional': '61234567'})
        self.assertEqual(casa.telefono_de_respaldo('+507 6123-4567')['guardar'], '+507 6123-4567')
        fijo = casa.telefono_de_respaldo('234-5678')
        self.assertEqual((fijo['guardar'], fijo['tel'], fijo['wa']), ('+507 234-5678', '+5072345678', ''),
                         'un fijo se llama, pero no tiene WhatsApp')
        for malo in ('', None, '123', '+1 305 555 1234', '6123-4567 y 6999-8888', 'mi mamá', '61234567890'):
            with self.subTest(malo=malo):
                self.assertIsNone(casa.telefono_de_respaldo(malo))
        self.assertTrue(casa.mismo_telefono('+507 6123-4567', '61234567'))
        self.assertFalse(casa.mismo_telefono('6123-4567', '6999-8888'))

    def test_el_whatsapp_del_chofer(self):
        self.assertEqual(casa.numero_whatsapp('+507 6123-4567'), '50761234567')
        self.assertEqual(casa.numero_whatsapp('6123-4567'), '50761234567')
        self.assertEqual(casa.numero_whatsapp('+1 305 555 1234'), '13055551234')
        self.assertEqual(casa.numero_whatsapp('234-5678'), '', 'un fijo no tiene WhatsApp')
        self.assertEqual(casa.numero_whatsapp(''), '')
        texto = 'Hola Ana, ya llegué con tu pedido S00042 📦'
        enlace = casa.enlace_whatsapp('50761234567', texto)
        self.assertTrue(enlace.startswith('https://api.whatsapp.com/send?phone=50761234567&text='))
        self.assertEqual(unquote(enlace.split('&text=', 1)[1]), texto)
        self.assertEqual(casa.enlace_whatsapp('', texto), '')

    def test_la_foto_sale_sin_exif_derecha_y_chica(self):
        original = foto_de_prueba(orientacion=6)
        self.assertIn(b'TelefonoDePrueba', original, 'la foto de prueba sí trae su EXIF')
        self.assertTrue(Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825), 'y su GPS')
        imagen = sin_datos_ocultos(self, casa.procesar_foto(original))
        self.assertEqual(imagen.size, (960, 1280), 'enderezada (venía acostada) y de 1280 px de lado')

    def test_png_con_transparencia_y_webp_tambien(self):
        for formato, modo in (('PNG', 'RGBA'), ('WEBP', 'RGB')):
            with self.subTest(formato=formato):
                imagen = sin_datos_ocultos(self, casa.procesar_foto(foto_de_prueba(800, 600, formato=formato,
                                                                                     modo=modo)))
                self.assertEqual(imagen.size, (800, 600), 'una foto chica no se agranda')

    def test_lo_que_no_es_foto_no_se_guarda(self):
        gif = io.BytesIO()
        Image.new('RGB', (20, 20)).save(gif, 'GIF')
        enorme = io.BytesIO()
        Image.new('1', (8000, 7000)).save(enorme, 'PNG')     # 56 megapíxeles en pocos KB
        casos = ((b'', 'vacia'), (None, 'vacia'), (b'%PDF-1.4 no soy una foto', 'formato'),
                 (b'<svg xmlns="http://www.w3.org/2000/svg"/>', 'formato'), (gif.getvalue(), 'formato'),
                 (enorme.getvalue(), 'pesada'), (b'x' * (casa.MAX_FOTO_BYTES + 1), 'pesada'))
        for datos, motivo in casos:
            with self.subTest(motivo=motivo, inicio=(datos or b'')[:12]):
                with self.assertRaises(casa.FotoInvalida) as error:
                    casa.procesar_foto(datos)
                self.assertEqual(error.exception.motivo, motivo)
                self.assertIn('📷', str(error.exception.args[0]), 'un mensaje corto para el cliente')

    def test_lo_opcional_del_checkout(self):
        self.assertEqual(quien_recibe_del_formulario({}), (None, None, None), 'un formulario viejo no toca la ficha')
        self.assertEqual(quien_recibe_del_formulario({'dcasa_recibe': '  Rosa,  su mamá ',
                                                      'dcasa_tel_respaldo': '69998888'}),
                         ('Rosa, su mamá', '+507 6999-8888', None))
        self.assertEqual(quien_recibe_del_formulario({'dcasa_recibe': '', 'dcasa_tel_respaldo': ' '}), ('', '', None),
                         'vacíos (venían llenos con lo de la ficha): se borran')
        _recibe, telefono, error = quien_recibe_del_formulario({'dcasa_tel_respaldo': '+1 305 555 1234'})
        self.assertEqual((telefono, error), (None, casa.MENSAJE_TELEFONO))


@tagged('post_install', '-at_install')
class TestQuienRecibeYFoto(UbicacionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.domicilio = cls.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        cls.producto = cls.env['product.product'].create({'name': 'Caja de la casa', 'list_price': 20, 'type': 'consu',
                                                          'sale_ok': True})

    def venta(self, con_envio=True):
        orden = self.env['sale.order'].create({
            'partner_id': self.cliente.id, 'order_line': [(0, 0, {'product_id': self.producto.id})]})
        if con_envio:
            orden.carrier_id = self.domicilio
        return orden

    def ultimo_aviso(self, conv):
        return self.env['dcasa.mensaje'].sudo().search([('conversacion_id', '=', conv.id), ('tipo', '=', 'aviso')],
                                                        order='id desc', limit=1)

    def test_la_ficha_guarda_quien_recibe_y_el_telefono_bien_escrito(self):
        c = self.cliente
        c._dcasa_poner_quien_recibe(recibe='  Rosa,   su mamá ', telefono='6999 8888')
        self.assertEqual((c.dcasa_recibe, c.dcasa_tel_respaldo), ('Rosa, su mamá', '+507 6999-8888'))
        c._dcasa_poner_quien_recibe()
        self.assertEqual(c.dcasa_recibe, 'Rosa, su mamá', 'None no toca nada')
        with self.assertRaises(casa.TelefonoInvalido):
            c._dcasa_poner_quien_recibe(recibe='Otra', telefono='+1 305 555 1234')
        self.assertEqual(c.dcasa_recibe, 'Rosa, su mamá', 'con un teléfono malo no se guarda nada')
        c._dcasa_poner_quien_recibe(recibe='x' * 90)
        self.assertEqual(len(c.dcasa_recibe), casa.MAX_RECIBE)
        resumen = c._dcasa_ubic_resumen()
        self.assertEqual((resumen['telefono_respaldo'], resumen['tiene_foto_fachada']), ('+507 6999-8888', False))
        c._dcasa_poner_quien_recibe(recibe='', telefono='')
        self.assertFalse(c.dcasa_recibe or c.dcasa_tel_respaldo)
        # En el panel: la ficha lo deja bien escrito y no acepta uno que no es de Panamá.
        nueva = self.env['res.partner'].new({'dcasa_tel_respaldo': '61234567'})
        nueva._onchange_dcasa_tel_respaldo()
        self.assertEqual(nueva.dcasa_tel_respaldo, '+507 6123-4567')
        c.write({'dcasa_tel_respaldo': '234-5678'})
        with self.assertRaises(ValidationError):
            c.write({'dcasa_tel_respaldo': 'no sé'})

    def test_la_foto_de_la_casa_es_una_por_cliente(self):
        c = self.cliente
        c._dcasa_poner_fachada(foto_de_prueba(orientacion=6))
        self.assertTrue(c.dcasa_fachada_fecha)
        self.assertEqual(sin_datos_ocultos(self, c._dcasa_fachada_jpeg()).size, (960, 1280))
        dominio = [('res_model', '=', 'res.partner'), ('res_id', '=', c.id), ('res_field', '=', 'dcasa_fachada')]
        adjunto = self.env['ir.attachment'].sudo().search(dominio)
        self.assertEqual(len(adjunto), 1, 'un adjunto ligado a la ficha')
        self.assertFalse(adjunto.public)
        c._dcasa_poner_fachada(foto_de_prueba(300, 200, formato='PNG'))
        self.assertEqual(self.env['ir.attachment'].sudo().search(dominio), adjunto,
                         'la nueva reemplaza a la anterior en el mismo adjunto')
        self.assertEqual(Image.open(io.BytesIO(c._dcasa_fachada_jpeg())).size, (300, 200))
        self.assertTrue(c._dcasa_ubic_resumen()['tiene_foto_fachada'])
        self.assertIn('foto de su casa', c.message_ids[:1].body)
        with self.assertRaises(casa.FotoInvalida):
            c._dcasa_poner_fachada(b'no soy una foto')
        self.assertEqual(Image.open(io.BytesIO(c._dcasa_fachada_jpeg())).size, (300, 200), 'la buena sigue')
        # Quitarla: el cliente del portal no puede; el equipo sí.
        portal = new_test_user(self.env, login='portal_casa', name='Portal Casa', groups='base.group_portal')
        with self.assertRaises(AccessError):
            c.with_user(portal).action_dcasa_quitar_fachada()
        c.action_dcasa_quitar_fachada()
        self.assertFalse(c.dcasa_fachada_fecha or c._dcasa_fachada_jpeg())
        self.assertFalse(c._dcasa_quitar_fachada(), 'ya no había')

    def test_el_chofer_avisa_que_llego_y_tiene_el_respaldo(self):
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Portón negro')
        self.cliente._dcasa_poner_quien_recibe(recibe='Rosa, su mamá', telefono='6999-8888')
        orden = self.venta()
        orden.action_confirm()
        entrega = self.env['dcasa.ubicacion.entrega']._de_la_venta(orden, crear=False)
        tienda = entrega._nombre_de_la_tienda()
        self.assertTrue(tienda, 'el nombre sale del sitio o de la compañía, no escrito a mano')
        datos = entrega._para_el_chofer()
        self.assertTrue(datos['avisar_llegue'].startswith('https://api.whatsapp.com/send?phone=50761234567&text='))
        self.assertEqual(unquote(datos['avisar_llegue'].split('&text=', 1)[1]),
                         f'Hola Ana, soy el chofer de {tienda}. Ya llegué con tu pedido {orden.name} 📦')
        self.assertEqual((datos['recibe'], datos['respaldo'], datos['respaldo_tel']),
                         ('Rosa, su mamá', '+507 6999-8888', '+50769998888'))
        self.assertTrue(datos['respaldo_whatsapp'].startswith('https://api.whatsapp.com/send?phone=50769998888&text='))
        self.assertEqual(unquote(datos['respaldo_whatsapp'].split('&text=', 1)[1]),
                         f'Hola, soy el chofer de {tienda}. Ya llegué con el pedido {orden.name} de Ana 📦',
                         'al respaldo le escribe a otra persona: el pedido es «de Ana»')
        self.assertFalse(datos['fachada_url'])
        self.assertEqual(orden.dcasa_recibe_entrega, 'Rosa, su mamá', 'la venta también lo muestra')
        # Un fijo se llama, sin WhatsApp; el mismo celular del cliente no se repite como respaldo.
        self.cliente._dcasa_poner_quien_recibe(telefono='234-5678')
        datos = entrega._para_el_chofer()
        self.assertEqual((datos['respaldo_tel'], datos['respaldo_whatsapp']), ('+5072345678', ''))
        self.cliente._dcasa_poner_quien_recibe(telefono='6123-4567')
        self.assertFalse(entrega._para_el_chofer()['respaldo'])
        # La foto, por su ruta con el mismo secreto de la página.
        self.cliente._dcasa_poner_fachada(foto_de_prueba(400, 300))
        self.assertEqual(entrega._para_el_chofer()['fachada_url'], f'/entrega/{entrega.sudo().token}/fachada')
        # Sin celular, no hay «Avisar que llegué» (ni «Llamar»): el respaldo sigue ahí.
        self.cliente.phone = False
        datos = entrega._para_el_chofer()
        self.assertFalse(datos['avisar_llegue'] or datos['telefono_tel'])

    def test_el_comprobante_dice_quien_recibe_sin_crear_nada(self):
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa 8')
        self.cliente._dcasa_poner_quien_recibe(recibe='Rosa, su mamá', telefono='6999-8888')
        self.cliente._dcasa_poner_fachada(foto_de_prueba(400, 300))
        orden = self.venta()
        orden.action_confirm()
        factura = orden._create_invoices()
        factura.action_post()
        with patch.object(type(self.env['dcasa.ubicacion.entrega']), 'create',
                          side_effect=AssertionError('el PDF no crea nada')):
            html = str(self.env['ir.qweb']._render('dcasa_ubicacion.bloque_chofer', {'registro': factura}))
        for texto in ('Para el chofer', 'Recibe: Rosa, su mamá', 'Si no contesta: +507 6999-8888',
                      'Con foto de la casa'):
            self.assertIn(texto, html)

    def test_al_confirmar_el_enlace_guarda_quien_recibe_y_avisa_al_equipo(self):
        conv = self.conversacion(id_externo='50761230030')
        self.configurar_worker()
        enlace, _url = self.env['dcasa.ubicacion.enlace']._crear(conv.partner_id, conversacion=conv, creado_por='juan')
        enlace._confirmar(*CERCA, 'gps', precision=9, referencia='Casa 3', recibe='Rosa', telefono='6999-8888')
        partner = conv.partner_id
        self.assertEqual((partner.dcasa_recibe, partner.dcasa_tel_respaldo), ('Rosa', '+507 6999-8888'))
        avisos = ' '.join(self.env['dcasa.mensaje'].sudo().search(
            [('conversacion_id', '=', conv.id), ('tipo', '=', 'aviso')]).mapped('texto'))
        self.assertIn('👤 Recibe: Rosa.', avisos)
        self.assertIn('+507 6999-8888', avisos)
        al_chat = self.env['dcasa.mensaje'].sudo().search([('conversacion_id', '=', conv.id), ('origen', '=', 'odoo'),
                                                           ('tipo', '=', 'mensaje')])
        self.assertNotIn('6999', ' '.join(al_chat.mapped('texto')), 'el teléfono de respaldo no va al chat')
        # Vacío no borra lo que ya había (la página no lo muestra lleno).
        otro, _url = self.env['dcasa.ubicacion.enlace']._crear(partner)
        otro._confirmar(*CERCA, 'pin', referencia='Casa 3', recibe='', telefono='')
        self.assertEqual(partner.dcasa_recibe, 'Rosa')

    def test_juan_guarda_quien_recibe_solo_si_la_cliente_lo_dijo(self):
        conv = self.conversacion('Lo recibe mi mamá Rosa. Si no contesto, llamen al 6999-8888',
                                 id_externo='50761230020')
        Juan = self.env['brian.herramientas'].with_context(juan_conversacion_id=conv.id)
        for argumentos in ({}, {'telefono': '6555-1212'}, {'telefono': '+1 305 555 1234'}):
            with self.subTest(argumentos=argumentos), self.assertRaises(BrianError):
                Juan._juan_guardar_quien_recibe(**argumentos)
        datos = Juan._juan_guardar_quien_recibe(nombre='Rosa, su mamá', telefono='6999-8888')
        self.assertTrue(datos['guardado'] and datos['telefono_de_respaldo'])
        self.assertNotIn('6999', json.dumps(datos, ensure_ascii=False), 'el número no vuelve al modelo')
        partner = conv.partner_id
        self.assertEqual((partner.dcasa_recibe, partner.dcasa_tel_respaldo), ('Rosa, su mamá', '+507 6999-8888'))
        aviso = self.ultimo_aviso(conv).texto
        self.assertIn('👤 Recibe: Rosa, su mamá.', aviso)
        self.assertIn('+507 6999-8888', aviso)
        # El mismo celular de la conversación no hace falta como respaldo.
        otra = self.conversacion('Mejor llamen a este mismo: 6123-0021', id_externo='50761230021')
        datos = self.env['brian.herramientas'].with_context(juan_conversacion_id=otra.id)._juan_guardar_quien_recibe(
            telefono='6123-0021')
        self.assertFalse(datos['telefono_de_respaldo'])
        self.assertIn('mismo de su ficha', datos['instruccion'])
        self.assertFalse(otra.partner_id.dcasa_tel_respaldo)

    def test_brian_lee_pone_y_quita(self):
        vendedora = new_test_user(self.env, login='vend_casa', name='Vendedora Casa',
                                  groups='base.group_user,sales_team.group_sale_salesman')
        Brian = self.env['brian.herramientas'].with_user(vendedora)
        datos = Brian._brian_poner_quien_recibe(cliente='Ana Prueba', nombre='Rosa', telefono='6999 8888')
        self.assertEqual((datos['recibe'], datos['telefono_respaldo']), ('Rosa', '+507 6999-8888'))
        with self.assertRaises(BrianError):
            Brian._brian_poner_quien_recibe(cliente='Ana Prueba', telefono='123')
        with self.assertRaises(BrianError):
            Brian._brian_poner_quien_recibe(cliente='Ana Prueba')
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Casa azul')
        self.cliente._dcasa_poner_fachada(foto_de_prueba(400, 300))
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id, 'user_id': vendedora.id})
        leido = Brian._brian_ubicacion_de_entrega(venta=orden.name)
        self.assertEqual((leido['recibe'], leido['telefono_respaldo'], leido['tiene_foto_fachada']),
                         ('Rosa', '+507 6999-8888', True))
        self.assertNotIn('fachada_url', leido, 'Brian dice si hay foto; la foto se ve en la ficha o en la página')
        self.assertTrue(Brian._brian_quitar_foto_de_fachada(cliente='Ana Prueba')['quitada'])
        self.assertFalse(Brian._brian_ubicacion_de_entrega(venta=orden.name)['tiene_foto_fachada'])
        datos = Brian._brian_poner_quien_recibe(cliente='Ana Prueba', nombre='', telefono='')
        self.assertEqual((datos['recibe'], datos['telefono_respaldo']), ('(nadie anotado)', '(ninguno)'))
        todas = self.env['brian.herramientas']._todas()
        self.assertEqual(todas['juan_guardar_quien_recibe']['grupos'], GRUPOS, 'solo Juan')
        self.assertIn('SOLO si el cliente lo dice por su cuenta', todas['juan_guardar_quien_recibe']['descripcion'])
        for nombre in ('poner_quien_recibe', 'quitar_foto_de_fachada'):
            self.assertEqual(todas[nombre]['grupos'], ('base.group_user',), 'el equipo, también por MCP')

    def test_la_tarjeta_para_marcar_la_casa_al_pagar(self):
        orden = self.venta()
        url = orden._dcasa_ubic_url_para_marcar()
        self.assertEqual(url, f'/u/pedido/{orden.id}?access_token={orden.access_token}')
        self.assertTrue(orden.access_token)
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'busqueda', referencia='Casa 4')
        self.assertTrue(orden._dcasa_ubic_url_para_marcar(), 'un punto solo buscado no es confiable')
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'gps', precision=9, referencia='Casa 4')
        self.assertEqual(orden._dcasa_ubic_url_para_marcar(), '')
        self.assertEqual(self.venta(con_envio=False)._dcasa_ubic_url_para_marcar(), '', 'sin domicilio, nada')


@tagged('post_install', '-at_install')
class TestRutasDeLaCasa(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gerencia = new_test_user(cls.env, login='ger_casa_http', name='Gerencia Casa',
                                 groups='base.group_user,dcasa_base.group_gerencia')
        importar(cls.env, gerencia)
        cls.env['dcasa.envio.tarifa'].search([], limit=1).with_user(gerencia).action_aprobar()
        cls.cliente = cls.env['res.partner'].create({'name': 'Carla Prueba', 'phone': '+507 6555-0101'})
        cls.domicilio = cls.env['delivery.carrier'].sudo().search([('dcasa_por_cotizar', '=', True)], limit=1)
        cls.producto = cls.env['product.product'].create({'name': 'Caja de la ruta', 'list_price': 20,
                                                          'type': 'consu', 'sale_ok': True})

    def setUp(self):
        super().setUp()
        reiniciar_limite()
        self.addCleanup(reiniciar_limite)
        entorno = patch.dict(os.environ, SIN_CLAVES)
        entorno.start()
        self.addCleanup(entorno.stop)

    def enlace(self):
        enlace, url = self.env['dcasa.ubicacion.enlace']._crear(self.cliente)
        return enlace, '/u/' + url.rsplit('/u/', 1)[1]

    def post_json(self, ruta, cuerpo):
        return self.url_open(ruta, data=json.dumps(cuerpo), headers={'Content-Type': 'application/json'})

    def post_foto(self, ruta, datos):
        return self.url_open(ruta, data=datos, headers={'Content-Type': 'image/jpeg'})

    def venta_confirmada(self):
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id, 'carrier_id': self.domicilio.id,
                                               'order_line': [(0, 0, {'product_id': self.producto.id})]})
        orden.action_confirm()
        return orden

    def test_la_pagina_del_enlace_pide_lo_opcional_y_lo_guarda(self):
        enlace, base = self.enlace()
        pagina = self.url_open(base)
        for texto in ('¿Quién recibe? (opcional)', 'Otro teléfono (opcional)', 'Foto de tu casa (opcional)',
                      'accept="image/*"'):
            self.assertIn(texto, pagina.text)
        self.assertNotIn('capture=', pagina.text, 'cámara o galería: puede no estar en su casa al comprar')
        self.assertNotIn(' style="', pagina.text, 'la CSP sin mapa no deja atributos style')
        punto = {'lat': CERCA[0], 'lon': CERCA[1], 'origen': 'pin', 'referencia': 'Casa 5'}
        malo = self.post_json(base + '/guardar', dict(punto, telefono='+1 305 555 1234'))
        self.assertEqual((malo.status_code, malo.json()['campo']), (400, 'telefono'))
        self.assertEqual(enlace.estado, 'vigente', 'con el teléfono malo no se usa el enlace')
        bien = self.post_json(base + '/guardar', dict(punto, recibe='Rosa, su mamá', telefono='6999 8888'))
        self.assertEqual(bien.status_code, 200, bien.text)
        self.cliente.invalidate_recordset()
        self.assertEqual((self.cliente.dcasa_recibe, self.cliente.dcasa_tel_respaldo),
                         ('Rosa, su mamá', '+507 6999-8888'))

    def test_la_foto_de_la_casa_sube_sin_exif(self):
        enlace, base = self.enlace()
        respuesta = self.post_foto(base + '/foto', foto_de_prueba(orientacion=6))
        self.assertEqual(respuesta.status_code, 200, respuesta.text)
        self.assertEqual(respuesta.headers['Cache-Control'], 'no-store')
        self.cliente.invalidate_recordset()
        self.assertEqual(sin_datos_ocultos(self, self.cliente._dcasa_fachada_jpeg()).size, (960, 1280))
        basura = self.post_foto(base + '/foto', b'%PDF-1.4 no soy una foto')
        self.assertEqual((basura.status_code, basura.json()['motivo']), (422, 'formato'))
        self.assertEqual(self.post_foto(base + '/foto', b'x' * (casa.MAX_FOTO_BYTES + 1)).status_code, 413)
        # Usado el enlace, la foto puede llegar justo después (una hora); días después, no.
        enlace.sudo().usado_el = fields.Datetime.now()
        self.assertEqual(self.post_foto(base + '/foto', foto_de_prueba(300, 200)).status_code, 200)
        enlace.sudo().usado_el = fields.Datetime.now() - timedelta(hours=2)
        self.assertEqual(self.post_foto(base + '/foto', foto_de_prueba(300, 200)).status_code, 404)
        self.assertEqual(self.post_foto('/u/' + 'z' * 22 + '/foto', foto_de_prueba(300, 200)).status_code, 404)
        self.cliente.invalidate_recordset()
        self.assertEqual(Image.open(io.BytesIO(self.cliente._dcasa_fachada_jpeg())).size, (300, 200))

    def test_el_chofer_ve_la_foto_y_avisa_que_llego(self):
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'pin', referencia='Portón negro')
        self.cliente._dcasa_poner_quien_recibe(recibe='Rosa, su mamá', telefono='6999-8888')
        entrega = self.env['dcasa.ubicacion.entrega']._de_la_venta(self.venta_confirmada(), crear=False)
        token = entrega.sudo().token
        self.assertEqual(self.url_open(f'/entrega/{token}/fachada').status_code, 404, 'sin foto todavía')
        self.cliente._dcasa_poner_fachada(foto_de_prueba(orientacion=6))
        pagina = self.url_open(f'/entrega/{token}')
        self.assertEqual(pagina.status_code, 200)
        for texto in ('Avisar que llegué', 'https://api.whatsapp.com/send?phone=50765550101&amp;text=', 'Rosa, su mamá',
                      'Si no contesta', '+507 6999-8888', 'tel:+50769998888',
                      'https://api.whatsapp.com/send?phone=50769998888&amp;text=',
                      f'src="/entrega/{token}/fachada"', 'Así se ve la casa'):
            self.assertIn(texto, pagina.text)
        self.assertNotIn(' style="', pagina.text, 'la CSP sin mapa no deja atributos style')
        foto = self.url_open(f'/entrega/{token}/fachada')
        self.assertEqual(foto.status_code, 200)
        self.assertEqual(foto.headers['Content-Type'], 'image/jpeg')
        self.assertEqual(foto.headers['Cache-Control'], 'no-store')
        self.assertIn('noindex', foto.headers['X-Robots-Tag'])
        sin_datos_ocultos(self, foto.content)
        self.assertEqual(self.url_open('/entrega/' + 'y' * 24 + '/fachada').status_code, 404)
        entrega.order_id.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing').sudo().write(
            {'state': 'done', 'date_done': fields.Datetime.now() - timedelta(days=4)})
        self.assertEqual(self.url_open(f'/entrega/{token}/fachada').status_code, 404, 'se cierra con la página')

    def test_al_pagar_sale_la_tarjeta_para_marcar_la_casa(self):
        sesion = self.authenticate(None, None)
        orden = self.env['sale.order'].create({'partner_id': self.cliente.id, 'carrier_id': self.domicilio.id,
                                               'order_line': [(0, 0, {'product_id': self.producto.id})]})
        sesion['sale_last_order_id'] = orden.id
        odoo.http.root.session_store.save(sesion)
        self.env.flush_all()
        pagina = self.url_open('/shop/confirmation')
        self.assertEqual(pagina.status_code, 200)
        self.assertIn('Marcar mi casa en el mapa', pagina.text)
        orden.invalidate_recordset()
        self.assertIn(f'/u/pedido/{orden.id}?access_token={orden.access_token}', pagina.text)
        self.cliente._dcasa_poner_ubicacion(*CERCA, 'gps', precision=9, referencia='Casa 4')
        self.assertNotIn('Marcar mi casa en el mapa', self.url_open('/shop/confirmation').text)
