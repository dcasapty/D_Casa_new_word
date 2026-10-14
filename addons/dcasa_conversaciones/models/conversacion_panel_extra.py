"""Lo que la pantalla «Conversaciones» necesita además de ``conversacion_panel.py``: subir archivos, el equipo de
ventas, crear la oportunidad sin salir de la pantalla y pedir un borrador de respuesta al Worker.

Todo exige ser del equipo de ventas EN EL SERVIDOR y devuelve diccionarios sencillos. Las firmas de
``conversacion_panel.py`` no se tocan: aquí solo hay métodos nuevos.
"""
import base64
import binascii
import logging
import os
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.mimetypes import guess_mimetype

from . import adjuntos as A
from . import horario as H
from .ajustes import CANALES
from .conversacion import MAX_NOTA, MAX_NOTA_PARA_EL_BOT
from .conversacion_panel import MAX_RESPUESTA, _entero
from .mensaje import adjunto_como_dict

_logger = logging.getLogger(__name__)

MAX_PENDIENTES = 10
HORAS_DE_UNA_SUBIDA_SIN_USAR = 48
CONTEXTO_PARA_SUGERIR = 14          # últimos mensajes que se le pasan al Worker
CONTEXTO_PARA_RESUMIR = 60          # un resumen lee más que un borrador (el máximo que acepta el Worker)
ESPERA_ENTRE_RESUMENES = timedelta(seconds=60)
MAX_TEXTO_PARA_SUGERIR = 1500
# Lo que una vendedora puede mandar por el canal. Nada que un navegador pueda ejecutar (HTML, SVG, JS…).
TIPOS_QUE_SE_SUBEN = {
    'image/jpeg': ('.jpg', '.jpeg'), 'image/png': ('.png',), 'image/webp': ('.webp',), 'image/gif': ('.gif',),
    'application/pdf': ('.pdf',),
    'application/msword': ('.doc',),
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ('.docx',),
    'application/vnd.ms-excel': ('.xls',),
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ('.xlsx',),
    'text/plain': ('.txt',), 'text/csv': ('.csv',),
}


def tipo_de_archivo(nombre, contenido):
    """El tipo del archivo si se puede mandar por el canal; ``None`` si no.

    Se mira el CONTENIDO (no solo el nombre) y la extensión tiene que corresponder: una foto que dice ser PDF, un
    ejecutable o un HTML con nombre de imagen no pasan. Los Word y Excel viejos (.doc/.xls) y los textos
    (.txt/.csv) no se distinguen por el contenido, así que ahí decide la extensión.
    """
    extension = os.path.splitext(nombre or '')[1].lower()
    detectado = guess_mimetype(contenido, default='application/octet-stream')
    if detectado in ('application/msword', 'application/x-ole-storage'):
        detectado = {'.doc': 'application/msword', '.xls': 'application/vnd.ms-excel'}.get(extension)
    elif detectado == 'text/plain':
        detectado = {'.txt': 'text/plain', '.csv': 'text/csv'}.get(extension)
    if detectado not in TIPOS_QUE_SE_SUBEN or extension not in TIPOS_QUE_SE_SUBEN[detectado]:
        return None
    return detectado


