from markupsafe import Markup

from odoo import fields, models

from . import formato

# (campo, título impreso). El texto lo redacta la dueña; vacío no se imprime.
BLOQUES_LEGALES = [
    ('dcasa_factura_garantia', 'Garantía'),
    ('dcasa_factura_cambios', 'Cambios y devoluciones'),
    ('dcasa_factura_terminos', 'Términos'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    dcasa_factura_garantia = fields.Text(
        string='Garantía (factura)',
        help='Texto corto que se imprime en facturas, cotizaciones y pedidos. Vacío: no se imprime.')
    dcasa_factura_cambios = fields.Text(
        string='Cambios y devoluciones (factura)',
        help='Texto corto que se imprime en facturas, cotizaciones y pedidos. Vacío: no se imprime.')
    dcasa_factura_terminos = fields.Text(
        string='Términos (factura)',
        help='Texto corto que se imprime en facturas, cotizaciones y pedidos. Vacío: no se imprime.')

    def _dcasa_bloques_legales(self):
        """[(título, texto)] de garantía, cambios y términos; solo los que la dueña escribió."""
        self.ensure_one()
        bloques = []
        for campo, titulo in BLOQUES_LEGALES:
            texto = (self[campo] or '').strip()
            if texto:
                bloques.append((titulo, texto))
        return bloques

    def _dcasa_whatsapp(self):
        """El WhatsApp del pie: el configurado en el sitio web si existe; si no, el teléfono de la empresa."""
        self.ensure_one()
        if 'website' in self.env:
            Website = self.env['website'].sudo()
            if 'dcasa_whatsapp_number' in Website._fields:
                website = Website.search([('company_id', '=', self.id)], limit=1) or Website.search([], limit=1)
                if website.dcasa_whatsapp_number:
                    return website.dcasa_whatsapp_number
        return self.phone or ''

    def _dcasa_direccion_corta(self):
        """«Avenida Las Américas, Urbanización Santa Clara, Local 4550 PB-1, La Chorrera» para el pie."""
        self.ensure_one()
        partes = [self.street, self.street2, self.city]
        return ', '.join(parte.strip() for parte in partes if parte and parte.strip())

    def _dcasa_url_publica(self):
        """La dirección del sitio que se imprime en un papel: nunca localhost.

        Por orden: el dominio del sitio web, ``web.base.url`` y la web de la empresa.
        """
        self.ensure_one()
        candidatos = []
        if 'website' in self.env:
            website = self.env['website'].sudo().search([('company_id', '=', self.id)], limit=1)
            candidatos.append(website.domain)
        candidatos += [self.env['ir.config_parameter'].sudo().get_param('web.base.url'), self.website]
        for candidato in candidatos:
            url = formato.url_con_esquema(candidato)
            if url and not formato.url_es_local(url):
                return url
        return ''

    def _dcasa_url_publica_corta(self):
        """'https://dcasapty.com' → 'dcasapty.com' (así se lee mejor en papel)."""
        return self._dcasa_url_publica().split('://', 1)[-1]

    def _dcasa_sin_enlaces_locales(self, html):
        """Cambia en un texto la URL local del servidor por la pública (p. ej. …/terms)."""
        if not html:
            return html
        local = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        publica = self._dcasa_url_publica()
        texto = str(html)
        if local and publica and formato.url_es_local(local) and local in texto:
            texto = texto.replace(local, publica)
        return Markup(texto) if isinstance(html, Markup) else texto
