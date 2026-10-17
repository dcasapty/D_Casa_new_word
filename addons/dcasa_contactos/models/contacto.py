"""Celular y correo bien escritos y obligatorios (pedido de la dueña, 2026-10-16; casilla del 2026-10-17).

«Debería el vendedor siempre, obligatoriamente, capturar el número de teléfono y correo electrónico, pero bien escrito»:
ahí le llegan al cliente su factura y cómo ver sus puntos. Qué es «bien escrito» lo deciden las funciones puras de
``dcasa_socios.models.bien_escrito``; aquí se decide quién lo exige y cuándo.

* **La puerta.** Solo la pasa quien trabaja en Odoo (usuario interno) sin ``sudo``: la vendedora en el formulario y
  Brian, que corre como ella. No la pasan Juan, la tienda ni Socios (corren con ``sudo``), la fusión de contactos
  (``dcasa_sin_duplicados``), los crons ni el importador (``dcasa_sin_exigir_contacto``).
* **Al escribir** un correo o un celular en una ficha de cliente: si está mal escrito no se guarda (con «¿Quisiste
  decir…?»); si está bien, se guarda limpio (``ana@gmail.com``, ``+507 6026-1919``). El correo de alguien del equipo o
  de la empresa no sirve como correo del cliente. Lo viejo no se toca: solo se revisa lo que cambia.
* **Al crear una persona como cliente** (Ventas › Clientes, «Crear y editar» en la cotización, «Nuevo cliente» del
  Inicio): el celular y el correo son obligatorios, salvo que se marque «Cliente no tiene correo electrónico». La
  creación rápida (escribir el nombre y Enter en un campo) y las empresas no se frenan al crear: las frenan la venta y
  la factura, que es donde importa (así no falla, por ejemplo, crear la empresa de un contacto desde su ficha).
* **Al confirmar una venta y al publicar una factura** (``sale_order.py`` y ``account_move.py``): sin un celular y un
  correo que sirvan, no se puede. «Pagar» nunca se bloquea.
* **«Cliente no tiene correo electrónico»** (decisión de la dueña, 2026-10-17): la única excepción, y solo del correo
  (el celular sigue obligatorio). La marca la vendedora en la ficha o en la cotización; queda en el historial de la
  ficha quién la marcó. Si después se le escribe un correo, se desmarca sola.
* Nada de esto se revisa mientras se escribe: el formulario guarda solo (la nube) y un borrador a medias se guarda
  igual. Lo único que se avisa al salir de un campo es el «¿Quisiste decir…?».
* No aplica a fichas solo de proveedor, ni a las de usuarios, empleados o empresas propias.
"""
from odoo import api, fields, models
from odoo.addons.dcasa_socios.models import bien_escrito as B
from odoo.exceptions import ValidationError

from .res_partner import SIN_DUPLICADOS, SIN_EXIGIR_CONTACTO

