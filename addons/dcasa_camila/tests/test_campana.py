"""La campaña: qué productos escoge Camila, con qué precio, qué texto, cómo se ve el correo, qué revisa el servidor al
enviar y cómo habla con Resend (falso: nunca se llama a Resend de verdad)."""
import json
import re
from datetime import timedelta
from unittest.mock import patch

from lxml import html as lxml_html

from odoo import fields
from odoo.addons.dcasa_brian.models import proveedores as P
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from ..models import reglas as R
from .comun import CamilaComun


def estilo(elemento):
    return re.sub(r'\s+', '', (elemento.get('style') or '') + ';bgcolor:' + (elemento.get('bgcolor') or '')).lower()


@tagged('post_install', '-at_install')
class TestArmar(CamilaComun):

    def test_escoge_solo_lo_que_hay_en_tienda_con_foto_publicado_y_con_precio(self):
        agotado = self.producto('ZZCM AGOTADO', stock=0)
        sin_foto = self.producto('ZZCM SIN FOTO', con_foto=False)
        sin_publicar = self.producto('ZZCM SIN PUBLICAR', publicado=False)
        sin_precio = self.producto('ZZCM SIN PRECIO', precio=0.0)
        datos = self.armar()
        lineas = datos['campana']['lineas']
        self.assertEqual(len(lineas), R.PRODUCTOS_POR_CAMPANA)
        ids = {linea['producto_id'] for linea in lineas}
        self.assertTrue(ids <= set(self.productos.ids), 'Solo productos en tienda, con foto, publicados y con precio')
        self.assertFalse(ids & set((agotado | sin_foto | sin_publicar | sin_precio).ids))

    def test_reparte_lo_nuevo_lo_vendido_y_lo_quieto(self):
        viejo = fields.Datetime.now() - timedelta(days=120)
        nuevo = self.productos[3]
        self.env.cr.execute('UPDATE product_template SET create_date = %s WHERE id IN %s',
                            [viejo, tuple((self.productos - nuevo).ids)])
        self.env.cr.execute('UPDATE product_template SET create_date = %s WHERE id = %s',
                            [fields.Datetime.now() - timedelta(days=2), nuevo.id])
        self.productos.invalidate_recordset(['create_date'])
        datos = self.armar()
        grupos = {linea['producto_id']: linea['grupo'] for linea in datos['campana']['lineas']}
        self.assertEqual(grupos[nuevo.id], 'nuevo')
        self.assertIn('quieto', grupos.values(), 'Con stock y sin ventas: lo quieto de Marketing')

    def test_el_precio_es_el_de_la_tienda_en_linea(self):
        self.productos.write({'list_price': 1070.5})
        datos = self.armar()
        self.assertEqual({linea['precio'] for linea in datos['campana']['lineas']}, {'$1,070.50'})
        # Con tarifas encendidas: la tarifa del sitio, la misma que ve el visitante anónimo (-10 %).
        grupo_tarifas = self.env.ref('product.group_product_pricelist')
        self.env.ref('base.group_user').sudo().implied_ids |= grupo_tarifas
        tarifa = self.env['product.pricelist'].create({
            'name': 'ZZCM Tarifa web', 'website_id': self.website.id, 'selectable': True, 'sequence': 1,
            'item_ids': [(0, 0, {'applied_on': '3_global', 'compute_price': 'percentage', 'percent_price': 10})]})
        self.website.user_id.partner_id.sudo().property_product_pricelist = tarifa
        precios = self.Camila._precios(self.productos[:1], self.website)
        self.assertAlmostEqual(precios[self.productos[0].id][0], 963.45)

    def test_la_ia_escribe_y_el_codigo_pone_productos_precios_y_enlace(self):
        p0 = self.productos[-1]   # el más nuevo: Camila lo escoge primero
        self.guion_ia(lineas={str(p0.id): 'Para que tu sala se vea más amplia.'})
        datos = self.armar()
        campana = datos['campana']
        self.assertEqual(campana['asunto'], 'Lo nuevo para tu sala')
        self.assertEqual(campana['entrada'], 'Llegaron muebles que te van a gustar.')
        linea = next(linea for linea in campana['lineas'] if linea['producto_id'] == p0.id)
        self.assertEqual(linea['texto'], 'Para que tu sala se vea más amplia.')
        enviado = P.LLAMADAS[-1]['mensajes'][0]['texto']
        self.assertNotIn('@', enviado, 'A la IA no le llega ningún dato de clientes')
        self.assertIn(p0._dcasa_nombre_cliente(), enviado)

    def test_si_la_ia_falla_o_no_pasa_la_revision_queda_el_texto_fijo(self):
        self.guion_ia(asunto='¡¡REMATE!! 50% menos', entrada='Visítenos hoy')
        datos = self.armar()
        self.assertEqual(datos['campana']['asunto'], R.ASUNTO_FIJO)
        self.assertEqual(datos['campana']['entrada'], R.ENTRADA_FIJA)
        self.assertIn('revisión de marca', datos['campana']['nota'])
        self.Camila.with_user(self.marketing).descartar(datos['campana']['id'])
        with patch.object(P.ProveedorPrueba, 'chatear', side_effect=P.ProveedorError('sin conexión')):
            datos = self.armar()
        self.assertEqual(datos['campana']['asunto'], R.ASUNTO_FIJO)
        self.assertIn('La IA no respondió', datos['campana']['nota'])
        self.assertEqual(datos['campana']['fuente'], 'Texto fijo')

    def test_el_correo_lleva_la_marca(self):
        self.website.dcasa_whatsapp_number = '+507 6026-1919'
        self.env.company.write({'street': 'Frente al Parque de Prueba', 'street2': False, 'city': 'La Chorrera'})
        datos = self.armar()
        campana = self.env['dcasa.camila.campana'].browse(datos['campana']['id'])
        cuerpo = self.Camila._html(campana, para_resend=True)
        minusculas = cuerpo.lower()
        for prohibido in ('gradient', 'box-shadow', 'text-shadow', '<script', '<style', 'javascript:'):
            self.assertNotIn(prohibido, minusculas)
        arbol = lxml_html.fromstring(cuerpo)
        # El amarillo solo dentro de la banda azul: nunca toca el blanco.
        amarillos = [td for td in arbol.iter('td') if '#fed00f' in estilo(td)]
        self.assertEqual(len(amarillos), 1)
        self.assertTrue(any('#1340b1' in estilo(padre) for padre in amarillos[0].iterancestors('td')))
        (boton,) = [a for a in arbol.iter('a') if 'WhatsApp' in a.text_content()]
        self.assertEqual(boton.text_content().strip(), 'Escríbenos por WhatsApp')
        self.assertTrue(boton.get('href').startswith('https://wa.me/50760261919?text='))
        self.assertIn(campana.marca, boton.get('href').replace('%20', ' ').replace('%2D', '-'))
        (baja,) = arbol.xpath("//a[contains(@class, 'o_camila_baja')]")
        self.assertEqual(baja.get('href'), '{{{RESEND_UNSUBSCRIBE_URL}}}')
        (baja_previa,) = lxml_html.fromstring(campana.html).xpath("//a[contains(@class, 'o_camila_baja')]")
        self.assertEqual(baja_previa.get('href'), '#', 'La vista previa no lleva el enlace de Resend')
        fotos = [img.get('src') for img in arbol.iter('img')][1:]
        self.assertEqual(len(fotos), R.PRODUCTOS_POR_CAMPANA)
        for src in fotos:
            self.assertRegex(src, r'^https://tienda\.example\.com/dcasa/img/product\.template/\d+/image_1920/1024\.jpg'
                                  r'\?v=[0-9a-f]{12}$')
        texto = arbol.text_content()
        for linea in campana.linea_ids:
            self.assertIn(linea.precio_texto, texto)
            self.assertRegex(linea.precio_texto, r'^\$\d{3}\.\d{2}$')
        self.assertIn('Frente al Parque de Prueba, La Chorrera', texto)
        self.assertIn('WhatsApp +507 6026-1919', texto)
        self.assertNotIn('Camila', texto, 'El cliente recibe el correo de D\'CASA, nunca de «Camila»')

    def test_la_foto_publica_la_sirve_la_tienda(self):
        datos = self.armar()
        campana = self.env['dcasa.camila.campana'].browse(datos['campana']['id'])
        ruta = campana.linea_ids[0].imagen.removeprefix('https://tienda.example.com')
        self.assertTrue(ruta.startswith('/dcasa/img/'))

    def test_un_solo_borrador_abierto_y_volver_a_armar_lo_reemplaza(self):
        primero = self.armar()['campana']['id']
        segundo = self.armar()['campana']['id']
        self.assertEqual(primero, segundo)
        self.assertEqual(self.env['dcasa.camila.campana'].search_count([('estado', 'in', ('borrador', 'aprobada'))]),
                         1)

    def test_editar_pasa_por_la_revision_y_los_precios_los_pone_odoo(self):
        datos = self.armar()
        campana = datos['campana']
        lineas = [{'producto_id': linea['producto_id'], 'texto': linea['texto']} for linea in campana['lineas']]
        with self.assertRaisesRegex(UserError, 'Sin cifras ni precios'):
            self.Camila.with_user(self.marketing).guardar(campana['id'], {'asunto': 'Sofás desde $99'})
        agotado = self.producto('ZZCM AGOTADO DOS', stock=0)
        with self.assertRaisesRegex(UserError, 'no se puede ofrecer'):
            self.Camila.with_user(self.marketing).guardar(
                campana['id'], {'lineas': lineas + [{'producto_id': agotado.id, 'texto': 'Bonito.'}]})
        nuevo = self.producto('ZZCM SILLÓN NUEVO', precio=250.0)
        datos = self.Camila.with_user(self.marketing).guardar(campana['id'], {
            'asunto': 'Tu sala te espera', 'lineas': [{'producto_id': nuevo.id, 'texto': 'Cómodo y firme.'}]})
        (linea,) = datos['campana']['lineas']
        self.assertEqual((linea['nombre'], linea['precio'], linea['grupo']),
                         (nuevo._dcasa_nombre_cliente(), '$250.00', 'elegido'))
        self.assertEqual(datos['campana']['asunto'], 'Tu sala te espera')
        self.assertIn('Tu sala te espera', datos['campana']['html'])

    def test_buscar_productos_solo_trae_lo_que_se_puede_ofrecer(self):
        self.producto('ZZCM MESA AGOTADA', stock=0)
        mesa = self.producto('ZZCM MESA LISTA', precio=80.0)
        encontrados = self.Camila.with_user(self.marketing).buscar_productos('ZZCM MESA')
        self.assertEqual([p['id'] for p in encontrados], [mesa.id])
        self.assertEqual(encontrados[0]['precio'], '$80.00')

    def test_solo_el_equipo_de_marketing(self):
        for metodo, argumentos in (('panel', []), ('armar', []), ('buscar_productos', ['x']),
                                   ('guardar', [1, {}]), ('enviar', [1, '']), ('enviar_prueba', [1]),
                                   ('descartar', [1]), ('actualizar_resultados', [1])):
            with self.subTest(metodo), self.assertRaises(AccessError):
                getattr(self.Camila.with_user(self.vendedora), metodo)(*argumentos)
        self.assertTrue(self.Camila.with_user(self.gerencia).panel())
        self.assertFalse(self.Camila.with_user(self.marketing).panel()['ve_dinero'], 'El rol Marketing no ve dinero')
        self.assertTrue(self.Camila.with_user(self.gerencia).panel()['ve_dinero'])
        with self.assertRaises(AccessError):
            self.env['dcasa.camila.campana'].with_user(self.marketing).create({'name': 'A mano'})


