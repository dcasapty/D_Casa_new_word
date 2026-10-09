"""«Foto del catálogo» y «Cotización en PDF» de la caja de respuesta (docs/JUAN_PANEL.md).

* **Foto del catálogo**: busca productos con LAS MISMAS reglas de vista pública que las herramientas del asistente
  (solo productos publicados, precio «+ ITBMS», existencias solo como etiqueta ``disponible``/``pocas``/``agotado``,
  nunca el número ni costos). Al elegir uno, manda la foto con un pie armado: nombre, precio + ITBMS, medidas y enlace.
  La foto viaja como cualquier adjunto: el puente la baja con la URL firmada de vida corta (``firma.py``) y el Worker
  la manda como imagen.
* **Cotización en PDF**: la cotización abierta más reciente del cliente (o un borrador con líneas del catálogo, nunca
  confirmado) como documento por el canal.
"""
import base64
import logging
import re
import unicodedata

from odoo import api, fields, models
from odoo.addons.website_dcasa.models.imagen import codificar
from odoo.exceptions import UserError

from . import adjuntos as A
from . import horario as H
from . import publico as P
from .conversacion_panel import _entero
from .mensaje import adjunto_como_dict

_logger = logging.getLogger(__name__)

ANCHO_DE_LA_FOTO = 1024
MAX_LINEAS = 20
MAX_CANTIDAD = 999
MAX_VARIANTES = 10
MAX_GALERIA = 12
ESTADOS_DE_COTIZACION = {'draft': 'Borrador', 'sent': 'Enviada'}
INFORME_DE_COTIZACION = 'sale.action_report_saleorder'


def pie_de_foto(nombre, precio_texto, medidas=None, url=None):
    """El texto que acompaña la foto: nombre, precio + ITBMS, medidas y enlace. Solo lo que hay: no se rellena nada."""
    lineas = [str(nombre or '').strip(), str(precio_texto or '').strip()]
    if (medidas or '').strip():
        lineas.append(f'Medidas: {medidas.strip()}')
    if (url or '').strip():
        lineas.append(url.strip())
    return '\n'.join(linea for linea in lineas if linea)


def nombre_de_foto(nombre, numero=1):
    """«Cama Queen Grey» → «cama-queen-grey-1.jpg» (sin acentos ni símbolos)."""
    limpio = unicodedata.normalize('NFKD', str(nombre or 'producto'))
    limpio = ''.join(c for c in limpio if not unicodedata.combining(c))
    limpio = re.sub(r'[^a-zA-Z0-9]+', '-', limpio).strip('-').lower()[:40] or 'producto'
    return f'{limpio}-{numero}.jpg'


