from markupsafe import Markup

from odoo import models

from . import formato


class ResCompany(models.Model):
    _inherit = 'res.company'

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
