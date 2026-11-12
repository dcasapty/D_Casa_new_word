"""La promoción de envío (Envíos › Promoción de envío; solo Gerencia y los administradores la cambian).

Pedido de la dueña (2026-11-12): Juan dice cuánto cuesta el envío, si el cliente quiere se lo suma a la cotización y
aplica la promoción del mes. «Los precios de envío no cambian. Lo que cambia es el precio de cómo les queda con la
promoción, pero solo por este mes». Por eso la tarifa, la calculadora y Brian siguen dando el precio normal, y la
promoción es una capa aparte, con fechas:

* Nombre, desde y hasta (fechas de Panamá, ambas incluidas), el mínimo de la compra («compras superiores a» = más que
  eso) y si se mide con o sin ITBMS, las provincias (y, si hace falta, distritos) con envío gratis, el abono en el
  resto (en dólares) y si no aplica cuando la compra lleva colchón.
* Una sola promoción vigente a la vez: dos activas con fechas que se cruzan no se pueden guardar.
* El historial (quién cambió qué) queda en la ficha.
* La cuenta la hace el motor (``motor/promocion.py``), nunca el modelo de IA.
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..motor import promocion as motor_promocion
from ..motor.buscador import sin_tildes

ZONA_HORARIA = 'America/Panama'


def _renglones(texto):
    """«Panamá\\nPanamá Oeste» → ['Panamá', 'Panamá Oeste'] (también separado por comas), sin repetir."""
    vistos, salida = set(), []
    for parte in (texto or '').replace(',', '\n').splitlines():
        limpio = ' '.join(parte.split())
        clave = sin_tildes(limpio)
        if limpio and clave not in vistos:
            vistos.add(clave)
            salida.append(limpio)
    return salida


class EnvioPromocion(models.Model):
    _name = 'dcasa.envio.promocion'
    _inherit = ['mail.thread']
    _description = 'Promoción de envío'
    _order = 'desde desc, id desc'

    name = fields.Char('Nombre', required=True, tracking=True,
                       help='Como la conoce el cliente, p. ej. «Envío Gratis Todo Noviembre».')
    desde = fields.Date('Desde', required=True, tracking=True, help='Primer día (hora de Panamá), incluido.')
    hasta = fields.Date('Hasta', required=True, tracking=True, help='Último día (hora de Panamá), incluido.')
    minimo = fields.Float('La compra tiene que pasar de ($)', digits=(10, 2), required=True, tracking=True,
                          help='«Compras superiores a $200» = 200: la compra tiene que ser MAYOR que esto (con $200 '
                               'justos no aplica). Se mide sobre los productos de la cotización, sin contar el envío.')
    mide = fields.Selection(list(motor_promocion.MIDE.items()), string='El mínimo se mide', required=True,
                            default='sin_itbms', tracking=True,
                            help='Sin ITBMS: el subtotal de los productos. Con ITBMS: el subtotal más el 7 %.')
    provincias_gratis = fields.Text(
        'Envío gratis en estas provincias', tracking=True,
        help='Una por renglón, como salen en Envíos › Lugares (columna Provincia): Panamá, Panamá Oeste, Colón…')
    distritos_gratis = fields.Text(
        'Y en estos distritos', tracking=True,
        help='Opcional, uno por renglón: distritos con envío gratis aunque su provincia no lo tenga.')
    abono = fields.Float('Abono en el resto ($)', digits=(10, 2), tracking=True,
                         help='Fuera de las zonas gratis se descuenta esto del envío (nunca queda en negativo: si el '
                              'envío cuesta menos, queda gratis). 0 = en el resto no hay promoción.')
    excluye_colchon = fields.Boolean('No aplica si la compra lleva colchón', default=True, tracking=True)
    active = fields.Boolean('Activa', default=True, tracking=True)
    vigente_hoy = fields.Boolean('Vigente hoy', compute='_compute_vigente_hoy')
    resumen = fields.Text('Así lo dice Juan', compute='_compute_resumen',
                          help='Las condiciones como se las dice Juan a un cliente que todavía no tiene cotización '
                               '(un envío a una zona gratis y otro al resto).')

    # --- Validaciones ----------------------------------------------------------------------------------------------
    @api.constrains('desde', 'hasta', 'minimo', 'abono', 'provincias_gratis', 'distritos_gratis')
    def _revisar_valores(self):
        for promocion in self:
            if promocion.hasta < promocion.desde:
                raise ValidationError(self.env._('«Hasta» no puede ser antes de «Desde».'))
            if promocion.minimo < 0 or promocion.abono < 0:
                raise ValidationError(self.env._('El mínimo y el abono no pueden ser negativos.'))
            if not (_renglones(promocion.provincias_gratis) or _renglones(promocion.distritos_gratis)
                    or promocion.abono > 0):
                raise ValidationError(self.env._('La promoción no da nada: escribe las provincias con envío gratis o '
                                                 'el abono en el resto.'))
            promocion._revisar_zonas()

    def _revisar_zonas(self):
        """Una provincia o un distrito mal escrito («Panamá Oste») haría que la promoción no aplique nunca: se compara
        con los de Envíos › Lugares (sin tildes ni mayúsculas). Si todavía no hay lugares, o al instalar, no se mira."""
        if self.env.context.get('install_mode'):
            return
        self.env.cr.execute("SELECT DISTINCT prov, dist FROM dcasa_envio_lugar WHERE active")
        filas = self.env.cr.fetchall()
        if not filas:
            return
        for campo, posicion, que in (('provincias_gratis', 0, 'la provincia'), ('distritos_gratis', 1, 'el distrito')):
            conocidos = {sin_tildes(' '.join((fila[posicion] or '').split())) for fila in filas}
            for nombre in _renglones(self[campo]):
                if sin_tildes(nombre) not in conocidos:
                    raise ValidationError(self.env._(
                        'No hay lugares en %(que)s «%(nombre)s»: escríbela como sale en Envíos › Lugares.',
                        que=que, nombre=nombre))

    @api.constrains('desde', 'hasta', 'active')
    def _una_sola_vigente(self):
        for promocion in self.filtered('active'):
            otra = self.search([('id', '!=', promocion.id), ('active', '=', True),
                                ('desde', '<=', promocion.hasta), ('hasta', '>=', promocion.desde)], limit=1)
            if otra:
                raise ValidationError(self.env._(
                    'Ya hay una promoción activa en esas fechas («%(otra)s», del %(desde)s al %(hasta)s): solo puede '
                    'haber una a la vez. Cambia las fechas o archiva una de las dos.',
                    otra=otra.name, desde=otra.desde, hasta=otra.hasta))

    # --- Para el motor ---------------------------------------------------------------------------------------------
    @api.model
    def _hoy(self):
        return fields.Date.context_today(self.with_context(tz=ZONA_HORARIA))

    def _como_motor(self):
        self.ensure_one()
        return {
            'nombre': self.name or '', 'desde': self.desde, 'hasta': self.hasta, 'minimo': self.minimo,
            'mide': self.mide, 'provincias_gratis': _renglones(self.provincias_gratis),
            'distritos_gratis': _renglones(self.distritos_gratis), 'abono': self.abono,
            'excluye_colchon': self.excluye_colchon,
        }

    @api.model
    def _vigente(self, fecha=None):
        """La promoción activa en esa fecha de Panamá (hoy si no se dice), o un registro vacío."""
        fecha = fecha or self._hoy()
        return self.sudo().search([('active', '=', True), ('desde', '<=', fecha), ('hasta', '>=', fecha)],
                                  order='desde desc, id desc', limit=1)

    @api.model
    def _aplicar(self, precio_envio, prov, dist, compra=None, fecha=None):
        """La promoción vigente aplicada a un envío (ver ``motor/promocion.aplicar``) y el registro que la dio."""
        fecha = fecha or self._hoy()
        promocion = self._vigente(fecha)
        datos = promocion._como_motor() if promocion else None
        return motor_promocion.aplicar(datos, precio_envio, prov, dist, fecha, compra), promocion

    # --- La ficha ----------------------------------------------------------------------------------------------------
    @api.depends('desde', 'hasta', 'active')
    def _compute_vigente_hoy(self):
        hoy = self._hoy()
        for promocion in self:
            promocion.vigente_hoy = bool(promocion.active and promocion.desde and promocion.hasta
                                         and promocion.desde <= hoy <= promocion.hasta)

    @api.depends('name', 'desde', 'hasta', 'minimo', 'mide', 'provincias_gratis', 'distritos_gratis', 'abono',
                 'excluye_colchon')
    def _compute_resumen(self):
        for promocion in self:
            if not (promocion.desde and promocion.hasta) or promocion.hasta < promocion.desde:
                promocion.resumen = False
                continue
            datos = promocion._como_motor()
            ejemplos = []
            if datos['provincias_gratis'] or datos['distritos_gratis']:
                ejemplos.append(('Ejemplo de un envío de $100 a una zona gratis',
                                 (datos['provincias_gratis'] or [''])[0], (datos['distritos_gratis'] or [''])[0]))
            if promocion.abono > 0:
                ejemplos.append(('Ejemplo de un envío de $100 al resto del país', '', ''))
            renglones = []
            for titulo, prov, dist in ejemplos:
                resultado = motor_promocion.aplicar(datos, 100.0, prov, dist, promocion.desde)
                completa = motor_promocion.con_el_precio_normal(resultado, 'ese lugar')
                if completa:
                    renglones.append(f'{titulo}: {completa}')
            promocion.resumen = '\n'.join(renglones) or False
