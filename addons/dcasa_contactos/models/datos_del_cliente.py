"""Los datos del cliente, a la vista y corregibles dentro de la cotización y la factura (pedido de la dueña,
2026-11-04: «se deberían poder modificar estos datos en el momento en que se factura, de forma muy fácil»).

Debajo de «Cliente» salen su nombre, su celular, su teléfono fijo, su correo y su cédula o RUC. Lo que se corrige ahí
se guarda en la ficha del cliente al guardar el documento:

* **Solo lo que cambió.** Cada dato es un campo calculado con SU PROPIO inverso (no ``related``): el formulario los
  manda al crear un documento o al cambiar de cliente aunque nadie los toque, y un ``related`` volvía a escribir la
  ficha completa cada vez (con datos viejos mal escritos, la cotización no se guardaba). Cada inverso compara su dato
  con la ficha y escribe solo si es distinto (revisión adversarial, 2026-11-04). Un solo cálculo para los cinco no
  sirve: mientras Odoo guarda uno, congela los otros de su mismo cálculo y se leerían vacíos (borraría la ficha).
* Se escribe como quien edita (sin ``sudo``): Odoo anota en el historial de la ficha quién cambió el nombre, el
  correo, el celular o el RUC y qué decía antes. Con las reglas de siempre: bien escrito y sin repetir el celular, el
  correo ni la cédula de otra ficha. Mientras se escribe sale el aviso («¿Quisiste decir…?», «Ese celular ya es de…»).
* **Dónde:** en la cotización mientras no esté cancelada; en la factura, nota o recibo **de cliente** mientras sea
  borrador (una publicada ya salió con sus datos: se corrige en su ficha). Nunca en facturas de proveedor.
* **No se corrigen aquí** los datos de alguien del equipo (usuario o empleado: se corrigen en su usuario) ni la cédula
  de un contacto de una empresa (Odoo la sube a la empresa, y la factura electrónica usa la de la empresa): esos campos
  se ven pero no se escriben.
"""
from odoo import api, fields, models
from odoo.addons.dcasa_socios.models import bien_escrito as B
from odoo.exceptions import UserError

from . import claves
from .res_partner import DATOS

# Campo del documento → campo de la ficha
CAMPOS = (
    ('dcasa_cliente_nombre', 'name'),
    ('dcasa_cliente_celular', 'phone'),
    ('dcasa_cliente_fijo', 'dcasa_telefono_fijo'),
    ('dcasa_cliente_correo', 'email'),
    ('dcasa_cliente_cedula', 'vat'),
)
TIPOS_DE_CLIENTE = ('out_invoice', 'out_refund', 'out_receipt')


def metodos_del_dato(campo_doc, campo_ficha):
    """El cálculo y el inverso de UN dato del cliente (cada dato el suyo: ver arriba)."""
    @api.depends('partner_id', f'partner_id.{campo_ficha}')
    def calcular(self):
        for documento in self:
            documento[campo_doc] = documento.partner_id[campo_ficha] if documento.partner_id else False

    def guardar(self):
        guardar_el_dato(self, campo_doc, campo_ficha)

    return calcular, guardar


def guardar_el_dato(documentos, campo_doc, campo_ficha):
    """Escribe en la ficha ESTE dato, solo si se cambió en el documento."""
    for documento in documentos:
        ficha = documento.partner_id
        if not ficha or not documento._dcasa_se_corrigen_los_datos():
            continue
        if campo_ficha == 'vat' and ficha.parent_id:
            continue  # la cédula de un contacto de una empresa: Odoo la subiría a la empresa
        nuevo = documento[campo_doc]
        nuevo = (nuevo.strip() if isinstance(nuevo, str) else nuevo) or False
        if nuevo == (ficha[campo_ficha] or False):
            continue
        if not documento.dcasa_cliente_corregible:
            raise UserError(documento.env._(
                'Los datos de alguien del equipo se corrigen en su usuario, no en el documento.'))
        ficha.write({campo_ficha: nuevo})


