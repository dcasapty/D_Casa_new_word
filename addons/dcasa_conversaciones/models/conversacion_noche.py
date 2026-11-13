"""De noche nadie recibe clientes ni avisos (pedido de la dueña, 2026-11-13: «yo entro a la 1 de la mañana y veo
vendedoras activas porque no saben en qué momento llega un cliente… las muchachas tal vez tampoco descansan»).

Con «De noche nadie recibe clientes» encendido en Ajustes de Juan (de fábrica, y en producción por la migración
19.0.1.5.0) y fuera del horario de la tienda (``ajustes.horario()``):

* Juan atiende y anota como siempre, y lo que le dice al cliente ya dice cuándo le escriben.
* Cuando pasa un cliente a una persona, el reparto no se lo da a nadie aunque haya alguien conectada
  (``_dejar_para_la_manana``): queda sin dueña, con ``reparto_desde``, como lo entiende el cron del reparto. El que ya
  era de una vendedora sigue siendo suyo. La tarea y el aviso en el hilo, como de día.
* Ningún Telegram a las vendedoras por clientes: ni el del traspaso, ni el de un comprobante, una cédula o un archivo,
  ni el de un cliente que espera. Siguen igual las menciones en una nota (las escribe una persona a propósito), «tomó a
  tu cliente», el programado que no salió y los de Gerencia. Lo que no se avisó queda anotado en la conversación
  (``aviso_de_noche``, ``archivo_de_noche``).
* Al abrir (``dcasa.reparto._cron_reasignar``, cada 5 minutos dentro del horario): los clientes de la noche vuelven al
  reparto (``_volver_al_reparto_lo_de_la_noche``: la pausa del asistente vence de noche y el cliente volvía al bot sin
  que nadie lo recibiera), se reparten de a pocos con el tope, como siempre (su vendedora de siempre primero), y cada
  vendedora recibe UN Telegram por vuelta con su lista (``_avisar_lo_de_la_noche``), con un «Atender» por cliente.
  Lo que no es de nadie (con el reparto apagado, o un comprobante de un cliente que atendía Juan) llega en un solo aviso
  a las personas de siempre.

Con el interruptor apagado, todo como antes.
"""
import logging

from odoo import api, fields, models

from . import horario as H
from .avisos_texto import armar, frase
from .conversacion import ARCHIVOS_DE_NOCHE, FRASE_DE_LA_LISTA, SIN_AVISOS_DE_NOCHE

_logger = logging.getLogger(__name__)

# Lo más importante gana: un comprobante de pago tapa a una cédula.
PRIORIDAD_DE_ARCHIVO = {clave: len(ARCHIVOS_DE_NOCHE) - i for i, (clave, _n) in enumerate(ARCHIVOS_DE_NOCHE)}
# Clientes por mensaje en la lista de la mañana (más de esto, otro mensaje): corto para leer en el celular.
MAX_EN_UNA_LISTA = 10
# Conversaciones que mira cada vuelta de la mañana.
LOTE_DE_LA_MANANA = 200
# Un botón «Atender» con el nombre del cliente: Telegram corta lo largo.
MAX_TEXTO_DE_BOTON = 40