class DcasaConversacionCatalogo(models.Model):
    _inherit = 'dcasa.conversacion'

    # ------------------------------------------------------------------
    # Buscar en el catálogo
    # ------------------------------------------------------------------

    @api.model
    def _vista_publica(self):
        """Las ayudas de vista pública del asistente: publicados, «+ ITBMS» y existencias en etiqueta."""
        return self.env['brian.herramientas']

    @api.model
    def _plantilla_publicada(self, producto_id):
        producto_id = _entero(producto_id, 'producto_id', minimo=1)
        plantilla = self._vista_publica()._j_plantillas_publicadas().filtered(lambda p: p.id == producto_id)
        if not plantilla:
            raise UserError(self.env._('Ese producto ya no está publicado en la tienda.'))
        return plantilla

    @api.model
    def _ficha_de_catalogo(self, plantilla, base, website=None):
        """Un producto como lo pinta la pantalla (sin existencias en número, sin costos)."""
        herramientas = self._vista_publica()
        website = website if website is not None else self.env['website'].sudo().search(
            [], order='sequence, id', limit=1)
        ficha = herramientas._j_ficha_corta(plantilla, base)
        fotos = (1 if ficha['foto'] else 0) + len(plantilla.sudo().product_template_image_ids)
        ficha.update({
            'id': plantilla.id,
            'miniatura': (website._dcasa_img_url(plantilla, 256) if website and ficha['foto'] else None),
            'fotos_total': fotos,
            'variante_id': plantilla.sudo().product_variant_id.id if plantilla.sudo().product_variant_count == 1
            else None,
            'variantes': [] if plantilla.sudo().product_variant_count <= 1 else [{
                'id': v.id,
                'nombre': v.with_context(display_default_code=False).display_name,
                'codigo': v.default_code or '',
                'precio_texto': P.precio_texto(v.lst_price, ficha['mas_itbms']),
                'disponibilidad': herramientas._j_existencias(plantilla, v),
            } for v in plantilla.sudo().product_variant_ids[:MAX_VARIANTES]],
        })
        ficha.pop('combo', None)
        return ficha

    @api.model
    def buscar_catalogo(self, consulta, limite=P.LIMITE_MAXIMO):
        """Busca productos publicados por nombre, código, categoría, tamaño o color: ``{productos, encontrados}``."""
        self._exigir_vendedora()
        consulta = str(consulta or '').strip()[:200]
        if not P.palabras(consulta):
            return {'productos': [], 'encontrados': 0}
        herramientas = self._vista_publica()
        puntuados = []
        for plantilla, nombre, codigo, extra in herramientas._j_candidatos(herramientas._j_plantillas_publicadas()):
            puntos = P.puntuar(consulta, nombre, codigo, extra)
            if puntos:
                puntuados.append((-puntos, nombre, plantilla.id, plantilla))
        puntuados.sort(key=lambda t: t[:3])
        base = herramientas._j_base_url()
        website = self.env['website'].sudo().search([], order='sequence, id', limit=1)
        tope = P.limite_seguro(limite, defecto=P.LIMITE_MAXIMO, maximo=P.LIMITE_MAXIMO)
        return {'productos': [self._ficha_de_catalogo(t[3], base, website) for t in puntuados[:tope]],
                'encontrados': len(puntuados)}

    @api.model
    def fotos_catalogo(self, producto_id):
        """Las fotos de un producto (la principal y la galería): ``{producto, fotos: [{ref, miniatura, grande}]}``."""
        self._exigir_vendedora()
        plantilla = self._plantilla_publicada(producto_id)
        website = self.env['website'].sudo().search([], order='sequence, id', limit=1)
        base = self._vista_publica()._j_base_url()
        ficha = self._ficha_de_catalogo(plantilla, base)
        fotos = []
        if ficha['foto']:
            fotos.append({'ref': 'principal', 'miniatura': website._dcasa_img_url(plantilla, 256),
                          'grande': website._dcasa_img_url(plantilla, 1024)})
        for imagen in plantilla.sudo().product_template_image_ids[:MAX_GALERIA]:
            if imagen.image_1920:
                fotos.append({'ref': f'galeria-{imagen.id}', 'miniatura': website._dcasa_img_url(imagen, 256),
                              'grande': website._dcasa_img_url(imagen, 1024)})
        return {'producto': ficha, 'fotos': fotos}

    # ------------------------------------------------------------------
    # Mandar la foto
    # ------------------------------------------------------------------

    @api.model
    def _bytes_de_la_foto(self, plantilla, ref):
        """Los bytes de la foto ``ref`` (``principal`` o ``galeria-<id>``) ya en JPEG de 1024 px, sin transparencias."""
        plantilla = plantilla.sudo()
        if ref == 'principal':
            origen = plantilla.image_1920
        else:
            coincide = re.fullmatch(r'galeria-(\d+)', ref or '')
            imagen = plantilla.product_template_image_ids.filtered(
                lambda i: coincide and i.id == int(coincide.group(1)))[:1]
            origen = imagen.image_1920
        if not origen:
            raise UserError(self.env._('Esa foto de «%s» ya no existe.', plantilla.name))
        return codificar(base64.b64decode(origen), ANCHO_DE_LA_FOTO, 'jpg')

    @api.model
    def preparar_foto_catalogo(self, conversacion_id, producto_id, fotos=None, texto=None):
        """Deja las fotos del producto listas como adjuntos y arma el pie. Devuelve ``{texto, adjuntos}``.

        ``fotos``: referencias de ``fotos_catalogo`` (por defecto, la principal). Hasta 5 por mensaje.
        """
        conv = self._para_panel(conversacion_id, escritura=True)
        plantilla = self._plantilla_publicada(producto_id)
        fotos = ['principal'] if not fotos else fotos
        if not isinstance(fotos, (list, tuple)) or not all(isinstance(f, str) for f in fotos) \
                or not 0 < len(set(fotos)) <= A.MAX_ADJUNTOS:
            raise UserError(self.env._('Elige de 1 a %s fotos.', A.MAX_ADJUNTOS))
        if texto is not None and not isinstance(texto, str):
            raise UserError(self.env._('El texto del pie tiene que ser texto.'))
        ficha = self._ficha_de_catalogo(plantilla, self._vista_publica()._j_base_url())
        if texto is None:
            texto = pie_de_foto(ficha['nombre'], ficha['precio_texto'], ficha['medidas'], ficha['url'])
        adjuntos = self.env['ir.attachment']
        for numero, ref in enumerate(dict.fromkeys(fotos), start=1):
            adjuntos |= self.env['ir.attachment'].create({
                'name': nombre_de_foto(plantilla.name, numero), 'raw': self._bytes_de_la_foto(plantilla, ref),
                'mimetype': 'image/jpeg', 'res_model': self._name, 'res_id': conv.id, 'public': False})
        return {'texto': texto, 'adjuntos': [adjunto_como_dict(a) for a in adjuntos]}

    @api.model
    def enviar_foto_catalogo(self, conversacion_id, producto_id, fotos=None, texto=None):
        """Manda la foto del producto con su pie por el canal (como cualquier respuesta de una vendedora)."""
        preparado = self.preparar_foto_catalogo(conversacion_id, producto_id, fotos, texto)
        return self.enviar_respuesta(conversacion_id, preparado['texto'], [a['id'] for a in preparado['adjuntos']])

    # ------------------------------------------------------------------
    # Cotización en PDF
    # ------------------------------------------------------------------

    @api.model
    def _cotizaciones_abiertas(self, conv):
        """Cotizaciones sin confirmar del cliente (borrador o enviada), la más reciente primero."""
        partner = conv.partner_id.sudo()
        if not partner:
            return self.env['sale.order']
        return self.env['sale.order'].search([
            ('partner_id', 'child_of', partner.commercial_partner_id.id), ('state', 'in', ('draft', 'sent')),
        ], order='write_date desc, id desc', limit=10)

    @api.model
    def _orden_como_dict(self, orden):
        horario = self.env['dcasa.juan.ajustes'].obtener().horario()
        return {
            'id': orden.id, 'nombre': orden.name, 'estado': orden.state,
            'estado_nombre': ESTADOS_DE_COTIZACION.get(orden.state, orden.state),
            'subtotal': round(orden.amount_untaxed, 2), 'impuestos': round(orden.amount_tax, 2),
            'total': round(orden.amount_total, 2),
            'moneda': orden.currency_id.symbol or '$',
            'fecha': H.a_iso(orden.date_order),
            'fecha_texto': H.texto_fecha_hora(orden.date_order, horario) if orden.date_order else '',
            'valida_hasta': fields.Date.to_string(orden.validity_date) if orden.validity_date else None,
            'lineas': [{
                'id': linea.id, 'producto': linea.product_id.with_context(display_default_code=False).display_name
                or linea.name, 'codigo': linea.product_id.default_code or '', 'cantidad': linea.product_uom_qty,
                'precio_unitario': round(linea.price_unit, 2), 'subtotal': round(linea.price_subtotal, 2),
            } for linea in orden.order_line.filtered(lambda linea: not linea.display_type)],
        }

    @api.model
    def cotizaciones_abiertas(self, conversacion_id):
        """``{cotizaciones: [...]}``: las cotizaciones sin confirmar del cliente; la primera es la más reciente."""
        conv = self._para_panel(conversacion_id)
        if not conv.partner_id:
            return {'cotizaciones': [], 'cliente': False}
        ordenes = self._cotizaciones_abiertas(conv)
        return {'cotizaciones': [self._orden_como_dict(o) for o in ordenes[:5]], 'cliente': True}

    @api.model
    def crear_cotizacion(self, conversacion_id, lineas):
        """Crea una cotización BORRADOR para el cliente con productos del catálogo. Nunca la confirma.

        ``lineas``: ``[{variante_id, cantidad}]`` (productos publicados).
        """
        conv = self._para_panel(conversacion_id, escritura=True)
        if not conv.partner_id:
            raise UserError(self.env._('Esta conversación todavía no tiene un cliente.'))
        if not isinstance(lineas, (list, tuple)) or not 0 < len(lineas) <= MAX_LINEAS:
            raise UserError(self.env._('Elige de 1 a %s productos para la cotización.', MAX_LINEAS))
        publicadas = self._vista_publica()._j_plantillas_publicadas()
        valores = []
        for linea in lineas:
            if not isinstance(linea, dict):
                raise UserError(self.env._('Cada línea lleva el producto y la cantidad.'))
            variante_id = _entero(linea.get('variante_id'), 'variante_id', minimo=1)
            cantidad = _entero(linea.get('cantidad', 1), 'cantidad', minimo=1, maximo=MAX_CANTIDAD)
            variante = self.env['product.product'].sudo().browse(variante_id).exists()
            if not variante or variante.product_tmpl_id not in publicadas:
                raise UserError(self.env._('Alguno de los productos ya no está publicado en la tienda.'))
            valores.append((0, 0, {'product_id': variante.id, 'product_uom_qty': cantidad}))
        orden = self.env['sale.order'].create({
            'partner_id': conv.partner_id.id, 'user_id': self.env.uid,
            'origin': self.env._('Conversación %s', conv.name or conv.id_externo), 'order_line': valores})
        orden.message_post(body=self.env._('Cotización creada por %(quien)s desde la conversación de %(canal)s. '
                                           'Sin confirmar.', quien=self.env.user.name, canal=conv.canal),
                           subtype_xmlid='mail.mt_note')
        conv._aviso(self.env._('%(quien)s creó la cotización borrador %(n)s.', quien=self.env.user.name, n=orden.name))
        return {'cotizacion': self._orden_como_dict(orden)}

    @api.model
    def enviar_cotizacion(self, conversacion_id, orden_id=None, texto=None):
        """Manda la cotización en PDF por el canal. Sin ``orden_id``, la abierta más reciente del cliente."""
        conv = self._para_panel(conversacion_id, escritura=True)
        abiertas = self._cotizaciones_abiertas(conv)
        if orden_id is None:
            orden = abiertas[:1]
        else:
            orden_id = _entero(orden_id, 'orden_id', minimo=1)
            orden = abiertas.filtered(lambda o: o.id == orden_id)
        if not orden:
            raise UserError(self.env._(
                'Este cliente no tiene una cotización abierta. Crea una con productos del catálogo.'))
        if texto is not None and not isinstance(texto, str):
            raise UserError(self.env._('El texto tiene que ser texto.'))
        informe = self.env['ir.actions.report'].with_context(force_report_rendering=True)
        pdf, tipo = informe._render_qweb_pdf(INFORME_DE_COTIZACION, [orden.id])
        if tipo != 'pdf' or not pdf or not pdf.startswith(b'%PDF'):
            raise UserError(self.env._('No pude armar el PDF de la cotización. Ábrela en Odoo y descárgala.'))
        adjunto = self.env['ir.attachment'].create({
            'name': A.nombre_seguro(f'Cotizacion-{orden.name}.pdf'), 'raw': pdf, 'mimetype': 'application/pdf',
            'res_model': self._name, 'res_id': conv.id, 'public': False})
        if texto is None:
            texto = self.env._('Aquí tienes tu cotización %s. Los precios son más ITBMS.', orden.name)
        resultado = self.enviar_respuesta(conv.id, texto, [adjunto.id])
        if orden.state == 'draft':
            orden.action_quotation_sent()
        orden.message_post(body=self.env._('Enviada en PDF por %(quien)s por %(canal)s.', quien=self.env.user.name,
                                           canal=conv.canal), subtype_xmlid='mail.mt_note')
        resultado['cotizacion'] = self._orden_como_dict(orden)
        return resultado
