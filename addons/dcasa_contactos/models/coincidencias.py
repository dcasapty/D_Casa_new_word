"""Encontrar al cliente que ya existe y corregir sus datos sin salir de lo que se está haciendo (pedido de la dueña,
2026-11-04).

«Los clientes escriben por WhatsApp y el sistema los guarda con lo que tengan en su perfil (un emoji, una frase, una
empresa). Cuando llegan a la tienda, la vendedora pone el nombre y el celular, y el celular ya estaba: le sale un error
y, por evitarlo, crea otro cliente con otro número. Tiene que ser fácil verificar si es la misma persona y actualizar
sus datos, sin perder lo que se está facturando.»

* **Buscar por celular.** En el selector de «Cliente» (cotización, factura) y en el buscador de Contactos, el celular
  escrito de cualquier forma (6123-4567, 61234567, +507 6123 4567 o solo una parte) encuentra la ficha. En la lista que
  se despliega para elegir el cliente, junto al nombre sale su celular: así se reconoce a la persona aunque su nombre
  sea el de su perfil de WhatsApp.
* **«Ya existe esta persona».** Al crear un cliente («Crear y editar» de la cotización o la factura, Nuevo cliente del
  Inicio, Contactos), apenas el celular, el correo o la cédula que se escriben son de otra ficha, sale esa ficha con sus
  datos; si no, las de nombre parecido. El botón «Es esta persona» (``static/src/coincidencias``) abre esa ficha en la
  misma ventana con lo que se escribió encima: se revisa, se guarda y queda elegida en la cotización. Es una edición
  normal de la ficha (las mismas reglas y permisos de siempre): no hay atajo en el servidor.
* Solo para el equipo (usuarios internos): quien viene del sitio o del chat no ve fichas ajenas. Las fichas son las
  de siempre (``_dcasa_dominio_fichas``): ni usuarios, ni empleados, ni direcciones, ni la empresa propia.
"""
from odoo import api, fields, models
from odoo.addons.dcasa_socios.models import reglas as R
from odoo.fields import Domain

from . import claves

MAXIMO_COINCIDENCIAS = 5


