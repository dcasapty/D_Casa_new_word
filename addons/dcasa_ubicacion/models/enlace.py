"""El enlace de un solo uso para que el cliente marque su punto de entrega desde el chat (``/u/<secreto>``).

Lo crea Juan (herramienta ``enlace_de_ubicacion``) o alguien del equipo (Brian). Está amarrado a una ficha (y, si
viene del chat, a su conversación): el cliente solo marca el punto en el mapa y, al confirmar, Juan le escribe con la
zona y el precio del envío. **No copia ni pega nada.**

* El secreto (128 bits al azar) se manda una vez y se guarda como huella SHA-256: ni la base lo tiene en texto.
* Vence a las ``HORAS_VIGENCIA`` horas y sirve una sola vez (después dice «ya recibimos su ubicación»).
"""
import logging
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import api, fields, models

from ..motor import geo

_logger = logging.getLogger(__name__)

HORAS_VIGENCIA = 24
RUTA = '/u/'


class UbicacionEnlace(models.Model):
    _name = 'dcasa.ubicacion.enlace'
    _description = 'Enlace para marcar la ubicación de entrega'
    _order = 'id desc'

    huella = fields.Char(required=True, readonly=True, copy=False, index=True, groups='base.group_system')
    partner_id = fields.Many2one('res.partner', 'Cliente', required=True, readonly=True, ondelete='cascade',
                                 index=True)
    conversacion_id = fields.Many2one('dcasa.conversacion', 'Conversación', readonly=True, ondelete='cascade',
                                      index=True)
    orden_id = fields.Many2one('sale.order', 'Pedido', readonly=True, ondelete='cascade', index='btree_not_null',
                               help='Si vino del link de pago (la página del pedido): al confirmar se recalcula su '
                                    'envío y el cliente vuelve a su pedido.')
    creado_por = fields.Selection([('juan', 'Juan (el asistente)'), ('equipo', 'El equipo'),
                                   ('aviso', 'El aviso de la venta'), ('pedido', 'La página del pedido')],
                                  readonly=True, required=True, default='equipo',
                                  help='«El aviso de la venta»: se lo pidió el sistema al confirmar una venta a '
                                       'domicilio sin su casa en el mapa, o con «🚚 Sale hoy» (models/avisos.py).')
    usuario_id = fields.Many2one('res.users', 'Lo pidió', readonly=True, default=lambda self: self.env.user)
    vence = fields.Datetime(required=True, readonly=True)
    usado_el = fields.Datetime('Usado el', readonly=True)
    zona = fields.Char('Zona marcada', readonly=True)
    fotos_subidas = fields.Integer('Fotos subidas', readonly=True, default=0)
    estado = fields.Selection([('vigente', 'Esperando al cliente'), ('usado', 'Ya marcó su punto'),
                               ('vencido', 'Venció')], compute='_compute_estado')

    _huella_unica = models.Constraint('UNIQUE(huella)', 'Ese enlace ya existe.')

    @api.depends('vence', 'usado_el')
    def _compute_estado(self):
        ahora = fields.Datetime.now()
        for enlace in self:
            # Vencido manda (aunque se haya usado): pasadas las 24 horas la página ya no dice ni la zona.
            enlace.estado = 'vencido' if enlace.vence < ahora else 'usado' if enlace.usado_el else 'vigente'

    @api.model
    def _crear(self, partner, conversacion=None, creado_por='equipo', orden=None, para_otra_casa=False):
        """``(enlace, url)`` nuevo para esa ficha. El secreto solo vive en la URL que se devuelve. Con
        ``para_otra_casa`` (un regalo, la abuela, el trabajo) el punto va a una dirección de entrega aparte de la
        cliente (``_otra_casa``), nunca a la suya: antes la pisaba, y el QR de su venta ya confirmada mandaba al
        chofer a la otra casa (auditoría 1)."""
        if para_otra_casa:
            partner = self._otra_casa(partner)
        token = geo.token_nuevo()
        ahora = fields.Datetime.now()
        if orden:
            # Uno vivo por pedido y ficha: abrir otra vez la página del pedido (o un lector de enlaces del correo)
            # no deja secretos vigentes regados (auditoría 1). Los anteriores sin usar vencen ya.
            self.sudo().search([('orden_id', '=', orden.id), ('partner_id', '=', partner.id),
                                ('usado_el', '=', False), ('vence', '>', ahora)]).write({'vence': ahora})
        enlace = self.sudo().create({
            'huella': geo.huella(token), 'partner_id': partner.id,
            'conversacion_id': conversacion.id if conversacion else False,
            'orden_id': orden.id if orden else False,
            'creado_por': creado_por if creado_por in ('juan', 'aviso', 'pedido') else 'equipo',
            'vence': ahora + timedelta(hours=HORAS_VIGENCIA),
        })
        return enlace, enlace._url(token)

    @api.model
    def _otra_casa(self, partner):
        """La dirección aparte («Otra casa de Ana») para un pedido que va a otro lugar. Tipo «otra», no «entrega»: si
        no, Odoo la tomaba como la dirección de entrega por defecto de TODA venta nueva del cliente (auditoría 2).
        Una por pedido pendiente: se reusa solo una sin punto que no tenga un enlace vigente (si no, la casa de la
        hermana pisaba la de la mamá). Al marcarla, su nombre lleva la zona (``_confirmar``)."""
        partner = partner.sudo()
        nombre = self.env._('Otra casa de %s', (partner.name or '').strip() or self.env._('el cliente'))
        ahora = fields.Datetime.now()
        vacias = self.env['res.partner'].sudo().search([
            ('parent_id', '=', partner.id), ('dcasa_otra_casa', '=', True), ('dcasa_ubic_fecha', '=', False)],
            order='id desc', limit=5)
        for vacia in vacias:
            if not self.sudo().search_count([('partner_id', '=', vacia.id), ('usado_el', '=', False),
                                             ('vence', '>', ahora)]):
                return vacia
        return self.env['res.partner'].sudo().create({
            'parent_id': partner.id, 'type': 'other', 'name': nombre, 'dcasa_otra_casa': True})

    def _url(self, token):
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        website = self.env['website'].sudo().search([], limit=1)
        if website and website.domain:
            dominio = website.domain if '://' in website.domain else 'https://' + website.domain
            base = dominio.rstrip('/')
        return f'{base}{RUTA}{token}'

    @api.model
    def _del_secreto(self, token):
        """El enlace de ese secreto (vigente, usado o vencido) o un registro vacío. Busca por la huella."""
        if not isinstance(token, str) or not 16 <= len(token) <= 64:
            return self.sudo().browse()
        return self.sudo().search([('huella', '=', geo.huella(token))], limit=1)

    def _confirmar(self, lat, lon, origen, precision=None, referencia=None, recibe=None, telefono=None):
        """El cliente confirmó su punto en la página del enlace. Guarda el punto en su ficha (y, si los escribió, quién
        recibe y el teléfono de respaldo: ``None`` o vacío no borra lo que ya había), marca el enlace usado y le
        escribe por el chat (si vino de una conversación). Devuelve la zona; ``UbicacionInvalida`` si el punto no
        sirve o ``TelefonoInvalido`` si el teléfono no es de Panamá (el enlace sigue vigente para que lo intente otra
        vez). La foto de la casa va aparte (``POST /u/<secreto>/foto``), apenas la toma."""
        self.ensure_one()
        enlace = self.sudo()
        zona = enlace.partner_id._dcasa_poner_ubicacion(lat, lon, origen, precision=precision,
                                                        referencia=referencia, confirmada=True)
        enlace.partner_id._dcasa_poner_quien_recibe(recibe=recibe or None, telefono=telefono or None, al_dia=False)
        enlace.write({'usado_el': fields.Datetime.now(), 'zona': zona['texto'] or False})
        casa = enlace.partner_id
        if casa.dcasa_otra_casa and casa.parent_id and (zona.get('barriada') or zona.get('distrito')):
            # Que el equipo las distinga al elegir la dirección de la venta: «Otra casa de Ana (Villa Lucre)».
            casa.write({'name': self.env._('Otra casa de %(quien)s (%(donde)s)', quien=casa.parent_id.name or '',
                                           donde=zona.get('barriada') or zona.get('distrito'))})
        enlace.partner_id.message_post(
            body=Markup('<p>%s</p>') % escape(self.env._(
                'El cliente marcó su punto de entrega con el enlace del chat: %(zona)s (%(origen)s).',
                zona=zona['texto'] or self.env._('sin zona en la tabla'), origen=geo.etiqueta(origen))),
            subtype_xmlid='mail.mt_note')
        orden = enlace.orden_id.sudo()
        if orden and orden.state in ('draft', 'sent') and orden.carrier_id.dcasa_por_cotizar:
            motivo = orden._dcasa_ubic_no_recalcular()
            if motivo:
                # Auditoría 1: con un pago en curso, cambiar el total hacía que el pago ya no confirmara la venta; y el
                # envío que puso una persona no se reemplaza solo. El equipo decide con la nota.
                orden._dcasa_ubic_nota_sin_recalcular(zona, motivo)
            else:
                orden._set_delivery_method(orden.carrier_id)   # el envío del pedido sale del punto nuevo
        if orden:
            orden.message_post(body=Markup('<p>%s</p>') % escape(self.env._(
                'El cliente marcó su punto de entrega desde la página del pedido: %s.', zona['texto'] or '—')),
                subtype_xmlid='mail.mt_note')
        if enlace.conversacion_id:
            enlace._avisar_por_el_chat(zona)
            enlace.conversacion_id.sudo()._aviso(enlace.partner_id._dcasa_ubic_aviso_para_el_equipo())
        return zona

    def _avisar_por_el_chat(self, zona):
        """Juan le escribe al cliente con la zona y el precio del envío (como el asistente: no toma la
        conversación). Un fallo aquí no deshace el punto: queda guardado y Juan cotiza cuando ella escriba."""
        self.ensure_one()
        conv = self.conversacion_id.sudo()
        try:
            with self.env.cr.savepoint():
                # Queda «por enviar» y sale por la cola del asistente (como los avisos): mandarlo aquí mismo hacía
                # COMMIT a mitad de la petición de la página (auditoría 1).
                conv._dcasa_escribir_como_asistente(self._texto_para_la_cliente(zona))
        except Exception:   # noqa: BLE001 — el punto ya quedó; el aviso es un extra
            _logger.exception('Ubicación: no se pudo avisar por el chat a la conversación %s', conv.id)

    def _texto_para_la_cliente(self, zona):
        """«✅ ¡Listo! Recibimos tu ubicación: Brisas del Golf, San Miguelito. 🚚 Envío $5.00. ¿Te lo sumamos a tu
        pedido?» Corto y con íconos (el dueño, 2026-11-25: la gente no lee párrafos), de tú y sin coordenadas. Sin
        precio: se lo confirma la tienda.

        Con la venta ya confirmada (el enlace del aviso al comprar o de «🚚 Sale hoy», models/avisos.py), nada de precio
        ni de «¿te lo sumamos?»: lo cobrado no se cambia. «✅ ¡Listo! Ya tenemos tu casa: Villa Lucre, San Miguelito.
        🏠 Casa 24. Tu pedido S00042 va para allá.» Si el envío de la tabla es otro, el equipo lo ve en la venta."""
        donde = ', '.join(p for p in (zona.get('barriada') or zona.get('corregimiento'), zona.get('distrito')) if p)
        # La casa que escribió en la página (el paso 3): así Juan no se la vuelve a preguntar.
        casa = geo.texto_corto(self.partner_id.sudo().dcasa_referencia, 80)
        orden = self.orden_id.sudo()
        if orden and orden.state not in ('draft', 'sent'):
            listo = (self.env._('✅ ¡Listo! Ya tenemos tu casa: %s.', donde) if donde
                     else self.env._('✅ ¡Listo! Ya tenemos tu casa.'))
            if casa:
                listo += ' ' + self.env._('🏠 %s.', casa.rstrip('.'))
            if orden.state == 'sale':
                listo += ' ' + self.env._('Tu pedido %s irá a esa dirección.', orden.name)
            return listo
        recibido = (self.env._('✅ ¡Listo! Recibimos tu ubicación: %s.', donde) if donde
                    else self.env._('✅ ¡Listo! Recibimos tu ubicación.'))
        if casa:
            recibido += ' ' + self.env._('🏠 %s.', casa.rstrip('.'))
        precio = self.env['dcasa.ubicacion']._precio(zona.get('lugar'))
        if not precio['con_precio']:
            return recibido + ' ' + self.env._('🚚 El costo del envío te lo confirmamos en un momento.')
        promocion = self._promocion_de_envio(zona.get('lugar'))
        if promocion == 'aplica':
            # La promoción ya le toca: la cifra la da Juan con su frase (la que calcula la promoción y pasa por su
            # guardia). Un precio sin la promoción contradecía al motor (auditoría 1).
            return recibido + ' ' + self.env._('🚚 Tu envío tiene promoción: ¿te confirmo cuánto te queda?')
        if promocion == 'condicional':
            return recibido + ' ' + self.env._('🚚 Envío %s (precio normal). Tenemos promoción de envío: ¿te cuento?',
                                               precio['total_txt'])
        return recibido + ' ' + self.env._('🚚 Envío %s. ¿Te lo sumamos a tu pedido?', precio['total_txt'])

    def _promocion_de_envio(self, lugar):
        """La promoción de envío de hoy para ese lugar, con la compra de la cotización abierta de la conversación (si
        hay una sola): ``'aplica'``, ``'condicional'`` o ``''``. Si no se puede saber, ``'aplica'``: mejor no decir
        una cifra que decir una equivocada."""
        try:
            Herramientas = self.env['brian.herramientas'].sudo()
            tarjeta = Herramientas._j_envio_tarjeta(lugar.sudo())
            abiertas = Herramientas._j_cotizaciones_de_la_conversacion(self.conversacion_id.sudo(), limite=2) \
                if self.conversacion_id else self.env['sale.order']
            compra = abiertas._dcasa_envio_compra() if len(abiertas) == 1 else None
            resultado, _promocion = self.env['dcasa.envio.promocion'].sudo()._aplicar(
                tarjeta['total'], tarjeta['prov'], tarjeta['dist'], compra)
        except Exception:   # noqa: BLE001 — ante la duda, sin cifra
            _logger.exception('Ubicación: no se pudo saber si hay promoción de envío para el lugar %s', lugar.id)
            return 'aplica'
        if not resultado.get('hay_promocion'):
            return ''
        return 'aplica' if resultado.get('aplica') else 'condicional' if resultado.get('condicional') else ''

    @api.autovacuum
    def _gc_enlaces_viejos(self):
        """Los enlaces vencidos hace más de 30 días no sirven para nada: se borran."""
        limite = fields.Datetime.now() - timedelta(days=30)
        self.sudo().search([('vence', '<', limite)]).unlink()