# La creación rápida desde un campo (escribir el nombre y Enter): no exige el celular ni el correo al crear.
ALTA_RAPIDA = 'dcasa_alta_rapida'
SIN_CORREO = 'dcasa_sin_correo'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dcasa_sin_correo = fields.Boolean(
        'Cliente no tiene correo electrónico', tracking=True, copy=False,
        help='Márcalo solo si el cliente de verdad no tiene correo: así se puede confirmar su venta y publicar su '
             'factura sin él. El celular sigue siendo obligatorio. Si después le escribes un correo, se desmarca '
             'solo. En el historial de la ficha queda quién lo marcó.')

    # ------------------------------------------------------------------
    # Quién pasa por la puerta
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_exige_contacto(self):
        """¿Se le exige el celular y el correo bien escritos a quien está escribiendo? Solo al equipo, sin sudo."""
        contexto = self.env.context
        return bool(not self.env.su and not contexto.get(SIN_EXIGIR_CONTACTO) and not contexto.get(SIN_DUPLICADOS)
                    and self.env.user._is_internal())

    def _dcasa_sujetas_al_contacto(self):
        """De estas fichas, las que son (o pueden ser) de un cliente: no las solo de proveedor ni las del equipo."""
        if self.env.context.get('res_partner_search_mode') == 'supplier':
            return self.browse()
        equipo = self._dcasa_contactos_del_equipo()
        return self.filtered(lambda p: p not in equipo
                             and not (p.sudo().supplier_rank > 0 and not p.sudo().customer_rank))

    @api.model
    def _dcasa_correos_del_equipo(self, excepto=None):
        """Los correos de los usuarios internos activos y de las empresas propias (sin los de ``excepto``)."""
        usuarios = self.env['res.users'].sudo().search([('share', '=', False)])
        fichas = usuarios.partner_id | self.env['res.company'].sudo().search([]).partner_id
        if excepto:
            fichas -= excepto.sudo()
        return {correo for correo in fichas.mapped('email_normalized') if correo}

    # ------------------------------------------------------------------
    # Al escribir en la ficha
    # ------------------------------------------------------------------

    def _dcasa_limpiar_contacto(self, vals):
        """Revisa el correo y el celular que llegan en ``vals`` y los deja limpios (cambia ``vals``). Falla con el
        mensaje en palabras sencillas si alguno está mal escrito. Lo vacío no se revisa aquí (lo exigen las puertas)."""
        if vals.get('email'):
            escrito = vals['email']
            codigo, sugerencia = B.problema_del_correo(escrito)
            if codigo:
                raise ValidationError(B.mensaje_del_correo(self.env, escrito, codigo, sugerencia))
            limpio = B.correo_limpio(escrito)
            if limpio in self._dcasa_correos_del_equipo(excepto=self):
                raise ValidationError(B.mensaje_del_correo(self.env, escrito, 'equipo'))
            vals['email'] = limpio
        if vals.get('phone'):
            escrito = vals['phone']
            codigo = B.problema_del_telefono(escrito)
            if codigo:
                raise ValidationError(B.mensaje_del_telefono(self.env, escrito, codigo))
            vals['phone'] = B.telefono_para_guardar(escrito)
        return vals

    @staticmethod
    def _dcasa_correo_desmarca(vals):
        """Si llega un correo, «Cliente no tiene correo electrónico» se desmarca sola (cambia ``vals``): el correo
        escrito manda sobre la casilla."""
        correo = vals.get('email')
        if isinstance(correo, str) and correo.strip():
            vals[SIN_CORREO] = False
        return vals

    @api.model
    def _dcasa_es_empresa_al_crear(self, vals):
        if 'is_company' in vals:
            return bool(vals['is_company'])
        if 'company_type' in vals:
            return vals['company_type'] == 'company'
        return bool(self.env.context.get('default_is_company'))

    @api.model
    def _dcasa_revisar_contacto_al_crear(self, vals_list):
        """Antes de crear: correo y celular limpios y, al crear una persona como cliente desde un formulario, los dos
        obligatorios (el correo, salvo «Cliente no tiene correo electrónico»)."""
        for vals in vals_list:
            self._dcasa_correo_desmarca(vals)
        if not self._dcasa_exige_contacto():
            return
        contexto = self.env.context
        modo = contexto.get('res_partner_search_mode')
        if modo == 'supplier':
            return
        for vals in vals_list:
            if vals.get('supplier_rank') and not vals.get('customer_rank'):
                continue
            self._dcasa_limpiar_contacto(vals)
            con_padre = vals.get('parent_id') or contexto.get('default_parent_id')
            if modo != 'customer' or con_padre or contexto.get(ALTA_RAPIDA) or self._dcasa_es_empresa_al_crear(vals):
                continue
            faltan = [campo for campo, falta in (
                ('celular', not vals.get('phone')),
                ('correo', not vals.get('email') and not vals.get(SIN_CORREO)),
            ) if falta]
            if faltan:
                raise ValidationError(self._dcasa_mensaje_al_crear(faltan))

    def _dcasa_revisar_contacto_al_editar(self, vals):
        """Antes de guardar un cambio: solo lo que cambia (lo viejo no se toca). Devuelve los valores a guardar (una
        copia: nunca cambia el diccionario de quien llama)."""
        vals = dict(vals)
        if SIN_CORREO in vals or self.sudo().filtered(SIN_CORREO):
            self._dcasa_correo_desmarca(vals)
        if not (vals.get('email') or vals.get('phone')) or not self._dcasa_exige_contacto():
            return vals
        sujetas = self._dcasa_sujetas_al_contacto()
        if not sujetas:
            return vals
        return sujetas._dcasa_limpiar_contacto(vals)

    @api.model
    def name_create(self, name):
        """La creación rápida (escribir el nombre y Enter en un campo, p. ej. la empresa de un contacto) no exige el
        celular ni el correo al crear: los exigen la venta y la factura. Lo que traiga se revisa igual."""
        return super(ResPartner, self.with_context(**{ALTA_RAPIDA: True})).name_create(name)

    @api.onchange('email')
    def _onchange_dcasa_sin_correo(self):
        """Mientras se edita: si se escribe un correo, la casilla «Cliente no tiene correo electrónico» se desmarca."""
        if self.email and self.email.strip() and self.dcasa_sin_correo:
            self.dcasa_sin_correo = False

    @api.model
    def _dcasa_mensaje_al_crear(self, faltan):
        que = {
            ('celular',): self.env._('el celular'),
            ('correo',): self.env._('el correo'),
        }.get(tuple(faltan), self.env._('el celular y el correo'))
        mensaje = self.env._(
            'Escribe %(que)s del cliente: sin eso no se puede confirmar su venta ni le llega su factura.', que=que)
        if 'correo' in faltan:
            mensaje += ' ' + self._dcasa_ayuda_sin_correo()
        return mensaje

    @api.model
    def _dcasa_ayuda_sin_correo(self):
        return self.env._('Si de verdad no tiene correo, marca «Cliente no tiene correo electrónico» en su ficha o '
                          'junto al cliente en la cotización.')

    def _dcasa_aviso_bien_escrito(self):
        """El aviso «¿Quisiste decir…?» del formulario, antes de guardar (solo de lo que se acaba de cambiar)."""
        self.ensure_one()
        if not self.env.user.has_group('base.group_user') or \
                self.env.context.get('res_partner_search_mode') == 'supplier' or \
                (self.supplier_rank > 0 and not self.customer_rank):
            return None
        origen = self._origin
        if self.email and self.email != origen.email:
            codigo, sugerencia = B.problema_del_correo(self.email)
            if codigo:
                return B.mensaje_del_correo(self.env, self.email, codigo, sugerencia)
        if self.phone and self.phone != origen.phone:
            codigo = B.problema_del_telefono(self.phone)
            if codigo:
                return B.mensaje_del_telefono(self.env, self.phone, codigo)
        return None

    # ------------------------------------------------------------------
    # Lo que tiene un documento (venta o factura)
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_contacto_del_documento(self, partner_documento, sin_correo=None):
        """El correo y el celular que sirven para el cliente de un documento (la venta o la factura).

        Correo: el primero bien escrito entre la dirección del documento, su ficha y la ficha comercial. Celular: el
        primero bien escrito entre el teléfono de la dirección, el de la ficha comercial y el celular de Socios.
        Devuelve ``{'correo', 'celular', 'sin_correo', 'malos'}``; ``malos`` guarda lo que existe pero está mal
        escrito (``{'correo': (valor, código, sugerencia), 'celular': (valor, código, None)}``). ``sin_correo``: la
        casilla «Cliente no tiene correo electrónico» de alguna de esas fichas, o el valor que se le pase (el de la
        cotización, que puede estar cambiando en pantalla antes de guardarse)."""
        documento = partner_documento.sudo()
        cadena = []
        for partner in (documento, documento.parent_id, documento.commercial_partner_id):
            if partner and partner not in cadena:
                cadena.append(partner)
        propias = self.browse([partner._origin.id for partner in cadena if partner._origin.id])
        equipo = self._dcasa_correos_del_equipo(excepto=propias)
        if sin_correo is None:
            sin_correo = any(partner.dcasa_sin_correo for partner in cadena)
        datos = {'correo': None, 'celular': None, 'malos': {}, 'sin_correo': bool(sin_correo)}
        for partner in cadena:
            if not partner.email:
                continue
            codigo, sugerencia = B.problema_del_correo(partner.email)
            if not codigo and B.correo_limpio(partner.email) in equipo:
                codigo, sugerencia = 'equipo', None
            if codigo:
                datos['malos'].setdefault('correo', (partner.email, codigo, sugerencia))
                continue
            datos['correo'] = B.correo_limpio(partner.email)
            break
        comercial = documento.commercial_partner_id
        for telefono in (documento.phone, comercial.phone, comercial.dcasa_celular):
            if not telefono:
                continue
            codigo = B.problema_del_telefono(telefono)
            if codigo:
                datos['malos'].setdefault('celular', (telefono, codigo, None))
                continue
            datos['celular'] = B.telefono_para_guardar(telefono)
            break
        return datos

    @staticmethod
    def _dcasa_lo_que_falta(datos):
        return [campo for campo, falta in (
            ('celular', not datos['celular']),
            ('correo', not datos['correo'] and not datos['sin_correo']),
        ) if falta]

    @api.model
    def _dcasa_faltantes(self, partner_documento, sin_correo=None):
        """``['celular', 'correo']``: lo que le falta (o está mal escrito) al cliente del documento. Con «Cliente no
        tiene correo electrónico» marcada, el correo no falta (el celular sí)."""
        return self._dcasa_lo_que_falta(self._dcasa_contacto_del_documento(partner_documento, sin_correo=sin_correo))

    @api.model
    def _dcasa_mensaje_faltantes(self, partner_documento, puerta, sin_correo=None):
        """El mensaje de la puerta (``'venta'`` o ``'factura'``), o ``None`` si al cliente no le falta nada."""
        datos = self._dcasa_contacto_del_documento(partner_documento, sin_correo=sin_correo)
        faltan = self._dcasa_lo_que_falta(datos)
        if not faltan:
            return None
        if puerta == 'venta':
            inicio, accion = self.env._('Para confirmar la venta'), self.env._('confirmar')
        else:
            inicio, accion = self.env._('Para publicar la factura'), self.env._('publicarla')
        partes = []
        vacios = [campo for campo in faltan if campo not in datos['malos']]
        if vacios:
            que = {
                ('celular',): self.env._('el celular'),
                ('correo',): self.env._('el correo'),
            }.get(tuple(vacios), self.env._('el celular y el correo'))
            escribelo = self.env._('Escríbelos') if len(vacios) > 1 else self.env._('Escríbelo')
            partes.append(self.env._(
                '%(inicio)s, a «%(cliente)s» le falta %(que)s. %(escribelo)s en su ficha y vuelve a %(accion)s: ahí '
                'le llegan su factura y cómo ver sus puntos.', inicio=inicio,
                cliente=partner_documento.sudo().commercial_partner_id.display_name, que=que, escribelo=escribelo,
                accion=accion))
        for campo in faltan:
            if campo not in datos['malos']:
                continue
            valor, codigo, sugerencia = datos['malos'][campo]
            if campo == 'correo':
                partes.append(B.mensaje_del_correo(self.env, valor, codigo, sugerencia, vuelve_a=accion))
            else:
                partes.append(B.mensaje_del_telefono(self.env, valor, codigo, vuelve_a=accion))
        if 'correo' in vacios:
            partes.append(self._dcasa_ayuda_sin_correo())
        return '\n'.join(partes)

    # ------------------------------------------------------------------
    # La tienda en línea
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_errores_de_contacto(self, celular, correo):
        """``{campo: mensaje}`` para quien compra en la tienda: el celular mal escrito y el correo con un error de dedo
        (el formato del correo ya lo revisa Odoo). Palabras para el cliente, de tú."""
        errores = {}
        if correo:
            codigo, sugerencia = B.problema_del_correo(correo)
            if codigo == 'dedo':
                errores['email'] = self.env._('Revisa tu correo: ¿quisiste decir %s? Ahí te llega tu factura.',
                                              sugerencia)
            elif codigo == 'relleno':
                errores['email'] = self.env._('Escribe tu correo de verdad: ahí te llega tu factura.')
            elif codigo == 'varios':
                errores['email'] = self.env._('Escribe un solo correo.')
        if celular:
            codigo = B.problema_del_telefono(celular)
            if codigo == 'varios':
                errores['phone'] = self.env._('Escribe un solo número de celular.')
            elif codigo:
                errores['phone'] = self.env._(
                    'Revisa tu celular: en Panamá son 8 números, como 6123-4567. Si es de otro país, escríbelo con + '
                    'y el código del país.')
        return errores
