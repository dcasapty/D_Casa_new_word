"""``dcasa.correo``: la configuración y las piezas que comparten todos los correos de D'CASA.

Modelo abstracto SIN ACL y con todos sus métodos privados: por RPC no se llama ninguno (S-09).

La clave de Resend viene **solo** de la variable de entorno ``RESEND_API_KEY`` (GitHub → Worker → contenedor): nunca
de ``ir.config_parameter``, de un campo ni de un log. Sin clave, Odoo se comporta exactamente como antes.
"""
import logging
import os
from email.utils import formataddr

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import email_normalize, format_amount, format_date, str2bool
from odoo.tools.mail import single_email_re

from . import politica, resend

_logger = logging.getLogger(__name__)

VARIABLE_CLAVE = 'RESEND_API_KEY'
LAYOUT = 'dcasa_correo.layout_correo'

P_REMITENTE = 'dcasa_correo.remitente'
P_NOMBRE = 'dcasa_correo.nombre'
P_RESPONDER_A = 'dcasa_correo.responder_a'
P_A_CLIENTES = 'dcasa_correo.enviar_a_clientes'
P_AL_PAGAR = 'dcasa_correo.al_pagar'
P_BIENVENIDA = 'dcasa_correo.bienvenida'
P_BIENVENIDA_DESDE = 'dcasa_correo.bienvenida_desde'

# Decisión de la dueña (17/10/2026): sale como «D'CASA Panamá <ventas@dcasapty.com>» y se responde a info@.
REMITENTE = 'ventas@dcasapty.com'
NOMBRE = "D'CASA Panamá"
RESPONDER_A = 'info@dcasapty.com'

TEXTO_WHATSAPP = "Hola D'CASA, te escribo por el correo que me mandaron."
AZUL = '#1340B1'


def correo_valido(texto):
    """El correo normalizado si está bien escrito (una sola @, formato estricto); si no, ``None``."""
    texto = (texto or '').strip()
    if texto.count('@') != 1:
        return None
    normal = email_normalize(texto, strict=True)
    if not normal or not single_email_re.match(normal):
        return None
    return normal


def motivo_legible(error, clave=''):
    """La última línea útil de un error de envío, sin prefijos técnicos, sin la clave y sin correos."""
    partes = [str(a) for a in getattr(error, 'args', ()) if a] or [str(error)]
    texto = partes[-1].strip().split('\n')[-1]
    if texto.startswith(('RuntimeError: ', 'AssertionError: ')):
        texto = texto.split(': ', 1)[1]
    for prefijo in (resend.PREFIJO_REINTENTAR, resend.PREFIJO_NO_ENVIADO):
        texto = texto.removeprefix(prefijo).strip()
    return resend.tachar(texto, clave)


def centavos(monto):
    return int(round((monto or 0.0) * 100))


