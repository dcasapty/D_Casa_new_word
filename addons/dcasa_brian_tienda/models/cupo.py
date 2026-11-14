"""Los contadores del tope de pases (``dcasa.brian.tienda._reservar``): una fila por red y por hora. Nunca la red ni la
IP: la llave es una huella HMAC (``red:<huella>``). Solo el servidor escribe aquí; nadie la ve por la interfaz."""
from datetime import timedelta

from odoo import api, fields, models

GUARDAR_DIAS = 2


class DcasaBrianTiendaCupo(models.Model):
    _name = 'dcasa.brian.tienda.cupo'
    _description = 'Brian de la tienda: contadores del tope de pases (sin datos de nadie)'
    _log_access = False

    llave = fields.Char(required=True, readonly=True)
    ventana = fields.Datetime('Hora', required=True, readonly=True, index=True)
    cuenta = fields.Integer(required=True, readonly=True, default=0)

    _llave_unica = models.Constraint('UNIQUE(llave)', 'Una sola fila por llave.')

    @api.model
    def _cron_limpiar(self):
        """Borra los contadores de más de dos días: solo hace falta la hora en curso."""
        self.env.cr.execute('DELETE FROM dcasa_brian_tienda_cupo WHERE ventana < %s',
                            [fields.Datetime.now() - timedelta(days=GUARDAR_DIAS)])
        return True
