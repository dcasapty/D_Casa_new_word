"""Ajustes › «Meta (Facebook e Instagram)» (solo administradores; res.config.settings ya es solo de ellos).

Todo apagado y vacío de fábrica. Compuertas al ENCENDER (un ``UserError`` en palabras sencillas):

* El píxel exige un ID válido y la política de privacidad publicada con la sección ``id="privacidad-meta"``; al
  encenderlo se enciende también el aviso de cookies del sitio.
* «Ventas de la web» y «Ventas de la tienda» exigen además el token en el entorno (``META_CAPI_TOKEN``).

Lo ya encendido no se vuelve a examinar al guardar otra cosa (así un ajuste ajeno nunca queda trabado), pero el sitio
y el cron vuelven a mirar las condiciones cada vez (``website._dcasa_meta_pixel_html``, ``_dcasa_puede_enviar``).
El token jamás se muestra: solo «cargado» o «falta».
"""
import time
import uuid

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import meta_api
from .meta_evento import PARAM_TOKEN_RECHAZADO, leer_config

CLAVES_HTML = ('pixel_id', 'pixel_activo')  # lo que cambia el HTML del sitio (y las páginas guardadas en el borde)
INTERRUPTORES = (('pixel_activo', 'dcasa_meta_pixel_activo'), ('capi_web', 'dcasa_meta_capi_web'),
                 ('capi_tienda', 'dcasa_meta_capi_tienda'))


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dcasa_meta_pixel_id = fields.Char(
        'ID del píxel de Meta', config_parameter='dcasa_meta.pixel_id',
        help='El número del conjunto de datos (píxel) que muestra Meta › Administrador de eventos. No es secreto.')
    dcasa_meta_pixel_activo = fields.Boolean(
        'Píxel en el sitio', config_parameter='dcasa_meta.pixel_activo',
        help='Mide visitas, productos vistos y carrito, solo de quien acepta las cookies. Enciende también el aviso '
             'de cookies.')
    dcasa_meta_capi_web = fields.Boolean(
        'Ventas de la web', config_parameter='dcasa_meta.capi_web',
        help='Cuando un pedido de la tienda en línea queda pagado, se reporta a Meta (con consentimiento).')
    dcasa_meta_capi_tienda = fields.Boolean(
        'Ventas de la tienda', config_parameter='dcasa_meta.capi_tienda',
        help='Cuando una factura de la tienda queda pagada, se reporta a Meta, solo de clientes que aceptaron.')
    dcasa_meta_test_event_code = fields.Char(
        'Código de prueba', config_parameter='dcasa_meta.test_event_code',
        help='El que muestra Meta › Administrador de eventos › Probar eventos. Fuera de producción, sin él no sale '
             'nada.')
    dcasa_meta_graph_version = fields.Char(
        'Versión de la API de Meta', config_parameter='dcasa_meta.graph_version', default=meta_api.VERSION_GRAPH)
    dcasa_meta_token_estado = fields.Char('Token de Meta', compute='_compute_dcasa_meta_estado')
    dcasa_meta_token_rechazado = fields.Boolean(compute='_compute_dcasa_meta_estado')
    dcasa_meta_estado = fields.Char('Estado de Meta', compute='_compute_dcasa_meta_estado')

    @api.depends('dcasa_meta_capi_web', 'dcasa_meta_capi_tienda', 'dcasa_meta_pixel_activo')
    def _compute_dcasa_meta_estado(self):
        cargado = bool(meta_api.token())
        rechazado = self.env['ir.config_parameter'].sudo().get_param(PARAM_TOKEN_RECHAZADO)
        if not cargado:
            token = self.env._('Token de Meta: falta (se carga como secreto META_CAPI_TOKEN, nunca aquí)')
        elif rechazado:
            token = self.env._('Token de Meta: cargado · El token de Meta no funciona (Meta lo rechazó el %s UTC)',
                               rechazado[:16])
        else:
            token = self.env._('Token de Meta: cargado')
        partes = []
        if not meta_api.es_produccion():
            partes.append(self.env._('Este servidor no es el de producción: el píxel no se dibuja y a Meta solo salen '
                                     'eventos con el código de prueba.'))
        if not self.env['website']._dcasa_meta_privacidad_lista():
            partes.append(self.env._('La política de privacidad todavía no tiene la sección de Meta: no se puede '
                                     'encender nada.'))
        estado = ' '.join(partes) or self.env._('Listo para encender (con el visto bueno del abogado).')
        for ajustes in self:
            ajustes.dcasa_meta_token_estado = token
            ajustes.dcasa_meta_token_rechazado = bool(cargado and rechazado)
            ajustes.dcasa_meta_estado = estado

    # ------------------------------------------------------------------
    # Compuertas al guardar
    # ------------------------------------------------------------------

    def _dcasa_meta_validar(self, antes):
        self.ensure_one()
        pixel = (self.dcasa_meta_pixel_id or '').strip()
        if pixel and not meta_api.RE_PIXEL.match(pixel):
            raise UserError(self.env._(
                'El ID del píxel de Meta son solo números (lo copias de Meta › Administrador de eventos).'))
        codigo = (self.dcasa_meta_test_event_code or '').strip()
        if codigo and not meta_api.RE_CODIGO_PRUEBA.match(codigo):
            raise UserError(self.env._('El código de prueba de Meta son letras y números, sin espacios.'))
        version = (self.dcasa_meta_graph_version or '').strip()
        if version and not meta_api.RE_VERSION.match(version):
            raise UserError(self.env._('La versión de la API de Meta se escribe así: v26.0'))
        enciende = {clave: bool(self[campo]) and not antes[clave] for clave, campo in INTERRUPTORES}
        if not any(enciende.values()):
            return
        if not pixel:
            raise UserError(self.env._('Para encender Meta primero pega el ID del píxel.'))
        website = self.website_id or self.env['website'].get_current_website()
        if not self.env['website']._dcasa_meta_privacidad_lista(website.id):
            raise UserError(self.env._(
                'Todavía no se puede encender: la política de privacidad publicada no tiene la sección de Meta. '
                'Primero el abogado aprueba ese texto y lo publicamos; después se enciende.'))
        if (enciende['capi_web'] or enciende['capi_tienda']) and not meta_api.token():
            raise UserError(self.env._(
                'Falta el token de Meta en el servidor. Guárdalo en GitHub como secreto META_CAPI_TOKEN (nunca aquí '
                'ni por el chat) y avísanos para desplegar.'))

    def set_values(self):
        """Valida ANTES de guardar (res.config.settings es solo de administradores) y, si cambió algo que se ve en el
        sitio, marca las páginas guardadas en el borde para volver a armarlas."""
        antes = leer_config(self.env)
        for ajustes in self:
            ajustes._dcasa_meta_validar(antes)
        super().set_values()
        despues = leer_config(self.env)
        cambia_html = any(antes[clave] != despues[clave] for clave in CLAVES_HTML)
        if despues['pixel_activo'] and not antes['pixel_activo']:
            # Al encender el píxel se enciende el aviso de cookies: sin aceptar, el píxel no carga.
            sin_aviso = self.env['website'].sudo().search([('cookies_bar', '=', False)])
            if sin_aviso:
                sin_aviso.write({'cookies_bar': True})
                cambia_html = True
        if cambia_html:
            self.env['dcasa.tienda.pendiente']._dcasa_marcar([0], 'meta')

    # ------------------------------------------------------------------
    # Botón «Enviar evento de prueba»
    # ------------------------------------------------------------------

    def action_dcasa_meta_enviar_prueba(self):
        """Manda en el momento UN PageView de prueba (con ``test_event_code``), sin datos de ninguna persona.

        Exige administrador en el servidor (también por RPC con ``ids=[]``), el código de prueba y el token. No exige
        la política de privacidad: no lleva datos de nadie y sirve para probar antes de encender.
        """
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise AccessError(self.env._('Solo un administrador manda el evento de prueba de Meta.'))
        config = leer_config(self.env)
        ajustes = self[:1]
        pixel = ((ajustes.dcasa_meta_pixel_id if ajustes else '') or config['pixel_id']).strip()
        codigo = ((ajustes.dcasa_meta_test_event_code if ajustes else '') or config['test_event_code']).strip()
        version = ((ajustes.dcasa_meta_graph_version if ajustes else '') or config['graph_version']).strip()
        if not meta_api.RE_PIXEL.match(pixel):
            raise UserError(self.env._('Primero pega el ID del píxel de Meta (solo números).'))
        if not codigo or not meta_api.RE_CODIGO_PRUEBA.match(codigo):
            raise UserError(self.env._(
                'Primero pega el código de prueba (Meta › Administrador de eventos › Probar eventos).'))
        if not meta_api.RE_VERSION.match(version):
            raise UserError(self.env._('La versión de la API de Meta se escribe así: v26.0'))
        secreto = meta_api.token()
        if not secreto:
            raise UserError(self.env._('Falta el token de Meta en el servidor (secreto META_CAPI_TOKEN).'))
        website = (ajustes.website_id if ajustes else False) or self.env['website'].get_current_website()
        base = website._dcasa_url_publica() or website.get_base_url().rstrip('/')
        event_id = f'prueba-{uuid.uuid4()}'
        evento = {
            'event_name': 'PageView',
            'event_time': int(time.time()),
            'event_id': event_id,
            'action_source': 'website',
            'event_source_url': f'{base}/',
            'user_data': {
                'client_user_agent': 'DCASA-prueba',
                'external_id': meta_api.sha256('dcasa-prueba'),
            },
        }
        resultado = meta_api.enviar([evento], pixel, version, secreto, codigo)
        ok = resultado['tipo'] == meta_api.OK
        ahora = fields.Datetime.now()
        self.env['dcasa.meta.evento'].sudo().create({
            'event_name': 'PageView', 'event_id': event_id, 'action_source': 'website', 'origen': 'prueba',
            'event_time': ahora, 'es_prueba': True, 'intentos': 1,
            'estado': 'enviado' if ok else 'error',
            'enviado_en': ahora if ok else False,
            'fbtrace_id': resultado['fbtrace_id'] or False,
            'ultimo_error': resultado['mensaje'] or False,
            'motivo': self.env._('Evento de prueba'),
        })
        if ok:
            mensaje = self.env._(
                'Meta recibió el evento de prueba (%(n)s). Míralo en Administrador de eventos › Probar eventos. '
                'Rastreo (fbtrace_id): %(t)s', n=resultado['recibidos'], t=resultado['fbtrace_id'] or '—')
        else:
            mensaje = self.env._('Meta no aceptó el evento de prueba: %(m)s · Rastreo (fbtrace_id): %(t)s',
                                 m=resultado['mensaje'] or resultado['status'], t=resultado['fbtrace_id'] or '—')
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': self.env._('Meta: evento de prueba'),
                'message': mensaje,
                'type': 'success' if ok else 'danger',
                'sticky': not ok,
            },
        }
