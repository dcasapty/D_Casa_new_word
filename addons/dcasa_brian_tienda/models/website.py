import json
import re

from odoo import models

RUTA_POSES = '/dcasa_brian_tienda/static/src/img/poses/'
# Donde la burbuja no sale: el pago (taparía «Confirmar»), las pantallas de Odoo y el acceso.
RUTAS_SIN_BURBUJA = ('/shop/checkout', '/shop/address', '/shop/payment', '/shop/confirm', '/shop/extra_info',
                     '/shop/confirmation', '/web', '/odoo', '/my/', '/brian', '/envios/choferes')
RE_WA = re.compile(r'^https://wa\.me/(\d{8,15})\?')


class Website(models.Model):
    _inherit = 'website'

    def _dcasa_brian_tienda_activa(self):
        """¿Se dibuja la burbuja de Brian? (Sitio web › Brian de la tienda). Apagada vuelve la de WhatsApp."""
        return self.env['dcasa.brian.tienda']._activo()

    def _dcasa_brian_en_esta_pagina(self, ruta):
        return self._dcasa_brian_tienda_activa() and not str(ruta or '').startswith(RUTAS_SIN_BURBUJA)

    def _dcasa_brian_datos(self):
        """Lo que la página necesita para la burbuja, igual para todo visitante (la página se puede guardar en el
        borde): el WhatsApp del sitio, el horario de Ajustes de Juan (para saber si es de noche sin pedir nada) y la
        clave pública de Turnstile si el sitio lo tiene. Nada de la sesión."""
        self.ensure_one()
        coincide = RE_WA.match(self._dcasa_whatsapp_url('') or '')
        horario = self.env['dcasa.juan.ajustes'].sudo().obtener().horario()
        return {
            'whatsapp': coincide.group(1) if coincide else '',
            'horario': json.dumps(horario.como_json(), separators=(',', ':')),
            'poses': RUTA_POSES,
            'turnstile': self.env['dcasa.brian.tienda'].sudo()._turnstile_clave_publica(),
        }
