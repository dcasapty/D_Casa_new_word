"""El permiso del cliente para recibir novedades por correo (decisión de la dueña, 2026-11-06).

Solo se le escribe a quien dijo que sí, con **cuándo, por dónde y con quién** (el mismo patrón que el consentimiento
de Meta en ``dcasa_meta_eventos``). Vive en la ficha comercial (``commercial_partner_id``), con historial:

* **Formas de decir que sí** en la etapa 1: la casilla de la ficha (la marca la vendedora cuando el cliente se lo
  dice: «tienda»), el enlace firmado «Sí, quiero» al pie del correo de la factura o de la bienvenida («factura»,
  «bienvenida») y el correo que dio cuando Sofía se lo pidió para avisarle de promociones («sofia_whatsapp»: solo si el
  texto que de verdad se le mandó lo decía; ``_dcasa_promos_de_sofia``). «web» queda para la etapa siguiente.
* **Una baja se respeta siempre** y es final en esta etapa: con baja, nada la vuelve a dar de alta (ni la casilla, ni
  el enlace, ni Sofía) y nunca sale en un segmento. Llega del enlace de Resend en cada campaña (lo lee el cron y,
  siempre, el envío antes de mandar) o se anota en la ficha («Darle de baja»); la de la ficha también se sube a Resend.
* Los campos no se escriben a mano ni por RPC: solo el sistema, desde la casilla, el botón, el enlace o el cron.
* Al fusionar dos fichas se conserva el permiso más reciente y cualquier baja manda (``partner_merge.py``).
"""
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.dcasa_correo.models.correo import correo_valido
from odoo.addons.dcasa_sofia.models import reglas as reglas_sofia
from odoo.exceptions import AccessError, UserError

from . import reglas as R

_logger = logging.getLogger(__name__)

