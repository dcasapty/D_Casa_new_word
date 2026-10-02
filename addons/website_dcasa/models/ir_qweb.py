"""Imágenes con `srcset`/`sizes` y prioridad de carga desde `t-field` (auditoría ronda 4).

El widget `image` de Odoo solo pinta un `src` (las tarjetas de /shop pedían `image_1024` para
~180 px) y el sitio le pone `loading="lazy"` a toda imagen. Opciones nuevas del widget:

* `dcasa_srcset`: campos de imagen a ofrecer, p. ej. `('image_256', 'image_512', 'image_1024')`;
  el ancho de cada uno sale del nombre (`image_512` → `512w`).
* `dcasa_sizes`: el atributo `sizes` (obligatorio para que el `srcset` con `w` sirva).
* `dcasa_prioridad`: verdadero solo para la imagen LCP → `loading="eager"` y
  `fetchpriority="high"`; el resto queda perezoso.
* `dcasa_webp`: envuelve la `<img>` en `<picture>` con un `<source type="image/webp">` de los
  mismos anchos servidos por `/dcasa/img/...` (models/imagen.py); la `<img>` queda de respaldo.
"""
import re
from collections import OrderedDict

from markupsafe import Markup

from odoo import api, models
from odoo.addons.website_dcasa.models.imagen import ANCHOS

_ANCHO_CAMPO = re.compile(r'^image_(\d+)$')


class IrQwebFieldImage(models.AbstractModel):
    _inherit = 'ir.qweb.field.image'

    @api.model
    def _dcasa_atributos_img(self, record, field_name, options):
        atributos = OrderedDict()
        campos = options.get('dcasa_srcset') or ()
        if campos and not options.get('qweb_img_raw_data'):
            candidatos = []
            for campo in campos:
                ancho = _ANCHO_CAMPO.match(campo)
                if ancho and campo in record._fields:
                    url, _zoom = self._get_src_urls(record, field_name, dict(options, preview_image=campo))
                    candidatos.append(f'{url} {ancho.group(1)}w')
            if candidatos:
                atributos['srcset'] = ', '.join(candidatos)
                atributos['sizes'] = options.get('dcasa_sizes') or '100vw'
        if 'dcasa_prioridad' in options:
            if options['dcasa_prioridad']:
                atributos['loading'] = 'eager'
                atributos['fetchpriority'] = 'high'
            else:
                atributos['loading'] = 'lazy'
            atributos['decoding'] = 'async'
        return atributos

    @api.model
    def record_to_html(self, record, field_name, options):
        atributos = self._dcasa_atributos_img(record, field_name, options)
        if atributos:
            # El widget arma sus atributos y llama a ir.qweb._post_processing_att: los nuestros
            # entran ahí, antes de que el sitio ponga su loading="lazy" por defecto.
            img = super(IrQwebFieldImage, self.with_context(dcasa_img_atts=atributos)).record_to_html(
                record, field_name, options)
        else:
            img = super().record_to_html(record, field_name, options)
        return self._dcasa_picture_webp(record, options, img, atributos.get('sizes'))

    @api.model
    def _dcasa_picture_webp(self, record, options, img, sizes):
        if not (img and options.get('dcasa_webp') and not options.get('qweb_img_raw_data')):
            return img
        pedidos = [int(m.group(1)) for c in options.get('dcasa_srcset') or () if (m := _ANCHO_CAMPO.match(c))]
        anchos = [ancho for ancho in pedidos if ancho in ANCHOS]
        srcset = self.env['website']._dcasa_img_srcset(record, anchos or (512,))
        if not srcset:
            return img
        fuente = Markup('<source type="image/webp" srcset="%s"%s/>') % (
            srcset, Markup(' sizes="%s"') % sizes if sizes else '')
        return Markup('<picture>%s%s</picture>') % (fuente, img)


class IrQweb(models.AbstractModel):
    _inherit = 'ir.qweb'

    def _post_processing_att(self, tagName, atts):
        extra = self.env.context.get('dcasa_img_atts')
        if extra and tagName == 'img':
            atts = OrderedDict(atts)
            atts.update(extra)
        return super()._post_processing_att(tagName, atts)
