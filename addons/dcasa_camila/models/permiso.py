"""El permiso del cliente para recibir novedades por correo (decisión de la dueña, 2026-11-06).

Solo se le escribe a quien dijo que sí, con **cuándo, por dónde, con quién y a qué correo** (el mismo patrón que el
consentimiento de Meta en ``dcasa_meta_eventos``). Vive en la ficha comercial (``commercial_partner_id``), con
historial:

* **Formas de decir que sí** en la etapa 1: la casilla de la ficha (la marca la vendedora cuando el cliente se lo
  dice: «tienda»), el enlace firmado «Sí, quiero» al pie del correo de la factura o de la bienvenida («factura»,
  «bienvenida») y el correo que dio cuando Sofía se lo pidió para avisarle de promociones («sofia_whatsapp»: solo si el
  mensaje que de verdad salió tenía la frase de la plantilla; ``_dcasa_promos_de_sofia``). «web» queda para la etapa
  siguiente.
* **El permiso es del correo** al que se dio (``dcasa_promos_correo``): si la ficha cambia de correo, al nuevo no le
  llega nada hasta que vuelva a decir que sí. Sin un correo bien escrito no se marca.
* **Una baja se respeta siempre, por correo y no ficha por ficha**: si CUALQUIER ficha con ese correo (otra repetida,
  una archivada, un contacto hijo, la de su empresa) se dio de baja o pidió que no la contacten, ese correo no recibe
  campañas, no se vuelve a dar de alta y la baja sube a Resend. Es final en esta etapa. Llega del enlace de Resend en
  cada campaña (lo lee el cron y, siempre, el envío antes de mandar) o del botón «Darle de baja» de la ficha.
* **La casilla, una ficha a la vez** y solo desde la ficha (ni en grupo por RPC ni importando). Desmarcarla quita el
  permiso pero NO es la baja: la baja final solo sale del botón, que pide confirmación.
* Los campos no se escriben a mano ni por RPC: solo el sistema, desde la casilla, el botón, el enlace o el cron.
* Al fusionar dos fichas se conserva el permiso más reciente y cualquier baja manda (``partner_merge.py``).
* **Etapa 1b (decisión de la dueña, 2026-11-06): la lista crece sola**, sin marcar a nadie de golpe. Dos caminos
  nuevos: **«En la venta»** (``venta``: Odoo le pregunta a la persona del equipo al confirmar una venta o registrar un
  pago desde la pantalla, ``pregunta.py``) y **«WhatsApp (Juan)»** (``juan_whatsapp``: Juan lo pregunta y Odoo solo lo
  anota si el cliente contestó que sí a ESA pregunta, ``juan_permiso.py``). Queda con quién, cuándo y la referencia
  (la venta, el pago o el mensaje del cliente). Un «No» queda con su fecha y no se vuelve a preguntar en
  ``dcasa_camila.dias_entre_preguntas`` días (180 de fábrica); Juan tampoco pregunta dos veces en ese plazo.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.dcasa_correo.models.correo import correo_valido
from odoo.addons.dcasa_sofia.models import reglas as reglas_sofia
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain

from . import reglas as R

_logger = logging.getLogger(__name__)

ORIGENES = [
    ('tienda', 'En la tienda (lo marcó la vendedora)'),
    ('factura', 'Enlace del correo de su factura'),
    ('bienvenida', 'Enlace del correo de bienvenida'),
    ('sofia_whatsapp', 'WhatsApp (pidió Sofía)'),
    ('web', 'Sitio web'),
    ('venta', 'En la venta (se le preguntó al confirmar o cobrar)'),
    ('juan_whatsapp', 'WhatsApp (Juan)'),
]
ORIGENES_BAJA = [
    ('correo', 'Con el enlace del correo de la campaña'),
    ('ficha', 'Lo pidió y se anotó en su ficha'),
]
CAMPOS_PERMISO = frozenset({
    'dcasa_promos_fecha', 'dcasa_promos_origen', 'dcasa_promos_usuario_id', 'dcasa_promos_correo',
    'dcasa_promos_baja_fecha', 'dcasa_promos_baja_origen', 'dcasa_promos_baja_usuario_id',
    'dcasa_promos_referencia', 'dcasa_promos_no_fecha', 'dcasa_promos_pregunta_fecha',
})
SIN_PERMISO = {'dcasa_promos_fecha': False, 'dcasa_promos_origen': False, 'dcasa_promos_usuario_id': False,
               'dcasa_promos_correo': False, 'dcasa_promos_referencia': False}
# Cómo se llama cada camino en la pantalla de Camila (los conteos de la etapa 1b). «web» solo si hay alguno.
CAMINOS = [('venta', 'En la venta'), ('juan_whatsapp', 'Juan (WhatsApp)'), ('factura', 'Enlace de la factura'),
           ('bienvenida', 'Enlace de bienvenida'), ('sofia_whatsapp', 'Sofía (WhatsApp)'),
           ('tienda', 'Casilla de la ficha'), ('web', 'Sitio web')]
# Cuántos días no se vuelve a preguntar a quien dijo que no (y Juan, a quien ya preguntó): un ajuste.
P_DIAS_PREGUNTA = 'dcasa_camila.dias_entre_preguntas'
DIAS_PREGUNTA = 180
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
    dcasa_promos_correo = fields.Char(
        'Novedades: correo al que dijo que sí', readonly=True, copy=False, tracking=True,
        help='El permiso es de este correo: si la ficha cambia de correo, al nuevo no le llega nada hasta que el '
             'cliente vuelva a decir que sí.')
    dcasa_promos_referencia = fields.Char(
        'Novedades: dónde dijo que sí', readonly=True, copy=False, tracking=True,
        help='La venta, el pago o el mensaje del chat en que el cliente dijo que sí.')
    dcasa_promos_no_fecha = fields.Datetime(
        'Novedades: dijo que no el', readonly=True, copy=False, tracking=True,
        help='No se le vuelve a preguntar hasta que pasen los días del ajuste (180 de fábrica).')
    dcasa_promos_pregunta_fecha = fields.Datetime(
        'Novedades: se le preguntó el', readonly=True, copy=False,
        help='La última vez que se le preguntó (en la venta o por WhatsApp).')
    dcasa_promos_baja_fecha = fields.Datetime(
        'Novedades: se dio de baja el', readonly=True, copy=False, tracking=True,
        help='Con baja no se le vuelve a escribir ninguna campaña: es final.')
    dcasa_promos_baja_origen = fields.Selection(ORIGENES_BAJA, 'Novedades: cómo se dio de baja', readonly=True,
                                                copy=False, tracking=True)
    dcasa_promos_baja_usuario_id = fields.Many2one('res.users', 'Novedades: anotó la baja', readonly=True, copy=False,
                                                   tracking=True, ondelete='set null')
    dcasa_promos = fields.Boolean(
        'Quiere recibir novedades por correo', compute='_compute_dcasa_promos', inverse='_inverse_dcasa_promos',
        help='Márcalo solo si el cliente dijo que sí. Queda con la fecha, con tu nombre y con su correo.')
    dcasa_promos_estado = fields.Selection(
        [('sin', 'Sin permiso'), ('si', 'Con permiso'), ('otro_correo', 'Cambió de correo'),
         ('baja', 'Se dio de baja')], 'Novedades por correo', compute='_compute_dcasa_promos_estado')

    # ------------------------------------------------------------------
    # El estado y la casilla
    # ------------------------------------------------------------------

    def _dcasa_promos_estado_de(self, bloqueos):
        """El estado de UNA ficha comercial (sudo) con los bloqueos por correo ya leídos."""
        correo = correo_valido(self.email)
        if self.dcasa_promos_baja_fecha or (correo and bloqueos.get(correo) == 'baja'):
            return 'baja'
        if self.dcasa_promos_fecha:
            return 'si' if correo and correo == self.dcasa_promos_correo else 'otro_correo'
        return 'sin'

    def _dcasa_promos_estados(self):
        """``{partner: estado}`` con una sola consulta de bajas por correo."""
        fichas = self.commercial_partner_id.sudo()
        bloqueos = self._dcasa_promos_bloqueos_por_correo(correo_valido(f.email) for f in fichas)
        return {partner: partner.commercial_partner_id.sudo()._dcasa_promos_estado_de(bloqueos) for partner in self}

    @api.depends('commercial_partner_id.dcasa_promos_fecha', 'commercial_partner_id.dcasa_promos_correo',
                 'commercial_partner_id.dcasa_promos_baja_fecha', 'commercial_partner_id.email')
    def _compute_dcasa_promos_estado(self):
        estados = self._dcasa_promos_estados()
        for partner in self:
            partner.dcasa_promos_estado = estados[partner]

    # Aparte del estado: si compartieran el cálculo, leer el estado dentro del inverso volvería a calcular la casilla y
    # borraría lo que la persona acaba de marcar.
    @api.depends('commercial_partner_id.dcasa_promos_fecha', 'commercial_partner_id.dcasa_promos_correo',
                 'commercial_partner_id.dcasa_promos_baja_fecha', 'commercial_partner_id.email')
    def _compute_dcasa_promos(self):
        estados = self._dcasa_promos_estados()
        for partner in self:
            partner.dcasa_promos = estados[partner] == 'si'

    def _inverse_dcasa_promos(self):
        """Marcar: «tienda», con quién y a qué correo. Desmarcar: quita el permiso, sin baja (la baja es el botón).

        Una ficha a la vez y solo desde la ficha: ni muchas de una vez por RPC ni importando (la casilla es lo que el
        cliente le dijo a una persona)."""
        estados = self._dcasa_promos_estados()
        cambian = [p for p in self if p.dcasa_promos != (estados[p] == 'si')
                   and (p.dcasa_promos or estados[p] in ('si', 'otro_correo'))]
        if not cambian:
            return
        if len(self) > 1 or self.env.context.get('import_file'):
            raise UserError(self.env._(
                'La casilla de novedades se marca de una ficha a la vez, desde la ficha del cliente (ni en grupo ni '
                'importando): es lo que el cliente le dijo a una persona.'))
        partner = cambian[0]
        ficha = partner.commercial_partner_id
        if not partner.dcasa_promos:
            ficha._dcasa_promos_quitar(self.env.user)
            return
        if estados[partner] == 'baja':
            raise UserError(self.env._(
                'Este correo se dio de baja de las novedades (en esta ficha o en otra con el mismo correo): no se le '
                'vuelve a escribir.'))
        if not correo_valido(ficha.sudo().email):
            raise UserError(self.env._(
                'Para marcarla, la ficha necesita un correo bien escrito: el permiso es de ese correo.'))
        ficha._dcasa_promos_registrar('tienda', self.env.user)

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
    # Anotar el sí, quitarlo y la baja
    # ------------------------------------------------------------------

    def _dcasa_promos_registrar(self, origen, usuario=None, fecha=None, referencia=None):
        """Anota el «sí» en la ficha comercial (con quién, cuándo y a qué correo). Exige poder escribir la ficha (salvo
        el sistema).

        Nunca toca una ficha sin correo bien escrito, una que ya dijo que sí con ese mismo correo, ni una cuyo correo se
        dio de baja en CUALQUIER ficha (la baja es final). Si dijo que sí con otro correo, queda el «sí» del nuevo.
        Devuelve las fichas que quedaron con el permiso nuevo."""
        if origen not in dict(ORIGENES):
            raise ValueError(origen)
        if not self.env.su:
            self.check_access('write')
        fichas = self.commercial_partner_id.sudo()
        correos = {ficha: correo_valido(ficha.email) for ficha in fichas}
        bloqueos = self._dcasa_promos_bloqueos_por_correo(correos.values())
        nuevas = fichas.filtered(lambda f: correos[f] and not f.dcasa_promos_baja_fecha
                                 and bloqueos.get(correos[f]) != 'baja'
                                 and not (f.dcasa_promos_fecha and f.dcasa_promos_correo == correos[f]))
        usuario = usuario if usuario and not usuario._is_public() else self.env['res.users']
        for ficha in nuevas:
            ficha.write({
                'dcasa_promos_fecha': fecha or fields.Datetime.now(),
                'dcasa_promos_origen': origen,
                'dcasa_promos_usuario_id': usuario.id or False,
                'dcasa_promos_correo': correos[ficha],
                'dcasa_promos_referencia': (referencia or '')[:120] or False,
                'dcasa_promos_pregunta_fecha': fields.Datetime.now(),
                'dcasa_promos_no_fecha': False,
            })
        return nuevas

    # ------------------------------------------------------------------
    # Preguntar (etapa 1b): en la venta y por WhatsApp
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_promos_dias_pregunta(self):
        """Los días sin volver a preguntar (``dcasa_camila.dias_entre_preguntas``, 180 de fábrica; de 1 a 3650)."""
        valor = self.env['ir.config_parameter'].sudo().get_param(P_DIAS_PREGUNTA)
        try:
            dias = int(valor) if valor not in (None, False, '') else DIAS_PREGUNTA
        except (TypeError, ValueError):
            dias = DIAS_PREGUNTA
        return min(max(dias, 1), 3650)

    def _dcasa_promos_motivo_para_no_preguntar(self, juan=False):
        """``None`` si a esta ficha se le puede preguntar si quiere las novedades; si no, por qué (para las pruebas y
        el registro). No se pregunta: a una ficha archivada o de empresa (sin persona), del equipo, que ya tiene permiso
        con su correo de hoy, con baja o «no contactar» (por correo, en cualquier ficha), ni a quien dijo que no hace
        menos del ajuste. ``juan``: tampoco si ya se le preguntó en ese plazo (Juan pregunta una vez)."""
        self.ensure_one()
        ficha = self.commercial_partner_id.sudo()
        if not ficha.active or ficha.is_company:
            return 'empresa'
        equipo = self.env['res.users'].sudo().with_context(active_test=False).search(
            [('partner_id', '=', ficha.id)], limit=1)
        correo = correo_valido(ficha.email)
        if (equipo and not equipo.share) or ficha in self.env['res.company'].sudo().search([]).partner_id \
                or (correo and correo in self._dcasa_correos_del_equipo()):
            return 'equipo'
        if ficha.dcasa_no_contactar or ficha.dcasa_promos_baja_fecha:
            return 'baja'
        if correo:
            bloqueo = self._dcasa_promos_bloqueos_por_correo([correo]).get(correo)
            if bloqueo:
                return 'baja'
            if ficha.dcasa_promos_fecha and ficha.dcasa_promos_correo == correo:
                return 'ya_dijo_que_si'
        corte = fields.Datetime.now() - timedelta(days=self._dcasa_promos_dias_pregunta())
        if ficha.dcasa_promos_no_fecha and ficha.dcasa_promos_no_fecha > corte:
            return 'dijo_que_no'
        if juan and ficha.dcasa_promos_pregunta_fecha and ficha.dcasa_promos_pregunta_fecha > corte:
            return 'ya_se_le_pregunto'
        return None

    def _dcasa_promos_anotar_pregunta(self):
        """Se le preguntó (hoy): Juan no vuelve a preguntar en el plazo del ajuste."""
        self.commercial_partner_id.sudo().write({'dcasa_promos_pregunta_fecha': fields.Datetime.now()})

    def _dcasa_promos_anotar_no(self):
        """Dijo que no: no se le vuelve a preguntar en el plazo del ajuste (no es la baja ni quita nada)."""
        ahora = fields.Datetime.now()
        self.commercial_partner_id.sudo().write({'dcasa_promos_no_fecha': ahora, 'dcasa_promos_pregunta_fecha': ahora})

    def _dcasa_promos_quitar(self, usuario=None):
        """Desmarcar la casilla: quita el permiso (queda en el historial de la ficha) sin anotar baja."""
        if not self.env.su:
            self.check_access('write')
        fichas = self.commercial_partner_id.sudo().filtered('dcasa_promos_fecha')
        if fichas:
            fichas.write(SIN_PERMISO)
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
        """Botón «Darle de baja» de la ficha (pide confirmación): una ficha a la vez, quien puede editar al cliente
        (check_access ANTES del sudo)."""
        if len(self) != 1:
            raise UserError(self.env._('La baja se anota de un cliente a la vez, desde su ficha.'))
        self.check_access('write')
        self._dcasa_promos_baja('ficha', self.env.user)
        return True

    # ------------------------------------------------------------------
    # A quién se le puede escribir
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_promos_bloqueos_por_correo(self, correos=None):
        """``{correo: 'baja' | 'no_contactar'}``: los correos que no reciben campañas por NINGUNA ficha.

        Mira todas las fichas con ese correo (archivadas y contactos hijos incluidos): basta que una, o la ficha de su
        empresa, se haya dado de baja o haya pedido que no la contacten. Con ``correos`` solo mira esos (vacío:
        nada)."""
        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        dominio = Domain.OR([
            [('dcasa_promos_baja_fecha', '!=', False)],
            [('commercial_partner_id.dcasa_promos_baja_fecha', '!=', False)],
            [('dcasa_no_contactar', '=', True)], [('commercial_partner_id.dcasa_no_contactar', '=', True)]])
        if correos is not None:
            correos = sorted({correo for correo in correos if correo})
            if not correos:
                return {}
            dominio = Domain.AND([[('email_normalized', 'in', correos)], dominio])
        salida = {}
        for partner in Partner.search(dominio):
            baja = partner.dcasa_promos_baja_fecha or partner.commercial_partner_id.dcasa_promos_baja_fecha
            for correo in {correo_valido(partner.email), partner.email_normalized} - {None, False, ''}:
                if salida.get(correo) != 'baja':
                    salida[correo] = 'baja' if baja else 'no_contactar'
        return salida

    @api.model
    def _dcasa_promos_dominio(self):
        """Fichas comerciales activas con permiso, sin baja, con correo y que no pidieron que no las contacten."""
        return [('active', '=', True), ('parent_id', '=', False), ('dcasa_promos_fecha', '!=', False),
                ('dcasa_promos_correo', '!=', False), ('dcasa_promos_baja_fecha', '=', False),
                ('email_normalized', '!=', False), ('dcasa_no_contactar', '=', False)]

    @api.model
    def _dcasa_promos_con_permiso(self):
        """``{correo: ficha}`` de quienes reciben la campaña: un correo una sola vez, bien escrito, el MISMO al que dijo
        que sí, sin baja ni «no contactar» en ninguna ficha con ese correo y nunca del equipo (usuarios internos y la
        empresa propia)."""
        del_equipo = self._dcasa_correos_del_equipo()
        bloqueos = self._dcasa_promos_bloqueos_por_correo()
        salida = {}
        for ficha in self.sudo().search(self._dcasa_promos_dominio(), order='dcasa_promos_fecha, id'):
            correo = correo_valido(ficha.email)
            if correo and correo == ficha.dcasa_promos_correo and correo not in del_equipo \
                    and correo not in bloqueos and correo not in salida:
                salida[correo] = ficha
        return salida

    # ------------------------------------------------------------------
    # El correo que dio cuando Sofía se lo pidió
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_pedido_de_sofia(self, propuesta):
        """El mensaje que DE VERDAD salió de la propuesta de Sofía que pedía sus datos (o un registro vacío).

        * «Enviar ya»: el que se guardó al enviarlo (``dcasa_camila_mensaje_id``).
        * «Abrir el chat»: el PRIMER mensaje de la vendedora en ese chat después de aprobarla (la vendedora pudo
          cambiar el texto o escribir otra cosa: cuenta lo que salió primero)."""
        Mensaje = self.env['dcasa.mensaje'].sudo()
        conv = propuesta.conversacion_id
        if propuesta.accion == 'enviar':
            mensaje = propuesta.dcasa_camila_mensaje_id.sudo()
            return mensaje if mensaje.conversacion_id == conv else Mensaje
        return Mensaje.search([
            ('conversacion_id', '=', conv.id), ('autor', '=', 'vendedora'), ('tipo', '=', 'mensaje'),
            ('estado_envio', '=', 'enviado'), ('ts', '>=', propuesta.resuelta_en - HOLGURA_ENVIO),
            ('ts', '<=', propuesta.resuelta_en + timedelta(hours=HORAS_PARA_CONTESTAR))], order='ts, id', limit=1)

    @api.model
    def _dcasa_promos_de_sofia(self, dias=DIAS_DE_PEDIDOS):
        """Anota el permiso de quien dio su correo cuando Sofía se lo pidió «para avisarle de promociones».

        Cuenta solo si el mensaje que de verdad salió de esa propuesta (``_dcasa_pedido_de_sofia``) tenía la frase de
        la plantilla («te avisamos de promociones», sin negar) y le pedía el correo, y el cliente contestó hasta 2 días
        después con el MISMO correo que hoy tiene su ficha. Fecha: la de su respuesta; origen «WhatsApp (pidió Sofía)»;
        con quién: la persona que le escribió. Nunca da de alta a quien se dio de baja. Devuelve cuántas fichas
        quedaron con permiso."""
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
            if not ficha or ficha != propuesta.partner_id.commercial_partner_id or ficha.dcasa_promos_baja_fecha:
                continue
            correo = correo_valido(ficha.email)
            if not correo or (ficha.dcasa_promos_fecha and ficha.dcasa_promos_correo == correo):
                continue
            pedido = self._dcasa_pedido_de_sofia(propuesta)
            if not pedido or pedido.estado_envio != 'enviado' or not R.pide_correo_para_promociones(pedido.texto):
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
