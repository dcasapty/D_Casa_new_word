"""Los datos del cliente, a la vista y corregibles dentro de la cotización y la factura (pedido de la dueña,
2026-11-04: «se deberían poder modificar estos datos en el momento en que se factura, de forma muy fácil»).

Debajo de «Cliente» salen su nombre, su celular, su teléfono fijo, su correo y su cédula o RUC. Lo que se corrige ahí
se guarda en la ficha del cliente al guardar el documento: son los campos de la ficha (``related``), escritos como
quien edita (sin ``sudo``: queda su nombre en el historial de la ficha) y con las mismas reglas de siempre (bien
escrito, sin repetir el celular, el correo ni la cédula de otra ficha). Mientras se escribe, el aviso de siempre
(«¿Quisiste decir…?», «Ese celular ya es de…») sale antes de guardar.

* En la cotización se corrigen mientras no esté cancelada; en la factura, mientras sea borrador (una factura publicada
  ya salió con sus datos: el cliente se corrige en su ficha).
* Si el cliente del documento es una dirección de otra ficha (una factura a nombre de un contacto de una empresa), se
  corrige ese contacto: el que sale en el documento.
"""
from odoo import api, fields, models
from odoo.addons.dcasa_socios.models import bien_escrito as B

from . import claves
from .res_partner import DATOS


def aviso_de_los_datos(documento):
    """El aviso de lo que se acaba de escribir en los datos del cliente de un documento, o ``None``."""
    documento.ensure_one()
    env = documento.env
    ficha = documento.partner_id._origin
    Partner = env['res.partner']
    # 1. ¿Ya es de otra ficha? (solo si el cliente es una ficha: una dirección no tiene llaves propias)
    if ficha and not ficha.sudo().parent_id:
        propias = ficha.sudo()._dcasa_claves()
        for etiqueta, clave in (('celular', claves.llave_telefono(documento.dcasa_cliente_celular)),
                                ('correo', claves.llave_correo(documento.dcasa_cliente_correo)),
                                ('ruc', claves.llave_vat(documento.dcasa_cliente_cedula))):
            if not clave or clave in propias[etiqueta]:
                continue
            otra = ficha._dcasa_otra_ficha(etiqueta, clave)
            if otra:
                valor = claves.telefono_legible(clave) if etiqueta == 'celular' else clave
                return env._(
                    'El %(dato)s %(valor)s ya es de «%(nombre)s». Si es la misma persona, cambia el Cliente a '
                    '«%(nombre)s» (búscalo por su celular) en vez de escribirlo aquí. Para dejar una sola ficha, '
                    'Gerencia las une en Posibles duplicados.',
                    dato=DATOS[etiqueta], valor=valor, nombre=otra.display_name)
    # 2. ¿Está bien escrito? (solo lo que cambió)
    origen = ficha.sudo()
    correo, celular = documento.dcasa_cliente_correo, documento.dcasa_cliente_celular
    fijo = documento.dcasa_cliente_fijo
    if correo and correo != origen.email:
        codigo, sugerencia = B.problema_del_correo(correo)
        if not codigo and B.correo_limpio(correo) in Partner._dcasa_correos_del_equipo(excepto=ficha):
            codigo, sugerencia = 'equipo', None
        if codigo:
            return B.mensaje_del_correo(env, correo, codigo, sugerencia)
    if celular and celular != origen.phone:
        codigo = B.problema_del_telefono(celular)
        if codigo:
            return B.mensaje_del_telefono(env, celular, codigo)
    if fijo and fijo != origen.dcasa_telefono_fijo:
        codigo = B.problema_del_fijo(fijo)
        if codigo:
            return B.mensaje_del_fijo(env, fijo, codigo)
    return None


def onchange_de_los_datos(documento):
    if not documento.partner_id or not documento.env.user.has_group('base.group_user'):
        return None
    mensaje = aviso_de_los_datos(documento)
    if not mensaje:
        return None
    return {'warning': {'title': documento.env._('Revisa los datos del cliente'), 'message': mensaje}}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_cliente_nombre = fields.Char('Nombre del cliente', related='partner_id.name', readonly=False)
    dcasa_cliente_celular = fields.Char('Celular', related='partner_id.phone', readonly=False)
    dcasa_cliente_fijo = fields.Char('Teléfono fijo', related='partner_id.dcasa_telefono_fijo', readonly=False)
    dcasa_cliente_correo = fields.Char('Correo', related='partner_id.email', readonly=False)
    dcasa_cliente_cedula = fields.Char('Cédula o RUC', related='partner_id.vat', readonly=False)

    @api.onchange('dcasa_cliente_celular', 'dcasa_cliente_fijo', 'dcasa_cliente_correo', 'dcasa_cliente_cedula')
    def _onchange_dcasa_datos_del_cliente(self):
        return onchange_de_los_datos(self)


class AccountMove(models.Model):
    _inherit = 'account.move'

    dcasa_cliente_nombre = fields.Char('Nombre del cliente', related='partner_id.name', readonly=False)
    dcasa_cliente_celular = fields.Char('Celular', related='partner_id.phone', readonly=False)
    dcasa_cliente_fijo = fields.Char('Teléfono fijo', related='partner_id.dcasa_telefono_fijo', readonly=False)
    dcasa_cliente_correo = fields.Char('Correo', related='partner_id.email', readonly=False)
    dcasa_cliente_cedula = fields.Char('Cédula o RUC', related='partner_id.vat', readonly=False)

    @api.onchange('dcasa_cliente_celular', 'dcasa_cliente_fijo', 'dcasa_cliente_correo', 'dcasa_cliente_cedula')
    def _onchange_dcasa_datos_del_cliente(self):
        return onchange_de_los_datos(self)
