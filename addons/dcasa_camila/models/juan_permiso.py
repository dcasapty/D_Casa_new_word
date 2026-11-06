"""Juan pregunta por WhatsApp si el cliente quiere las novedades por correo (etapa 1b, decisión de la dueña,
2026-11-06).

La herramienta ``permiso_correo`` (en Brian: ``juan_permiso_correo``) tiene candados contra un «sí» inventado por la IA:

1. **«preguntar»**: Odoo dice si se puede (sin permiso con su correo de hoy, sin baja ni «no contactar», sin un «no»
   ni otra pregunta en el plazo del ajuste, que no sea del equipo, solo por WhatsApp) y deja la MARCA en la
   conversación (``dcasa_camila_permiso_pedido_en``). El primer mensaje del bot que se registra después es el que hizo
   la pregunta: se guarda su id (``dcasa_camila_permiso_msg_id``); nada se adivina por el texto.
2. **«anotar»**: solo si el ÚLTIMO mensaje del cliente es posterior a ESA pregunta, llegó en pocas horas
   (``HORAS_PARA_CONTESTAR``) y es un sí claro sin negación (``reglas.es_un_si_claro``). Sin un correo bien escrito no
   hay permiso: Juan se lo pide, el «sí» queda pendiente y, cuando lo escribe, el correo tiene que aparecer en lo que
   escribió el cliente (no lo inventa la IA) y se guarda en su ficha con las reglas de contactos de siempre. Queda
   «WhatsApp (Juan)» con el id del mensaje del cliente como prueba.
3. **«no»**: si el último mensaje del cliente después de la pregunta dice que no, queda con su fecha.

Además, en lo que Odoo le contesta al Worker (``/mensaje`` y ``/estado``) va ``permiso_correo``: «puedes_preguntar» o
«esperando_respuesta» (si no, la clave no va). Un error aquí nunca frena un mensaje.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.addons.dcasa_conversaciones.models.brian_juan import GRUPO_JUAN
from odoo.addons.dcasa_correo.models.correo import correo_valido
from odoo.addons.dcasa_sofia.models import reglas as reglas_sofia
from odoo.exceptions import AccessError, ValidationError

from . import reglas as R

_logger = logging.getLogger(__name__)

HORAS_PARA_CONTESTAR = 6
HORAS_PARA_EL_CORREO = 24
TOLERANCIA_RELOJ = timedelta(minutes=2)   # el reloj del Worker y el de Odoo
CANALES_WHATSAPP = ('whatsapp_qr', 'whatsapp_cloud')
CAMPOS_MARCA = frozenset({'dcasa_camila_permiso_pedido_en', 'dcasa_camila_permiso_msg_id',
                          'dcasa_camila_permiso_si_msg_id'})
TEXTO_SUGERIDO = '¿Quieres que te avisemos por correo cuando llegue algo nuevo a la tienda?'
MOTIVOS = {
    'empresa': 'Es una ficha de empresa: no se le pregunta.',
    'equipo': 'Es del equipo de D\'CASA.',
    'baja': 'Pidió que no lo contacten o se dio de baja de las novedades: no se le pregunta.',
    'ya_dijo_que_si': 'Ya recibe las novedades con su correo.',
    'dijo_que_no': 'Hace poco dijo que no: no se le vuelve a preguntar todavía.',
    'ya_se_le_pregunto': 'Ya se le preguntó hace poco: no se le vuelve a preguntar todavía.',
    'canal': 'Solo se pregunta por WhatsApp.',
    'sin_ficha': 'La conversación no tiene ficha de cliente.',
}


class DcasaConversacionPermiso(models.Model):
    _inherit = 'dcasa.conversacion'

    dcasa_camila_permiso_pedido_en = fields.Datetime('Novedades: Juan las ofreció el', readonly=True, copy=False)
    dcasa_camila_permiso_msg_id = fields.Many2one('dcasa.mensaje', 'Novedades: mensaje del bot que preguntó',
                                                  readonly=True, copy=False, ondelete='set null')
    dcasa_camila_permiso_si_msg_id = fields.Many2one('dcasa.mensaje', 'Novedades: el sí del cliente (falta su correo)',
                                                     readonly=True, copy=False, ondelete='set null')

    def write(self, vals):
        """La marca de la pregunta solo la escribe el sistema (la herramienta y el registro del mensaje del bot)."""
        if CAMPOS_MARCA.intersection(vals) and not self.env.su:
            raise AccessError(self.env._('La pregunta de las novedades la marca el sistema; no se escribe a mano.'))
        return super().write(vals)

    def _despues_de_mensaje(self, mensaje):
        super()._despues_de_mensaje(mensaje)
        if mensaje.autor != 'bot' or not self.dcasa_camila_permiso_pedido_en or self.dcasa_camila_permiso_msg_id:
            return
        if mensaje.ts < self.dcasa_camila_permiso_pedido_en - TOLERANCIA_RELOJ:
            return
        try:
            with self.env.cr.savepoint():
                self.sudo().write({'dcasa_camila_permiso_msg_id': mensaje.id})
        except Exception:
            _logger.warning('Camila: no se pudo guardar el mensaje de la pregunta (chat %s)', self.id, exc_info=True)

    def _estado_para_worker(self, ajustes=None):
        estado = super()._estado_para_worker(ajustes)
        try:
            with self.env.cr.savepoint():
                permiso = self._dcasa_camila_permiso_para_juan()
        except Exception:   # Juan contesta igual, sin el dato
            _logger.warning('Camila: no se pudo armar el dato del permiso para Juan (chat %s)', self.id, exc_info=True)
            permiso = None
        if permiso:
            estado['permiso_correo'] = permiso
        return estado

    # ------------------------------------------------------------------

    def _dcasa_camila_motivo_para_no_preguntar(self):
        self.ensure_one()
        if self.canal not in CANALES_WHATSAPP:
            return 'canal'
        ficha = self.partner_id.commercial_partner_id
        if not ficha:
            return 'sin_ficha'
        return ficha._dcasa_promos_motivo_para_no_preguntar(juan=True)

    def _dcasa_camila_pregunta_vigente(self):
        """El mensaje del bot que preguntó, si la pregunta sigue abierta (en el plazo para contestar)."""
        pregunta = self.sudo().dcasa_camila_permiso_msg_id
        if pregunta and fields.Datetime.now() - pregunta.ts <= timedelta(hours=HORAS_PARA_EL_CORREO):
            return pregunta
        return pregunta.browse()

    def _dcasa_camila_permiso_para_juan(self):
        """«esperando_respuesta» si Juan ya preguntó y la pregunta sigue abierta; «puedes_preguntar» si se puede."""
        self.ensure_one()
        conv = self.sudo()
        if conv._dcasa_camila_pregunta_vigente() and conv.canal in CANALES_WHATSAPP:
            return 'esperando_respuesta'
        if conv.estado != 'bot' or conv._dcasa_camila_motivo_para_no_preguntar():
            return None
        return 'puedes_preguntar'


class BrianHerramientasJuanPermiso(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @herramienta(
        nombre='juan_permiso_correo',
        # Corta a propósito (contrato para modelos pequeños: menos de 260 letras); el detalle va en los parámetros.
        descripcion='El permiso del cliente para recibir las novedades de D\'CASA por correo: «preguntar» antes de '
                    'hacerle la pregunta, «anotar» si contestó que sí, «no» si dijo que no. Odoo solo lo anota si su '
                    'último mensaje, tras tu pregunta, dice que sí.',
        parametros={
            'accion': {'type': 'string', 'enum': ['preguntar', 'anotar', 'no'],
                       'description': '«preguntar» antes de hacer la pregunta; «anotar» si dijo que sí; «no» si dijo '
                                      'que no.'},
            'correo': {'type': 'string',
                       'description': 'Opcional, con «anotar»: el correo TAL COMO lo escribió el cliente en el chat.'},
        },
        requeridos=['accion'], nivel='construccion', categoria='clientes', grupos=(GRUPO_JUAN,),
        ejemplos=['el cliente te dio su correo o le mandaste una cotización → permiso_correo(accion="preguntar")',
                  'contestó «sí, dale» a tu pregunta → permiso_correo(accion="anotar")'],
    )
    def _juan_permiso_correo(self, accion, correo=None):
        conversacion = self._j_conversacion()
        if accion == 'preguntar':
            return self._permiso_preguntar(conversacion)
        if accion == 'anotar':
            return self._permiso_anotar(conversacion, correo)
        if accion == 'no':
            return self._permiso_no(conversacion)
        raise BrianError('«accion» es «preguntar», «anotar» o «no».')

    @api.model
    def _permiso_preguntar(self, conversacion):
        motivo = conversacion._dcasa_camila_motivo_para_no_preguntar()
        if motivo:
            return {'puedes_preguntar': False, 'motivo': MOTIVOS.get(motivo, motivo),
                    'nota': 'No le preguntes por las novedades por correo.'}
        ficha = conversacion.partner_id.commercial_partner_id.sudo()
        conversacion.sudo().write({'dcasa_camila_permiso_pedido_en': fields.Datetime.now(),
                                   'dcasa_camila_permiso_msg_id': False, 'dcasa_camila_permiso_si_msg_id': False})
        ficha._dcasa_promos_anotar_pregunta()
        return {
            'puedes_preguntar': True, 'texto_sugerido': TEXTO_SUGERIDO,
            'tiene_correo': bool(correo_valido(ficha.email)),
            'nota': 'Hazle esa pregunta en esta respuesta, con tus palabras y una sola vez. Si contesta que sí, '
                    'llama a permiso_correo con accion="anotar"; si dice que no, accion="no". Nunca lo anotes sin '
                    'su sí.',
        }

    @api.model
    def _permiso_ultimo_del_cliente(self, conversacion):
        return self.env['dcasa.mensaje'].sudo().search([
            ('conversacion_id', '=', conversacion.id), ('autor', '=', 'cliente'), ('tipo', '=', 'mensaje')],
            order='ts desc, id desc', limit=1)

    @api.model
    def _permiso_respuesta(self, conversacion):
        """``(pregunta, ultimo)``: el mensaje del bot que preguntó y el último del cliente después de él (en plazo)."""
        conv = conversacion.sudo()
        pregunta = conv._dcasa_camila_pregunta_vigente()
        if not pregunta:
            raise BrianError('No hay una pregunta tuya abierta: primero permiso_correo(accion="preguntar") y que el '
                             'cliente conteste. No lo anotes sin su sí.')
        ultimo = self._permiso_ultimo_del_cliente(conv)
        if not ultimo or (ultimo.ts, ultimo.id) <= (pregunta.ts, pregunta.id):
            raise BrianError('El cliente todavía no contestó tu pregunta: espera su respuesta.')
        return pregunta, ultimo

    @api.model
    def _permiso_anotar(self, conversacion, correo=None):
        conv = conversacion.sudo()
        pregunta, ultimo = self._permiso_respuesta(conv)
        if R.es_un_si_claro(ultimo.texto) and ultimo.ts - pregunta.ts <= timedelta(hours=HORAS_PARA_CONTESTAR):
            si = ultimo
        elif conv.dcasa_camila_permiso_si_msg_id and ultimo.id >= conv.dcasa_camila_permiso_si_msg_id.id \
                and not R.es_un_no(ultimo.texto):
            si = conv.dcasa_camila_permiso_si_msg_id   # ya dijo que sí; ahora escribió su correo
        else:
            raise BrianError('Su último mensaje no es un sí claro a tu pregunta: no lo anotes. Si quiere, que lo diga '
                             'con sus palabras.')
        ficha = conv.partner_id.commercial_partner_id.sudo()
        motivo = ficha._dcasa_promos_motivo_para_no_preguntar()
        if motivo in ('baja', 'equipo', 'empresa'):
            raise BrianError(MOTIVOS[motivo])
        self._permiso_guardar_correo(conv, ficha, correo, si)
        if not correo_valido(ficha.email):
            conv.write({'dcasa_camila_permiso_si_msg_id': si.id})
            return {'anotado': False, 'necesita_correo': True,
                    'mensaje': 'Dijo que sí, pero su ficha no tiene correo: pídeselo. Cuando lo escriba, vuelve a '
                               'llamar con accion="anotar" y correo tal como lo escribió.'}
        referencia = f'Chat {conv.id} · mensaje {si.id}'
        nuevas = ficha._dcasa_promos_registrar('juan_whatsapp', referencia=referencia, fecha=si.ts)
        conv.write({'dcasa_camila_permiso_pedido_en': False, 'dcasa_camila_permiso_msg_id': False,
                    'dcasa_camila_permiso_si_msg_id': False})
        return {'anotado': bool(nuevas) or ficha.dcasa_promos_estado == 'si',
                'mensaje': 'Quedó anotado: le llegan las novedades a su correo. Agradécele con naturalidad; si algún '
                           'día no las quiere, en cada correo hay un enlace para darse de baja.'}

    @api.model
    def _permiso_guardar_correo(self, conv, ficha, correo, si):
        """El correo que dio el cliente: tiene que estar en lo que ÉL escribió en el chat (desde poco antes de su sí) y
        se guarda en su ficha solo si la ficha no tiene uno bien escrito (si tiene otro, lo cambia una vendedora)."""
        if not correo:
            return
        dado = correo_valido(correo)
        if not dado:
            raise BrianError('Ese correo no está bien escrito: pídele que lo revise.')
        escritos = self.env['dcasa.mensaje'].sudo().search([
            ('conversacion_id', '=', conv.id), ('autor', '=', 'cliente'),
            ('ts', '>=', si.ts - timedelta(hours=HORAS_PARA_EL_CORREO)), ('texto', 'ilike', '@')], limit=50)
        if dado not in {correo_valido(c) for m in escritos for c in reglas_sofia.correos_en(m.texto)}:
            raise BrianError('Ese correo no lo escribió el cliente en el chat: pídeselo y usa el que escriba.')
        actual = correo_valido(ficha.email)
        if actual and actual != dado:
            raise BrianError('Su ficha ya tiene otro correo: no lo cambies tú. Dile que una vendedora lo confirma y '
                             'pásala si hace falta.')
        if not actual:
            try:
                ficha.write({'email': dado})   # las reglas de contactos de siempre
            except ValidationError as error:
                raise BrianError(str(error.args[0] if error.args else error)) from None

    @api.model
    def _permiso_no(self, conversacion):
        conv = conversacion.sudo()
        _pregunta, ultimo = self._permiso_respuesta(conv)
        if not R.es_un_no(ultimo.texto):
            raise BrianError('Su último mensaje no dice que no: no lo anotes como un no.')
        conv.partner_id.commercial_partner_id._dcasa_promos_anotar_no()
        conv.write({'dcasa_camila_permiso_pedido_en': False, 'dcasa_camila_permiso_msg_id': False,
                    'dcasa_camila_permiso_si_msg_id': False})
        return {'anotado': True, 'mensaje': 'Quedó anotado que no: no se le vuelve a preguntar en un buen tiempo.'}
