"""La pantalla de Sofía: lo que ve cada quien y lo que aprueba. Métodos públicos (los llama la pantalla por RPC).

Todos exigen ser del equipo de ventas EN EL SERVIDOR y validan cada argumento. La vendedora solo ve y resuelve LO SUYO
(regla de registro de ``dcasa.sofia.propuesta``); repartir es solo de Gerencia. Cada acción se hace con los permisos de
quien la aprueba (sin ``sudo``): asignar una oportunidad, escribirle al cliente por la MISMA ruta que la pantalla de
Conversaciones (``enviar_respuesta``), crear una tarea o guardar en la ficha los datos que el cliente escribió. Antes
de hacerla se revisa que todavía haga falta; si ya no, la propuesta queda «ya no hacía falta» y no se hace nada.
"""
import re
from datetime import timedelta

from markupsafe import escape
from psycopg2.errors import LockNotAvailable

from odoo import api, fields, models
from odoo.addons.dcasa_contactos.models import claves
from odoo.addons.dcasa_conversaciones.models import crm_reglas as CRM
from odoo.addons.dcasa_conversaciones.models import horario as H
from odoo.addons.dcasa_conversaciones.models.conversacion_panel import MAX_RESPUESTA
from odoo.addons.dcasa_socios.models import bien_escrito as B
from odoo.addons.dcasa_socios.models import reglas as RS
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import SQL

from . import reglas as R
from .corrida import ORIGENES
from .motor import HORAS_EN_CURSO
from .propuesta import ACCIONES, CON_MENSAJE, GRUPO_DEL_TIPO, NOMBRE_TIPO

GRUPO_VENDEDORA = 'sales_team.group_sale_salesman'
GRUPO_GERENCIA = 'sales_team.group_sale_manager'
MAX_EN_PANTALLA = 500
SEGUNDOS_ENTRE_REVISIONES = 60   # el botón no vuelve a revisar si alguien acaba de hacerlo
MINUTOS_DOBLE_CLIC = 5           # quien acaba de resolverla y vuelve a tocar: «ya quedó», no un error
CAMPOS_DE_LA_FICHA = ('nombre', 'correo', 'cumple')   # lo que «Guarda sus datos» deja corregir antes de guardar
MAX_CAMPO = 120


class YaNoHaceFalta(Exception):
    """La propuesta ya no aplica (alguien se adelantó, la oportunidad se cerró…): se marca y no se hace nada."""