class DcasaConversacionPanelExtra(models.Model):
    _inherit = 'dcasa.conversacion'

    # ------------------------------------------------------------------
    # Archivos para la caja de respuesta
    # ------------------------------------------------------------------

    @api.model
    def subir_adjunto(self, conversacion_id, nombre, datos, mimetype=None):
        """Sube un archivo (``datos`` en base64) para adjuntarlo a la próxima respuesta.

        Solo fotos (JPG, PNG, WebP, GIF), PDF, Word, Excel y texto; hasta 10 MB. El archivo queda a nombre de quien
        lo sube, sin dueño todavía: se pasa a ``enviar_respuesta`` con su id. ``mimetype`` es solo una pista.
        """
        conv = self._para_panel(conversacion_id, escritura=True)
        if not isinstance(nombre, str) or not isinstance(datos, str) or not datos:
            raise UserError(self.env._('Falta el archivo.'))
        if len(datos) > (A.MAX_BYTES * 4) // 3 + 16:
            raise UserError(self.env._('«%s» pesa demasiado (máximo 10 MB).', A.nombre_seguro(nombre)))
        try:
            contenido = base64.b64decode(datos.partition(',')[2] if datos.startswith('data:') else datos,
                                         validate=True)
        except (binascii.Error, ValueError):
            raise UserError(self.env._('No pude leer el archivo. Súbelo otra vez.')) from None
        nombre = A.nombre_seguro(nombre)
        if not contenido:
            raise UserError(self.env._('«%s» está vacío.', nombre))
        if len(contenido) > A.MAX_BYTES:
            raise UserError(self.env._('«%s» pesa demasiado (máximo 10 MB).', nombre))
        tipo = tipo_de_archivo(nombre, contenido)
        if not tipo:
            raise UserError(self.env._(
                '«%s» no se puede enviar. Adjunta una foto (JPG, PNG, WebP), un PDF, un Word, un Excel o un texto.',
                nombre))
        Adjunto = self.env['ir.attachment']
        pendientes = Adjunto.search_count([
            ('res_model', '=', self._name), ('res_id', '=', conv.id), ('create_uid', '=', self.env.uid)])
        if pendientes >= MAX_PENDIENTES:
            raise UserError(self.env._('Tienes muchos archivos sin enviar en esta conversación. '
                                       'Envía la respuesta o quítalos antes de subir más.'))
        adjunto = Adjunto.create({
            'name': nombre, 'raw': contenido, 'mimetype': tipo, 'res_model': self._name, 'res_id': conv.id,
            'public': False,
        })
        return {'adjunto': adjunto_como_dict(adjunto)}

    @api.model
    def descartar_adjunto(self, adjunto_id):
        """Quita un archivo que se subió y todavía no se envió (el que ya salió en un mensaje no se toca)."""
        self._exigir_vendedora()
        adjunto_id = _entero(adjunto_id, 'adjunto_id', minimo=1)
        adjunto = self.env['ir.attachment'].browse(adjunto_id).exists()
        if not adjunto or adjunto.res_model != self._name or adjunto.create_uid != self.env.user:
            raise UserError(self.env._('Ese archivo no se puede quitar.'))
        adjunto.check_access('unlink')
        adjunto.sudo().unlink()
        return {'quitado': adjunto_id}

    @api.model
    def _cron_limpiar_subidas(self):
        """Cada día: borra los archivos que se subieron para una respuesta y nunca se enviaron (más de 48 h)."""
        limite = fields.Datetime.now() - timedelta(hours=HORAS_DE_UNA_SUBIDA_SIN_USAR)
        viejos = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name), ('create_date', '<', limite)])
        # Los que viajan en un mensaje del chatter de la conversación (Odoo los liga a ella) son de esa nota, no sobras.
        en_el_chatter = self.env['mail.message'].sudo().search([
            ('model', '=', self._name), ('attachment_ids', 'in', viejos.ids)]).attachment_ids
        viejos -= en_el_chatter
        viejos.unlink()
        return len(viejos)

    # ------------------------------------------------------------------
    # Arranque de la pantalla, el equipo y la oportunidad
    # ------------------------------------------------------------------

    @api.model
    def iniciar_panel(self):
        """Todo lo que la pantalla necesita al abrir, en UNA llamada: quién es, límites, etiquetas, atajos y equipo."""
        self._exigir_vendedora()
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        return {
            'usuario': {'id': self.env.uid, 'nombre': self.env.user.name,
                        'es_gerencia': self.env.user.has_group('sales_team.group_sale_manager'),
                        'disponible': bool(self.env.user.sudo().dcasa_disponible),
                        # Gerencia la sacó del reparto (vacaciones, ausencia…): no le asignan nuevas, esté como esté.
                        'fuera_del_reparto': not self.env.user.sudo()._dcasa_en_el_reparto(
                            self.env['dcasa.reparto']._hoy())},
            'reparto': ajustes.reparto_modo,
            'resumen_ia': bool(ajustes.resumen_ia_activo),
            'bot': {'conectado': bool(self.env['dcasa.juan.cliente'].configurado()),
                    'encendido': bool(ajustes.bot_activo_global)},
            'limites': {'adjuntos': A.MAX_ADJUNTOS, 'bytes': A.MAX_BYTES, 'respuesta': MAX_RESPUESTA,
                        'nota': MAX_NOTA, 'nota_para_el_bot': MAX_NOTA_PARA_EL_BOT,
                        'pausa_minutos': ajustes.pausa_por_defecto_minutos,
                        'espera_aviso_minutos': ajustes.aviso_espera_minutos},
            'canales': [{'id': clave, 'nombre': nombre} for clave, nombre in CANALES],
            'etiquetas': self.env['dcasa.conversacion.etiqueta'].lista(),
            'rapidas': self.env['dcasa.respuesta.rapida'].lista(),
            'equipo': self.equipo(),
        }

    # ------------------------------------------------------------------
    # Adjuntar un comprobante a una factura o a un pedido del cliente
    # ------------------------------------------------------------------

    @api.model
    def documentos_del_cliente(self, conversacion_id):
        """Los pedidos y las facturas recientes del cliente, para elegir a cuál se adjunta un comprobante."""
        conv = self._para_panel(conversacion_id)
        if not conv.partner_id:
            return {'cliente': False, 'pedidos': [], 'facturas': []}
        comercial = conv.partner_id.sudo().commercial_partner_id
        estados_pedido = dict(self.env['sale.order']._fields['state']._description_selection(self.env))
        pedidos = self.env['sale.order'].sudo().search([
            ('partner_id.commercial_partner_id', '=', comercial.id), ('state', '!=', 'cancel')],
            order='date_order desc, id desc', limit=8)
        facturas = self.env['account.move'].sudo().search([
            ('commercial_partner_id', '=', comercial.id), ('move_type', '=', 'out_invoice'),
            ('state', '!=', 'cancel')], order='invoice_date desc, id desc', limit=8)
        estados_factura = dict(self.env['account.move']._fields['state']._description_selection(self.env))
        return {
            'cliente': True,
            'pedidos': [{'id': o.id, 'nombre': o.name, 'estado_nombre': estados_pedido.get(o.state, o.state),
                         'total': round(o.amount_total, 2)} for o in pedidos],
            'facturas': [{'id': f.id, 'nombre': f.name or self.env._('Borrador'),
                          'estado_nombre': estados_factura.get(f.state, f.state),
                          'total': round(f.amount_total, 2)} for f in facturas],
        }

    @api.model
    def adjuntar_a_documento(self, conversacion_id, adjunto_id, modelo, registro_id):
        """Copia un archivo que mandó el cliente (un comprobante) al chatter de SU pedido o factura.

        Solo archivos de ESTA conversación mandados por el cliente, solo pedidos y facturas del MISMO cliente y solo si
        quien lo pide puede escribir en ese documento. La IA no interviene: el archivo nunca se le muestra.
        """
        conv = self._para_panel(conversacion_id, escritura=True)
        adjunto_id = _entero(adjunto_id, 'adjunto_id', minimo=1)
        registro_id = _entero(registro_id, 'registro_id', minimo=1)
        if modelo not in ('sale.order', 'account.move'):
            raise UserError(self.env._('Solo se puede adjuntar a un pedido o a una factura.'))
        if not conv.partner_id:
            raise UserError(self.env._('Esta conversación todavía no tiene un cliente.'))
        mensaje = self.env['dcasa.mensaje'].sudo().search([
            ('conversacion_id', '=', conv.id), ('autor', '=', 'cliente'), ('adjunto_ids', 'in', [adjunto_id])], limit=1)
        if not mensaje:
            raise UserError(self.env._('Ese archivo no es de esta conversación.'))
        destino = self.env[modelo].browse(registro_id).exists()
        if not destino:
            raise UserError(self.env._('Ese documento ya no existe.'))
        try:
            destino.check_access('write')
        except AccessError:
            raise UserError(self.env._('No tienes permiso para adjuntar archivos a ese documento.')) from None
        cliente = conv.partner_id.sudo().commercial_partner_id
        dueno = destino.sudo().partner_id.commercial_partner_id
        if modelo == 'account.move' and destino.sudo().move_type != 'out_invoice':
            raise UserError(self.env._('Solo se puede adjuntar a facturas de cliente.'))
        if dueno != cliente:
            raise UserError(self.env._('Ese documento es de otro cliente.'))
        original = self.env['ir.attachment'].sudo().browse(adjunto_id)
        repetido = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', modelo), ('res_id', '=', destino.id), ('checksum', '=', original.checksum)], limit=1)
        nombre_doc = destino.sudo().display_name
        if repetido:
            return {'ok': True, 'ya_estaba': True, 'documento': nombre_doc, 'modelo': modelo}
        copia = original.copy({'res_model': modelo, 'res_id': destino.id})
        canal = dict(CANALES).get(conv.canal, conv.canal)
        destino.sudo().message_post(
            body=self.env._('%(quien)s adjuntó «%(archivo)s», que mandó el cliente por %(canal)s, desde la '
                            'conversación.', quien=self.env.user.name, archivo=original.name, canal=canal),
            attachment_ids=[copia.id], subtype_xmlid='mail.mt_note')
        conv._aviso(self.env._('%(quien)s adjuntó «%(archivo)s» a %(doc)s.', quien=self.env.user.name,
                               archivo=original.name, doc=nombre_doc))
        return {'ok': True, 'ya_estaba': False, 'documento': nombre_doc, 'modelo': modelo}

    @api.model
    def equipo(self):
        """Las personas a quienes se puede asignar una conversación: ``[{id, nombre}]``."""
        self._exigir_vendedora()
        usuarios = self._usuarios_del_panel().sorted(lambda u: (u.name or '').lower())
        return [{'id': u.id, 'nombre': u.name} for u in usuarios]

    @api.model
    def fijar_disponible(self, disponible):
        """«Estoy disponible» / «No estoy»: con el reparto por turnos, solo a quien lo está le tocan conversaciones."""
        self._exigir_vendedora()
        if not isinstance(disponible, bool):
            raise UserError(self.env._('Disponible es sí o no.'))
        self.env.user.sudo().dcasa_disponible = disponible
        return {'disponible': disponible}

    @api.model
    def presencia(self, conversacion_id=None, escribiendo=False):
        """El pulso de la pantalla (cada 20 s y mientras se teclea): qué conversación tiene abierta esta persona.

        Devuelve quiénes están viendo cuáles ahora: ``{presencia: {conversacion_id: [{usuario_id, escribiendo}]}}``."""
        self._exigir_vendedora()
        conversacion = self._para_panel(conversacion_id) if conversacion_id else self.browse()
        if not isinstance(escribiendo, bool):
            raise UserError(self.env._('Escribiendo es sí o no.'))
        mapa = self.env['dcasa.presencia']._pulso(self.env.user, conversacion, escribiendo)
        return {'presencia': mapa}

    @api.model
    def resumir_conversacion(self, conversacion_id, regenerar=False):
        """«Resumir»: unas líneas de lo que pasó en la conversación, para quien la recibe. Cuesta un poco de IA, así que
        solo se pide al apretar el botón: si el resumen guardado ya cubre el último mensaje (o se pidió hace menos de un
        minuto), se devuelve ese y no se gasta nada. ``regenerar`` fuerza uno nuevo.
        """
        conv = self._para_panel(conversacion_id)
        if not isinstance(regenerar, bool):
            raise UserError(self.env._('Regenerar es sí o no.'))
        if not self.env['dcasa.juan.ajustes'].obtener().resumen_ia_activo:
            raise UserError(self.env._('El resumen con IA está apagado en Ajustes de Juan.'))
        ultimo = self.env['dcasa.mensaje'].search([
            ('conversacion_id', '=', conv.id), ('tipo', '=', 'mensaje'), ('estado_envio', '!=', 'programado')],
            order='id desc', limit=1).id
        if not ultimo:
            raise UserError(self.env._('Todavía no hay mensajes que resumir.'))
        ahora = fields.Datetime.now()
        reciente = conv.resumen_ia_en and ahora - conv.resumen_ia_en < ESPERA_ENTRE_RESUMENES
        if conv.resumen_ia and ((conv.resumen_ia_hasta_id >= ultimo and not regenerar) or reciente):
            return {**conv._resumen_ia_datos(ultimo), 'desde_cache': True, 'avisos': []}
        mensajes = conv._mensajes_para_sugerir(CONTEXTO_PARA_RESUMIR)
        if not any(m['autor'] == 'cliente' for m in mensajes):
            raise UserError(self.env._('Todavía no hay nada del cliente que resumir.'))
        Cliente = self.env['dcasa.juan.cliente']
        if not Cliente.configurado():
            raise UserError(self.env._(
                'Falta conectar el bot: no hay dirección o clave del Worker de Juan. Pídele a Gerencia que la '
                'cargue (Conversaciones › Conexiones).'))
        respuesta = Cliente.resumir(conv.id, conv.canal, mensajes, nombre=conv._nombre_de_pila(),
                                    etiquetas=conv.etiqueta_ids.mapped('name'))
        texto = str(respuesta.get('texto') or '').strip() if respuesta.get('ok') else ''
        if not texto:
            raise UserError(self.env._(
                'No pude resumir la conversación ahora: %s',
                (respuesta.get('error') or 'el Worker no devolvió texto')[:300]))
        conv.sudo().write({'resumen_ia': texto[:4000], 'resumen_ia_en': ahora, 'resumen_ia_hasta_id': ultimo})
        avisos = [str(a)[:200] for a in (respuesta.get('avisos') or []) if isinstance(a, str)][:5]
        return {**conv._resumen_ia_datos(ultimo), 'desde_cache': False, 'avisos': avisos}

    @api.model
    def nueva_oportunidad(self, conversacion_id):
        """«Crear oportunidad» sin salir de la pantalla. Si ya hay una abierta reciente, no crea otra."""
        conv = self._para_panel(conversacion_id, escritura=True)
        if not conv.partner_id:
            raise UserError(self.env._('Esta conversación todavía no tiene un cliente.'))
        lead, nueva = conv._oportunidad(
            resumen=self.env._('Creada por %s desde la pantalla de Conversaciones.', self.env.user.name),
            interes=None, usuario=self.env.user)
        return {'oportunidad': {'id': lead.id, 'nombre': lead.name, 'etapa': lead.stage_id.name or ''},
                'nueva': nueva, 'conversacion': conv._resumen_panel()}

    @api.model
    def reintentar_envios_panel(self, conversacion_id):
        """«Reintentar» lo que no salió: devuelve cuántos mensajes salieron ahora."""
        conv = self._para_panel(conversacion_id, escritura=True)
        pendientes = conv.mensaje_ids.filtered(
            lambda m: m.estado_envio in ('por_enviar', 'fallido') and m.origen == 'odoo')
        antes = len(pendientes)
        pendientes.action_reintentar()
        pendientes.invalidate_recordset()
        faltan = len(pendientes.filtered(lambda m: m.exists() and m.estado_envio != 'enviado'))
        return {'reintentados': antes, 'salieron': antes - faltan, 'conversacion': conv._resumen_panel()}

    # ------------------------------------------------------------------
    # «Sugerir»: un borrador de respuesta que redacta el Worker (no envía nada)
    # ------------------------------------------------------------------

    def _mensajes_para_sugerir(self, limite=CONTEXTO_PARA_SUGERIR):
        """Los últimos mensajes del cliente, del asistente y de las vendedoras, listos para el Worker.

        Nunca viajan las notas internas ni los avisos del sistema, ni lo que está programado y todavía no salió. Un
        mensaje con un comprobante o documento de identidad (adjunto sensible) viaja SIN su texto: ni la IA lo ve
        (regla 5 del contrato).
        """
        self.ensure_one()
        tramo = self.env['dcasa.mensaje'].search(
            [('conversacion_id', '=', self.id), ('tipo', '=', 'mensaje'), ('estado_envio', '!=', 'programado')],
            order='id desc', limit=limite).sorted('id')
        mensajes = []
        for mensaje in tramo:
            if mensaje.tiene_sensible:
                texto = '[archivo sensible: lo revisa una vendedora]'
            else:
                texto = (mensaje.texto or '').strip()
                if not texto and mensaje.adjunto_ids:
                    texto = '[envió un archivo]'
            if not texto:
                continue
            mensajes.append({'autor': {'cliente': 'cliente', 'bot': 'asistente'}.get(mensaje.autor, 'vendedora'),
                             'texto': texto[:MAX_TEXTO_PARA_SUGERIR], 'ts': H.a_iso(mensaje.ts)})
        return mensajes

    def _resumen_ia_datos(self, hasta_id=None):
        """Lo guardado, para la pantalla: ``{texto, generado_en, vigente}`` o ``None`` si nunca se pidió.

        ``vigente``: el resumen ya cubre el último mensaje (``hasta_id``, si se conoce).
        """
        self.ensure_one()
        if not self.resumen_ia:
            return None
        return {'texto': self.resumen_ia, 'generado_en': H.a_iso(self.resumen_ia_en),
                'vigente': None if hasta_id is None else self.resumen_ia_hasta_id >= hasta_id}

    def _interes_para_sugerir(self):
        """Lo que el cliente quiere, en pocas palabras: la oportunidad o su último mensaje SIN archivo sensible."""
        self.ensure_one()
        if self.oportunidad_id:
            return (self.oportunidad_id.name or '')[:200]
        ultimo = self.env['dcasa.mensaje'].search([
            ('conversacion_id', '=', self.id), ('autor', '=', 'cliente'), ('tipo', '=', 'mensaje'),
            ('tiene_sensible', '=', False)], order='ts desc, id desc', limit=1)
        return (ultimo.texto or '')[:200]

    @api.model
    def sugerir_respuesta(self, conversacion_id):
        """Pide al Worker un borrador para la vendedora: ``{texto, avisos}``. No envía ni guarda nada."""
        conv = self._para_panel(conversacion_id, escritura=True)
        mensajes = conv._mensajes_para_sugerir()
        if not any(m['autor'] == 'cliente' for m in mensajes):
            raise UserError(self.env._('Todavía no hay nada del cliente a lo que responder.'))
        Cliente = self.env['dcasa.juan.cliente']
        if not Cliente.configurado():
            raise UserError(self.env._(
                'Falta conectar el bot: no hay dirección o clave del Worker de Juan. Pídele a Gerencia que la '
                'cargue (Conversaciones › Conexiones).'))
        respuesta = Cliente.sugerir(
            conv.id, conv.canal, conv.id_externo, mensajes, nombre=conv._nombre_de_pila(),
            interes=conv._interes_para_sugerir(), etiquetas=conv.etiqueta_ids.mapped('name'))
        texto = str(respuesta.get('texto') or '').strip() if respuesta.get('ok') else ''
        if not texto:
            raise UserError(self.env._(
                'No pude armar un borrador ahora: %s',
                (respuesta.get('error') or 'el Worker no devolvió texto')[:300]))
        avisos = [str(a)[:200] for a in (respuesta.get('avisos') or []) if isinstance(a, str)][:5]
        return {'texto': texto[:4000], 'avisos': avisos}
