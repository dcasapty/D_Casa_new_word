"""Fusionar dos fichas: el consentimiento para Meta pasa ENTERO o no pasa.

Contactos (``dcasa_contactos``) trae a la ficha que queda, campo por campo, los datos de los programas que no se
copian (``copy=False``). Con el consentimiento eso mezclaría dos registros: la fecha y el «dónde» de una ficha con el
«quién lo registró» de la otra (por ejemplo, una aceptación en la web, sin usuario, quedaría «registrada» por la
vendedora que marcó la otra ficha). Aquí los tres datos van juntos: si la ficha que queda ya aceptó, se queda con lo
suyo; si no, recibe el consentimiento más reciente de las que se van, completo. Queda en su historial.
"""
from odoo import models

from .res_partner import CAMPOS_CONSENTIMIENTO


class BasePartnerMergeAutomaticWizard(models.TransientModel):
    _inherit = 'base.partner.merge.automatic.wizard'

    def _dcasa_campos_del_programa(self):
        return [nombre for nombre in super()._dcasa_campos_del_programa() if nombre not in CAMPOS_CONSENTIMIENTO]

    def _dcasa_traer_datos_del_programa(self, src_partners, dst_partner):
        super()._dcasa_traer_datos_del_programa(src_partners, dst_partner)
        destino = dst_partner.sudo()
        if destino.dcasa_meta_consentimiento_fecha:
            return
        aceptaron = src_partners.sudo().filtered('dcasa_meta_consentimiento_fecha')
        origen = aceptaron.sorted('dcasa_meta_consentimiento_fecha', reverse=True)[:1]
        if origen:
            destino.write({
                'dcasa_meta_consentimiento_fecha': origen.dcasa_meta_consentimiento_fecha,
                'dcasa_meta_consentimiento_origen': origen.dcasa_meta_consentimiento_origen,
                'dcasa_meta_consentimiento_usuario_id': origen.dcasa_meta_consentimiento_usuario_id.id,
            })
