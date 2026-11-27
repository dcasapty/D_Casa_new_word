"""El punto de entrega de un cliente (su dirección de entrega en Odoo: ``res.partner``).

Se guarda solo aquí y en la entrega de cada venta (``dcasa.ubicacion.entrega``): nunca en el texto de una
conversación, en la auditoría de Brian ni en el registro del servidor (docs/UBICACION.md › «Privacidad»).

Junto al punto, para que el chofer no vuelva con el pedido: **quién recibe** (si no es el cliente), un **teléfono de
respaldo** de Panamá y la **foto de la fachada** (sin EXIF: ver ``motor/casa.py``). Los tres son opcionales.
"""
import base64

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..motor import casa, geo


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # partner_latitude / partner_longitude vienen de Odoo (base): son las coordenadas del punto.
    dcasa_ubic_origen = fields.Selection(geo.ORIGENES, string='De dónde salió el punto', readonly=True)
    dcasa_ubic_precision_m = fields.Integer('Precisión del GPS (m)', readonly=True)
    dcasa_ubic_fecha = fields.Datetime('Punto puesto el', readonly=True)
    dcasa_ubic_confirmada = fields.Boolean(
        'El cliente confirmó el punto', readonly=True,
        help='Tocó «Sí, aquí es» en el mapa, o compartió su ubicación por el chat.')
    dcasa_ubic_lugar_id = fields.Many2one(
        'dcasa.envio.lugar', 'Lugar de la calculadora', readonly=True, ondelete='set null',
        help='El lugar de la tabla de envíos más cercano al punto (a no más de 3 km): pone el precio del envío.')
    dcasa_ubic_zona = fields.Char('Zona de entrega', readonly=True,
                                  help='Barriada · corregimiento · distrito · provincia, deducidos del punto.')
    dcasa_barriada = fields.Char('Barriada')
    dcasa_corregimiento = fields.Char('Corregimiento')
    dcasa_distrito = fields.Char('Distrito')
    dcasa_provincia = fields.Char('Provincia')
    dcasa_otra_casa = fields.Boolean(
        'Otra casa (regalo)', readonly=True, copy=False,
        help='Dirección aparte que creó «para otra casa» (un regalo, la abuela, el trabajo): nunca es la dirección de '
             'entrega por defecto; se elige en la venta.')
    dcasa_referencia = fields.Char('Cómo reconocer el sitio', size=geo.MAX_REFERENCIA,
                                   help='Casa verde de portón negro, frente al chino… Lo lee el chofer.')
    dcasa_ubic_direccion_mapa = fields.Char('Dirección según el mapa', readonly=True,
                                            help='La que da Google para el punto (una ayuda; lo escrito manda).')
    dcasa_ubic_etiqueta = fields.Char('Origen del punto', compute='_compute_dcasa_ubic_etiqueta')
    dcasa_ubic_tiene_punto = fields.Boolean('Tiene punto de entrega', compute='_compute_dcasa_ubic_etiqueta')
    # Quién recibe y el teléfono de respaldo (opcionales): los ve el chofer, la venta y el equipo (también Brian,
    # que es del equipo: su auditoría los guarda tapados). Juan no los ve: solo los guarda si el cliente los dice.
    dcasa_recibe = fields.Char('Quién recibe', size=casa.MAX_RECIBE,
                               help='Si no es el cliente: «Rosa, su mamá», «el guardia del PH»… Lo lee el chofer.')
    dcasa_tel_respaldo = fields.Char('Teléfono de respaldo',
                                     help='Otro celular o fijo de Panamá por si el cliente no contesta.')
    # La foto de la fachada: un adjunto de la ficha (en R2 con dcasa_adjuntos_r2), uno por cliente. Solo la ve el
    # equipo (aquí) y el chofer (con el secreto de su página, /entrega/<secreto>/fachada); nunca /web/content
    # suelto.
    dcasa_fachada = fields.Binary('Foto de la casa', attachment=True, readonly=True, copy=False,
                                  groups='base.group_user')
    dcasa_fachada_fecha = fields.Datetime('Foto de la casa puesta el', readonly=True, copy=False)
    # Cuántas fotos subió hoy (auditoría 2: con enlaces nuevos del pedido se esquivaba el tope de cinco por enlace).
    dcasa_fachada_dia = fields.Date(readonly=True, copy=False)
    dcasa_fachada_hoy = fields.Integer(readonly=True, copy=False)

    @api.depends('dcasa_ubic_origen', 'dcasa_ubic_precision_m', 'partner_latitude', 'partner_longitude')
    def _compute_dcasa_ubic_etiqueta(self):
        for partner in self:
            partner.dcasa_ubic_tiene_punto = partner._dcasa_ubic_punto() is not None
            partner.dcasa_ubic_etiqueta = geo.etiqueta(
                partner.dcasa_ubic_origen, partner.dcasa_ubic_precision_m or None) if partner.dcasa_ubic_origen else ''

    @api.constrains('dcasa_tel_respaldo')
    def _check_dcasa_tel_respaldo(self):
        for partner in self:
            if partner.dcasa_tel_respaldo and not casa.telefono_de_respaldo(partner.dcasa_tel_respaldo):
                raise ValidationError(self.env._(
                    'El teléfono de respaldo tiene que ser de Panamá: un celular (6123-4567) o un fijo (234-5678).'))

    @api.onchange('dcasa_tel_respaldo')
    def _onchange_dcasa_tel_respaldo(self):
        numero = casa.telefono_de_respaldo(self.dcasa_tel_respaldo)
        if numero:
            self.dcasa_tel_respaldo = numero['guardar']

    def _dcasa_ubic_punto(self):
        """``(lat, lon)`` del punto de entrega, o ``None`` (sin punto, o escrito a mano)."""
        self.ensure_one()
        if self.dcasa_ubic_origen in (False, 'escrita'):
            return None
        return geo.punto(self.partner_latitude, self.partner_longitude)

    def _dcasa_poner_ubicacion(self, lat, lon, origen, precision=None, referencia=None, confirmada=True,
                               nombre_lugar=None, direccion=None):
        """Guarda el punto de entrega (con ``sudo``: lo llaman el checkout, la página del enlace, la API de Juan y
        Brian después de comprobar quién es). ``UbicacionInvalida`` si el punto no sirve.

        Devuelve la zona (``dcasa.ubicacion._zona``) con ``aviso`` vacío: el que compara lo escrito lo arma quien
        tiene el texto."""
        self.ensure_one()
        if origen not in geo.ETIQUETAS or origen == 'escrita':
            raise ValueError(f'Origen de ubicación desconocido: {origen!r}')
        Ubicacion = self.env['dcasa.ubicacion']
        lat, lon, zona = Ubicacion._validar(lat, lon)
        calle = Ubicacion._calle_de_google(lat, lon)
        if not calle:
            # WhatsApp manda el nombre y la dirección cuando el cliente elige un lugar en vez de su ubicación.
            calle = ', '.join(p for p in (geo.texto_corto(nombre_lugar, 120), geo.texto_corto(direccion, 200)) if p)
        valores = {
            'partner_latitude': lat, 'partner_longitude': lon,
            'dcasa_ubic_origen': origen,
            'dcasa_ubic_precision_m': geo.precision_m(precision) if origen == 'gps' else False,
            'dcasa_ubic_fecha': fields.Datetime.now(),
            'dcasa_ubic_confirmada': bool(confirmada),
            'dcasa_ubic_lugar_id': zona['lugar'].id or False,
            'dcasa_ubic_zona': zona['texto'] or False,
            'dcasa_barriada': zona['barriada'] or False,
            'dcasa_corregimiento': zona['corregimiento'] or False,
            'dcasa_distrito': zona['distrito'] or False,
            'dcasa_provincia': zona['provincia'] or False,
            'dcasa_ubic_direccion_mapa': calle or False,
        }
        if referencia is not None:
            valores['dcasa_referencia'] = geo.texto_corto(referencia, geo.MAX_REFERENCIA) or False
        if zona['distrito'] and not self.city:
            valores['city'] = zona['distrito']
        self.sudo().write(valores)
        self._dcasa_ubic_al_dia_en_ventas()
        return zona

    def _dcasa_ubic_al_dia_en_ventas(self):
        """Las ventas confirmadas que van a esta dirección y TODAVÍA no se entregan quedan con su entrega armada (para
        el QR). Las ya entregadas no se tocan: su página se cierra sola (``dcasa.ubicacion.entrega._abierta``)."""
        ordenes = self.env['sale.order'].sudo().search([('partner_shipping_id', '=', self.id), ('state', '=', 'sale')],
                                                       limit=20, order='id desc')
        for orden in ordenes:
            salidas = orden.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel')
            if salidas and all(p.state == 'done' for p in salidas):
                continue
            orden._dcasa_entrega_chofer()

    def _dcasa_poner_quien_recibe(self, recibe=None, telefono=None, al_dia=True):
        """Guarda quién recibe y el teléfono de respaldo (con ``sudo``: lo llaman el checkout, la página del enlace,
        Juan y Brian después de comprobar quién es). ``None`` no toca ese dato; ``''`` lo borra. El teléfono se guarda
        bien escrito («+507 6123-4567»); si no es de Panamá, ``TelefonoInvalido`` y no se guarda nada.

        Con ``al_dia`` las ventas confirmadas que van a esta dirección quedan con su entrega armada (como la
        referencia). Devuelve lo que se escribió."""
        self.ensure_one()
        valores = {}
        if recibe is not None:
            valores['dcasa_recibe'] = casa.recibe_limpio(recibe) or False
        if telefono is not None:
            texto = geo.texto_corto(telefono, casa.MAX_TELEFONO)
            numero = casa.telefono_de_respaldo(texto) if texto else None
            if texto and not numero:
                raise casa.TelefonoInvalido(casa.MENSAJE_TELEFONO)
            valores['dcasa_tel_respaldo'] = numero['guardar'] if numero else False
        if valores:
            self.sudo().write(valores)
            if al_dia:
                self._dcasa_ubic_al_dia_en_ventas()
        return valores

    def _dcasa_poner_fachada(self, datos):
        """Guarda la foto de la fachada que mandó el cliente (``datos``: los bytes tal cual llegaron). Se limpia y se
        achica antes (``casa.procesar_foto``: sin EXIF, que lleva el GPS); la nueva reemplaza a la anterior (Odoo cambia
        el contenido del mismo adjunto; el objeto viejo de R2 lo recoge su limpieza, nunca se borra al momento).
        ``FotoInvalida`` si no es una foto que se pueda abrir o pesa demasiado."""
        self.ensure_one()
        partner = self.sudo()
        hoy = fields.Date.context_today(partner)
        subidas = partner.dcasa_fachada_hoy if partner.dcasa_fachada_dia == hoy else 0
        if subidas >= casa.MAX_FOTOS_POR_DIA:
            raise casa.FotoInvalida('muchas')
        jpeg = casa.procesar_foto(datos)
        partner.write({'dcasa_fachada': base64.b64encode(jpeg), 'dcasa_fachada_fecha': fields.Datetime.now(),
                       'dcasa_fachada_dia': hoy, 'dcasa_fachada_hoy': subidas + 1})
        partner.message_post(body=Markup('<p>%s</p>') % escape(self.env._(
            '📷 El cliente subió la foto de su casa para el chofer (en la pestaña «Ubicación de entrega»).')),
            subtype_xmlid='mail.mt_note')
        return len(jpeg)

    def _dcasa_quitar_fachada(self):
        """Quita la foto de la fachada de la ficha (el objeto de R2 lo recoge su limpieza a los 45 días)."""
        self.ensure_one()
        if self.sudo().dcasa_fachada_fecha:
            self.sudo().write({'dcasa_fachada': False, 'dcasa_fachada_fecha': False})
            return True
        return False

    def _dcasa_fachada_jpeg(self):
        """Los bytes del JPEG de la fachada, o ``None``."""
        self.ensure_one()
        partner = self.sudo()
        if not partner.dcasa_fachada_fecha or not partner.dcasa_fachada:
            return None
        return base64.b64decode(partner.dcasa_fachada)

    def action_dcasa_quitar_fachada(self):
        """Panel: quita la foto de la casa (si el cliente lo pide o la foto no sirve)."""
        self.ensure_one()
        self.check_access('write')
        self._dcasa_quitar_fachada()
        return True

    def _dcasa_poner_escrita(self, referencia=None):
        """El cliente prefirió escribir la dirección: sin punto (el chofer llama antes)."""
        self.ensure_one()
        valores = {'dcasa_ubic_origen': 'escrita', 'dcasa_ubic_confirmada': False, 'dcasa_ubic_lugar_id': False,
                   'dcasa_ubic_precision_m': False, 'dcasa_ubic_fecha': fields.Datetime.now(),
                   'dcasa_ubic_direccion_mapa': False, 'dcasa_ubic_zona': False,
                   'partner_latitude': 0.0, 'partner_longitude': 0.0}
        if referencia is not None:
            valores['dcasa_referencia'] = geo.texto_corto(referencia, geo.MAX_REFERENCIA) or False
        self.sudo().write(valores)
        self._dcasa_ubic_al_dia_en_ventas()

    def action_dcasa_enlace_ubicacion(self):
        """Panel: crea el enlace de un solo uso y lo muestra para copiarlo y mandárselo al cliente."""
        self.ensure_one()
        self.check_access('write')
        _enlace, url = self.env['dcasa.ubicacion.enlace']._crear(self.sudo(), creado_por='equipo')
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'info', 'sticky': True, 'title': self.env._('Enlace para marcar la ubicación (vence en 24 horas)'),
            'message': url}}

    def _dcasa_ubic_aviso_para_el_equipo(self):
        """Lo que ve el equipo en el chat de Odoo cuando llega la ubicación (un aviso del sistema: no sale por el
        canal). Sin coordenadas: la ruta (Waze y Google Maps) está en la ficha y en la venta."""
        self.ensure_one()
        partner = self.sudo()
        precio = self.env['dcasa.ubicacion']._precio(partner.dcasa_ubic_lugar_id)
        zona = (partner.dcasa_ubic_zona or self.env._('sin zona de la tabla')).replace(' · ', ', ')
        partes = [self.env._('📍 Ubicación de entrega: %s.', zona)]
        if partner.parent_id and (partner.dcasa_otra_casa or partner.type == 'delivery'):
            partes.append(self.env._('📦 Es la dirección «%s»: en la venta, elígela como dirección de entrega.',
                                     partner.name or ''))
        if partner.dcasa_ubic_direccion_mapa:
            partes.append(self.env._('Según el mapa: %s.', partner.dcasa_ubic_direccion_mapa))
        partes.append(self.env._('🏠 %s.', partner.dcasa_referencia) if partner.dcasa_referencia
                      else self.env._('🏠 Falta el número de casa y las indicaciones.'))
        if partner.dcasa_recibe:
            partes.append(self.env._('👤 Recibe: %s.', partner.dcasa_recibe))
        if partner.dcasa_tel_respaldo:
            partes.append(self.env._('📞 Otro teléfono: %s.', partner.dcasa_tel_respaldo))
        partes.append(self.env._('Punto: %s.', partner.dcasa_ubic_etiqueta or ''))
        partes.append(self.env._('🚚 Envío %s.', precio['total_txt']) if precio['con_precio']
                      else self.env._('🚚 Envío por cotizar.'))
        partes.append(self.env._('La ruta (Waze y Google Maps): en la ficha › Ubicación de entrega o «Ruta del '
                                 'chofer» en la venta.'))
        return ' '.join(partes)

    def _dcasa_abrir_ruta(self, cual):
        """La ruta de Waze o de Google Maps hasta el punto, en una pestaña nueva (solo el equipo de ventas)."""
        self.ensure_one()
        if not self.env.user.has_group('sales_team.group_sale_salesman'):
            raise AccessError(self.env._('Solo el equipo de ventas abre la ruta de la entrega.'))
        self.check_access('read')
        punto = self.sudo()._dcasa_ubic_punto()
        if not punto:
            raise UserError(self.env._('Esta ficha todavía no tiene su casa marcada en el mapa.'))
        return {'type': 'ir.actions.act_url', 'url': geo.enlaces(*punto)[cual], 'target': 'new'}

    def action_dcasa_abrir_waze(self):
        return self._dcasa_abrir_ruta('waze')

    def action_dcasa_abrir_google_maps(self):
        return self._dcasa_abrir_ruta('google')

    def _dcasa_ubic_resumen(self):
        """Lo que se muestra de la entrega (panel, Brian, la página del chofer): sin ids internos."""
        self.ensure_one()
        partner = self.sudo()
        punto = partner._dcasa_ubic_punto()
        direccion = ', '.join(p for p in (partner.street, partner.street2, partner.city) if p)
        resumen = {
            'tiene_punto': punto is not None,
            'origen': partner.dcasa_ubic_etiqueta or '',
            # Un solo criterio en todo el módulo (auditoría 1): el de los avisos (models/avisos.py).
            'confiable': partner._dcasa_ubic_confiable(),
            'confirmada': bool(partner.dcasa_ubic_confirmada),
            'zona': partner.dcasa_ubic_zona or geo.zona_texto({
                'barriada': partner.dcasa_barriada, 'corregimiento': partner.dcasa_corregimiento,
                'distrito': partner.dcasa_distrito, 'provincia': partner.dcasa_provincia}),
            'direccion': direccion,
            'direccion_mapa': partner.dcasa_ubic_direccion_mapa or '',
            'referencia': partner.dcasa_referencia or '',
            'recibe': partner.dcasa_recibe or '',
            'telefono_respaldo': partner.dcasa_tel_respaldo or '',
            'tiene_foto_fachada': bool(partner.dcasa_fachada_fecha),
        }
        if punto:
            resumen['enlaces'] = geo.enlaces(*punto)
        return resumen