def parece_telefono(texto):
    """¿Lo que se escribió en un buscador parece un teléfono? Al menos 4 números y casi nada más (+, guiones,
    paréntesis, espacios)."""
    if not isinstance(texto, str):
        return False
    digitos = R.solo_digitos(texto)
    compacto = texto.replace(' ', '')
    return len(digitos) >= 4 and len(compacto) - len(digitos) <= 3


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dcasa_coincidencias = fields.Json(
        'Ya existe esta persona', compute='_compute_dcasa_coincidencias',
        help='Al crear un cliente: las fichas que ya tienen su celular, su correo o su cédula (o un nombre parecido), '
             'para usar esa en vez de crear otra.')

    # ------------------------------------------------------------------
    # Buscar por celular
    # ------------------------------------------------------------------

    @api.model
    def _search_display_name(self, operator, value):
        """Además de lo que ya busca Socios (los números del celular, también una parte), el celular completo escrito
        con +507, 00507 o de otro país encuentra la ficha por su llave."""
        dominio = super()._search_display_name(operator, value)
        if operator != 'ilike' or not parece_telefono(value):
            return dominio
        llave = claves.llave_telefono(value)
        if not llave:
            return dominio
        return Domain.OR([dominio, self._dcasa_dominio_de_la_llave('celular', llave)])

    @api.depends('phone', 'dcasa_telefono_fijo')
    @api.depends_context('res_partner_search_mode')
    def _compute_display_name(self):
        """En la lista que se despliega para elegir el cliente, el celular (o el fijo) junto al nombre, en gris."""
        super()._compute_display_name()
        contexto = self.env.context
        if not contexto.get('formatted_display_name') or contexto.get('res_partner_search_mode') != 'customer':
            return
        for partner in self:
            telefono = partner.phone or partner.dcasa_telefono_fijo
            if telefono:
                partner.display_name = f'{partner.display_name} \t --{telefono}--'

    @api.model
    def default_get(self, fields_list):
        """«Crear y editar» después de buscar un celular o un correo que no estaba: lo buscado va a su campo (celular o
        correo), no al nombre. Solo para el equipo."""
        valores = super().default_get(fields_list)
        nombre = valores.get('name')
        if not isinstance(nombre, str) or not self.env.user._is_internal():
            return valores
        if 'phone' in fields_list and not valores.get('phone') and parece_telefono(nombre):
            valores.update(phone=nombre.strip(), name=False)
        elif 'email' in fields_list and not valores.get('email') and '@' in nombre and claves.llave_correo(nombre):
            valores.update(email=nombre.strip(), name=False)
        return valores

    # ------------------------------------------------------------------
    # «Ya existe esta persona»
    # ------------------------------------------------------------------

    @api.onchange('phone')
    def _onchange_dcasa_phone_duplicado(self):
        """Al CREAR una ficha, el celular repetido ya no sale como ventana de error («Ese celular ya está registrado»):
        lo dice «Ya existe esta persona», con su ficha y el botón para usarla. Al editar una ficha que ya existe, el
        aviso de siempre."""
        if not self._origin.id and not self.parent_id and self.env.user.has_group('base.group_user'):
            return None
        return super()._onchange_dcasa_phone_duplicado()

    @api.onchange('email', 'vat', 'phone', 'dcasa_telefono_fijo')
    def _onchange_dcasa_duplicado(self):
        """Lo mismo con el correo y la cédula repetidos al crear; el «¿Quisiste decir…?» sigue saliendo."""
        if not self._origin.id and not self.parent_id and self.env.user.has_group('base.group_user'):
            mensaje = self._dcasa_aviso_bien_escrito()
            if mensaje:
                return {'warning': {'title': self.env._('Revisa lo que escribiste'), 'message': mensaje}}
            return None
        return super()._onchange_dcasa_duplicado()

    @api.depends('name', 'phone', 'email', 'vat')
    def _compute_dcasa_coincidencias(self):
        es_equipo = self.env.user.has_group('base.group_user')
        for partner in self:
            partner.dcasa_coincidencias = False
            # Solo mientras se crea una ficha (no una dirección de otra), y solo al equipo.
            if not es_equipo or partner._origin.id or partner.parent_id:
                continue
            partner.dcasa_coincidencias = partner._dcasa_buscar_coincidencias() or False

    def _dcasa_buscar_coincidencias(self):
        """``[{id, nombre, por, fuerte, datos, origen, archivada}]``: primero las fichas con el mismo celular, correo o
        cédula (la llave, como el candado); después, si hay lugar, las de nombre parecido."""
        self.ensure_one()
        Partner = self.sudo().with_context(active_test=False)
        encontradas = {}
        for etiqueta, clave in (('celular', claves.llave_telefono(self.phone)),
                                ('correo', claves.llave_correo(self.email)),
                                ('ruc', claves.llave_vat(self.vat))):
            if not clave:
                continue
            fichas = Partner.search(self._dcasa_dominio_fichas() + self._dcasa_dominio_de_la_llave(etiqueta, clave),
                                    order='id', limit=MAXIMO_COINCIDENCIAS)
            for ficha in fichas:
                encontradas.setdefault(ficha.id, (ficha, []))[1].append(etiqueta)
        if len(encontradas) < MAXIMO_COINCIDENCIAS and self.name:
            for ficha in self._dcasa_fichas_parecidas(self.name, limite=MAXIMO_COINCIDENCIAS):
                encontradas.setdefault(ficha.id, (ficha, ['nombre']))
        salida = [self._dcasa_describir_coincidencia(ficha, por) for ficha, por in encontradas.values()]
        # Las del mismo dato primero; a igual, la más vieja (la que tiene la historia).
        salida.sort(key=lambda c: (not c['fuerte'], c['id']))
        return salida[:MAXIMO_COINCIDENCIAS]

    def _dcasa_describir_coincidencia(self, ficha, por):
        ficha = ficha.sudo()
        datos = []
        celular = ficha.phone or (ficha.dcasa_celular and R.celular_fmt(ficha.dcasa_celular))
        for etiqueta, valor in ((self.env._('Celular'), celular),
                                (self.env._('Teléfono fijo'), ficha.dcasa_telefono_fijo),
                                (self.env._('Correo'), ficha.email),
                                (self.env._('Cédula o RUC'), ficha.vat)):
            if valor:
                datos.append([etiqueta, valor])
        return {
            'id': ficha.id,
            'nombre': ficha.name or '',
            'por': [self._dcasa_etiqueta_coincidencia(p) for p in por],
            'fuerte': any(p != 'nombre' for p in por),
            'datos': datos,
            'origen': self._dcasa_origen_de_la_ficha(ficha),
            'archivada': not ficha.active,
        }

    def _dcasa_etiqueta_coincidencia(self, por):
        return {
            'celular': self.env._('el celular'),
            'correo': self.env._('el correo'),
            'ruc': self.env._('la cédula o RUC'),
        }.get(por) or self.env._('un nombre parecido')

    def _dcasa_origen_de_la_ficha(self, ficha):
        """«Llegó por el chat el 03/11/2026», «Se registró solo con el código QR el …» o «Creada el …»."""
        fecha = ''
        if ficha.create_date:
            fecha = fields.Datetime.context_timestamp(self, ficha.create_date).strftime('%d/%m/%Y')
        quien = ficha.dcasa_creado_por
        if quien == 'juan':
            return self.env._('Llegó por el chat el %s', fecha)
        if quien == 'qr':
            return self.env._('Se registró solo con el código QR el %s', fecha)
        return self.env._('Creada el %s', fecha) if fecha else ''
