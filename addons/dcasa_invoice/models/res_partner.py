from odoo import models

from . import formato


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _dcasa_etiqueta_identificacion(self):
        """«Cédula» (persona, p. ej. 2-723-510) o «RUC» (empresa o con DV)."""
        self.ensure_one()
        ficha = self.commercial_partner_id
        return formato.etiqueta_identificacion(ficha.vat, ficha.l10n_pa_dv, ficha.is_company)

    def _dcasa_lineas_direccion(self):
        """La dirección completa, línea por línea, con «Panamá» con tilde."""
        self.ensure_one()
        ciudad = ', '.join(dict.fromkeys(p for p in (self.city, self.state_id.name) if p))
        pais = ''
        if self.country_id:
            pais = 'Panamá' if self.country_id.code == 'PA' else self.country_id.name
        return [linea.strip() for linea in (self.street, self.street2, ciudad, pais) if linea and linea.strip()]

    def _dcasa_telefono_fmt(self):
        self.ensure_one()
        return formato.telefono_fmt(self.phone)

    def _dcasa_telefonos(self):
        """Teléfono y celular, con guion y sin repetir."""
        self.ensure_one()
        numeros = []
        for campo in ('phone', 'mobile'):
            if campo in self._fields and self[campo]:
                numero = formato.telefono_fmt(self[campo])
                if numero and numero not in numeros:
                    numeros.append(numero)
        return ' · '.join(numeros)
