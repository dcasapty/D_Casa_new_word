"""La API de la pantalla «Conversaciones» (panel OWL, docs/JUAN_PANEL.md): métodos públicos del modelo.

Todos exigen ser del equipo de ventas EN EL SERVIDOR (por RPC cualquiera los llamaría) y devuelven diccionarios
sencillos listos para JSON: nada de registros de Odoo ni de campos que la pantalla no use.

* ``lista``      — la bandeja, de 30 en 30, con filtros y búsqueda, y UN número fijo de consultas (no depende de
                   cuántas conversaciones haya: probado con 5.000).
* ``hilo``       — los mensajes por tramos de 50 hacia atrás (``antes_de_id``), nunca el hilo completo.
* ``eliminar``   — borra una conversación (solo Gerencia): primero la copia del bot, luego la de Odoo.
* ``enviar_respuesta``, ``tomar``, ``devolver``, ``cerrar``, ``asignar``, ``poner_etiquetas``, ``agregar_nota``,
  ``marcar_leida`` — lo que hacen los botones, por la MISMA ruta que los botones del formulario.
* ``ficha``      — el cliente y lo que Odoo sabe de él (Socios solo lectura, oportunidades, compras, qué sabe el bot).
"""
import json
import logging
import re
from datetime import UTC, datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from . import adjuntos as A
from . import horario as H
from .ajustes import CANALES
from .conversacion import ESTADOS, GRUPO_VENDEDORA, MAX_NOTA

_logger = logging.getLogger(__name__)

GRUPO_GERENCIA = 'sales_team.group_sale_manager'
MAX_MENCIONES = 8
MAX_DIAS_PROGRAMADO = 30
MAX_PROGRAMADOS_VISIBLES = 20
LIMITE_LISTA = 100
LIMITE_LISTA_POR_DEFECTO = 30
LIMITE_HILO = 100
LIMITE_HILO_POR_DEFECTO = 50
MAX_BUSQUEDA = 100
MAX_RESPUESTA = 4000
MAX_PAUSA_MINUTOS = 7 * 24 * 60
MAX_ETIQUETAS = 12
FILTROS = ('canal', 'estado', 'etiqueta_id', 'asignada_a_mi', 'sin_leer', 'con_oportunidad', 'busqueda')
ESTADOS_FILTRO = tuple(clave for clave, _nombre in ESTADOS) + ('necesita_atencion',)
HERRAMIENTAS_DE_PRODUCTOS = ('juan_buscar_productos', 'juan_ver_producto')
ORIGENES_DE_ADJUNTO_PERMITIDOS = ('dcasa.conversacion', 'mail.compose.message')


def _entero(valor, nombre, minimo=None, maximo=None, permitir_nulo=False):
    """Un entero de verdad (ni booleano, ni texto) dentro de rango; si no, un error en español."""
    if valor is None and permitir_nulo:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise UserError(f'«{nombre}» tiene que ser un número entero.')
    if (minimo is not None and valor < minimo) or (maximo is not None and valor > maximo):
        raise UserError(f'«{nombre}» tiene que estar entre {minimo} y {maximo}.')
    return valor


def iniciales(nombre):
    """«Ana María Pérez» → «AM» (para el círculo cuando no hay foto)."""
    palabras = [p for p in re.split(r'[\s·]+', nombre or '') if p[:1].isalnum()]
    return ''.join(p[0] for p in palabras[:2]).upper() or '?'


