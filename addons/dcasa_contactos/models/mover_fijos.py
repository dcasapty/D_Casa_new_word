"""Pasar a «Teléfono fijo» los fijos que quedaron guardados en «Celular» (decisión de la dueña, 2026-10-22: «Sí, hazlo
si puedes»). Corre una sola vez, desde la migración 19.0.1.1.0 del módulo; aquí, para poder probarlo.

* Solo fichas de clientes y proveedores: no las de usuarios del sistema, empleados ni empresas propias.
* Solo si el «Celular» es un fijo de Panamá bien escrito (7 números que no empiezan por 0, 1 ni 6, con o sin +507;
  ``bien_escrito.problema_del_fijo``) y el «Teléfono fijo» está vacío. Se guarda limpio («+507 234-5678») y el celular
  queda vacío. Si el fijo ya tiene otro número, no se toca nada.
* **Socios y vendedores del programa no se tocan** (su llave es el celular, regla 5): se cuentan aparte para que la
  dueña decida.
* Rastro: una nota en el historial de cada ficha movida y un resumen con solo números en el registro del servidor.
* Correr otra vez no hace nada: lo movido ya no está en «Celular».
"""
import logging

from markupsafe import Markup

from odoo.addons.dcasa_socios.models import bien_escrito as B

from .res_partner import SIN_DUPLICADOS, SIN_EXIGIR_CONTACTO

_logger = logging.getLogger(__name__)


def _fijo_de_panama(numero):
    """El fijo limpio («+507 234-5678») si ``numero`` es un fijo de Panamá bien escrito; si no, ``None``."""
    if B.problema_del_fijo(numero):
        return None
    limpio = B.fijo_para_guardar(numero)
    return limpio if limpio.startswith(f'+{B.PANAMA} ') else None


def _es_del_programa(partner):
    """¿Es socio o vendedor del programa (o tiene movimientos de puntos)? Su llave es el celular: no se toca."""
    for ficha in partner | partner.commercial_partner_id:
        if (ficha.dcasa_socio_codigo or ficha.dcasa_celular or ficha.dcasa_vendedor_codigo
                or ficha.dcasa_vendedor_estado or ficha.dcasa_movimiento_ids or ficha.dcasa_vend_movimiento_ids):
            return True
    return False


def pasar_fijos_del_celular(env):
    """Mueve los fijos guardados en «Celular» a «Teléfono fijo». Devuelve los conteos (sin datos de personas)."""
    Partner = env['res.partner'].sudo().with_context(
        active_test=False, **{SIN_DUPLICADOS: True, SIN_EXIGIR_CONTACTO: True})
    equipo = Partner._dcasa_contactos_del_equipo()
    conteo = {'movidas': 0, 'del_programa': 0, 'con_fijo': 0, 'de_usuarios': 0}
    for partner in Partner.search([('phone', '!=', False)], order='id'):
        fijo = _fijo_de_panama(partner.phone)
        if not fijo:
            continue
        if partner in equipo or partner.user_ids:
            conteo['de_usuarios'] += 1
        elif _es_del_programa(partner):
            conteo['del_programa'] += 1
        elif partner.dcasa_telefono_fijo:
            conteo['con_fijo'] += 1
        else:
            numero = partner.phone
            partner.write({'phone': False, 'dcasa_telefono_fijo': fijo})
            partner.message_post(
                body=Markup('<p>%s</p>') % env._('Se pasó el número %(numero)s de Celular a Teléfono fijo.',
                                                 numero=numero),
                message_type='notification', subtype_xmlid='mail.mt_note')
            conteo['movidas'] += 1
    _logger.info(
        "D'CASA fijos en «Celular»: %(movidas)s fichas pasaron el número a «Teléfono fijo»; %(del_programa)s de "
        "Socios o vendedores sin tocar (que decida la dueña); %(con_fijo)s con el fijo ya lleno, sin tocar; "
        "%(de_usuarios)s de usuarios o del equipo, sin tocar.", conteo)
    return conteo