class YaResuelta(UserError):
    """La propuesta ya no está pendiente. Si la acaba de resolver esta misma persona (un doble clic, o Odoo que repite
    la petición después de un choque), no es un error: ya quedó hecho."""

    def __init__(self, mensaje, propuesta):
        super().__init__(mensaje)
        self.propuesta = propuesta


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
            raise YaResuelta(self.env._('Esa propuesta ya se resolvió (%s).',
                                        dict(propuesta._fields['estado'].selection).get(propuesta.estado)),
                             propuesta)
        return propuesta

    def _ya_estaba(self, error):
        """Lo que se contesta cuando la propuesta ya estaba resuelta: si fue esta persona hace un momento, el resultado
        de entonces (nada se hace dos veces); si no, el error."""
        p = error.propuesta.sudo()
        if p.resuelta_por == self.env.user and p.resuelta_en \
                and fields.Datetime.now() - p.resuelta_en < timedelta(minutes=MINUTOS_DOBLE_CLIC):
            return {'resultado': p.resultado or self.env._('Ya quedó hecho.'), 'ya_estaba': True}
        raise error

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
        if not self._abierta(lead):
            acciones = [a for a in acciones if a != 'tarea']
        datos = p.datos or {}
        if p.tipo == 'guardar_datos':
            aviso = datos.get('aviso') or ''
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
            # «Guarda sus datos»: lo que escribió (se puede corregir antes de guardar) y lo que tiene hoy su ficha.
            'campos': dict(datos.get('campos') or {}) if p.tipo == 'guardar_datos' else {},
            'antes': dict(datos.get('antes') or {}) if p.tipo == 'guardar_datos' else {},
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
    def aplicar(self, propuesta_id, accion, texto=None, campos=None):
        """Aprueba la propuesta con ``accion`` (una de las que ofrece la pantalla): ``{resultado, accion?}``.

        ``campos`` solo con «Guarda sus datos»: lo que la vendedora dejó en la tarjeta (``{nombre, correo, cumple}``,
        texto; vacío = no guardar ese dato). Sin ``campos`` se guarda lo que propuso Sofía."""
        self._exigir_vendedora()
        try:
            propuesta = self._propuesta(propuesta_id)
        except YaResuelta as error:
            return self._ya_estaba(error)
        if not isinstance(accion, str) or accion not in ACCIONES[propuesta.tipo]:
            raise UserError(self.env._('Esa acción no se puede hacer con esta propuesta.'))
        if texto is not None:
            if not isinstance(texto, str):
                raise UserError(self.env._('El mensaje tiene que ser texto.'))
            texto = texto.strip()
            if len(texto) > MAX_RESPUESTA:
                raise UserError(self.env._('El mensaje es muy largo (máximo %s letras).', MAX_RESPUESTA))
        if campos is not None:
            propuestos = (propuesta.sudo().datos or {}).get('campos') or {}
            if propuesta.tipo != 'guardar_datos' or not isinstance(campos, dict) \
                    or any(clave not in CAMPOS_DE_LA_FICHA for clave in campos) \
                    or any(not isinstance(valor, str) or len(valor) > MAX_CAMPO for valor in campos.values()):
                raise UserError(self.env._('Esos datos no son válidos.'))
            if any(clave not in propuestos for clave in campos):
                raise UserError(self.env._('Sofía puso al día esta propuesta: vuelve a cargar la pantalla.'))
        p = propuesta.sudo()
        try:
            if accion == 'guardar':
                resultado, extra = self._aplicar_guardar(p, campos)
            else:
                resultado, extra = getattr(self, f'_aplicar_{accion}')(p, texto or '')
        except YaNoHaceFalta as motivo:
            p._resolver('vencida', str(motivo), self.env.user)
            return {'resultado': str(motivo), 'ya_no_hace_falta': True}
        p._resolver('aplicada', resultado, self.env.user, accion)
        return {'resultado': resultado, **(extra or {})}

    @api.model
    def descartar(self, propuesta_id):
        self._exigir_vendedora()
        try:
            propuesta = self._propuesta(propuesta_id)
        except YaResuelta as error:
            return self._ya_estaba(error)
        propuesta._resolver('descartada', self.env._('La descartó %s.', self.env.user.name), self.env.user)
        return {'resultado': self.env._('Descartada. Sofía no la vuelve a proponer en unos días.')}

    # --- cada acción -------------------------------------------------------

    def _exigir_oportunidad_abierta(self, p):
        lead = p.lead_id
        if lead and not self._abierta(lead.exists()):
            raise YaNoHaceFalta(self.env._('La oportunidad ya se cerró.'))
        return lead

    def _exigir_que_se_pueda_escribir(self, p):
        """Antes de escribirle (o de abrir su chat con el mensaje), se revisa todo otra vez: entre la revisión y este
        clic pudo pasar de todo. Si ya no hace falta, la propuesta queda «ya no hacía falta» y no se escribe nada."""
        conv = p.conversacion_id
        ahora = fields.Datetime.now()
        if not conv:
            raise YaNoHaceFalta(self.env._('Ese cliente ya no tiene chat.'))
        if p.partner_id.dcasa_no_contactar or conv.partner_id.dcasa_no_contactar:
            raise YaNoHaceFalta(self.env._('El cliente pidió que no lo contacten.'))
        if p.partner_id and conv.partner_id.commercial_partner_id != p.partner_id.commercial_partner_id:
            raise YaNoHaceFalta(self.env._('Ese chat ahora es de otra ficha de cliente.'))
        if not R.ventana_abierta(conv.canal, conv.ultimo_mensaje_cliente, ahora):
            raise UserError(self.env._(
                'Ya pasaron 24 horas desde su último mensaje: por %s no se le puede escribir hasta que vuelva a '
                'escribir. Crea una tarea para llamarlo.', self._canal(conv)))
        if p.tipo == 'contestar':
            if conv.estado != 'humano' or conv.ultimo_mensaje_autor != 'cliente':
                raise YaNoHaceFalta(self.env._('Ya le contestaron.'))
            return conv
        self._exigir_que_siga_haciendo_falta(p, conv, ahora)
        return conv

    def _exigir_que_siga_haciendo_falta(self, p, conv, ahora):
        """Lo mismo que miró la revisión para proponer el mensaje (escribirle, pedir sus datos, su cotización vence)."""
        if p.tipo in ('escribir', 'pedir_datos'):
            self._exigir_oportunidad_abierta(p)
        ctx = {'ahora': ahora}
        if self._juan_esta_por_escribir(conv, ctx):
            raise YaNoHaceFalta(self.env._('Juan está por mandarle su seguimiento automático: se le deja.'))
        if conv.estado != 'humano' and conv.ultimo_mensaje_cliente \
                and ahora - conv.ultimo_mensaje_cliente < timedelta(hours=HORAS_EN_CURSO):
            raise YaNoHaceFalta(self.env._(
                'El cliente está conversando con Juan ahora mismo: se le deja. Sofía lo vuelve a mirar después.'))
        if p.tipo == 'escribir' and p.lead_id and not self.env['crm.lead'].sudo().search_count(
                Domain(self.env['crm.lead']._dcasa_dominio_para_hoy()) & Domain('id', '=', p.lead_id.id)):
            raise YaNoHaceFalta(self.env._('Alguien del equipo ya le escribió hoy.'))
        if p.tipo == 'vence':
            orden = p.orden_id
            if not orden or orden.state not in ('draft', 'sent') or orden.locked \
                    or fields.Date.to_string(orden.validity_date) != (p.datos or {}).get('vence_el'):
                raise YaNoHaceFalta(self.env._(
                    'La cotización ya no está por vencer: se confirmó, se canceló o cambió su fecha.'))
        if p.tipo == 'pedir_datos':
            partner = p.partner_id
            if not R.falta_el_nombre(partner.name, self._provisionales(conv)) and not R.falta_el_correo(partner.email):
                raise YaNoHaceFalta(self.env._('Su ficha ya tiene su nombre y su correo.'))

    def _aplicar_asignar(self, p, _texto):
        if not self._es_gerencia():
            raise AccessError(self.env._('Repartir oportunidades lo aprueba Gerencia.'))
        lead = self._exigir_oportunidad_abierta(p)
        destino = p.destino_id
        if not lead:
            raise YaNoHaceFalta(self.env._('La oportunidad ya no existe.'))
        if not destino.active or destino.share or not destino.has_group(GRUPO_VENDEDORA):
            raise YaNoHaceFalta(self.env._('%s ya no está en el equipo.', destino.name))
        if p.tipo == 'sincronizar' and p.conversacion_id.asignada_a != destino:
            raise YaNoHaceFalta(self.env._('Su chat ya no lo atiende %s.', destino.name))
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
        return self.env._('Ahora es de %s.', destino.name), {}

    def _aplicar_chat(self, p, texto):
        conv = self._exigir_que_se_pueda_escribir(p)
        conv = self.env['dcasa.conversacion']._para_panel(conv.id, escritura=True)
        accion = conv._accion_abrir_en_panel()
        if texto and p.tipo in CON_MENSAJE:
            # El texto NO va en la acción (quedaría en la dirección y volvería al recargar): la pantalla lo pasa una
            # sola vez al chat (sofia.js → conversaciones.js).
            return (self.env._('Abrió el chat con el mensaje listo para enviar.'),
                    {'accion': accion, 'texto': texto, 'conversacion_id': conv.id})
        return self.env._('Abrió el chat.'), {'accion': accion}

    def _aplicar_enviar(self, p, texto):
        if not texto:
            raise UserError(self.env._('Escribe el mensaje antes de enviarlo.'))
        conv = self._exigir_que_se_pueda_escribir(p)
        # Enviar confirma la base A MITAD de la petición (antes de llamar al Worker): la propuesta queda aprobada en
        # esa misma confirmación. Así un doble clic, otra persona o Odoo repitiendo la petición la ven resuelta y el
        # cliente nunca recibe el mensaje dos veces (revisión adversarial, 2026-11-05).
        p._resolver('aplicada', self.env._('Enviando…'), self.env.user, 'enviar')
        self.env.flush_all()
        respuesta = self.env['dcasa.conversacion'].enviar_respuesta(conv.id, texto)
        if respuesta.get('enviado'):
            return self.env._('Enviado por %s.', self._canal(conv)), {}
        return self.env._('Quedó por enviar: se reintenta solo.'), {}

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
        return self.env._('Tarea creada para %s.', usuario.name), {}

    def _aplicar_guardar(self, p, campos=None):
        """«Guardar en su ficha»: solo los datos que la ficha todavía no tiene, con nuestro formato, sin duplicar a
        nadie y con los permisos de quien aprueba. Deja una nota en la ficha con el antes y el después."""
        if p.tipo == 'guardar_correo':   # las de antes de «Guarda sus datos» (solo el correo)
            return self._aplicar_guardar_correo(p)
        partner, conv = self._exigir_ficha_para_guardar(p)
        propuestos = (p.datos or {}).get('campos') or {}
        if campos is None:
            campos = propuestos
        campos = {clave: ' '.join((valor or '').split()) for clave, valor in campos.items()}
        provisionales = self._provisionales(conv) if conv else ()
        revisar = (('nombre', self.env._('su nombre'), lambda v: self._nombre_para_guardar(partner, v, provisionales)),
                   ('correo', self.env._('su correo'), lambda v: self._correo_para_guardar(partner, v)),
                   ('cumple', self.env._('su cumpleaños'), lambda v: self._cumple_para_guardar(partner, v)))
        valores, ya_tenia, notas = {}, [], []
        for clave, nombre_del_dato, revisar_dato in revisar:
            if not campos.get(clave):
                continue
            listo = revisar_dato(campos[clave])   # ``None`` si la ficha ya lo tiene; un dato mal escrito: UserError
            if listo is None:
                ya_tenia.append(nombre_del_dato)
                continue
            campo, valor, nota = listo
            valores[campo] = valor
            if campos[clave] != propuestos.get(clave):   # que la nota no diga «lo escribió» si se corrigió
                nota += self.env._(' (lo corrigió %(quien)s; en el chat: «%(chat)s»)', quien=self.env.user.name,
                                   chat=propuestos.get(clave) or '')
            notas.append(nota)
        if not valores:
            if ya_tenia:
                raise YaNoHaceFalta(self.env._('Su ficha ya tiene esos datos.'))
            raise UserError(self.env._('No queda ningún dato para guardar. Si no sirve, descártala.'))
        ficha = self.env['res.partner'].browse(partner.id)   # con los permisos de quien aprueba
        try:
            with self.env.cr.savepoint():
                ficha.write(valores)
        except (UserError, ValidationError) as error:
            raise UserError(self.env._('No se pudo guardar en su ficha: %s', error.args[0] if error.args else error)) \
                from None
        ficha.message_post(body=escape(self.env._(
            'Sofía guardó los datos que escribió en el chat (lo aprobó %(quien)s). %(cambios)s.',
            quien=self.env.user.name, cambios='. '.join(notas))), subtype_xmlid='mail.mt_note')
        guardado = self.env._('Guardado en su ficha.')
        if ya_tenia:
            guardado += self.env._(' Ya tenía %s.', ', '.join(ya_tenia))
        return guardado, {}

    def _exigir_ficha_para_guardar(self, p):
        partner, conv = p.partner_id, p.conversacion_id
        if not partner:
            raise YaNoHaceFalta(self.env._('Ese cliente ya no existe.'))
        if partner.is_company:
            raise YaNoHaceFalta(self.env._('Es la ficha de una empresa: los datos de la persona que escribe van en su '
                                           'propio contacto.'))
        if conv and conv.partner_id != partner:
            raise YaNoHaceFalta(self.env._('Ese chat ahora es de otra ficha de cliente.'))
        return partner, conv

    def _nombre_para_guardar(self, partner, valor, provisionales):
        nombre = R.nombre_con_formato(valor)
        if not R.falta_el_nombre(partner.name, provisionales):
            return None
        motivo = R.falta_el_nombre(nombre)
        if not nombre or (motivo and motivo != R.SOLO_EL_NOMBRE):
            raise UserError(self.env._('«%(nombre)s» no sirve como nombre: %(motivo)s. Escribe su nombre y '
                                       'apellido o borra ese dato.', nombre=valor, motivo=motivo or ''))
        if not R.mejora_el_nombre(partner.name, nombre, provisionales):
            raise UserError(self.env._(
                'Su ficha dice «%s»: escribe ese nombre con su apellido o borra este dato (si de verdad se llama '
                'distinto, corrígelo en su ficha).', partner.name))
        return 'name', nombre, self.env._('Nombre: «%(antes)s» → «%(ahora)s»', antes=partner.name or '', ahora=nombre)

    def _correo_para_guardar(self, partner, valor):
        if not R.falta_el_correo(partner.email):
            return None
        correo = B.correo_limpio(valor)
        if not correo:
            _codigo, sugerencia = B.problema_del_correo(valor)
            raise UserError(self.env._('El correo «%s» no está bien escrito.', valor)
                            + (self.env._(' ¿Quisiste decir %s?', sugerencia) if sugerencia else ''))
        if correo in self.env['res.partner']._dcasa_correos_del_equipo():
            raise UserError(self.env._('%s es un correo de D\'CASA, no del cliente.', correo))
        llave = claves.llave_correo(correo)
        otra = llave and partner._dcasa_otra_ficha('correo', llave)
        if otra:
            raise UserError(self.env._(
                'El correo %(correo)s ya es de «%(otra)s». Si es la misma persona, Gerencia las une en Posibles '
                'duplicados. Para guardar lo demás, borra el correo.', correo=correo, otra=otra.display_name))
        nota = (self.env._('Correo: %(antes)s → %(ahora)s', antes=partner.email, ahora=correo) if partner.email
                else self.env._('Correo: %s', correo))
        return 'email', correo, nota

    def _cumple_para_guardar(self, partner, valor):
        if partner.dcasa_cumple:
            return None
        if not re.fullmatch(r'[0-9]{2}-[0-9]{2}', valor) or not RS.cumple_valido(valor):
            raise UserError(self.env._('Ese cumpleaños no es una fecha: elige el día y el mes.'))
        return 'dcasa_cumple', valor, self.env._('Cumpleaños: %s', R.cumple_para_mostrar(valor))

    def _aplicar_guardar_correo(self, p):
        partner = p.partner_id
        correo = B.correo_limpio((p.datos or {}).get('correo') or '')
        if not partner or not correo:
            raise YaNoHaceFalta(self.env._('Ese correo ya no se puede guardar.'))
        if partner.email:
            raise YaNoHaceFalta(self.env._('Su ficha ya tiene correo: %s.', partner.email))
        if p.conversacion_id and p.conversacion_id.partner_id != partner:
            raise YaNoHaceFalta(self.env._('Ese chat ahora es de otra ficha de cliente.'))
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
        return self.env._('Correo guardado en su ficha.'), {}
