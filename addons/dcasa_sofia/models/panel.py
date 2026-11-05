"""La pantalla de Sofía: lo que ve cada quien y lo que aprueba. Métodos públicos (los llama la pantalla por RPC).

Todos exigen ser del equipo de ventas EN EL SERVIDOR y validan cada argumento. La vendedora solo ve y resuelve LO SUYO
(regla de registro de ``dcasa.sofia.propuesta``); repartir es solo de Gerencia. Cada acción se hace con los permisos de
quien la aprueba (sin ``sudo``): asignar una oportunidad, escribirle al cliente por la MISMA ruta que la pantalla de
Conversaciones (``enviar_respuesta``), crear una tarea o guardar el correo en la ficha. Antes de hacerla se revisa que
todavía haga falta; si ya no, la propuesta queda «ya no hacía falta» y no se hace nada.
"""
from datetime import timedelta

from markupsafe import escape
from psycopg2.errors import LockNotAvailable

from odoo import api, fields, models
from odoo.addons.dcasa_contactos.models import claves
from odoo.addons.dcasa_conversaciones.models import crm_reglas as CRM
from odoo.addons.dcasa_conversaciones.models import horario as H
from odoo.addons.dcasa_conversaciones.models.conversacion_panel import MAX_RESPUESTA
from odoo.addons.dcasa_socios.models import bien_escrito as B
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import SQL

from . import reglas as R
from .corrida import ORIGENES
from .propuesta import ACCIONES, CON_MENSAJE, GRUPO_DEL_TIPO, NOMBRE_TIPO

GRUPO_VENDEDORA = 'sales_team.group_sale_salesman'
GRUPO_GERENCIA = 'sales_team.group_sale_manager'
MAX_EN_PANTALLA = 500
SEGUNDOS_ENTRE_REVISIONES = 60   # el botón no vuelve a revisar si alguien acaba de hacerlo


class YaNoHaceFalta(Exception):
    """La propuesta ya no aplica (alguien se adelantó, la oportunidad se cerró…): se marca y no se hace nada."""