ORIGENES = [
    ('tienda', 'En la tienda (lo marcó la vendedora)'),
    ('factura', 'Enlace del correo de su factura'),
    ('bienvenida', 'Enlace del correo de bienvenida'),
    ('sofia_whatsapp', 'WhatsApp (pidió Sofía)'),
    ('web', 'Sitio web'),
]
ORIGENES_BAJA = [
    ('correo', 'Con el enlace del correo de la campaña'),
    ('ficha', 'Lo pidió y se anotó en su ficha'),
]
CAMPOS_PERMISO = frozenset({
    'dcasa_promos_fecha', 'dcasa_promos_origen', 'dcasa_promos_usuario_id',
    'dcasa_promos_baja_fecha', 'dcasa_promos_baja_origen', 'dcasa_promos_baja_usuario_id',
})
# Sofía: lo que el cliente contesta hasta 2 días después de que se le pidió (como Sofía, docs/SOFIA.md) y hasta cuándo
# se miran sus pedidos (lo de antes ya quedó anotado en una vuelta anterior del cron).
HORAS_PARA_CONTESTAR = 48
DIAS_DE_PEDIDOS = 30
HOLGURA_ENVIO = timedelta(minutes=5)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dcasa_promos_fecha = fields.Datetime(
        'Novedades: dijo que sí el', readonly=True, copy=False, tracking=True,
        help='Si tiene fecha (y no se dio de baja), puede recibir las campañas de novedades por correo.')
    dcasa_promos_origen = fields.Selection(ORIGENES, 'Novedades: por dónde', readonly=True, copy=False, tracking=True)
    dcasa_promos_usuario_id = fields.Many2one('res.users', 'Novedades: lo registró', readonly=True, copy=False,
                                              tracking=True, ondelete='set null')
    dcasa_promos_baja_fecha = fields.Datetime(
        'Novedades: se dio de baja el', readonly=True, copy=False, tracking=True,
        help='Con baja no se le vuelve a escribir ninguna campaña: es final.')
    dcasa_promos_baja_origen = fields.Selection(ORIGENES_BAJA, 'Novedades: cómo se dio de baja', readonly=True,
                                                copy=False, tracking=True)
    dcasa_promos_baja_usuario_id = fields.Many2one('res.users', 'Novedades: anotó la baja', readonly=True, copy=False,
                                                   tracking=True, ondelete='set null')
    dcasa_promos = fields.Boolean(
        'Quiere recibir novedades por correo', compute='_compute_dcasa_promos', inverse='_inverse_dcasa_promos',
        help='Márcalo solo si el cliente dijo que sí. Queda con la fecha y con tu nombre.')
    dcasa_promos_estado = fields.Selection(
        [('sin', 'Sin permiso'), ('si', 'Con permiso'), ('baja', 'Se dio de baja')], 'Novedades por correo',
        compute='_compute_dcasa_promos_estado')

    @api.depends('commercial_partner_id.dcasa_promos_fecha', 'commercial_partner_id.dcasa_promos_baja_fecha')
    def _compute_dcasa_promos_estado(self):
        for partner in self:
            ficha = partner.commercial_partner_id.sudo()
            if ficha.dcasa_promos_baja_fecha:
                partner.dcasa_promos_estado = 'baja'
            elif ficha.dcasa_promos_fecha:
                partner.dcasa_promos_estado = 'si'
            else:
                partner.dcasa_promos_estado = 'sin'

    # Aparte del estado: si compartieran el cálculo, leer el estado dentro del inverso volvería a calcular la casilla y
    # borraría lo que la persona acaba de marcar.
    @api.depends('commercial_partner_id.dcasa_promos_fecha', 'commercial_partner_id.dcasa_promos_baja_fecha')
    def _compute_dcasa_promos(self):
        for partner in self:
            ficha = partner.commercial_partner_id.sudo()
            partner.dcasa_promos = bool(ficha.dcasa_promos_fecha and not ficha.dcasa_promos_baja_fecha)

    def _inverse_dcasa_promos(self):
        for partner in self:
            quiere = partner.dcasa_promos
            ficha = partner.commercial_partner_id
            guardado = ficha.sudo()
            tiene, baja = bool(guardado.dcasa_promos_fecha), bool(guardado.dcasa_promos_baja_fecha)
            if quiere and baja:
                raise UserError(self.env._(
                    'Este cliente se dio de baja de las novedades: no se le vuelve a escribir.'))
            if quiere and not tiene:
                ficha._dcasa_promos_registrar('tienda', self.env.user)
            elif not quiere and tiene and not baja:
                ficha._dcasa_promos_baja('ficha', self.env.user)

    def write(self, vals):
        """El permiso solo lo escribe el sistema (la casilla, el botón, el enlace o el cron), nunca a mano."""
        if CAMPOS_PERMISO.intersection(vals) and not self.env.su:
            raise AccessError(self.env._(
                'El permiso de novedades se marca con su casilla y la baja con su botón; no se escribe a mano.'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(CAMPOS_PERMISO.intersection(vals) for vals in vals_list):
            raise AccessError(self.env._('El permiso de novedades no se escribe a mano.'))
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Anotar el sí y la baja
    # ------------------------------------------------------------------

    def _dcasa_promos_registrar(self, origen, usuario=None, fecha=None):
        """Anota el «sí» en la ficha comercial (con quién y cuándo). Exige poder escribir la ficha (salvo el sistema).

        Nunca toca una ficha que ya dijo que sí ni una que se dio de baja (la baja es final). Devuelve las fichas que
        quedaron con el permiso nuevo."""
        if origen not in dict(ORIGENES):
            raise ValueError(origen)
        if not self.env.su:
            self.check_access('write')
        fichas = self.commercial_partner_id.sudo().filtered(
            lambda f: not f.dcasa_promos_fecha and not f.dcasa_promos_baja_fecha)
        usuario = usuario if usuario and not usuario._is_public() else self.env['res.users']
        if fichas:
            fichas.write({
                'dcasa_promos_fecha': fecha or fields.Datetime.now(),
                'dcasa_promos_origen': origen,
                'dcasa_promos_usuario_id': usuario.id or False,
            })
        return fichas

    def _dcasa_promos_baja(self, origen, usuario=None, fecha=None):
        """Anota la baja (final). La ficha la anota quien puede escribirla; el enlace de Resend, el sistema."""
        if origen not in dict(ORIGENES_BAJA):
            raise ValueError(origen)
        if not self.env.su:
            self.check_access('write')
        fichas = self.commercial_partner_id.sudo().filtered(lambda f: not f.dcasa_promos_baja_fecha)
        usuario = usuario if usuario and not usuario._is_public() else self.env['res.users']
        if fichas:
            fichas.write({
                'dcasa_promos_baja_fecha': fecha or fields.Datetime.now(),
                'dcasa_promos_baja_origen': origen,
                'dcasa_promos_baja_usuario_id': usuario.id or False,
            })
        return fichas

    def action_dcasa_promos_baja(self):
        """Botón «Darle de baja» de la ficha: quien puede editar al cliente (check_access ANTES del sudo)."""
        self.check_access('write')
        self._dcasa_promos_baja('ficha', self.env.user)
        return True

    # ------------------------------------------------------------------
    # A quién se le puede escribir
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_promos_dominio(self):
        """Fichas comerciales activas con permiso, sin baja, con correo y que no pidieron que no las contacten."""
        return [('active', '=', True), ('parent_id', '=', False), ('dcasa_promos_fecha', '!=', False),
                ('dcasa_promos_baja_fecha', '=', False), ('email_normalized', '!=', False),
                ('dcasa_no_contactar', '=', False)]

    @api.model
    def _dcasa_promos_con_permiso(self):
        """``{correo: ficha}`` de quienes reciben la campaña: un correo una sola vez, bien escrito y nunca del equipo
        (usuarios internos y la empresa propia)."""
        del_equipo = self._dcasa_correos_del_equipo()
        salida = {}
        for ficha in self.sudo().search(self._dcasa_promos_dominio(), order='dcasa_promos_fecha, id'):
            correo = correo_valido(ficha.email)
            if correo and correo not in del_equipo and correo not in salida:
                salida[correo] = ficha
        return salida

    # ------------------------------------------------------------------
    # El correo que dio cuando Sofía se lo pidió
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_promos_de_sofia(self, dias=DIAS_DE_PEDIDOS):
        """Anota el permiso de quien dio su correo cuando Sofía se lo pidió «para avisarle de promociones».

        Cuenta solo si el mensaje que de verdad salió por el chat (Gerencia puede cambiar los textos de Sofía, y la
        vendedora puede cambiarlo antes de enviarlo) decía que era para promociones, y el cliente contestó hasta 2 días
        después con el MISMO correo que hoy tiene su ficha. Fecha: la de su respuesta; origen «WhatsApp (pidió
        Sofía)»; con quién: la persona que le escribió. Nunca da de alta a quien se dio de baja. Devuelve cuántas
        fichas quedaron con permiso."""
        if 'dcasa.sofia.propuesta' not in self.env:
            return 0
        desde = fields.Datetime.now() - timedelta(days=dias)
        propuestas = self.env['dcasa.sofia.propuesta'].sudo().search([
            ('pide_datos', '=', True), ('estado', '=', 'aplicada'), ('accion', 'in', ('enviar', 'chat')),
            ('resuelta_en', '>=', desde), ('conversacion_id', '!=', False), ('partner_id', '!=', False)],
            order='resuelta_en, id')
        Mensaje = self.env['dcasa.mensaje'].sudo()
        anotadas = 0
        for propuesta in propuestas:
            conv = propuesta.conversacion_id
            ficha = conv.partner_id.commercial_partner_id
            if not ficha or ficha != propuesta.partner_id.commercial_partner_id \
                    or ficha.dcasa_promos_fecha or ficha.dcasa_promos_baja_fecha:
                continue
            correo = correo_valido(ficha.email)
            if not correo:
                continue
            pedido = Mensaje.search([
                ('conversacion_id', '=', conv.id), ('autor', '=', 'vendedora'), ('tipo', '=', 'mensaje'),
                ('estado_envio', '=', 'enviado'), ('ts', '>=', propuesta.resuelta_en - HOLGURA_ENVIO),
                ('ts', '<=', propuesta.resuelta_en + timedelta(hours=HORAS_PARA_CONTESTAR))],
                order='ts, id', limit=20).filtered(lambda m: R.menciona_promociones(m.texto))[:1]
            if not pedido:
                continue
            respuestas = Mensaje.search([
                ('conversacion_id', '=', conv.id), ('autor', '=', 'cliente'), ('tipo', '=', 'mensaje'),
                ('ts', '>=', pedido.ts), ('ts', '<=', pedido.ts + timedelta(hours=HORAS_PARA_CONTESTAR)),
                ('texto', 'ilike', '@')], order='ts, id', limit=20)
            respuesta = respuestas.filtered(
                lambda m, correo=correo: correo in {correo_valido(c) for c in reglas_sofia.correos_en(m.texto)})[:1]
            if not respuesta:
                continue
            quien = pedido.usuario_id or propuesta.resuelta_por
            if ficha.with_context(active_test=False)._dcasa_promos_registrar(
                    'sofia_whatsapp', quien, fecha=respuesta.ts):
                anotadas += 1
        return anotadas