class DcasaCorreo(models.AbstractModel):
    _name = 'dcasa.correo'
    _description = "Correo a clientes de D'CASA (Resend)"

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------

    @api.model
    def _clave(self):
        """La clave de Resend del entorno. Solo la usa el transporte; nunca se guarda ni se muestra."""
        return (os.environ.get(VARIABLE_CLAVE) or '').strip()

    @api.model
    def _hay_clave(self):
        return bool(self._clave())

    @api.model
    def _entorno(self):
        """``DCASA_ENTORNO`` tal cual (vacío si no está). Solo ``produccion`` le escribe a clientes: un servidor que no
        lo dice (una copia en una máquina, un staging mal configurado) no le manda nada a nadie más que al equipo."""
        return (os.environ.get('DCASA_ENTORNO') or '').strip().lower()

    @api.model
    def _config(self):
        """Lo que dicen Ajustes (sin la clave: para eso está ``_clave``)."""
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'hay_clave': self._hay_clave(),
            'remitente': (ICP.get_param(P_REMITENTE) or REMITENTE).strip(),
            'nombre': (ICP.get_param(P_NOMBRE) or NOMBRE).strip(),
            'responder_a': (ICP.get_param(P_RESPONDER_A) or RESPONDER_A).strip(),
            'enviar_a_clientes': str2bool(ICP.get_param(P_A_CLIENTES) or 'False', False),
            # Al instalar se dejan en True (post_init_hook); apagadas, Odoo borra el parámetro.
            'al_pagar': str2bool(ICP.get_param(P_AL_PAGAR) or 'False', False),
            'bienvenida': str2bool(ICP.get_param(P_BIENVENIDA) or 'False', False),
            'entorno': self._entorno(),
        }

    @api.model
    def _activo_para_clientes(self):
        """¿Sale correo a clientes? Hace falta la clave, el interruptor encendido y ser producción."""
        config = self._config()
        return bool(config['hay_clave'] and config['enviar_a_clientes']
                    and config['entorno'] == politica.ENTORNO_PRODUCCION)

    @api.model
    def _motivo_apagado(self):
        """Por qué no sale correo a clientes (texto para la persona), o ``''`` si sí sale."""
        config = self._config()
        if not config['hay_clave']:
            return self.env._('Todavía no hay clave de Resend: no sale ningún correo.')
        if config['entorno'] == 'staging':
            return self.env._('En staging nunca se envía correo a clientes.')
        if config['entorno'] != politica.ENTORNO_PRODUCCION:
            return self.env._('Este servidor no dice que es producción (DCASA_ENTORNO): no se envía correo a clientes.')
        if not config['enviar_a_clientes']:
            return self.env._('Los correos a clientes están apagados (Ajustes › Correo a clientes).')
        return ''

    @api.model
    def _remitente_formateado(self):
        config = self._config()
        return formataddr((config['nombre'], config['remitente']))

    @api.model
    def _correos_internos(self):
        """Los correos del equipo (usuarios internos activos): solo a ellos puede ir la prueba."""
        usuarios = self.env['res.users'].sudo().search([('share', '=', False), ('active', '=', True)])
        return [c for c in usuarios.mapped('email_normalized') if c]

    @api.model
    def _sesion(self):
        """La «conexión» que Odoo usa en vez de SMTP."""
        config = self._config()
        return resend.SesionResend(self._clave(), {
            'remitente': config['remitente'], 'nombre': config['nombre'], 'responder_a': config['responder_a'],
            'a_clientes': self._activo_para_clientes(), 'entorno': config['entorno'],
        }, self._correos_internos())

    # ------------------------------------------------------------------
    # A quién y con qué enlaces
    # ------------------------------------------------------------------

    @api.model
    def _destino(self, registro):
        """La ficha a la que se escribe: el contacto del documento si su correo sirve; si no, la ficha comercial.

        Devuelve un ``res.partner`` vacío si ninguna tiene un correo bien escrito.
        """
        Partner = self.env['res.partner']
        if not registro:
            return Partner
        registro = registro.sudo()
        if registro._name == 'res.partner':
            candidatos = [registro, registro.commercial_partner_id]
        elif 'partner_id' in registro._fields:
            candidatos = [registro.partner_id, registro.partner_id.commercial_partner_id]
        else:
            return Partner
        for partner in candidatos:
            if partner and correo_valido(partner.email):
                return partner.with_env(self.env)
        return Partner

    @api.model
    def _base(self):
        """La dirección pública del sitio para los enlaces y el logo: el dominio del sitio web, ``web.base.url`` (en
        producción, https://CANONICAL_HOST, congelada por el arranque) o la web de la empresa, nunca una local
        (``res.company._dcasa_url_publica`` de dcasa_invoice). Sin ninguna pública (una prueba, una copia en una
        máquina), ``web.base.url`` tal cual."""
        publica = self.env.company.sudo()._dcasa_url_publica()
        return (publica or self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')

    @api.model
    def _mi_cuenta_instalado(self):
        return bool(self.env['ir.module.module'].sudo().search_count(
            [('name', '=', 'dcasa_mi_cuenta'), ('state', '=', 'installed')]))

    @api.model
    def _enlaces(self):
        """Los enlaces de los correos. Ninguno lleva ``access_token``: el cliente entra con su celular y su PIN."""
        base = self._base()
        if self._mi_cuenta_instalado():
            enlaces = {'cuenta': f'{base}/mi-cuenta', 'compras': f'{base}/mi-cuenta/compras',
                       'puntos': f'{base}/mi-cuenta/puntos'}
        else:
            enlaces = {'cuenta': f'{base}/socios', 'compras': None, 'puntos': f'{base}/socios/cuenta'}
        enlaces.update({
            'base': base,
            'registro': f'{base}/socios/registro',
            'premios': f'{base}/socios/premios',
            'logo': f'{base}/dcasa_base/static/img/logo.png',
        })
        return enlaces

    @api.model
    def _whatsapp(self, texto=None):
        """El enlace de «Escríbenos por WhatsApp» (el número que la dueña puso en el sitio), siempre absoluto."""
        website = self.env['website'].sudo().search([], order='sequence, id', limit=1)
        url = website._dcasa_whatsapp_url(texto or TEXTO_WHATSAPP) if website else ''
        if url.startswith('/'):
            url = self._base() + url
        return url

    @api.model
    def _titular(self, registro):
        """El titular de la banda azul cuando el correo no trae uno (p. ej. el botón «Enviar» de Odoo)."""
        modelo = getattr(registro, '_name', '') if registro is not None else ''
        if modelo == 'account.move' and registro:
            registro = registro[:1].sudo()
            if registro.move_type == 'out_invoice':
                return registro._dcasa_correo_valores()['titular']
            if registro.move_type == 'out_refund':
                return self.env._('TU NOTA DE CRÉDITO')
            return self.env._('TU DOCUMENTO')
        if modelo == 'sale.order' and registro:
            return self.env._('TU COTIZACIÓN') if registro[:1].state in ('draft', 'sent') else self.env._('TU PEDIDO')
        if modelo == 'res.partner' and registro:
            nombre = self._primer_nombre(registro[:1].sudo())
            if nombre:
                return self.env._('¡Te damos la bienvenida, %s!', nombre)
            return self.env._('¡Te damos la bienvenida!')
        if modelo == 'res.users':
            return self.env._('CORREO DE PRUEBA')
        return "D'CASA"

    @api.model
    def _boton(self, registro):
        """El único botón del correo: ``{texto, url}``. La bienvenida lleva a Mi cuenta; la factura y el abono, a
        verlos en Mi cuenta; lo demás (la cotización, la prueba), a WhatsApp. Sale del tipo de documento, nunca del
        contexto."""
        modelo = getattr(registro, '_name', '') if registro is not None else ''
        enlaces = self._enlaces()
        if modelo == 'res.partner':
            return {'texto': self.env._('Entrar a Mi cuenta'), 'url': enlaces['cuenta']}
        if (modelo == 'account.move' and registro and registro[:1].sudo().move_type == 'out_invoice'
                and enlaces['compras']):
            return {'texto': self.env._('Ver en Mi cuenta'), 'url': enlaces['cuenta']}
        return {'texto': self.env._('Escríbenos por WhatsApp'), 'url': self._whatsapp()}

    @api.model
    def _pie(self, company):
        """El pie corto sale de la empresa y del sitio (nombre, dirección y WhatsApp): nada escrito a mano."""
        company = (company or self.env.company).sudo()
        website = self.env['website'].sudo().search([], order='sequence, id', limit=1)
        return {
            'nombre': company.name or '',
            'direccion': company._dcasa_direccion_corta(),
            'whatsapp': (website.dcasa_whatsapp_number or company.phone or company.partner_id.phone or '').strip(),
        }

    @api.model
    def _contexto_layout(self, registro=None, message=None, company=None):
        """Lo que pinta ``layout_correo``: titular, enlaces, logo, el botón, WhatsApp y pie."""
        contexto = self.env.context
        titular = contexto.get('dcasa_correo_titular') or self._titular(registro)
        asunto = (message.subject or '') if message is not None else ''
        boton = self._boton(registro)
        whatsapp = self._whatsapp()
        return {
            'titular': titular,
            'preencabezado': contexto.get('dcasa_correo_preencabezado') or asunto or titular,
            'enlaces': self._enlaces(),
            'boton': boton,
            'whatsapp': whatsapp,
            # «¿Dudas? Escríbenos por WhatsApp» como enlace de texto, solo si el botón no es ya el de WhatsApp.
            'whatsapp_aparte': boton['url'] != whatsapp,
            'pie': self._pie(company),
            'azul': AZUL,
        }

    # ------------------------------------------------------------------
    # Armar y dejar el correo en el chatter (la cola de Odoo lo manda después)
    # ------------------------------------------------------------------

    @api.model
    def _postear(self, registro, plantilla, destino, adjuntos=(), tipo='factura', titular=None):
        """Arma el correo con la plantilla y lo deja en el chatter del registro, con el layout D'CASA.

        Nunca manda en el momento (``mail_notify_force_send=False``): queda en la cola de Odoo, que dispara el cron.
        Solo le escribe a ``destino`` (no a los seguidores) y no crea ``access_token`` en el documento.
        """
        registro.ensure_one()
        valores = plantilla._generate_template([registro.id], ('subject', 'body_html'))[registro.id]
        cuerpo = valores.get('body_html') or ''
        company = registro.company_id if 'company_id' in registro._fields and registro.company_id else self.env.company
        mensaje = registro.with_context(
            mail_notify_force_send=False, dcasa_correo_sin_token=True, disable_attachment_import=True,
            no_document=True, mail_post_autofollow=False, mail_create_nosubscribe=True,
            dcasa_correo_titular=titular, dcasa_correo_preencabezado=valores.get('subject'),
        ).message_post(
            subject=valores.get('subject') or '',
            body=Markup(cuerpo),  # lo armó la plantilla del módulo, no el texto de una persona
            partner_ids=destino.ids,
            attachments=list(adjuntos or ()),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            email_layout_xmlid=LAYOUT,
            email_from=self._remitente_formateado(),
            author_id=company.partner_id.id,
            mail_headers={'X-Dcasa-Correo': tipo},
            notify_skip_followers=True,
        )
        return mensaje

    @api.model
    def _disparar_cola(self):
        """La cola de correo de Odoo se encarga del envío; así no espera a su próxima vuelta."""
        cron = self.env.ref('mail.ir_cron_mail_scheduler_action', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    # ------------------------------------------------------------------
    # Valores de las plantillas
    # ------------------------------------------------------------------

    @api.model
    def _primer_nombre(self, partner):
        nombre = ((partner.name or '').split() or [''])[0]
        return nombre[:1].upper() + nombre[1:].lower() if nombre else ''

    @api.model
    def _monto(self, monto, moneda):
        """Como en el papel de la factura: «$1,070.50» (en otra moneda, el formato de Odoo)."""
        from odoo.addons.dcasa_socios.models import reglas as R

        if moneda and moneda.name == 'USD':
            return R.como_dolares(R.a_centavos(monto or 0.0))
        return format_amount(self.env, monto or 0.0, moneda)

    @api.model
    def _puntos(self, puntos):
        from odoo.addons.dcasa_socios.models import reglas as R

        return R.como_puntos(int(puntos or 0))

    @api.model
    def _fecha(self, fecha):
        return format_date(self.env, fecha, date_format='dd/MM/yyyy') if fecha else ''

    @api.model
    def _valores_bienvenida(self, ficha):
        """Lo que dice la bienvenida (la dueña, 17/10/2026: corta y amigable, sin reglas de puntos, sin abonos y sin
        cifras): el nombre y cómo entra a Mi cuenta la primera vez."""
        return {'nombre': self._primer_nombre(ficha.sudo()), 'acceso': self._acceso_primera_vez(ficha),
                'enlaces': self._enlaces()}

    @api.model
    def _portal(self, ficha):
        """¿Tiene cuenta de la tienda en línea (usuario portal activo)? Con ella entra a Mi cuenta con su correo."""
        ficha = ficha.sudo().commercial_partner_id
        personas = ficha | ficha.child_ids
        return bool(personas.with_context(active_test=False).user_ids.filtered(lambda u: u.active and u.share))

    @api.model
    def _acceso_primera_vez(self, ficha):
        """Cómo entra a Mi cuenta, sin prometer lo que el sistema no hace (``dcasa_mi_cuenta`` y ``/socios/registro``):

        * ``pin``: ya tiene PIN → «entra con tu celular y tu PIN»;
        * ``tienda``: tiene cuenta de la tienda en línea → entra con su correo y su contraseña («¿Compraste en la web
          con tu correo?» de /mi-cuenta);
        * ``registro``: tiene código de socio y celular en su ficha. Con compras, /socios/registro solo le deja
          reclamar su ficha con ese celular y el código impreso en la factura (``SociosDcasa._reclamar``) → «regístrate
          con tu celular, el código de tu factura y un PIN que tú eliges»;
        * ``whatsapp``: lo demás (sin celular que sirva) → «escríbenos y te ayudamos».
        """
        ficha = ficha.sudo().commercial_partner_id
        if ficha.dcasa_reclamada:
            return 'pin'
        if self._portal(ficha):
            return 'tienda'
        if ficha.dcasa_socio_codigo and ficha.dcasa_celular:
            return 'registro'
        return 'whatsapp'

    @api.model
    def _lista_para_bienvenida(self, ficha):
        """¿Puede entrar ya a Mi cuenta? Si no (su primera compra va en abono y el código de socio llega con la factura
        pagada), la bienvenida espera al pago que la termina: así nunca dice algo que todavía no puede hacer."""
        ficha = ficha.sudo().commercial_partner_id
        return bool(ficha.dcasa_reclamada or ficha.dcasa_socio_codigo or self._portal(ficha))

    @api.model
    def _valores_prueba(self, usuario):
        return {'nombre': self._primer_nombre(usuario.partner_id), 'enlaces': self._enlaces()}

    # ------------------------------------------------------------------
    # Correo de prueba (botón de Ajustes)
    # ------------------------------------------------------------------

    @api.model
    def _enviar_prueba(self, usuario):
        """Manda la plantilla de prueba al correo del usuario, ahora mismo, y devuelve ese correo.

        Sale aunque el interruptor esté apagado (solo a correos del equipo). Si Resend lo rechaza, el error se ve en
        pantalla (sin la clave)."""
        from odoo.addons.base.models.ir_mail_server import MailDeliveryException

        if not self._hay_clave():
            raise UserError(self.env._(
                'Todavía no hay clave de Resend en el servidor (RESEND_API_KEY). Mira docs/CORREO.md: se pega en '
                'GitHub y entra con el siguiente despliegue.'))
        destino = correo_valido(usuario.email)
        if not destino:
            raise UserError(self.env._(
                'Tu usuario no tiene un correo bien escrito. Escríbelo en tu perfil (Mis preferencias) y vuelve a '
                'probar.'))
        plantilla = self.env.ref('dcasa_correo.plantilla_prueba').sudo()
        valores = plantilla._generate_template([usuario.id], ('subject', 'body_html'))[usuario.id]
        company = self.env.company
        mensaje = self.env['mail.message'].sudo().new({'body': Markup(valores.get('body_html') or ''),
                                                      'subject': valores.get('subject')})
        cuerpo = self.env['ir.qweb'].with_context(dcasa_correo_titular=self._titular(usuario))._render(LAYOUT, {
            'message': mensaje, 'company': company, 'record': usuario,
            'dcasa': self.with_context(dcasa_correo_titular=self._titular(usuario))._contexto_layout(
                usuario, mensaje, company),
        }, minimal_qcontext=True, raise_if_not_found=False)
        correo = self.env['mail.mail'].sudo().create({
            'subject': valores.get('subject') or self.env._("Correo de prueba de D'CASA"),
            'body_html': cuerpo,
            'email_to': formataddr((usuario.name or '', destino)),
            'email_from': self._remitente_formateado(),
            'headers': repr({'X-Dcasa-Correo': 'prueba'}),
            'model': 'res.users',
            'res_id': usuario.id,
            'auto_delete': True,
        })
        try:
            correo.send(raise_exception=True)
        except MailDeliveryException as error:
            raise UserError(self.env._(
                'Resend no mandó la prueba: %s', motivo_legible(error, self._clave()))) from None
        return destino

    # ------------------------------------------------------------------
    # Estado para Ajustes
    # ------------------------------------------------------------------

    @api.model
    def _estado(self):
        """Una línea para Ajustes: si hay clave (enmascarada), si está encendido y el último error."""
        config = self._config()
        partes = []
        if config['entorno'] == 'staging':
            partes.append(self.env._('Staging: nunca se envía a clientes (la prueba sí sale).'))
        elif config['entorno'] != politica.ENTORNO_PRODUCCION:
            partes.append(self.env._('Sin DCASA_ENTORNO=produccion: nunca se envía a clientes (la prueba sí sale).'))
        clave = self._clave()
        if not clave:
            partes.append(self.env._('Sin clave: no sale ningún correo.'))
            return ' · '.join(partes)
        partes.append(self.env._('Clave cargada (…%s)', clave[-4:]))
        if self._activo_para_clientes():
            partes.append(self.env._('Encendido'))
        elif config['entorno'] == politica.ENTORNO_PRODUCCION:
            partes.append(self.env._('Apagado: solo sale el correo de prueba'))
        ultimo = self.env['mail.mail'].sudo().search(
            [('state', '=', 'exception'), ('failure_reason', 'ilike', 'Resend')], order='id desc', limit=1)
        if ultimo:
            texto = (ultimo.failure_reason or '').strip().split('\n')[-1]
            partes.append(self.env._('Último error: %s', resend.tachar(texto, clave)[:160]))
        return ' · '.join(partes)

    @api.model
    def _bienvenida_desde(self):
        valor = self.env['ir.config_parameter'].sudo().get_param(P_BIENVENIDA_DESDE)
        try:
            return fields.Datetime.to_datetime(valor) if valor else False
        except ValueError:
            return False
