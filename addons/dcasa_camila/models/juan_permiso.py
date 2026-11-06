"""Juan y las novedades por correo (etapa 1b; decisión de la dueña del 2026-11-06: se activan solas al agregar el
correo, y quien atiende las quita si el cliente dice que no).

Juan nunca las activa por su cuenta ni pregunta si las quiere. Dos herramientas:

1. **guardar_correo** (en Brian: ``juan_guardar_correo``): guarda en la ficha el correo que el cliente ESCRIBIÓ en el
   chat (tiene que estar en sus mensajes de las últimas horas: la IA no lo inventa), solo si la ficha no tiene uno bien
   escrito y con las reglas de contactos de siempre (errores de dedo, correos del equipo, otra ficha con ese correo).
   Al guardarlo, las novedades se activan solas como en cualquier ficha (origen «Se activó sola al agregar su correo»,
   con Juan como quien lo agregó y el mensaje del cliente como referencia), salvo baja, «no contactar» o un «no». La
   respuesta le dice a Juan qué contarle: que le llegarán a ese correo y que puede decir que no cuando quiera.
2. **no_quiere_novedades** (``juan_no_quiere_novedades``): si el cliente dice que no (claro o con dudas), se quitan y
   queda el «no» (origen «Se lo dijo a Juan en el chat»); con él ya no se activan solas. Siempre se honra un «no».

En lo que Odoo le contesta al Worker (``/mensaje`` y ``/estado``) va ``permiso_correo``: «activo» (recibe las
novedades: si dice que no, la herramienta) o «sin_correo» (si da su correo, guardarlo); si no, la clave no va. Un
error aquí nunca frena un mensaje.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.addons.dcasa_contactos.models import claves
from odoo.addons.dcasa_conversaciones.models.brian_juan import GRUPO_JUAN
from odoo.addons.dcasa_correo.models.correo import correo_valido
from odoo.addons.dcasa_sofia.models import reglas as reglas_sofia
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

HORAS_PARA_EL_CORREO = 24   # el correo tiene que estar en lo que escribió el cliente en estas horas


class DcasaConversacionPermiso(models.Model):
    _inherit = 'dcasa.conversacion'

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

    def _dcasa_camila_permiso_para_juan(self):
        """«activo» si recibe las novedades con su correo de hoy; «sin_correo» si su ficha no tiene un correo bien
        escrito (y puede tenerlo: no es del equipo ni una empresa); si no, ``None``."""
        self.ensure_one()
        ficha = self.sudo().partner_id.commercial_partner_id
        if not ficha:
            return None
        motivo = ficha._dcasa_promos_motivo_para_no_activar()
        if motivo in ('empresa', 'equipo'):
            return None
        if ficha.dcasa_promos_estado == 'si':
            return 'activo'
        if not correo_valido(ficha.email):
            return 'sin_correo'
        return None


class BrianHerramientasJuanPermiso(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    def _permiso_ficha(self, conversacion):
        ficha = conversacion.sudo().partner_id.commercial_partner_id
        if not ficha:
            raise BrianError('Esta conversación no tiene ficha de cliente: pásala a una vendedora si hace falta.')
        if ficha._dcasa_promos_motivo_para_no_activar() in ('empresa', 'equipo'):
            raise BrianError('Esta ficha es de una empresa o del equipo: su correo lo cambia una vendedora.')
        return ficha

    @api.model
    def _permiso_ultimo_del_cliente(self, conversacion):
        return self.env['dcasa.mensaje'].sudo().search([
            ('conversacion_id', '=', conversacion.id), ('autor', '=', 'cliente'), ('tipo', '=', 'mensaje')],
            order='ts desc, id desc', limit=1)

    @herramienta(
        nombre='juan_guardar_correo',
        descripcion='Guarda en su ficha el correo que el cliente te escribió en el chat (solo si su ficha no tiene '
                    'uno). Al guardarlo le empiezan a llegar las novedades de D\'CASA: la respuesta te dice qué '
                    'contarle.',
        parametros={
            'correo': {'type': 'string',
                       'description': 'El correo TAL COMO lo escribió el cliente en el chat (nunca uno inventado).'},
        },
        requeridos=['correo'], nivel='construccion', categoria='clientes', grupos=(GRUPO_JUAN,),
        ejemplos=['el cliente escribe «mi correo es ana@gmail.com» → guardar_correo(correo="ana@gmail.com")'],
    )
    def _juan_guardar_correo(self, correo):
        conv = self._j_conversacion().sudo()
        ficha = self._permiso_ficha(conv)
        dado = correo_valido(correo)
        if not dado:
            raise BrianError('Ese correo no está bien escrito: pídele que lo revise.')
        desde = fields.Datetime.now() - timedelta(hours=HORAS_PARA_EL_CORREO)
        escritos = self.env['dcasa.mensaje'].sudo().search([
            ('conversacion_id', '=', conv.id), ('autor', '=', 'cliente'), ('tipo', '=', 'mensaje'),
            ('ts', '>=', desde), ('texto', 'ilike', '@')], order='ts desc, id desc', limit=50)
        donde = escritos.filtered(
            lambda m: dado in {correo_valido(c) for c in reglas_sofia.correos_en(m.texto)})[:1]
        if not donde:
            raise BrianError('Ese correo no lo escribió el cliente en el chat: pídeselo y usa el que escriba.')
        actual = correo_valido(ficha.email)
        if actual and actual != dado:
            raise BrianError('Su ficha ya tiene otro correo: no lo cambies tú. Dile que una vendedora lo confirma y '
                             'pásala si hace falta.')
        if not actual:
            if dado in ficha._dcasa_correos_del_equipo():
                raise BrianError('Ese es un correo de D\'CASA, no del cliente.')
            llave = claves.llave_correo(dado)
            if llave and ficha._dcasa_otra_ficha('correo', llave):
                raise BrianError('Ese correo ya está en otra ficha de cliente: una vendedora lo revisa. Pásala si '
                                 'hace falta.')
            try:
                ficha.write({'email': dado})   # las reglas de contactos de siempre
            except ValidationError as error:
                raise BrianError(str(error.args[0] if error.args else error)) from None
            # Juan no es del equipo: la regla de la dueña (se activa sola al agregar el correo) se aplica aquí, con
            # Juan como quien lo agregó y el mensaje del cliente como prueba.
            ficha._dcasa_promos_activar_al_agregar_correo(
                None, usuario=self.env.user, referencia=f'Chat {conv.id} · mensaje {donde.id}')
        if ficha.dcasa_promos_estado == 'si':
            return {'guardado': True, 'novedades': True, 'correo': dado,
                    'nota': f'Dile con claridad, en tus palabras, que guardaste su correo {dado}, que ahí le van a '
                            'llegar las novedades de D\'CASA y que si no las quiere te lo diga cuando quiera.'}
        return {'guardado': True, 'novedades': False, 'correo': dado,
                'nota': 'Guardaste su correo (para sus cotizaciones y facturas). No le llegan las novedades por '
                        'correo: no se las ofrezcas.'}

    @herramienta(
        nombre='juan_no_quiere_novedades',
        descripcion='El cliente no quiere recibir novedades por correo (lo dijo claro o con dudas): se quitan y queda '
                    'anotado. Úsala siempre que diga que no; nunca las activa.',
        nivel='construccion', categoria='clientes', grupos=(GRUPO_JUAN,),
        ejemplos=['«no me manden correos» o «mejor no» a las novedades → no_quiere_novedades'],
    )
    def _juan_no_quiere_novedades(self):
        conv = self._j_conversacion().sudo()
        ficha = conv.partner_id.commercial_partner_id
        if not ficha:
            raise BrianError('Esta conversación no tiene ficha de cliente: pásala a una vendedora para que lo anote.')
        ficha._dcasa_promos_anotar_no('juan_whatsapp', self.env.user)
        ultimo = self._permiso_ultimo_del_cliente(conv)
        _logger.info('DCASA_CAMILA el cliente le dijo que no a Juan (chat %s, mensaje %s)', conv.id, ultimo.id)
        return {'anotado': True,
                'nota': 'Confírmale que ya no le llegan las novedades por correo (sus cotizaciones y facturas sí).'}