def calcular_si_se_corrigen(documentos):
    """Aparte de los datos: mientras Odoo guarda los datos (el inverso), los campos de su mismo cálculo quedan
    congelados y se leerían vacíos."""
    equipo = documentos.env['res.partner']._dcasa_contactos_del_equipo() if documentos.partner_id else None
    for documento in documentos:
        ficha = documento.partner_id
        documento.dcasa_cliente_corregible = bool(ficha) and ficha._origin not in equipo
        documento.dcasa_cliente_es_contacto = bool(ficha.parent_id)


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
    if not documento.partner_id or not documento.env.user.has_group('base.group_user') \
            or not documento._dcasa_se_corrigen_los_datos():
        return None
    mensaje = aviso_de_los_datos(documento)
    if not mensaje:
        return None
    return {'warning': {'title': documento.env._('Revisa los datos del cliente'), 'message': mensaje}}


_nombre = metodos_del_dato('dcasa_cliente_nombre', 'name')
_celular = metodos_del_dato('dcasa_cliente_celular', 'phone')
_fijo = metodos_del_dato('dcasa_cliente_fijo', 'dcasa_telefono_fijo')
_correo = metodos_del_dato('dcasa_cliente_correo', 'email')
_cedula = metodos_del_dato('dcasa_cliente_cedula', 'vat')
AVISA = ('dcasa_cliente_celular', 'dcasa_cliente_fijo', 'dcasa_cliente_correo', 'dcasa_cliente_cedula')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dcasa_cliente_nombre = fields.Char('Nombre del cliente', compute=_nombre[0], inverse=_nombre[1])
    dcasa_cliente_celular = fields.Char('Celular', compute=_celular[0], inverse=_celular[1])
    dcasa_cliente_fijo = fields.Char('Teléfono fijo', compute=_fijo[0], inverse=_fijo[1])
    dcasa_cliente_correo = fields.Char('Correo', compute=_correo[0], inverse=_correo[1])
    dcasa_cliente_cedula = fields.Char('Cédula o RUC', compute=_cedula[0], inverse=_cedula[1])
    dcasa_cliente_corregible = fields.Boolean(compute='_compute_dcasa_cliente_corregible')
    dcasa_cliente_es_contacto = fields.Boolean(compute='_compute_dcasa_cliente_corregible')

    @api.depends('partner_id', 'partner_id.parent_id')
    def _compute_dcasa_cliente_corregible(self):
        calcular_si_se_corrigen(self)

    def _dcasa_se_corrigen_los_datos(self):
        self.ensure_one()
        return self.state != 'cancel'

    @api.onchange(*AVISA)
    def _onchange_dcasa_datos_del_cliente(self):
        return onchange_de_los_datos(self)


class AccountMove(models.Model):
    _inherit = 'account.move'

    dcasa_cliente_nombre = fields.Char('Nombre del cliente', compute=_nombre[0], inverse=_nombre[1])
    dcasa_cliente_celular = fields.Char('Celular', compute=_celular[0], inverse=_celular[1])
    dcasa_cliente_fijo = fields.Char('Teléfono fijo', compute=_fijo[0], inverse=_fijo[1])
    dcasa_cliente_correo = fields.Char('Correo', compute=_correo[0], inverse=_correo[1])
    dcasa_cliente_cedula = fields.Char('Cédula o RUC', compute=_cedula[0], inverse=_cedula[1])
    dcasa_cliente_corregible = fields.Boolean(compute='_compute_dcasa_cliente_corregible')
    dcasa_cliente_es_contacto = fields.Boolean(compute='_compute_dcasa_cliente_corregible')

    @api.depends('partner_id', 'partner_id.parent_id')
    def _compute_dcasa_cliente_corregible(self):
        calcular_si_se_corrigen(self)

    def _dcasa_se_corrigen_los_datos(self):
        self.ensure_one()
        return self.move_type in TIPOS_DE_CLIENTE and self.state == 'draft'

    @api.onchange(*AVISA)
    def _onchange_dcasa_datos_del_cliente(self):
        return onchange_de_los_datos(self)
