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
* **Etapa 1b (decisiones de la dueña, 2026-11-06): la lista crece sola**, sin marcar a nadie de golpe.
  - **Se activa sola al agregar el correo** («en el momento en el que se añade un correo, ya debe activarse
    automáticamente»): cuando la ficha comercial pasa de no tener un correo bien escrito a tenerlo, o a otro distinto,
    queda con permiso y el origen honesto ``al_agregar_correo`` («Se activó sola al agregar su correo», con quién lo
    agregó), nunca «tienda». La ficha lo muestra así hasta que una persona lo confirma. Una ficha a la vez y solo si
    lo agrega una persona del equipo (o Juan con el correo que escribió el cliente): nunca importando, instalando
    módulos, en escrituras de muchas fichas, desde la web pública ni por el sistema (``SUPERUSER_ID``), y nada hacia
    atrás. Nunca con baja o «no contactar» de ese correo (en cualquier ficha) ni si alguien ya anotó un «no».
  - **El «no» queda anotado** (``dcasa_promos_no_*``: cuándo, por dónde y quién): desmarcar la casilla, el «no» en la
    venta o el que el cliente le dice a Juan. Con un «no», la casilla nunca se vuelve a activar sola (solo una persona
    puede volver a marcarla si el cliente cambia de idea).
  - **En la venta** (``pregunta.py``): al confirmar una venta o registrar un pago desde la pantalla, un cuadro con la
    casilla ya activada y su correo (si el cliente dijo que no, se desactiva); sin correo, «Sí / No» y lo pide.
  - **Juan** (``juan_permiso.py``) guarda el correo que el cliente escribió (se activa sola, y le avisa que puede decir
    que no) y honra siempre un «no». Nunca las activa por su cuenta.
