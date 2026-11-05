"""Los mensajes que Sofía propone, escritos con la voz de D'CASA y editables por Gerencia.

Sofía no inventa nada: arma cada mensaje con una de estas plantillas y los datos que Odoo ya sabe (el nombre de pila si
la ficha trae uno de verdad, lo que le interesó, el número de su cotización y hasta cuándo vale). No llevan precios ni
cifras del programa Socios: eso lo confirma la vendedora con las reglas vigentes.
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from . import reglas as R

CLAVES = [
    ('seguimiento_cotizacion', 'Seguimiento: tiene una cotización'),
    ('seguimiento_cuando', 'Seguimiento: dijo para cuándo lo quiere'),
    ('seguimiento_interes', 'Seguimiento: le interesó algo'),
    ('cotizacion_por_vencer', 'Su cotización vence'),
    ('pedir_datos', 'Pedir sus datos (mensaje solo)'),
    ('posdata_datos', 'Pedir sus datos (al final de un seguimiento)'),
]
MAX_TEXTO = 1500


class SofiaPlantilla(models.Model):
    _name = 'dcasa.sofia.plantilla'
    _description = 'Mensaje que propone Sofía'
    _order = 'id'
    _rec_name = 'clave'

    clave = fields.Selection(CLAVES, 'Para qué', required=True, readonly=True)
    texto = fields.Text(
        'Mensaje', required=True,
        help='Puedes usar: {nombre} (su nombre de pila, si su ficha lo tiene), {vendedora} (quien lo envía), '
             '{interes} (lo que le interesó), {cotizacion} (número), {vence} (hasta cuándo vale), {para_cuando} '
             '(lo que dijo) y {que_falta} (los datos que faltan). Sin precios ni cifras.')

    _clave_unica = models.Constraint('UNIQUE(clave)', 'Ya hay un mensaje para eso.')

    @api.constrains('texto')
    def _check_texto(self):
        for plantilla in self:
            desconocidas = R.claves_desconocidas(plantilla.texto)
            if desconocidas:
                raise ValidationError(self.env._(
                    'Sofía no sabe llenar %(claves)s. Usa solo: %(validas)s.',
                    claves=', '.join(f'{{{c}}}' for c in desconocidas),
                    validas=', '.join(f'{{{c}}}' for c in R.CLAVES_DE_PLANTILLA)))
            if len(plantilla.texto or '') > MAX_TEXTO:
                raise ValidationError(self.env._('El mensaje es muy largo (máximo %s letras).', MAX_TEXTO))

    @api.model
    def _textos(self):
        """``{clave: texto}`` de todas las plantillas (con sudo: las lee el motor y la pantalla)."""
        return {p.clave: p.texto for p in self.sudo().search([])}