class DcasaConversacionPanel(models.Model):
    _inherit = 'dcasa.conversacion'

    # ------------------------------------------------------------------
    # Ayudas
    # ------------------------------------------------------------------

    @api.model
    def _para_panel(self, conversacion_id, escritura=False):
        """La conversación pedida por la pantalla: del equipo de ventas, existente y con permiso."""
        self._exigir_vendedora()
        conversacion_id = _entero(conversacion_id, 'conversacion_id', minimo=1)
        conv = self.browse(conversacion_id).exists()
        if not conv:
            raise UserError(self.env._('Esa conversación ya no existe.'))
        conv.check_access('write' if escritura else 'read')
        return conv

    def _sin_leer(self, ids):
        """``{conversacion_id: n}`` con los mensajes del cliente que esta persona aún no leyó (UNA consulta)."""
        if not ids:
            return {}
        self.env.cr.execute("""
            SELECT m.conversacion_id, COUNT(*)
              FROM dcasa_mensaje m
         LEFT JOIN dcasa_conversacion_lectura l
                ON l.conversacion_id = m.conversacion_id AND l.usuario_id = %s
             WHERE m.conversacion_id IN %s AND m.tipo = 'mensaje' AND m.autor = 'cliente'
               AND m.id > COALESCE(l.ultimo_leido_id, 0)
          GROUP BY m.conversacion_id""", [self.env.uid, tuple(ids)])
        return dict(self.env.cr.fetchall())

    @api.model
    def _ids_con_sin_leer(self):
        """Las conversaciones que esta persona aún no terminó de leer (sin contar mensajes uno por uno)."""
        self.env.cr.execute("""
            SELECT c.id
              FROM dcasa_conversacion c
         LEFT JOIN dcasa_conversacion_lectura l
                ON l.conversacion_id = c.id AND l.usuario_id = %s
             WHERE c.ultimo_cliente_msg_id > COALESCE(l.ultimo_leido_id, 0)""", [self.env.uid])
        return [fila[0] for fila in self.env.cr.fetchall()]

    def _url_foto_perfil(self):
        """La dirección de la foto de perfil guardada (con su fecha, para que el navegador la renueve), o ``None``."""
        self.ensure_one()
        if not self.foto_perfil_en:
            return None
        version = int(fields.Datetime.to_datetime(self.foto_perfil_en).timestamp())
        return f'/web/image/dcasa.conversacion/{self.id}/foto_perfil/128x128?unique={version}'

    def _resumen_panel(self, sin_leer=None):
        """Una fila de la bandeja."""
        self.ensure_one()
        partner = self.partner_id
        nombre = partner.name or self.id_externo
        ahora = fields.Datetime.now()
        return {
            'id': self.id, 'nombre': nombre, 'iniciales': iniciales(nombre),
            'partner_id': partner.id or None,
            'foto': f'/web/image/res.partner/{partner.id}/avatar_128' if partner else None,
            'foto_perfil': self._url_foto_perfil(),
            'canal': self.canal, 'canal_nombre': dict(CANALES).get(self.canal, self.canal),
            'estado': self.estado, 'estado_nombre': dict(ESTADOS).get(self.estado),
            'bot_atiende': self._controla_bot(ahora) and self.estado != 'cerrada',
            'necesita_atencion': self.estado == 'humano' and self.ultimo_mensaje_autor == 'cliente',
            'sin_leer': (sin_leer or {}).get(self.id, 0),
            'ultimo_mensaje': {'texto': self.ultimo_mensaje_texto or '', 'autor': self.ultimo_mensaje_autor or None},
            'ultima_actividad': H.a_iso(self.ultima_actividad),
            'pausada_hasta': H.a_iso(self.pausada_hasta) if self.estado == 'humano' else None,
            'asignada_a': {'id': self.asignada_a.id, 'nombre': self.asignada_a.name} if self.asignada_a else None,
            'etiquetas': [{'id': e.id, 'nombre': e.name, 'color': e.color} for e in self.etiqueta_ids],
            'oportunidad_id': self.oportunidad_id.id or None,
            'por_enviar': self.por_enviar_count,
            'nota_para_el_bot': self.nota_para_el_bot or None,
        }

    # ------------------------------------------------------------------
    # La bandeja
    # ------------------------------------------------------------------

    @api.model
    def _dominio_panel(self, filtros):
        """De los filtros de la pantalla a un dominio. Un filtro desconocido es un error (un descuido se nota)."""
        if filtros is None:
            return []
        if not isinstance(filtros, dict):
            raise UserError(self.env._('Los filtros van en un diccionario.'))
        desconocidos = sorted(set(filtros) - set(FILTROS))
        if desconocidos:
            raise UserError(self.env._('Filtro desconocido: %s.', ', '.join(map(str, desconocidos))))
        dominio = self._dominio_canal_y_estado(filtros.get('canal'), filtros.get('estado'))
        if filtros.get('etiqueta_id'):
            dominio.append(('etiqueta_ids', 'in', [_entero(filtros['etiqueta_id'], 'etiqueta_id', minimo=1)]))
        if filtros.get('asignada_a_mi'):
            dominio.append(('asignada_a', '=', self.env.uid))
        if filtros.get('sin_leer'):
            dominio.append(('id', 'in', self._ids_con_sin_leer()))
        if filtros.get('con_oportunidad'):
            dominio.append(('oportunidad_id', '!=', False))
        return dominio + self._dominio_busqueda(filtros.get('busqueda'))

    @api.model
    def _dominio_canal_y_estado(self, canal, estado):
        dominio = []
        if canal:
            if canal not in dict(CANALES):
                raise UserError(self.env._('Canal desconocido: %s.', canal))
            dominio.append(('canal', '=', canal))
        if estado:
            if estado not in ESTADOS_FILTRO:
                raise UserError(self.env._('Estado desconocido: %s.', estado))
            if estado == 'necesita_atencion':
                dominio += [('estado', '=', 'humano'), ('ultimo_mensaje_autor', '=', 'cliente')]
            else:
                dominio.append(('estado', '=', estado))
        return dominio

    @api.model
    def _dominio_busqueda(self, texto):
        """Por nombre, celular o lo que se dijo en cualquier mensaje (notas incluidas)."""
        busqueda = ' '.join(str(texto or '').split())[:MAX_BUSQUEDA]
        if not busqueda:
            return []
        alternativas = [('partner_id.name', 'ilike', busqueda), ('ultimo_mensaje_texto', 'ilike', busqueda),
                        ('mensaje_ids.texto', 'ilike', busqueda)]
        digitos = re.sub(r'\D', '', busqueda)
        if len(digitos) >= 4:
            alternativas += [('id_externo', 'ilike', digitos), ('partner_id.phone', 'ilike', busqueda)]
        return ['|'] * (len(alternativas) - 1) + alternativas

    @api.model
    def lista(self, filtros=None, offset=0, limite=LIMITE_LISTA_POR_DEFECTO):
        """La bandeja: ``{conversaciones, total, hay_mas, sin_leer_total}``. Las más recientes primero."""
        self._exigir_vendedora()
        offset = _entero(offset, 'offset', minimo=0)
        limite = _entero(limite, 'limite', minimo=1, maximo=LIMITE_LISTA)
        dominio = self._dominio_panel(filtros)
        if self._dominio_busqueda((filtros or {}).get('busqueda')):
            # Con búsqueda, lo caro es mirar el texto de los mensajes: se hace UNA vez
            # (antes, una para contar y otra para la página).
            todas = self.search(dominio)
            total = len(todas)
            conversaciones = todas[offset:offset + limite]
        else:
            total = self.search_count(dominio)
            conversaciones = self.search(dominio, offset=offset, limit=limite)
        sin_leer = self._sin_leer(conversaciones.ids)
        return {
            'conversaciones': [c._resumen_panel(sin_leer) for c in conversaciones],
            'total': total, 'hay_mas': offset + len(conversaciones) < total,
            'sin_leer_total': len(self._ids_con_sin_leer()),
        }

    @api.model
    def hilo(self, conversacion_id, antes_de_id=None, limite=LIMITE_HILO_POR_DEFECTO):
        """Un tramo del hilo, del más viejo al más nuevo. ``antes_de_id`` pide el tramo anterior a ese mensaje."""
        conv = self._para_panel(conversacion_id)
        limite = _entero(limite, 'limite', minimo=1, maximo=LIMITE_HILO)
        antes_de_id = _entero(antes_de_id, 'antes_de_id', minimo=1, permitir_nulo=True)
        dominio = [('conversacion_id', '=', conv.id), ('estado_envio', '!=', 'programado')]
        if antes_de_id:
            dominio.append(('id', '<', antes_de_id))
        tramo = self.env['dcasa.mensaje'].search(dominio, order='id desc', limit=limite + 1)
        hay_mas = len(tramo) > limite
        tramo = tramo[:limite].sorted('id')
        return {
            'conversacion': conv._resumen_panel(conv._sin_leer(conv.ids)),
            'mensajes': [m._como_dict() for m in tramo],
            'hay_mas': hay_mas, 'primer_id': tramo[:1].id or None,
            # Lo que está escrito para más tarde no es parte del hilo todavía: se ve aparte, con su hora.
            'programados': [m._como_dict() for m in self.env['dcasa.mensaje'].search([
                ('conversacion_id', '=', conv.id), ('estado_envio', '=', 'programado')],
                order='programado_para, id', limit=MAX_PROGRAMADOS_VISIBLES)],
        }

    @api.model
    def marcar_leida(self, conversacion_ids):
        """Marca como leídas (para esta persona) una o varias conversaciones: hasta el último mensaje de hoy."""
        self._exigir_vendedora()
        if isinstance(conversacion_ids, int) and not isinstance(conversacion_ids, bool):
            conversacion_ids = [conversacion_ids]
        if not isinstance(conversacion_ids, (list, tuple)) or len(conversacion_ids) > LIMITE_LISTA:
            raise UserError(self.env._('Pásame hasta %s conversaciones.', LIMITE_LISTA))
        ids = [_entero(i, 'conversacion_ids', minimo=1) for i in conversacion_ids]
        conversaciones = self.browse(ids).exists()
        conversaciones.check_access('read')
        if conversaciones:
            self.env.cr.execute("""
                INSERT INTO dcasa_conversacion_lectura
                            (conversacion_id, usuario_id, ultimo_leido_id,
                             create_uid, create_date, write_uid, write_date)
                     SELECT c.id, %(uid)s,
                            COALESCE((SELECT MAX(m.id) FROM dcasa_mensaje m WHERE m.conversacion_id = c.id), 0),
                            %(uid)s, NOW() AT TIME ZONE 'UTC', %(uid)s, NOW() AT TIME ZONE 'UTC'
                       FROM dcasa_conversacion c WHERE c.id IN %(ids)s
                ON CONFLICT (conversacion_id, usuario_id) DO UPDATE
                        SET ultimo_leido_id = GREATEST(EXCLUDED.ultimo_leido_id,
                                                       dcasa_conversacion_lectura.ultimo_leido_id),
                            write_date = EXCLUDED.write_date""",
                {'uid': self.env.uid, 'ids': tuple(conversaciones.ids)})
            self.env['dcasa.conversacion.lectura'].invalidate_model()
        return {'marcadas': conversaciones.ids}

    # ------------------------------------------------------------------
    # Lo que hacen los botones
    # ------------------------------------------------------------------

    def _hora_de_envio(self, programar_para):
        """La hora (UTC, sin zona) a la que se programó un mensaje, validada: entre 1 minuto y 30 días desde ahora."""
        if not isinstance(programar_para, str):
            raise UserError(self.env._('La hora del envío no es válida.'))
        try:
            hora = datetime.fromisoformat(programar_para.replace('Z', '+00:00'))
        except ValueError:
            raise UserError(self.env._('La hora del envío no es válida.')) from None
        if hora.tzinfo is not None:
            hora = hora.astimezone(UTC).replace(tzinfo=None)
        ahora = fields.Datetime.now()
        if hora < ahora + timedelta(minutes=1):
            raise UserError(self.env._('La hora tiene que ser en el futuro.'))
        if hora > ahora + timedelta(days=MAX_DIAS_PROGRAMADO):
            raise UserError(self.env._('Solo se puede programar con %s días de anticipación como máximo.',
                                       MAX_DIAS_PROGRAMADO))
        return hora.replace(second=0, microsecond=0)

    @api.model
    def enviar_respuesta(self, conversacion_id, texto=None, adjuntos_ids=None, programar_para=None):
        """Una vendedora contesta desde la pantalla. Si el Worker no responde, queda «por enviar» y se reintenta.

        ``programar_para`` (fecha y hora ISO): en vez de enviar ahora, el mensaje sale solo a esa hora.
        """
        conv = self._para_panel(conversacion_id, escritura=True)
        cuando = self._hora_de_envio(programar_para) if programar_para else None
        texto = (texto or '').strip() if isinstance(texto, str) or texto is None else None
        if texto is None:
            raise UserError(self.env._('El texto de la respuesta tiene que ser texto.'))
        if len(texto) > MAX_RESPUESTA:
            raise UserError(self.env._('La respuesta es muy larga (máximo %s letras).', MAX_RESPUESTA))
        adjuntos = conv._adjuntos_de_la_respuesta(adjuntos_ids)
        if not texto and not adjuntos:
            raise UserError(self.env._('Escribe algo o adjunta un archivo antes de enviar.'))
        mensaje = conv._crear_mensaje_de_odoo(texto, adjuntos, usuario=self.env.user, programado_para=cuando)
        if cuando:
            conv.marcar_leida(conv.id)
            return {'mensaje': mensaje._como_dict(), 'enviado': False, 'programado': True,
                    'conversacion': conv._resumen_panel()}
        mensaje._enviar()
        if not mensaje.exists():
            # El Worker ya había registrado su eco de este mensaje y se fusionaron: queda el del Worker.
            mensaje = self.env['dcasa.mensaje'].search([
                ('conversacion_id', '=', conv.id), ('usuario_id', '=', self.env.uid), ('origen', '=', 'odoo'),
                ('tipo', '=', 'mensaje')], order='id desc', limit=1)
        conv.marcar_leida(conv.id)
        return {'mensaje': mensaje._como_dict(), 'enviado': mensaje.estado_envio == 'enviado',
                'conversacion': conv._resumen_panel()}

    @api.model
    def cancelar_programado(self, mensaje_id):
        """Cancela un mensaje que todavía no salió. Solo quien lo programó o Gerencia."""
        self._exigir_vendedora()
        mensaje = self.env['dcasa.mensaje'].browse(_entero(mensaje_id, 'mensaje_id', minimo=1)).exists()
        if not mensaje:
            raise UserError(self.env._('Ese mensaje ya no existe.'))
        conv = self._para_panel(mensaje.conversacion_id.id, escritura=True)
        mensaje = mensaje.sudo()
        if mensaje.estado_envio != 'programado':
            raise UserError(self.env._('Ese mensaje ya salió o ya no está programado.'))
        if mensaje.usuario_id != self.env.user and not self.env.user.has_group(GRUPO_GERENCIA):
            raise AccessError(self.env._('Solo quien lo programó, o Gerencia, puede cancelarlo.'))
        ya_dicho = self.env._('%(quien)s canceló un mensaje que había programado para el cliente.',
                              quien=self.env.user.name)
        mensaje.adjunto_ids.unlink()
        mensaje.unlink()
        conv._aviso(ya_dicho)
        return {'cancelado': True, 'conversacion': conv._resumen_panel()}

    def _adjuntos_de_la_respuesta(self, adjuntos_ids):
        """Los archivos que la vendedora subió para esta respuesta: suyos, sin dueño todavía y no más de cinco."""
        self.ensure_one()
        if not adjuntos_ids:
            return self.env['ir.attachment']
        if not isinstance(adjuntos_ids, (list, tuple)) or len(adjuntos_ids) > A.MAX_ADJUNTOS:
            raise UserError(self.env._('Puedes adjuntar hasta %s archivos por mensaje.', A.MAX_ADJUNTOS))
        ids = [_entero(i, 'adjuntos_ids', minimo=1) for i in adjuntos_ids]
        adjuntos = self.env['ir.attachment'].browse(ids).exists()
        if len(adjuntos) != len(set(ids)):
            raise UserError(self.env._('Alguno de los archivos ya no existe. Súbelo otra vez.'))
        for adjunto in adjuntos:
            adjunto.check_access('read')
            libre = (not adjunto.res_model or adjunto.res_model in ORIGENES_DE_ADJUNTO_PERMITIDOS) \
                and adjunto.res_id in (0, self.id)
            if not libre or adjunto.create_uid != self.env.user:
                raise UserError(self.env._('El archivo «%s» no se puede usar en esta respuesta.', adjunto.name))
            if (adjunto.file_size or 0) > A.MAX_BYTES:
                raise UserError(self.env._('«%s» pesa demasiado (máximo 10 MB).', adjunto.name))
        return adjuntos

    @api.model
    def tomar(self, conversacion_id, minutos=None):
        """«Atender»: el asistente calla ``minutos`` (0 = hasta que se la devuelvan; sin valor = el de los ajustes)."""
        conv = self._para_panel(conversacion_id, escritura=True)
        minutos = _entero(minutos, 'minutos', minimo=0, maximo=MAX_PAUSA_MINUTOS, permitir_nulo=True)
        conv._tomar(self.env.user, minutos)
        return conv._resumen_panel()

    @api.model
    def devolver(self, conversacion_id, nota=None):
        """«Devolver al asistente», con una nota opcional que el asistente lee en sus próximas respuestas."""
        conv = self._para_panel(conversacion_id, escritura=True)
        if nota is not None and not isinstance(nota, str):
            raise UserError(self.env._('La nota para el asistente tiene que ser texto.'))
        conv._devolver(self.env.user, nota)
        return conv._resumen_panel()

    @api.model
    def cerrar(self, conversacion_id):
        conv = self._para_panel(conversacion_id, escritura=True)
        conv._cerrar(self.env.user)
        return conv._resumen_panel()

    @api.model
    def eliminar(self, conversacion_id):
        """«Eliminar conversación» (solo Gerencia; Ley 81, derecho de borrado).

        Primero el bot olvida su copia de trabajo (si no, seguiría «recordando» lo borrado y, al volver a escribir la
        persona, reaparecería el historial); solo cuando eso salió bien se borra la conversación de Odoo, con sus
        mensajes y archivos. La oportunidad y la ficha del cliente NO se tocan: son registros del negocio.
        """
        conv = self._para_panel(conversacion_id, escritura=True)
        if not self.env.su and not self.env.user.has_group(GRUPO_GERENCIA):
            raise AccessError(self.env._('Solo Gerencia puede eliminar una conversación.'))
        conv.check_access('unlink')
        respuesta = self.env['dcasa.juan.cliente'].olvidar_conversacion(conv.canal, conv.id_externo)
        if not respuesta['sin_configurar'] and (respuesta['error'] or respuesta['cuerpo'].get('ok') is not True):
            raise UserError(self.env._(
                'No pude borrar la copia que guarda el bot de esta conversación (%s). No se eliminó nada: '
                'inténtalo de nuevo en unos minutos.', respuesta['error'] or self.env._('el bot no respondió')))
        _logger.info('Juan: %s eliminó la conversación %s (%s).', self.env.user.login, conv.id, conv.canal)
        conv.unlink()
        return {'eliminada': True, 'conversacion_id': conversacion_id}

    @api.model
    def asignar(self, conversacion_id, usuario_id=None):
        """Asigna la conversación a una persona del equipo de ventas (``None`` la deja sin asignar)."""
        conv = self._para_panel(conversacion_id, escritura=True)
        usuario_id = _entero(usuario_id, 'usuario_id', minimo=1, permitir_nulo=True)
        if usuario_id:
            usuario = self.env['res.users'].sudo().browse(usuario_id).exists()
            if not usuario or usuario.share or not usuario.has_group(GRUPO_VENDEDORA):
                raise UserError(self.env._('Solo se puede asignar a alguien del equipo de ventas.'))
            conv.sudo().write({'asignada_a': usuario.id})
            conv._aviso(self.env._('%(quien)s asignó la conversación a %(a)s.', quien=self.env.user.name,
                                   a=usuario.name))
        else:
            conv.sudo().write({'asignada_a': False})
            conv._aviso(self.env._('%s dejó la conversación sin asignar.', self.env.user.name))
        conv._notificar_panel('asignacion')
        return conv._resumen_panel()

    @api.model
    def cancelar_seguimiento(self, conversacion_id):
        """Cancela el seguimiento que esté por tocarle a esta persona (y los que faltaban): ya no insistimos.

        Si el Worker ya tiene pedido uno (``seguimiento_pedido_en``) ese no se puede detener desde aquí.
        """
        conv = self._para_panel(conversacion_id, escritura=True)
        if conv.seguimiento_pedido_en:
            raise UserError(self.env._('El seguimiento ya está en camino y no se puede cancelar.'))
        if not conv.seguimiento_proximo:
            raise UserError(self.env._('Esta conversación no tiene un seguimiento programado.'))
        maximo = self.env['dcasa.juan.ajustes'].obtener().seguimiento_maximo
        conv.sudo().write({'seguimiento_proximo': False,
                           'seguimientos_enviados': max(maximo, conv.seguimientos_enviados)})
        conv._aviso(self.env._('%s canceló el seguimiento programado.', self.env.user.name))
        return conv._resumen_panel()

    @api.model
    def poner_etiquetas(self, conversacion_id, etiqueta_ids):
        """Deja exactamente esas etiquetas (activas). Las inactivas que ya tenía se conservan."""
        conv = self._para_panel(conversacion_id, escritura=True)
        if not isinstance(etiqueta_ids, (list, tuple)) or len(etiqueta_ids) > MAX_ETIQUETAS:
            raise UserError(self.env._('Pásame la lista de etiquetas (hasta %s).', MAX_ETIQUETAS))
        ids = [_entero(i, 'etiqueta_ids', minimo=1) for i in etiqueta_ids]
        Etiqueta = self.env['dcasa.conversacion.etiqueta'].sudo()
        elegidas = Etiqueta.browse(ids).exists().filtered('activa')
        if len(elegidas) != len(set(ids)):
            raise UserError(self.env._('Alguna etiqueta no existe o está inactiva.'))
        inactivas = conv.sudo().etiqueta_ids.filtered(lambda e: not e.activa)
        conv.sudo().write({'etiqueta_ids': [(6, 0, (elegidas | inactivas).ids)]})
        conv._notificar_panel('etiquetas')
        return conv._resumen_panel()

    def _mencionadas_validas(self, menciones):
        """Las personas mencionadas con @ (``res.users``): del equipo de ventas, sin repetir y sin la misma autora."""
        if menciones in (None, []):
            return self.env['res.users']
        if not isinstance(menciones, (list, tuple)) or len(menciones) > MAX_MENCIONES:
            raise UserError(self.env._('Se pueden mencionar hasta %s personas por nota.', MAX_MENCIONES))
        ids = [_entero(i, 'menciones', minimo=1) for i in menciones]
        equipo = self._usuarios_del_panel()
        if not set(ids) <= set(equipo.ids):
            raise UserError(self.env._('Solo se puede mencionar a alguien del equipo de ventas.'))
        return equipo.filtered(lambda u: u.id in ids and u != self.env.user)

    @api.model
    def agregar_nota(self, conversacion_id, texto, menciones=None, tarea_para=None):
        """Una nota interna en el hilo (el cliente jamás la ve; queda también en la ficha del cliente).

        ``menciones``: ids de compañeras mencionadas con @; se les avisa en Odoo y por Telegram.
        ``tarea_para``: fecha ``AAAA-MM-DD``; si viene, cada mencionada recibe además una tarea con esa fecha.
        """
        conv = self._para_panel(conversacion_id, escritura=True)
        if not isinstance(texto, str) or not texto.strip():
            raise UserError(self.env._('Escribe la nota.'))
        if len(texto.strip()) > MAX_NOTA:
            raise UserError(self.env._('La nota es muy larga (máximo %s letras).', MAX_NOTA))
        mencionadas = self._mencionadas_validas(menciones)
        fecha = None
        if tarea_para not in (None, ''):
            try:
                fecha = fields.Date.to_date(tarea_para) if isinstance(tarea_para, str) else None
            except (ValueError, TypeError):
                fecha = None
            hoy = fields.Date.context_today(self)
            if not fecha or fecha < hoy or fecha > hoy + timedelta(days=366):
                raise UserError(self.env._('La fecha de la tarea no es válida.'))
            if not mencionadas:
                raise UserError(self.env._('Para crear una tarea, menciona con @ a quien la va a hacer.'))
        nota = self.env['dcasa.mensaje']._crear_interno(conv, 'nota', texto, self.env.user, menciones=mencionadas)
        nota._publicar_en_chatter()
        conv._notificar_panel('mensaje', nota)
        avisos = conv._avisar_mencion(nota, mencionadas, fecha) if mencionadas else {'telegram': 0, 'tareas': 0}
        return {'mensaje': nota._como_dict(), 'mencionadas': len(mencionadas), **avisos}

    # ------------------------------------------------------------------
    # La ficha del cliente
    # ------------------------------------------------------------------

    @api.model
    def ficha(self, conversacion_id):
        """El cliente y lo que Odoo sabe de él, solo lo que una vendedora necesita para contestar."""
        conv = self._para_panel(conversacion_id)
        partner = conv.partner_id.sudo()
        comercial = partner.commercial_partner_id
        socio = bool(comercial.dcasa_reclamada and comercial.dcasa_socio_estado == 'activo') if partner else False
        # Con sudo y solo de ESTE cliente: la oportunidad es suya aunque la lleve otra vendedora (y así no se
        # duplica el trabajo); se devuelven pocos campos.
        oportunidades = self.env['crm.lead'].sudo().search([
            ('partner_id', '=', partner.id), ('type', '=', 'opportunity'), ('won_status', '=', 'pending'),
        ], limit=5, order='id desc') if partner else self.env['crm.lead']
        compras = self.env['account.move'].sudo().search([
            ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'),
            ('commercial_partner_id', '=', comercial.id)], limit=5, order='invoice_date desc, id desc') \
            if partner else self.env['account.move']
        notas = self.env['dcasa.mensaje'].search(
            [('conversacion_id', '=', conv.id), ('tipo', '=', 'nota')], order='id desc', limit=10)
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        return {
            'conversacion': conv._resumen_panel(),
            'cliente': {
                'id': partner.id or None, 'nombre': partner.name or conv.id_externo, 'celular': conv.celular or '',
                'correo': partner.email or '', 'no_contactar': bool(partner.dcasa_no_contactar),
                'canal': conv.canal, 'canal_nombre': dict(CANALES).get(conv.canal, conv.canal),
            },
            'socio': {
                'es_socio': socio,
                # Solo lectura y solo el total: el detalle de movimientos vive en Socios.
                'puntos': comercial.dcasa_saldo if socio else None,
            },
            'oportunidades': [{
                'id': o.id, 'nombre': o.name, 'etapa': o.stage_id.name or '',
                'ingreso_esperado': round(o.expected_revenue or 0.0, 2),
            } for o in oportunidades],
            'compras': [{
                'id': f.id, 'numero': f.name,
                'fecha': fields.Date.to_string(f.invoice_date) if f.invoice_date else None,
                'total': round(f.amount_total, 2), 'pagada': f.payment_state in ('paid', 'in_payment'),
            } for f in compras],
            'notas': [n._como_dict() for n in notas],
            'seguimiento': {
                'enviados': conv.seguimientos_enviados, 'maximo': ajustes.seguimiento_maximo,
                'proximo': H.a_iso(conv.seguimiento_proximo),
                'pendiente': bool(conv.seguimiento_pedido_en),
            },
            'bot_sabe': conv._lo_que_sabe_el_bot(socio, oportunidades),
        }

    def _lo_que_sabe_el_bot(self, socio, oportunidades):
        """«Qué sabe el bot de esta persona»: nombre, canal, si es Socio, qué preguntó y su oportunidad abierta."""
        self.ensure_one()
        preguntados = []
        acciones = self.env['brian.accion'].sudo().search([
            ('dcasa_conversacion_id', '=', self.id), ('herramienta', 'in', HERRAMIENTAS_DE_PRODUCTOS),
            ('estado', '=', 'hecha')], order='id desc', limit=20)
        for accion in acciones:
            try:
                argumentos = json.loads(accion.argumentos or '{}')
            except ValueError:
                continue
            if not isinstance(argumentos, dict):
                continue
            producto = str(argumentos.get('consulta') or argumentos.get('codigo') or '').strip()[:80]
            if producto and producto.lower() not in [p.lower() for p in preguntados]:
                preguntados.append(producto)
        return {
            'nombre': self._nombre_de_pila() or None, 'celular': self.celular or None,
            'canal': dict(CANALES).get(self.canal, self.canal), 'es_socio': socio,
            'productos_preguntados': preguntados[:8],
            'oportunidad_abierta': oportunidades[:1].name if oportunidades else None,
            'etiquetas': self.etiqueta_ids.mapped('name'),
            'ultima_vez_que_hablo': H.a_iso(self.ultimo_mensaje_cliente),
            'seguimiento_pendiente': bool(self.seguimiento_proximo or self.seguimiento_pedido_en),
            'nota_para_el_bot': self.nota_para_el_bot or None,
        }