"""
import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models
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
    ('venta', 'En la venta (al confirmar o cobrar)'),
    ('juan_whatsapp', 'WhatsApp (Juan)'),
    ('al_agregar_correo', 'Se activó sola al agregar su correo'),
]
# La activación automática (cambio de la dueña, 2026-11-06): nunca se registra como «tienda».
AUTOMATICO = 'al_agregar_correo'
# Dónde quedó el «no» (desmarcar la casilla, en la venta o con Juan): con él, la casilla no se activa sola nunca más.
ORIGENES_NO = [
    ('ficha', 'Desmarcó la casilla de su ficha'),
    ('venta', 'En la venta (al confirmar o cobrar)'),
    ('juan_whatsapp', 'Se lo dijo a Juan en el chat'),
]
ORIGENES_BAJA = [
    ('correo', 'Con el enlace del correo de la campaña'),
    ('ficha', 'Lo pidió y se anotó en su ficha'),
]
CAMPOS_PERMISO = frozenset({
    'dcasa_promos_fecha', 'dcasa_promos_origen', 'dcasa_promos_usuario_id', 'dcasa_promos_correo',
    'dcasa_promos_baja_fecha', 'dcasa_promos_baja_origen', 'dcasa_promos_baja_usuario_id',
    'dcasa_promos_referencia', 'dcasa_promos_no_fecha', 'dcasa_promos_no_origen', 'dcasa_promos_no_usuario_id',
    'dcasa_promos_pregunta_fecha',
})
SIN_PERMISO = {'dcasa_promos_fecha': False, 'dcasa_promos_origen': False, 'dcasa_promos_usuario_id': False,
               'dcasa_promos_correo': False, 'dcasa_promos_referencia': False}
# Cómo se llama cada camino en la pantalla de Camila (los conteos de la etapa 1b). «web» solo si hay alguno.
CAMINOS = [('al_agregar_correo', 'Al agregar su correo'), ('venta', 'En la venta'),
           ('juan_whatsapp', 'Juan (WhatsApp)'), ('factura', 'Enlace de la factura'),
           ('bienvenida', 'Enlace de bienvenida'), ('sofia_whatsapp', 'Sofía (WhatsApp)'),
           ('tienda', 'Casilla de la ficha'), ('web', 'Sitio web')]
# Cuántos días el cuadro de la venta no vuelve a salir (después de mostrarlo o de un «no»): un ajuste.
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
        help='Con un «no» la casilla ya no se activa sola al agregar un correo (solo una persona puede volver a '
             'marcarla) y el cuadro de la venta no sale hasta que pasen los días del ajuste (180 de fábrica).')
    dcasa_promos_no_origen = fields.Selection(ORIGENES_NO, 'Novedades: dónde dijo que no', readonly=True,
                                              copy=False, tracking=True)
    dcasa_promos_no_usuario_id = fields.Many2one('res.users', 'Novedades: anotó el no', readonly=True, copy=False,
                                                 tracking=True, ondelete='set null')
    dcasa_promos_pregunta_fecha = fields.Datetime(
        'Novedades: se le preguntó el', readonly=True, copy=False,
        help='La última vez que salió el cuadro de la venta para esta ficha.')
    dcasa_promos_baja_fecha = fields.Datetime(
        'Novedades: se dio de baja el', readonly=True, copy=False, tracking=True,
        help='Con baja no se le vuelve a escribir ninguna campaña: es final.')
    dcasa_promos_baja_origen = fields.Selection(ORIGENES_BAJA, 'Novedades: cómo se dio de baja', readonly=True,
                                                copy=False, tracking=True)
    dcasa_promos_baja_usuario_id = fields.Many2one('res.users', 'Novedades: anotó la baja', readonly=True, copy=False,
                                                   tracking=True, ondelete='set null')
    dcasa_promos = fields.Boolean(
        'Quiere recibir novedades por correo', compute='_compute_dcasa_promos', inverse='_inverse_dcasa_promos',
        help='Se activa sola al agregar su correo. Desmárcala si el cliente dice que no (queda anotado y ya no se '
             'activa sola). Queda con la fecha, con quién y con su correo.')
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
            ficha._dcasa_promos_anotar_no('ficha', self.env.user)
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
        """El permiso solo lo escribe el sistema (la casilla, el botón, el enlace o el cron), nunca a mano. Si una
        persona le agrega (o le cambia) el correo a UNA ficha, las novedades se activan solas
        (``_dcasa_promos_activar_al_agregar_correo``)."""
        if CAMPOS_PERMISO.intersection(vals) and not self.env.su:
            raise AccessError(self.env._(
                'El permiso de novedades se marca con su casilla y la baja con su botón; no se escribe a mano.'))
        vigilar = 'email' in vals and len(self) == 1 and self._dcasa_promos_auto_permitido()
        antes = correo_valido(self.commercial_partner_id.sudo().email) if vigilar else None
        resultado = super().write(vals)
        if vigilar:
            self._dcasa_promos_activar_al_agregar_correo(antes)
        return resultado

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(CAMPOS_PERMISO.intersection(vals) for vals in vals_list):
            raise AccessError(self.env._('El permiso de novedades no se escribe a mano.'))
        partners = super().create(vals_list)
        # Una ficha a la vez (crear muchas de una vez, p. ej. importando, nunca las activa) y solo la ficha comercial:
        # el correo de un contacto hijo no cambia el de su ficha.
        if len(partners) == 1 and partners.email and partners.commercial_partner_id == partners \
                and self._dcasa_promos_auto_permitido():
            partners._dcasa_promos_activar_al_agregar_correo(None)
        return partners

    # ------------------------------------------------------------------
    # Se activa sola al agregar el correo (cambio de la dueña, 2026-11-06)
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_promos_auto_permitido(self):
        """¿Esta escritura puede activar sola las novedades? Solo si la hace una persona del equipo (``uid`` interno,
        aunque el código use ``sudo``) y no es una importación, la instalación de un módulo (sus datos) ni el sistema
        (crones, scripts y migraciones corren como ``SUPERUSER_ID``): así nadie da de alta en bloque a los clientes
        de siempre. La web pública y el portal tampoco (alguien podría escribir el correo de otro en un formulario;
        el «sí» desde la web es la etapa siguiente). Juan, que no es del equipo, lo llama aparte con el correo que
        escribió el cliente (``juan_permiso.py``)."""
        contexto = self.env.context
        if contexto.get('import_file') or contexto.get('install_mode') or contexto.get('dcasa_promos_sin_auto') \
                or not self.env.registry.ready or self.env.uid == SUPERUSER_ID:
            return False
        return self.env.user._is_internal()

    def _dcasa_promos_motivo_para_no_activar(self):
        """``None`` si esta ficha puede quedar con las novedades activadas solas; si no, por qué: ``empresa``
        (archivada o de empresa, sin persona), ``equipo``, ``baja`` (baja o «no contactar» de su correo en CUALQUIER
        ficha, o de la ficha), ``dijo_que_no`` (alguien anotó un «no», de cuando sea), ``ya_confirmado`` (ya dijo que
        sí con su correo de hoy, por un camino que no es el automático) o ``ya_activada`` (ya se activó sola)."""
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
        if ficha.dcasa_no_contactar or ficha.dcasa_promos_baja_fecha \
                or (correo and self._dcasa_promos_bloqueos_por_correo([correo]).get(correo)):
            return 'baja'
        if ficha.dcasa_promos_no_fecha:
            return 'dijo_que_no'
        if correo and ficha.dcasa_promos_fecha and ficha.dcasa_promos_correo == correo:
            return 'ya_activada' if ficha.dcasa_promos_origen == AUTOMATICO else 'ya_confirmado'
        return None

    def _dcasa_promos_activar_al_agregar_correo(self, antes, usuario=None, referencia=None):
        """Si la ficha comercial ahora tiene un correo bien escrito distinto de ``antes``, activa las novedades con el
        origen honesto «Se activó sola al agregar su correo» y quién lo agregó (salvo los motivos de
        ``_dcasa_promos_motivo_para_no_activar``). Nunca hace fallar la escritura del correo. Devuelve las fichas que
        quedaron activadas."""
        vacio = self.browse()
        try:
            with self.env.cr.savepoint():
                ficha = self.commercial_partner_id.sudo()
                ahora = correo_valido(ficha.email)
                if len(ficha) != 1 or not ahora or ahora == antes or ficha._dcasa_promos_motivo_para_no_activar():
                    return vacio
                quien = usuario if usuario is not None else self.env.user
                return ficha._dcasa_promos_registrar(AUTOMATICO, quien, referencia=referencia)
        except Exception:   # noqa: BLE001 — guardar el correo (una venta, Sofía, Juan) nunca falla por esto
            _logger.warning('DCASA_CAMILA no se pudieron activar solas las novedades de la ficha %s', self.ids,
                            exc_info=True)
            return vacio

    # ------------------------------------------------------------------
    # Anotar el sí, quitarlo y la baja
    # ------------------------------------------------------------------

    def _dcasa_promos_registrar(self, origen, usuario=None, fecha=None, referencia=None):
        """Anota el «sí» en la ficha comercial (con quién, cuándo y a qué correo). Exige poder escribir la ficha (salvo
        el sistema).

        Nunca toca una ficha sin correo bien escrito, una que ya dijo que sí con ese mismo correo, ni una cuyo correo se
        dio de baja en CUALQUIER ficha (la baja es final). Si dijo que sí con otro correo, queda el «sí» del nuevo. Un
        «sí» de verdad (cualquier origen salvo el automático) reemplaza al que se activó solo con el mismo correo: es la
        persona que lo confirma. Un «sí» borra el «no» anterior. Devuelve las fichas que quedaron con el permiso
        nuevo."""
        if origen not in dict(ORIGENES):
            raise ValueError(origen)
        if not self.env.su:
            self.check_access('write')
        fichas = self.commercial_partner_id.sudo()
        correos = {ficha: correo_valido(ficha.email) for ficha in fichas}
        bloqueos = self._dcasa_promos_bloqueos_por_correo(correos.values())
        nuevas = fichas.filtered(lambda f: correos[f] and not f.dcasa_promos_baja_fecha
                                 and bloqueos.get(correos[f]) != 'baja'
                                 and not (f.dcasa_promos_fecha and f.dcasa_promos_correo == correos[f]
                                          and (origen == AUTOMATICO or f.dcasa_promos_origen != AUTOMATICO)))
        usuario = usuario if usuario and not usuario._is_public() else self.env['res.users']
        for ficha in nuevas:
            ficha.write({
                'dcasa_promos_fecha': fecha or fields.Datetime.now(),
                'dcasa_promos_origen': origen,
                'dcasa_promos_usuario_id': usuario.id or False,
                'dcasa_promos_correo': correos[ficha],
                'dcasa_promos_referencia': (referencia or '')[:120] or False,
                'dcasa_promos_no_fecha': False,
                'dcasa_promos_no_origen': False,
                'dcasa_promos_no_usuario_id': False,
            })
        return nuevas

    # ------------------------------------------------------------------
    # El cuadro de la venta y el «no» (etapa 1b)
    # ------------------------------------------------------------------

    @api.model
    def _dcasa_promos_dias_pregunta(self):
        """Los días sin volver a mostrar el cuadro de la venta (``dcasa_camila.dias_entre_preguntas``, 180 de fábrica;
        de 1 a 3650)."""
        valor = self.env['ir.config_parameter'].sudo().get_param(P_DIAS_PREGUNTA)
        try:
            dias = int(valor) if valor not in (None, False, '') else DIAS_PREGUNTA
        except (TypeError, ValueError):
            dias = DIAS_PREGUNTA
        return min(max(dias, 1), 3650)

    def _dcasa_promos_que_preguntar(self):
        """El cuadro de la venta para esta ficha: ``(paso, casilla)`` o ``(None, None)`` si no sale.

        * ``casilla``: tiene un correo bien escrito. La casilla viene activada (se le enviarán novedades; si dijo que
          no, se desactiva), salvo que haya un «no» de hace más del plazo (entonces viene desactivada).
        * ``pregunta``: sin correo, «Sí / No» y, con «Sí», lo pide.

        No sale: a empresas, al equipo, con baja o «no contactar», a quien ya lo confirmó (un «sí» que no es el
        automático, con su correo de hoy), ni si el cuadro salió o dijo que no hace menos del ajuste."""
        self.ensure_one()
        ficha = self.commercial_partner_id.sudo()
        motivo = ficha._dcasa_promos_motivo_para_no_activar()
        if motivo in ('empresa', 'equipo', 'baja', 'ya_confirmado'):
            return None, None
        corte = fields.Datetime.now() - timedelta(days=self._dcasa_promos_dias_pregunta())
        if (ficha.dcasa_promos_pregunta_fecha and ficha.dcasa_promos_pregunta_fecha > corte) \
                or (ficha.dcasa_promos_no_fecha and ficha.dcasa_promos_no_fecha > corte):
            return None, None
        if not correo_valido(ficha.email):
            return 'pregunta', False
        return 'casilla', not ficha.dcasa_promos_no_fecha

    def _dcasa_promos_anotar_pregunta(self):
        """El cuadro de la venta salió hoy: no vuelve a salir en el plazo del ajuste."""
        self.commercial_partner_id.sudo().write({'dcasa_promos_pregunta_fecha': fields.Datetime.now()})

    def _dcasa_promos_anotar_no(self, origen, usuario=None):
        """El cliente dijo que no: quita el permiso (queda en el historial) y anota el «no» con cuándo, dónde y quién.
        No es la baja (esa es final y sube a Resend), pero con un «no» la casilla ya no se activa sola. Exige poder
        escribir la ficha (salvo el sistema)."""
        if origen not in dict(ORIGENES_NO):
            raise ValueError(origen)
        if not self.env.su:
            self.check_access('write')
        fichas = self.commercial_partner_id.sudo()
        usuario = usuario if usuario and not usuario._is_public() else self.env['res.users']
        ahora = fields.Datetime.now()
        if fichas:
            fichas.write(dict(SIN_PERMISO, dcasa_promos_no_fecha=ahora, dcasa_promos_no_origen=origen,
                              dcasa_promos_no_usuario_id=usuario.id or False, dcasa_promos_pregunta_fecha=ahora))
        return fichas

    def action_dcasa_promos_confirmar(self):
        """Botón «El cliente dijo que sí» de la ficha, cuando la casilla se activó sola: la persona lo confirma y queda
        «tienda» (lo marcó la vendedora), con su nombre. Una ficha a la vez, quien puede editar al cliente."""
        if len(self) != 1:
            raise UserError(self.env._('Se confirma de un cliente a la vez, desde su ficha.'))
        self.check_access('write')
        if self._dcasa_promos_motivo_para_no_activar() != 'ya_activada':
            raise UserError(self.env._('Las novedades de esta ficha no están activadas solas: no hay nada que '
                                       'confirmar.'))
        self.commercial_partner_id._dcasa_promos_registrar('tienda', self.env.user)
        return True

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
            if not correo or (ficha.dcasa_promos_fecha and ficha.dcasa_promos_correo == correo
                              and ficha.dcasa_promos_origen != AUTOMATICO):   # la que se activó sola, se confirma
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


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        """La ficha de un usuario nuevo (del equipo o del portal) no activa sola las novedades: el equipo no las
        recibe y el «sí» desde la web es la etapa siguiente."""
        return super(ResUsers, self.with_context(dcasa_promos_sin_auto=True)).create(vals_list)