class DcasaConversacionNoche(models.Model):
    _inherit = 'dcasa.conversacion'

    # ------------------------------------------------------------------
    # De noche
    # ------------------------------------------------------------------

    @api.model
    def _es_de_noche(self, ahora=None, ajustes=None):
        """¿Rige ahora «De noche nadie recibe clientes»? Encendido y fuera del horario de la tienda."""
        ajustes = ajustes or self.env['dcasa.juan.ajustes'].obtener()
        return bool(ajustes.reparto_nadie_de_noche) and \
            not H.dentro_de_horario(ahora or fields.Datetime.now(), ajustes.horario())

    def _dejar_para_la_manana(self, motivo, urgente):
        """Juan pasó el cliente a una persona de noche: nadie lo recibe ni se avisa. Queda esperando la apertura de la
        forma que entiende el cron del reparto (sin dueña y con ``reparto_desde``); el cliente que ya era de una
        vendedora del reparto sigue siendo suyo. Devuelve la frase para el hilo."""
        self.ensure_one()
        conv = self.sudo()
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        ahora = fields.Datetime.now()
        valores = {'aviso_de_noche_motivo': frase(motivo) or False,
                   'aviso_de_noche_urgente': bool(urgente or conv.aviso_de_noche_urgente)}
        if not conv.aviso_de_noche:
            valores['aviso_de_noche'] = ahora
        if ajustes.reparto_modo == 'manual':
            conv.write(valores)
            return self.env._('Llegó con la tienda cerrada: de noche no se avisa a nadie. Se avisa al abrir.')
        duena = conv.asignada_a if conv.asignada_a in self.env['dcasa.reparto']._equipo() else self.env['res.users']
        valores['reparto_desde'] = ahora
        if not duena:
            valores['asignada_a'] = False
        conv.write(valores)
        if duena:
            return self.env._('Llegó con la tienda cerrada: sigue con %s y se le avisa al abrir.', duena.name)
        return self.env._(
            'Llegó con la tienda cerrada: de noche nadie recibe clientes. Se reparte y se avisa al abrir.')

    def _anotar_archivo_de_noche(self, que):
        """Un comprobante, un archivo que Juan no lee o una cédula que llegó de noche: se avisa al abrir (queda lo más
        importante de lo que mandó)."""
        self.ensure_one()
        actual = self.sudo().archivo_de_noche
        if PRIORIDAD_DE_ARCHIVO.get(que, 0) > PRIORIDAD_DE_ARCHIVO.get(actual, 0):
            self.sudo().archivo_de_noche = que

    # ------------------------------------------------------------------
    # Al abrir
    # ------------------------------------------------------------------

    @api.model
    def _volver_al_reparto_lo_de_la_noche(self):
        """Los clientes que pidieron una persona de noche y nadie del equipo atendió vuelven al reparto: la pausa del
        asistente (2 horas de fábrica) vence de noche, la conversación vuelve al bot y el cron del reparto ya no la
        veía. Se ponen otra vez con una persona (el asistente calla, como cuando Juan la pasa) y su ``reparto_desde`` es
        la hora de la noche: cuenta como «de antes de abrir» para el tope. Devuelve cuántas volvieron."""
        # También la que sigue «con una persona» con la pausa ya vencida (el mantenimiento de cada 5 minutos todavía no
        # la devolvió al bot): si no, el reparto se la daría a alguien y enseguida volvería al asistente.
        volvieron = self.sudo().search([
            ('aviso_de_noche', '!=', False), ('traspaso_sin_atender_desde', '!=', False), ('estado', '!=', 'cerrada'),
            '|', '|', ('estado', '=', 'bot'), ('reparto_desde', '=', False),
            '&', ('pausada_hasta', '!=', False), ('pausada_hasta', '<=', fields.Datetime.now())],
            order='aviso_de_noche, id', limit=LOTE_DE_LA_MANANA)
        for conv in volvieron:
            conv._poner_en_humano()
            # El Worker pregunta el estado antes de contestar; el aviso se manda en el mantenimiento (sin esperar aquí).
            conv.write({'reparto_desde': conv.aviso_de_noche, 'estado_pendiente_de_avisar': True})
            conv._aviso(self.env._('Abrió la tienda y este cliente espera a una persona desde la noche: vuelve al '
                                   'reparto y el asistente calla mientras tanto.'))
            conv._notificar_panel('estado')
        return len(volvieron)

    @api.model
    def _avisar_lo_de_la_noche(self):
        """Lo que no se avisó de noche, al abrir (lo llama el cron del reparto en cada vuelta dentro del horario):

        * El cliente que pidió una persona, con el reparto encendido: cuando ya tiene a quién (el reparto se lo dio o ya
          era suyo), en la lista de ella. Mientras espera su turno (el tope), no se avisa a nadie.
        * El que no es de nadie (reparto apagado o «pasar a otra» en 0), o el comprobante, la cédula o el archivo de un
          cliente que atendía Juan: a las personas de siempre, como de día.

        A cada persona le llega UN mensaje por vuelta (``_aviso_de_la_manana``). Si ella no tiene Telegram, lo suyo va
        a las de siempre. Devuelve a cuántas personas les llegó algo."""
        if not H.dentro_de_horario(fields.Datetime.now(), self.env['dcasa.juan.ajustes'].obtener().horario()):
            return 0
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        reparte = ajustes.reparto_modo != 'manual' and ajustes.reparto_reasignar_minutos > 0
        pendientes = self.sudo().search(['|', ('aviso_de_noche', '!=', False), ('archivo_de_noche', '!=', False)],
                                        order='id', limit=LOTE_DE_LA_MANANA)
        por_persona, para_todas, listos = {}, self.sudo().browse(), self.sudo().browse()
        for conv in pendientes:
            espera = bool(conv.aviso_de_noche and conv.traspaso_sin_atender_desde) and conv.estado != 'cerrada'
            if espera and reparte and not conv.asignada_a:
                continue   # espera su turno en el reparto: se avisa cuando le toque a alguien
            listos |= conv
            if espera and reparte:
                por_persona[conv.asignada_a] = por_persona.get(conv.asignada_a, self.sudo().browse()) | conv
            elif espera or conv.archivo_de_noche:
                para_todas |= conv
        llegaron = 0
        for usuario, suyas in por_persona.items():
            enviados = suyas._aviso_de_la_manana(usuario)
            if enviados:
                llegaron += 1
            else:
                para_todas |= suyas   # sin Telegram vinculado: a las de siempre, como de día
        if para_todas:
            llegaron += para_todas._aviso_de_la_manana(None)
        # Lo que ya se avisó (en la lista o a las de siempre) no vuelve a sonar como «un cliente te espera» enseguida.
        listos.write({**SIN_AVISOS_DE_NOCHE, 'espera_avisada_en': fields.Datetime.now()})
        return llegaron

    def _aviso_de_la_manana(self, usuario):
        """Un solo mensaje para ``usuario`` (o, sin él, para las personas de siempre) con estos clientes de la noche. Si
        es uno solo, el aviso normal (con su pie para responder); si son varios, la lista con un «Atender» por cliente
        (de a ``MAX_EN_UNA_LISTA``). Devuelve a cuántas personas les llegó el primero."""
        convs = self.sorted(lambda c: (not c.aviso_de_noche_urgente, c.aviso_de_noche or c.write_date, c.id))
        usuarios = usuario or None
        if len(convs) == 1:
            return convs._avisar_por_telegram(convs._texto_de_la_manana(usuario), usuarios=usuarios, acciones=True)
        llegaron = 0
        for inicio in range(0, len(convs), MAX_EN_UNA_LISTA):
            tramo = convs[inicio:inicio + MAX_EN_UNA_LISTA]
            texto, botones = convs._lista_de_la_manana(tramo, usuario, primera=inicio == 0)
            enviados = convs[:1]._avisar_por_telegram(texto, usuarios=usuarios, botones=botones)
            llegaron = llegaron or enviados
        return llegaron

    # ------------------------------------------------------------------
    # Los textos de la mañana (la misma forma que los demás: ver ``conversacion_avisos.py``)
    # ------------------------------------------------------------------

    def _espera_a_una_persona(self):
        self.ensure_one()
        return bool(self.aviso_de_noche and self.traspaso_sin_atender_desde)

    def _es_suyo_de_antes(self, usuario):
        """¿El cliente ya era de ``usuario`` antes de esta mañana (lo tenía de noche, o volvió con su vendedora de
        siempre)? Si el reparto se lo acaba de dar por primera vez, no."""
        self.ensure_one()
        linea = self.env['dcasa.reparto'].sudo().search([
            ('conversacion_id', '=', self.id), ('usuario_id', '=', usuario.id),
            ('momento', '>=', self.aviso_de_noche)], order='id desc', limit=1)
        return not linea or linea.regla == 'misma'

    def _lo_que_mando_de_noche(self, corto=False):
        """«Mandó un comprobante de pago: verifícalo…»: lo que mandó de noche, en una frase (vacío si nada)."""
        self.ensure_one()
        textos = {
            'comprobante': (self.env._('Mandó un comprobante de pago: verifícalo en el banco antes de entregar nada.'),
                            self.env._('mandó un comprobante de pago: verifícalo en el banco antes de entregar nada.')),
            'documento': (self.env._('Mandó un archivo que Juan no puede leer: puede ser un comprobante.'),
                          self.env._('mandó un archivo que Juan no puede leer: puede ser un comprobante.')),
            'identidad': (self.env._('Mandó su cédula: revísala en Conversaciones.'),
                          self.env._('mandó su cédula: revísala en Conversaciones.')),
        }
        if not self.archivo_de_noche:
            return ''
        return textos[self.archivo_de_noche][1 if corto else 0]

    def _texto_de_la_manana(self, usuario):
        """El aviso de UN cliente de la noche: el del traspaso (o el del archivo) con «escribió de noche»."""
        self.ensure_one()
        if not self._espera_a_una_persona():
            return self._texto_archivo(self.archivo_de_noche, de_noche=True)
        texto = self._texto_traspaso(self.aviso_de_noche_motivo, self.aviso_de_noche_urgente, para_ella=bool(usuario),
                                     misma=bool(usuario) and self._es_suyo_de_antes(usuario), de_noche=True)
        mando = self._lo_que_mando_de_noche()
        if not mando:
            return texto
        # Lo que mandó va antes de «qué hacer» (la última línea).
        lineas = texto.split('\n')
        return armar(*lineas[:-1], mando, lineas[-1])

    def _renglon_de_la_manana(self, usuario):
        """Un renglón de la lista: quién, por dónde y qué quiere (o qué mandó)."""
        self.ensure_one()
        cliente, canal = self._aviso_cliente(), self._aviso_canal()
        if not self._espera_a_una_persona():
            return f'{cliente} ({canal}) {self._lo_que_mando_de_noche(corto=True)}'
        if usuario:
            partes = [f'{cliente} ({canal}):']
        else:
            partes = [self.env._('%(cliente)s (%(canal)s) pide una persona:', cliente=cliente, canal=canal)]
        partes.append(frase(self.aviso_de_noche_motivo) or self.env._('no dejó dicho qué quiere.'))
        if usuario and self._es_suyo_de_antes(usuario):
            partes.append(self.env._('Es tu cliente.'))
        if self.archivo_de_noche:
            partes.append(self._lo_que_mando_de_noche())
        if not usuario and self.sudo().asignada_a:
            partes.append(self.env._('Lo tiene %s.', self.sudo().asignada_a.name))
        renglon = ' '.join(partes)
        return f"{self.env._('🔴 URGENTE:')} {renglon}" if self.aviso_de_noche_urgente else renglon

    def _lista_de_la_manana(self, tramo, usuario, primera=True):
        """``(texto, botones)`` de la lista de la mañana de ``tramo`` (varios clientes)."""
        horario = self.env['dcasa.juan.ajustes'].obtener().horario()
        manana = H.a_local(fields.Datetime.now(), horario).hour < 12
        nombre = (usuario.name or '').split()[0] if usuario and usuario.name else ''
        if usuario:
            titulo = self.env._('☀️ Buenos días, %s', nombre) if manana else self.env._('☀️ Hola, %s', nombre)
            intro = self.env._('Te tocan %s clientes que escribieron de noche:', len(tramo))
        else:
            titulo = self.env._('☀️ Buenos días') if manana else self.env._('☀️ Lo que llegó de noche')
            intro = self.env._('Esto llegó de noche, con la tienda cerrada:')
        if not primera:
            titulo = self.env._('☀️ Más de la noche')
        renglones = [f'{n}. {conv._renglon_de_la_manana(usuario)}' for n, conv in enumerate(tramo, 1)]
        # Texto fijo (sin traducir): la consola de Telegram lo reconoce (``FRASE_DE_LA_LISTA``).
        hacer = f"{FRASE_DE_LA_LISTA} {self.env._('Te llega un mensaje: respóndele para escribirle al cliente.')}"
        botones = []
        for n, conv in enumerate(tramo, 1):
            texto_boton = f"{self.env._('Atender')} {n} · {conv._aviso_cliente()}"
            if len(texto_boton) > MAX_TEXTO_DE_BOTON:
                texto_boton = f'{texto_boton[:MAX_TEXTO_DE_BOTON - 1]}…'
            botones.append([{'text': texto_boton, 'callback_data': f'juan:t:{conv.id}'}])
        return armar(titulo, intro, *renglones, hacer), botones