@tagged('post_install', '-at_install')
class TestCron(CamilaComun):

    def test_prepara_un_borrador_cada_15_dias_y_nunca_envia(self):
        self.con_clave()
        self.permiso(self.ana)
        self.assertTrue(self.Camila._cron_preparar())
        campana = self.Camila._abierta()
        self.assertTrue(campana.automatica)
        self.assertEqual(campana.estado, 'borrador')
        self.assertFalse(self.resend.llamadas, 'El cron nunca envía ni habla con Resend')
        self.assertFalse(self.Camila._cron_preparar(), 'Ya hay uno abierto')
        campana.sudo().write({'estado': 'enviada', 'enviada_en': fields.Datetime.now() - timedelta(days=5)})
        self.assertFalse(self.Camila._cron_preparar(), 'No pasaron 15 días')
        campana.sudo().write({'enviada_en': fields.Datetime.now() - timedelta(days=16)})
        self.assertTrue(self.Camila._cron_preparar())

    def test_la_sincronizacion_de_cada_hora_solo_en_produccion_y_con_clave(self):
        self.permiso(self.ana)
        self.assertFalse(self.Camila._cron_sincronizar(), 'Sin clave no habla con Resend')
        self.con_clave()
        with patch.dict('os.environ', {'DCASA_ENTORNO': 'staging'}):
            self.assertFalse(self.Camila._cron_sincronizar())
        self.assertFalse(self.resend.llamadas, 'Staging nunca habla con Resend')
        self.assertTrue(self.Camila._cron_sincronizar())
        segmento = self.env['ir.config_parameter'].sudo().get_param('dcasa_camila.segmento_id')
        self.assertEqual(self.resend.en_segmento(segmento), {'ana.zzcm@example.com': False},
                         'Solo el correo de quien dijo que sí')


