"""Fusionar dos fichas: el permiso de novedades más reciente se queda y CUALQUIER baja manda.

Contactos (``dcasa_contactos``) trae a la ficha que queda, campo por campo, los datos que no se copian. Con el
permiso eso mezclaría dos registros (la fecha de una ficha con el «quién» de otra). Aquí:

* el «sí» va entero (fecha, por dónde, quién y a qué correo) desde la ficha con el permiso más reciente, sea la que
  queda o una de las que se van (si el correo de la que queda es otro, el permiso no le sirve: es de aquel correo);
* la baja también va entera, y con una sola ficha dada de baja la que queda queda dada de baja (la baja es final);
* el correo que estaba en Resend no se trae: la sincronización saca del segmento a quien ya no tiene ficha con
  permiso.
"""
from odoo import models

from .permiso import CAMPOS_PERMISO

PERMISO = ('dcasa_promos_fecha', 'dcasa_promos_origen', 'dcasa_promos_usuario_id', 'dcasa_promos_correo',
           'dcasa_promos_referencia')
# Etapa 1b: el «no» más reciente y la última vez que se le preguntó también pasan (no se le pregunta otra vez).
NO = ('dcasa_promos_no_fecha',)
PREGUNTA = ('dcasa_promos_pregunta_fecha',)
BAJA = ('dcasa_promos_baja_fecha', 'dcasa_promos_baja_origen', 'dcasa_promos_baja_usuario_id')


class BasePartnerMergeAutomaticWizard(models.TransientModel):
    _inherit = 'base.partner.merge.automatic.wizard'

    def _dcasa_campos_del_programa(self):
        return [nombre for nombre in super()._dcasa_campos_del_programa() if nombre not in CAMPOS_PERMISO]

    def _dcasa_traer_datos_del_programa(self, src_partners, dst_partner):
        super()._dcasa_traer_datos_del_programa(src_partners, dst_partner)
        destino = dst_partner.sudo()
        fichas = (src_partners | dst_partner).sudo()
        valores = {}
        for campos in (PERMISO, BAJA, NO, PREGUNTA):
            fecha = campos[0]
            mas_reciente = fichas.filtered(fecha).sorted(lambda f, c=fecha: (f[c], f.id), reverse=True)[:1]
            if mas_reciente and mas_reciente != destino:
                for campo in campos:
                    valor = mas_reciente[campo]
                    valores[campo] = valor.id if campo.endswith('_id') else valor
        if valores:
            destino.write(valores)