class Conversacion(models.Model):
    _inherit = 'dcasa.conversacion'

    def _dcasa_ubic_destino(self, para_punto=False):
        """La ficha de destino de esta conversación: la del enlace más reciente de las últimas 24 horas si es OTRA
        dirección (otra casa, o la dirección de entrega de una venta avisada); si no, la del cliente (auditoría 1:
        el punto del clip iba a su ficha aunque la venta fuera a otra dirección).

        Con ``para_punto`` (un punto nuevo: el clip, un enlace de mapa) solo mientras ese enlace siga **vigente y sin
        usar**: ya marcada la otra casa, la ubicación que el cliente comparte después es la suya y no puede mover en
        silencio el regalo (auditoría 2). Lo demás (cotizar sin lugar, el número de casa, quién recibe) sigue yendo a la
        otra casa durante esas 24 horas."""
        self.ensure_one()
        conv = self.sudo()
        ahora = fields.Datetime.now()
        reciente = self.env['dcasa.ubicacion.enlace'].sudo().search([
            ('conversacion_id', '=', conv.id), ('create_date', '>', ahora - timedelta(hours=HORAS_VIGENCIA))],
            order='id desc', limit=1)
        if not reciente or not reciente.partner_id or reciente.partner_id == conv.partner_id:
            return conv.partner_id.sudo()
        vigente = not reciente.usado_el and reciente.vence > ahora
        if vigente or (not para_punto and reciente.usado_el):
            return reciente.partner_id.sudo()
        return conv.partner_id.sudo()