@tagged('post_install', '-at_install')
class TestEnviar(CamilaComun):

    def preparar(self):
        self.con_clave()
        self.permiso(self.ana, self.beto)
        return self.armar()['campana']

    def enviar(self, campana, usuario=None):
        return self.Camila.with_user(usuario or self.marketing).enviar(campana['id'], campana['huella'])

    def test_envia_al_segmento_igual_a_odoo(self):
        campana = self.preparar()
        segmento = 'seg-viejo'
        self.resend.segmentos[segmento] = "D'CASA: clientes con permiso (Odoo)"
        self.env['ir.config_parameter'].sudo().set_param('dcasa_camila.segmento_id', segmento)
        # Lo que había en Resend: Carla se dio de baja con el enlace; un correo que ya no tiene permiso en Odoo.
        self.permiso(self.carla)
        self.resend.contacto('carla.zzcm@example.com', suscrito=False, segmentos=[segmento])
        self.resend.contacto('viejo.zzcm@example.com', segmentos=[segmento])
        resultado = self.enviar(campana)
        self.assertTrue(resultado['ok'], resultado)
        self.assertEqual(resultado['mensaje'], 'Listo: la campaña salió a 2 clientes.')
        self.assertEqual(self.carla.dcasa_promos_estado, 'baja', 'La baja de Resend volvió a la ficha')
        self.assertEqual(self.carla.dcasa_promos_baja_origen, 'correo')
        (broadcast,) = self.resend.broadcasts.values()
        self.assertEqual(broadcast['enviado_a'], ['ana.zzcm@example.com', 'beto.zzcm@example.com'])
        self.assertEqual(broadcast['segment_id'], segmento)
        self.assertEqual(broadcast['from'], '"D\'CASA Panamá" <ventas@dcasapty.com>')
        self.assertEqual(broadcast['reply_to'], 'info@dcasapty.com')
        self.assertIn('{{{RESEND_UNSUBSCRIBE_URL}}}', broadcast['html'])
        registro = self.env['dcasa.camila.campana'].browse(campana['id'])
        self.assertEqual((registro.estado, registro.destinatarios, registro.aprobada_por),
                         ('enviada', 2, self.marketing))
        self.assertEqual(self.enviar(campana)['ya_estaba'], True, 'Un doble clic no la manda dos veces')
        self.assertEqual(len(self.resend.broadcasts), 1)

    def test_la_baja_de_odoo_sube_a_resend(self):
        campana = self.preparar()
        self.enviar(campana)
        segmento = self.env['ir.config_parameter'].sudo().get_param('dcasa_camila.segmento_id')
        self.beto.with_user(self.vendedora).action_dcasa_promos_baja()
        self.Camila._sincronizar()
        self.assertTrue(self.resend.contactos['beto.zzcm@example.com']['unsubscribed'])
        self.assertNotIn('beto.zzcm@example.com', self.resend.en_segmento(segmento))

    def test_staging_nunca_envia(self):
        campana = self.preparar()
        with patch.dict('os.environ', {'DCASA_ENTORNO': 'staging'}):
            with self.assertRaisesRegex(UserError, 'En staging nunca salen campañas'):
                self.enviar(campana)
        self.assertFalse(self.resend.llamadas)

    def test_sin_clave_lo_dice_en_palabras_sencillas(self):
        self.permiso(self.ana)
        campana = self.armar()['campana']
        panel = self.Camila.with_user(self.marketing).panel()
        self.assertTrue(any('Todavía no está la clave de campañas de Resend' in b for b in panel['bloqueos']))
        with self.assertRaisesRegex(UserError, 'clave de campañas'):
            self.enviar(campana)
        self.assertFalse(self.resend.llamadas)

    def test_una_cada_15_dias(self):
        campana = self.preparar()
        self.enviar(campana)
        otra = self.armar()['campana']
        with self.assertRaisesRegex(UserError, 'la próxima puede salir desde el'):
            self.enviar(otra)
        self.env['dcasa.camila.campana'].browse(campana['id']).sudo().write(
            {'enviada_en': fields.Datetime.now() - timedelta(days=15)})
        self.assertTrue(self.enviar(self.Camila.with_user(self.marketing).panel()['campana'])['ok'])

    def test_sin_nadie_con_permiso_no_sale(self):
        self.con_clave()
        campana = self.armar()['campana']
        with self.assertRaisesRegex(UserError, 'ningún cliente dijo que sí'):
            self.enviar(campana)

    def test_si_cambio_un_precio_se_vuelve_a_mostrar(self):
        campana = self.preparar()
        self.productos.write({'list_price': 999.0})
        resultado = self.enviar(campana)
        self.assertFalse(resultado['ok'])
        self.assertTrue(resultado['cambio'])
        self.assertFalse(self.resend.broadcasts, 'No sale lo que la persona no vio')
        nueva = resultado['panel']['campana']
        self.assertEqual({linea['precio'] for linea in nueva['lineas']}, {'$999.00'})
        self.assertTrue(self.enviar(nueva)['ok'])

    def test_un_producto_agotado_sale_antes_de_enviar(self):
        campana = self.preparar()
        agotado = self.env['product.template'].browse(campana['lineas'][0]['producto_id'])
        self.env['stock.quant']._update_available_quantity(agotado.product_variant_id, self.bodega.lot_stock_id, -3)
        resultado = self.enviar(campana)
        self.assertTrue(resultado['cambio'])
        self.assertIn(agotado._dcasa_nombre_cliente(), resultado['mensaje'])
        self.assertNotIn(agotado.id, [linea['producto_id'] for linea in resultado['panel']['campana']['lineas']])

    def test_si_resend_falla_no_sale_y_se_puede_reintentar(self):
        campana = self.preparar()
        self.resend.fallar.append(('POST', r'^/broadcasts$', 500, 'Internal error'))
        resultado = self.enviar(campana)
        self.assertFalse(resultado['ok'])
        self.assertIn('Resend respondió 500', resultado['mensaje'])
        registro = self.env['dcasa.camila.campana'].browse(campana['id'])
        self.assertEqual(registro.estado, 'borrador', 'Nada quedó en Resend: vuelve a borrador')
        self.resend.fallar.clear()
        self.resend.fallar.append(('POST', r'/send$', 503, 'Unavailable'))
        resultado = self.enviar(resultado['panel']['campana'])
        self.assertFalse(resultado['ok'])
        self.assertEqual(registro.estado, 'aprobada', 'Ya está en Resend: se reintenta el envío, no se edita')
        self.resend.fallar.clear()
        resultado = self.enviar(resultado['panel']['campana'])
        self.assertTrue(resultado['ok'], resultado)
        self.assertEqual(len(self.resend.broadcasts), 1, 'Al reintentar no crea otra campaña en Resend')

    def test_la_prueba_va_solo_al_correo_de_quien_aprueba(self):
        campana = self.armar()['campana']
        with self.correo_transaccional() as post:
            resultado = self.Camila.with_user(self.marketing).enviar_prueba(campana['id'])
        self.assertIn('marketing.zzcm@example.com', resultado['mensaje'])
        datos = post.call_args.kwargs['json']
        self.assertEqual(datos['to'], ['marketing.zzcm@example.com'])
        self.assertTrue(datos['subject'].startswith('[Prueba] '))
        self.assertIn('Prueba:', datos['html'])
        self.assertNotIn('RESEND_UNSUBSCRIBE_URL', datos['html'])
        self.assertFalse(self.resend.llamadas, 'La prueba no toca la lista de clientes ni las campañas')
        # Si su correo no fuera del equipo, la política de siempre no la deja salir.
        with self.correo_transaccional() as post, patch(
                'odoo.addons.dcasa_correo.models.correo.DcasaCorreo._correos_internos', return_value=[]):
            with self.assertRaisesRegex(UserError, 'No salió la prueba'):
                self.Camila.with_user(self.marketing).enviar_prueba(campana['id'])
        post.assert_not_called()

    def test_descartar(self):
        campana = self.armar()['campana']
        datos = self.Camila.with_user(self.marketing).descartar(campana['id'])
        self.assertIsNone(datos['campana'])
        self.assertEqual(self.env['dcasa.camila.campana'].browse(campana['id']).estado, 'cancelada')
        with self.assertRaises(UserError):
            self.Camila.with_user(self.marketing).guardar(campana['id'], {'asunto': 'Hola'})
        otra = self.armar()['campana']
        self.env['dcasa.camila.campana'].browse(otra['id']).sudo().write(
            {'estado': 'aprobada', 'enviando_desde': fields.Datetime.now()})
        with self.assertRaisesRegex(UserError, 'se está enviando'):
            self.Camila.with_user(self.marketing).descartar(otra['id'])

    def test_la_ia_no_ve_datos_de_clientes(self):
        self.permiso(self.ana)
        self.guion_ia()
        self.armar()
        enviado = json.dumps(P.LLAMADAS, ensure_ascii=False)
        self.assertNotIn('ana.zzcm@example.com', enviado)
        self.assertNotIn('Ana Zzcm', enviado)