class SofiaPanel(models.AbstractModel):
    _inherit = 'dcasa.sofia'

    # ------------------------------------------------------------------
    # Permisos
    # ------------------------------------------------------------------

    @api.model
    def _exigir_vendedora(self):
        if not self.env.user.has_group(GRUPO_VENDEDORA):
            raise AccessError(self.env._('Sofía es para el equipo de ventas.'))

    @api.model
    def _es_gerencia(self):
        return self.env.user.has_group(GRUPO_GERENCIA)

    @api.model
    def _propuesta(self, propuesta_id):
        """La propuesta pedida, pendiente, que esta persona puede ver, BLOQUEADA para que nadie la resuelva a la vez."""
        if isinstance(propuesta_id, bool) or not isinstance(propuesta_id, int) or propuesta_id < 1:
            raise UserError(self.env._('Esa propuesta no es válida.'))
        propuesta = self.env['dcasa.sofia.propuesta'].browse(propuesta_id).exists()
        if not propuesta:
            raise UserError(self.env._('Esa propuesta ya no existe.'))
        propuesta.check_access('read')   # la regla de registro: la vendedora solo las suyas
        if propuesta.solo_gerencia and not self._es_gerencia():
            raise AccessError(self.env._('Repartir oportunidades lo aprueba Gerencia.'))
        try:
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute(SQL('SELECT id FROM dcasa_sofia_propuesta WHERE id = %s FOR UPDATE NOWAIT',
                                        propuesta.id))
        except LockNotAvailable:
            raise UserError(self.env._('Alguien más la está resolviendo en este momento.')) from None
        propuesta.invalidate_recordset()
        if propuesta.estado != 'pendiente':
            raise UserError(self.env._('Esa propuesta ya se resolvió (%s).',
                                       dict(propuesta._fields['estado'].selection).get(propuesta.estado)))
        return propuesta

    # ------------------------------------------------------------------
    # Lo que se ve
    # ------------------------------------------------------------------

    @api.model
    def panel(self):
        """Las propuestas pendientes de quien mira (Gerencia: todas), la última revisión y lo que quedó sin mostrar."""
        self._exigir_vendedora()
        propuestas = self.env['dcasa.sofia.propuesta'].search([('estado', '=', 'pendiente')], limit=MAX_EN_PANTALLA)
        textos = self.env['dcasa.sofia.plantilla']._textos()
        ahora = fields.Datetime.now()
        ultima = self.env['dcasa.sofia.corrida'].sudo().search([], limit=1)
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        return {
            'es_gerencia': self._es_gerencia(),
            'usuario': {'id': self.env.uid, 'nombre': self.env.user.name},
            'ultima': {
                'cuando': H.a_iso(ultima.fin or ultima.inicio),
                'hace': self.env['dcasa.reparto']._hace_cuanto(ultima.fin or ultima.inicio),
                'origen': dict(ORIGENES).get(ultima.origen, ''),
                'quien': ultima.usuario_id.name or '',
            } if ultima else None,
            'omitidas': (ultima.omitidas or {}) if ultima and self._es_gerencia() else {},
            'manana': bool(ajustes.sofia_manana),
            'propuestas': [self._fila(p, textos, ahora) for p in propuestas],
        }

    @api.model
    def _fila(self, propuesta, textos, ahora):
        """Una propuesta para la pantalla (diccionario sencillo; nada de registros)."""
        p = propuesta.sudo()   # quien mira ya pasó la regla de registro de la propuesta
        conv, lead, partner = p.conversacion_id, p.lead_id, p.partner_id
        acciones = list(ACCIONES[p.tipo])
        aviso = ''
        if p.tipo in CON_MENSAJE or p.tipo == 'contestar':
            if conv and not R.ventana_abierta(conv.canal, conv.ultimo_mensaje_cliente, ahora):
                aviso = self.env._('Ya pasaron 24 horas desde su último mensaje: por %s no se le puede escribir hasta '
                                   'que vuelva a escribir.', self._canal(conv))
                acciones = [a for a in acciones if a not in ('chat', 'enviar')]
        if not lead or not lead.active:
            acciones = [a for a in acciones if a != 'tarea']
        datos = p.datos or {}
        return {
            'id': p.id,
            'tipo': p.tipo,
            'tipo_nombre': NOMBRE_TIPO.get(p.tipo, p.tipo),
            'grupo': GRUPO_DEL_TIPO.get(p.tipo, 'otro'),
            'prioridad': p.prioridad,
            'prioridad_nombre': p._prioridad_nombre(),
            'temperatura': p.temperatura or '',
            'temperatura_nombre': CRM.NOMBRE_TEMPERATURA.get(p.temperatura, ''),
            'cliente': partner.display_name or (conv.name if conv else '') or '',
            'canal': self._canal(conv) if conv else '',
            'titulo': p.titulo or '',
            'motivo': p.motivo or '',
            'mensaje': self._texto(p, self.env.user, textos),
            'pide_datos': p.pide_datos,
            'acciones': acciones,
            'aviso': aviso,
            'para': p.usuario_id.name or '',
            'para_id': p.usuario_id.id or False,
            'destino': p.destino_id.name or '',
            'lead_id': lead.id or False,
            'conversacion_id': conv.id or False,
            'partner_id': partner.id or False,
            'correo': datos.get('correo') or '',
            'celular': datos.get('celular') or '',
            'oportunidad': lead.name or '',
        }

    @api.model
    def analizar(self):
        """El botón «Organizar con Sofía»: revisa el CRM ahora (si nadie lo acaba de hacer) y devuelve la pantalla."""
        self._exigir_vendedora()
        ultima = self.env['dcasa.sofia.corrida'].sudo().search([], limit=1)
        reciente = ultima.fin and fields.Datetime.now() - ultima.fin < timedelta(seconds=SEGUNDOS_ENTRE_REVISIONES)
        if not reciente:
            self.sudo()._analizar('boton')
        return self.panel()

    # ------------------------------------------------------------------
    # Lo que se aprueba
    # ------------------------------------------------------------------

    @api.model
    def aplicar(self, propuesta_id, accion, texto=None):
        """Aprueba la propuesta con ``accion`` (una de las que ofrece la pantalla): ``{resultado, accion?}``."""
        self._exigir_vendedora()
        propuesta = self._propuesta(propuesta_id)
        if not isinstance(accion, str) or accion not in ACCIONES[propuesta.tipo]:
            raise UserError(self.env._('Esa acción no se puede hacer con esta propuesta.'))
        if texto is not None:
            if not isinstance(texto, str):
                raise UserError(self.env._('El mensaje tiene que ser texto.'))
            texto = texto.strip()
            if len(texto) > MAX_RESPUESTA:
                raise UserError(self.env._('El mensaje es muy largo (máximo %s letras).', MAX_RESPUESTA))
        p = propuesta.sudo()
        try:
            resultado, accion_cliente = getattr(self, f'_aplicar_{accion}')(p, texto or '')
        except YaNoHaceFalta as motivo:
            p._resolver('vencida', str(motivo), self.env.user)
            return {'resultado': str(motivo), 'ya_no_hace_falta': True}
        p._resolver('aplicada', resultado, self.env.user)
        return {'resultado': resultado, 'accion': accion_cliente}

    @api.model
    def descartar(self, propuesta_id):
        self._exigir_vendedora()
        propuesta = self._propuesta(propuesta_id)
        propuesta._resolver('descartada', self.env._('La descartó %s.', self.env.user.name), self.env.user)
        return {'resultado': self.env._('Descartada. Sofía no la vuelve a proponer en unos días.')}

    # --- cada acción -------------------------------------------------------

    def _exigir_oportunidad_abierta(self, p):
        lead = p.lead_id
        if lead and (not lead.exists() or not lead.active or lead.won_status != 'pending'):
            raise YaNoHaceFalta(self.env._('La oportunidad ya se cerró.'))
        return lead

    def _exigir_que_se_pueda_escribir(self, p):
        conv = p.conversacion_id
        if not conv:
            raise YaNoHaceFalta(self.env._('Ese cliente ya no tiene chat.'))
        if p.partner_id.dcasa_no_contactar or conv.partner_id.dcasa_no_contactar:
            raise YaNoHaceFalta(self.env._('El cliente pidió que no lo contacten.'))
        self._exigir_oportunidad_abierta(p)
        return conv

    def _aplicar_asignar(self, p, _texto):
        if not self._es_gerencia():
            raise AccessError(self.env._('Repartir oportunidades lo aprueba Gerencia.'))
        lead = self._exigir_oportunidad_abierta(p)
        destino = p.destino_id
        if not lead:
            raise YaNoHaceFalta(self.env._('La oportunidad ya no existe.'))
        if not destino.active or destino.share:
            raise YaNoHaceFalta(self.env._('%s ya no está en el equipo.', destino.name))
        antes = (p.datos or {}).get('antes') or False
        if (lead.user_id.id or False) != antes:
            raise YaNoHaceFalta(self.env._('Alguien ya le cambió la vendedora (ahora: %s).',
                                           lead.user_id.name or self.env._('nadie')))
        self.env['crm.lead'].browse(lead.id).write({'user_id': destino.id})   # con los permisos de Gerencia
        lead.message_post(body=escape(self.env._(
            'Sofía propuso: %(titulo)s. %(motivo)s Lo aprobó %(quien)s.',
            titulo=p.titulo, motivo=p.motivo, quien=self.env.user.name)), subtype_xmlid='mail.mt_note')
        # Lo demás que Sofía tenía pendiente de esa oportunidad pasa a la nueva vendedora.
        self.env['dcasa.sofia.propuesta'].sudo().search([
            ('lead_id', '=', lead.id), ('estado', '=', 'pendiente'), ('solo_gerencia', '=', False),
            ('id', '!=', p.id)]).write({'usuario_id': destino.id})
        return self.env._('Ahora es de %s.', destino.name), None

    def _aplicar_chat(self, p, texto):
        conv = self._exigir_que_se_pueda_escribir(p)
        conv = self.env['dcasa.conversacion']._para_panel(conv.id, escritura=True)
        accion = conv._accion_abrir_en_panel()
        if texto and p.tipo in CON_MENSAJE:
            accion['params'] = {**(accion.get('params') or {}), 'texto': texto}
            return self.env._('Abrió el chat con el mensaje listo para enviar.'), accion
        return self.env._('Abrió el chat.'), accion

    def _aplicar_enviar(self, p, texto):
        conv = self._exigir_que_se_pueda_escribir(p)
        if not texto:
            raise UserError(self.env._('Escribe el mensaje antes de enviarlo.'))
        if not R.ventana_abierta(conv.canal, conv.ultimo_mensaje_cliente, fields.Datetime.now()):
            raise UserError(self.env._(
                'Ya pasaron 24 horas desde su último mensaje: por %s no se le puede escribir. Crea una tarea para '
                'llamarlo.', self._canal(conv)))
        respuesta = self.env['dcasa.conversacion'].enviar_respuesta(conv.id, texto)
        if respuesta.get('enviado'):
            return self.env._('Enviado por %s.', self._canal(conv)), None
        return self.env._('Quedó por enviar: se reintenta solo.'), None

    def _aplicar_tarea(self, p, texto):
        lead = self._exigir_oportunidad_abierta(p)
        if not lead:
            raise UserError(self.env._('Esta propuesta no tiene oportunidad donde dejar la tarea.'))
        usuario = p.usuario_id if p.usuario_id.active else self.env.user
        tipo = 'mail.mail_activity_data_call' if p.tipo == 'llamar' else 'mail.mail_activity_data_todo'
        nota = escape(p.motivo or '')
        if texto:
            nota = escape(self.env._('%(motivo)s\n\nMensaje que propuso Sofía:\n%(texto)s',
                                     motivo=p.motivo or '', texto=texto))
        self.env['crm.lead'].browse(lead.id).activity_schedule(
            tipo, date_deadline=self.env['dcasa.reparto']._hoy(), summary=(p.titulo or '')[:120],
            note=nota, user_id=usuario.id)
        return self.env._('Tarea creada para %s.', usuario.name), None

    def _aplicar_guardar(self, p, _texto):
        partner = p.partner_id
        correo = B.correo_limpio((p.datos or {}).get('correo') or '')
        if not partner or not correo:
            raise YaNoHaceFalta(self.env._('Ese correo ya no se puede guardar.'))
        if partner.email:
            raise YaNoHaceFalta(self.env._('Su ficha ya tiene correo: %s.', partner.email))
        llave = claves.llave_correo(correo)
        otra = llave and partner._dcasa_otra_ficha('correo', llave)
        if otra:
            raise YaNoHaceFalta(self.env._('Ese correo ya es de «%s».', otra.display_name))
        try:
            with self.env.cr.savepoint():
                # con los permisos de quien aprueba
                self.env['res.partner'].browse(partner.id).write({'email': correo})
        except (UserError, ValidationError) as error:
            raise UserError(self.env._('No se pudo guardar el correo: %s', error.args[0] if error.args else error)) \
                from None
        return self.env._('Correo guardado en su ficha.'), None
