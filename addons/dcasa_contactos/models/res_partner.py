"""Una ficha por persona: celular, correo y RUC o cédula no se repiten entre fichas.

* Solo cuentan las *fichas*: contactos sin padre, que no son un usuario, ni un empleado, ni la empresa propia. Así
  las direcciones de entrega, las cuentas de acceso y las empresas del grupo no chocan con el cliente que es la misma
  persona.
* Lo ya guardado no se toca: se revisa al crear y, al editar, solo lo que CAMBIÓ. Lo viejo repetido se limpia con
  «Socios › Posibles duplicados».
* Quien ve el aviso es de la casa: dice de quién es el dato. Quien viene del sitio o del chat no ve nombres ajenos.
* ``with_context(dcasa_sin_duplicados=True)`` salta la revisión (lo usan la fusión de contactos y la creación de
  usuarios, empleados y empresas, cuyos contactos todavía no tienen su vínculo).

Celular y correo bien escritos y obligatorios (pedido de la dueña, 2026-10-16): ver ``contacto.py``.
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from . import claves

SIN_DUPLICADOS = 'dcasa_sin_duplicados'
SIN_EXIGIR_CONTACTO = 'dcasa_sin_exigir_contacto'
CAMPOS_QUE_IDENTIFICAN = frozenset({'phone', 'email', 'vat', 'dcasa_celular', 'parent_id'})
DATOS = {'celular': 'celular', 'correo': 'correo', 'ruc': 'RUC o cédula'}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dcasa_telefono_llave = fields.Char(
        'Teléfono (llave)', compute='_compute_dcasa_telefono_llave', store=True, index='btree_not_null',
        help="«pa:60261919» (Panamá, con o sin +507) o «intl:13055551234» (otro país): sirve para encontrar a la "
             "persona y para no repetirla.")
    dcasa_vat_llave = fields.Char(
        'RUC o cédula (llave)', compute='_compute_dcasa_vat_llave', store=True, index='btree_not_null',
        help='El RUC o la cédula sin diferencias de espacios, puntos o mayúsculas.')

    @api.depends('phone')
    def _compute_dcasa_telefono_llave(self):
        for partner in self:
            partner.dcasa_telefono_llave = claves.llave_telefono(partner.phone)

    @api.depends('vat')
    def _compute_dcasa_vat_llave(self):
        for partner in self:
            partner.dcasa_vat_llave = claves.llave_vat(partner.vat)

    # ------------------------------------------------------------------
    # Qué es una ficha y cuáles son sus llaves
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_dominio_fichas(self):
        propias = self.env['res.company'].sudo().search([]).partner_id.ids
        return [('parent_id', '=', False), ('user_ids', '=', False), ('employee_ids', '=', False),
                ('id', 'not in', propias)]

    def _dcasa_es_ficha(self):
        self.ensure_one()
        return bool(self.sudo().with_context(active_test=False).search_count(
            [('id', '=', self.id)] + self._dcasa_dominio_fichas()))

    def _dcasa_claves(self):
        """``{'celular': {...}, 'correo': {...}, 'ruc': {...}}`` con las llaves de esta ficha."""
        self.ensure_one()
        telefonos = {self.dcasa_telefono_llave} if self.dcasa_telefono_llave else set()
        if self.dcasa_celular:
            telefonos.add(f'pa:{self.dcasa_celular}')
        return {
            'celular': telefonos,
            'correo': {self.email_normalized} if self.email_normalized else set(),
            'ruc': {self.dcasa_vat_llave} if self.dcasa_vat_llave else set(),
        }

    @api.model
    def _dcasa_dominio_de_la_llave(self, etiqueta, clave):
        if etiqueta == 'celular':
            if clave.startswith('pa:'):  # el celular de Socios también es un teléfono de la ficha
                return ['|', ('dcasa_telefono_llave', '=', clave), ('dcasa_celular', '=', clave[3:])]
            return [('dcasa_telefono_llave', '=', clave)]
        if etiqueta == 'correo':
            return [('email_normalized', '=', clave)]
        return [('dcasa_vat_llave', '=', clave)]

    def _dcasa_otra_ficha(self, etiqueta, clave):
        """La OTRA ficha que ya tiene esa llave (archivadas incluidas), o vacío."""
        self.ensure_one()
        dominio = (self._dcasa_dominio_fichas() + [('id', '!=', self.id)]
                   + self._dcasa_dominio_de_la_llave(etiqueta, clave))
        return self.sudo().with_context(active_test=False).search(dominio, limit=1)

    @api.model
    def _dcasa_buscar_ficha(self, celular=None, correo=None, ruc=None):
        """La ficha de esa persona por su celular, correo o RUC (en ese orden), o vacío. Nunca crea.

        Para quien necesita ENCONTRAR antes de crear (el chat, el sitio, los asistentes)."""
        Partner = self.sudo().with_context(active_test=False)
        for etiqueta, clave in (('celular', claves.llave_telefono(celular)), ('correo', claves.llave_correo(correo)),
                                ('ruc', claves.llave_vat(ruc))):
            if clave:
                ficha = Partner.search(self._dcasa_dominio_fichas() + self._dcasa_dominio_de_la_llave(etiqueta, clave),
                                       order='id', limit=1)
                if ficha:
                    return ficha
        return Partner.browse()

    @api.model
    def _dcasa_valores_de_direccion(self, valores, address_type):
        """Valores para crear la dirección que escribe un visitante en la tienda.

        Si el celular, el correo o el RUC ya son de una ficha, la dirección nueva cuelga de ELLA (dirección de entrega
        o de facturación): la compra suma en la misma ficha y no se crea otra persona. No se toca ningún dato de la
        ficha. Si no hay ficha, se devuelve lo mismo.
        """
        ficha = self._dcasa_buscar_ficha(celular=valores.get('phone'), correo=valores.get('email'),
                                         ruc=valores.get('vat'))
        if not ficha:
            return valores
        return {**valores, 'parent_id': ficha.id, 'type': 'delivery' if address_type == 'delivery' else 'invoice'}

    # ------------------------------------------------------------------
    # El candado
    # ------------------------------------------------------------------

    def _dcasa_mensaje_duplicado(self, etiqueta, clave, otra):
        dato = DATOS[etiqueta]
        if self.env.user.has_group('base.group_user'):
            valor = claves.telefono_legible(clave) if etiqueta == 'celular' else clave
            return self.env._(
                'El %(dato)s %(valor)s ya es de «%(nombre)s». Usa esa ficha en vez de crear otra: un %(dato)s, una '
                'persona.', dato=dato, valor=valor, nombre=otra.display_name)
        return self.env._(
            'Ese %(dato)s ya está registrado. Si es tuyo, entra con tu cuenta; si no puedes, escríbenos por WhatsApp y '
            'lo resolvemos.', dato=dato)

    def _dcasa_revisar_duplicados(self, antes):
        """Falla si una llave NUEVA de la ficha ya es de otra. ``antes``: las que ya tenía (vacío al crear)."""
        for partner in self:
            if not partner._dcasa_es_ficha():
                continue
            previas = antes.get(partner.id, {})
            for etiqueta, llaves in partner._dcasa_claves().items():
                for clave in sorted(llaves - previas.get(etiqueta, set())):
                    otra = partner._dcasa_otra_ficha(etiqueta, clave)
                    if otra:
                        raise ValidationError(partner._dcasa_mensaje_duplicado(etiqueta, clave, otra))

    @api.model_create_multi
    def create(self, vals_list):
        self._dcasa_revisar_contacto_al_crear(vals_list)
        partners = super().create(vals_list)
        if not self.env.context.get(SIN_DUPLICADOS):
            partners._dcasa_revisar_duplicados({})
        return partners

    def write(self, vals):
        vals = self._dcasa_revisar_contacto_al_editar(vals)
        if self.env.context.get(SIN_DUPLICADOS) or not CAMPOS_QUE_IDENTIFICAN.intersection(vals):
            return super().write(vals)
        antes = {partner.id: partner._dcasa_claves() for partner in self}
        resultado = super().write(vals)
        self._dcasa_revisar_duplicados(antes)
        return resultado

    @api.onchange('email', 'vat', 'phone')
    def _onchange_dcasa_duplicado(self):
        """Avisa ANTES de guardar (solo al personal) si el correo o el RUC ya son de otra ficha; si no, si el correo o
        el celular que se acaban de escribir están mal escritos («¿Quisiste decir…?»). Un solo aviso."""
        if not self.env.user.has_group('base.group_user'):
            return None
        propias = self._origin.ids
        for etiqueta, clave in (('correo', claves.llave_correo(self.email)), ('ruc', claves.llave_vat(self.vat))):
            if not clave:
                continue
            otra = self.sudo().with_context(active_test=False).search(
                self._dcasa_dominio_fichas() + [('id', 'not in', propias)]
                + self._dcasa_dominio_de_la_llave(etiqueta, clave), limit=1)
            if otra:
                return {'warning': {
                    'title': self.env._('Ya existe esa persona'),
                    'message': self._dcasa_mensaje_duplicado(etiqueta, clave, otra)}}
        mensaje = self._dcasa_aviso_bien_escrito()
        if mensaje:
            return {'warning': {'title': self.env._('Revisa lo que escribiste'), 'message': mensaje}}
        return None
