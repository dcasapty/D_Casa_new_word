import json
import re

from odoo import models

RUTA_POSES = '/dcasa_brian_tienda/static/src/img/poses/'
# Donde la burbuja no sale: el pago (taparía «Confirmar»), las pantallas de Odoo y el acceso.
# Sin burbuja de Brian (vuelve la de WhatsApp, o ninguna): el pago, el panel, el portal de Odoo y Mi cuenta (su barra
# de secciones va fija abajo en el celular y esconde la flotante de WhatsApp: la de Brian la taparía).
RUTAS_SIN_BURBUJA = ('/shop/checkout', '/shop/address', '/shop/payment', '/shop/confirm', '/shop/extra_info',
                     '/shop/confirmation', '/payment/status', '/web', '/odoo', '/my', '/mi-cuenta', '/brian',
                     '/envios/choferes')
# El número del WhatsApp de ventas (con el 507): la burbuja arma ahí su enlace (api.whatsapp.com/send).
RE_NUMERO = re.compile(r'^\d{8,15}$')


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
        clave pública de Turnstile si el sitio lo tiene; y si el robot duerme de noche (al cambiarlo se rehacen las
        páginas guardadas, como con el interruptor). Nada de la sesión."""
        self.ensure_one()
        numero = self._dcasa_whatsapp_numero()
        horario = self.env['dcasa.juan.ajustes'].sudo().obtener().horario()
        return {
            'whatsapp': numero if RE_NUMERO.match(numero) else '',
            'horario': json.dumps(horario.como_json(), separators=(',', ':')),
            'poses': RUTA_POSES,
            'turnstile': self.env['dcasa.brian.tienda'].sudo()._turnstile_clave_publica(),
            'dormir': '1' if self.env['dcasa.brian.tienda'].sudo()._dormir_de_noche() else '0',
        }
