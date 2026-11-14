"""De noche nadie recibe clientes ni avisos (pedido de la dueña, 2026-11-13: «yo entro a la 1 de la mañana y veo
vendedoras activas porque no saben en qué momento llega un cliente… las muchachas tal vez tampoco descansan»).

Con «De noche nadie recibe clientes» encendido en Ajustes de Juan (de fábrica, y en producción por la migración
19.0.1.5.0) y fuera del horario de la tienda (``ajustes.horario()``):

* Juan atiende y anota como siempre, y lo que le dice al cliente ya dice cuándo le escriben.
* Cuando pasa un cliente a una persona, el reparto no se lo da a nadie aunque haya alguien conectada
  (``_dejar_para_la_manana``): queda con ``reparto_desde``, como lo entiende el cron del reparto. Al que ya tenía a
  alguien no se le quita de noche; al abrir se decide con las reglas del día (``_soltar_lo_de_la_noche_ajeno``). La
  tarea y el aviso en el hilo, como de día.
* Ningún Telegram a las vendedoras por clientes: ni el del traspaso, ni el de un comprobante, una cédula o algo que
  Juan no leyó, ni el de un cliente que espera. Siguen igual las menciones en una nota (las escribe una persona a
  propósito), «tomó a tu cliente», el programado que no salió y los de Gerencia. Lo que no se avisó queda anotado en la
  conversación (``aviso_de_noche``, ``archivo_de_noche``).
* Al abrir (``dcasa.reparto._cron_reasignar``, cada 5 minutos dentro del horario):

  1. los clientes de la noche vuelven al reparto (``_volver_al_reparto_lo_de_la_noche``: la pausa del asistente vence
     de noche y el cliente volvía al bot sin que nadie lo recibiera), con ``reparto_desde`` justo antes de abrir (nunca
     fuera de la ventana del reparto, aunque la tienda cierre una semana);
  2. el que tenía dueña sigue con ella si está disponible y lo atendió en los «Días que un cliente sigue con su
     vendedora»; si no, se reparte como de día;
  3. se reparten de a pocos con el tope (su vendedora de siempre primero, aunque esté llena);
  4. cada vendedora recibe UN Telegram por vuelta con su lista (``_avisar_lo_de_la_noche``), con un «Atender» por
     cliente, y los 15 minutos de «pasar a otra» cuentan desde ese aviso. El comprobante, la cédula o lo que Juan no
     leyó les llega TAMBIÉN a las personas de siempre (a quién le llega un comprobante no cambia). Si no hay ninguna
     vendedora disponible, se avisa a las de siempre, como de día. Lo que no es de nadie (reparto apagado) llega en un
     solo aviso a las de siempre.

Con el interruptor apagado, todo como antes.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

from . import horario as H
from .avisos_texto import armar, frase
from .conversacion import ARCHIVOS_DE_NOCHE, FRASE_DE_LA_LISTA, SIN_AVISOS_DE_NOCHE

_logger = logging.getLogger(__name__)

# Lo más importante gana: un comprobante de pago tapa a una cédula, y una cédula a lo que Juan no leyó.
PRIORIDAD_DE_ARCHIVO = {clave: len(ARCHIVOS_DE_NOCHE) - i for i, (clave, _n) in enumerate(ARCHIVOS_DE_NOCHE)}
# Clientes por mensaje en la lista de la mañana (más de esto, otro mensaje): corto para leer en el celular.
MAX_EN_UNA_LISTA = 10
# Conversaciones que mira cada vuelta de la mañana.
LOTE_DE_LA_MANANA = 200
# Un botón «Atender» con el nombre del cliente: Telegram corta lo largo.
MAX_TEXTO_DE_BOTON = 40
# El cliente de la noche cuenta como «de antes de abrir» (para el tope): su ``reparto_desde`` queda este rato antes de
# la apertura de hoy, dentro de la ventana del reparto aunque haya escrito hace más de una semana.
ANTES_DE_ABRIR = timedelta(minutes=1)


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
        forma que entiende el cron del reparto (con ``reparto_desde``). A quien ya lo tenía no se le quita de noche: al
        abrir se decide con las reglas del día. Devuelve la frase para el hilo."""
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
        valores['reparto_desde'] = ahora
        conv.write(valores)
        if conv.asignada_a:
            return self.env._('Llegó con la tienda cerrada: de noche nadie recibe clientes. Al abrir sigue con %s si '
                              'está disponible; si no, se reparte.', conv.asignada_a.name)
        return self.env._(
            'Llegó con la tienda cerrada: de noche nadie recibe clientes. Se reparte y se avisa al abrir.')

    def _anotar_archivo_de_noche(self, que):
        """Un comprobante, una cédula o algo que Juan no leyó, de noche: se avisa al abrir (queda lo más importante de
        lo que mandó). Uno igual de importante que el que ya se avisó (un segundo comprobante) se vuelve a avisar."""
        self.ensure_one()
        actual = self.sudo().archivo_de_noche
        if PRIORIDAD_DE_ARCHIVO.get(que, 0) >= PRIORIDAD_DE_ARCHIVO.get(actual, 0):
            self.sudo().write({'archivo_de_noche': que, 'archivo_de_noche_avisado': False})

    # ------------------------------------------------------------------
    # Al abrir
    # ------------------------------------------------------------------

    @api.model
    def _volver_al_reparto_lo_de_la_noche(self):
        """Los clientes que pidieron una persona de noche y nadie del equipo atendió vuelven al reparto: la pausa del
        asistente (2 horas de fábrica) vence de noche, la conversación vuelve al bot y el cron del reparto ya no la
        veía. Se ponen otra vez con una persona (el asistente calla, como cuando Juan la pasa) y su ``reparto_desde``
        queda justo antes de abrir hoy: cuenta como «de antes de abrir» para el tope y nunca sale de la ventana del
        reparto (``DIAS_MAXIMOS_DE_ESPERA``), aunque la tienda cierre una semana. Devuelve cuántas volvieron."""
        ahora = fields.Datetime.now()
        antes_de_abrir = self.env['dcasa.reparto']._apertura_de_hoy() - ANTES_DE_ABRIR
        # Solo los que necesitan algo: los ya puestos en el reparto no ocupan el lote de la vuelta siguiente.
        de_la_noche = self.sudo().search([
            ('aviso_de_noche', '!=', False), ('traspaso_sin_atender_desde', '!=', False), ('estado', '!=', 'cerrada'),
            '|', '|', '|', ('estado', '=', 'bot'), ('reparto_desde', '=', False),
            ('reparto_desde', '<', antes_de_abrir), '&', ('pausada_hasta', '!=', False), ('pausada_hasta', '<=', ahora),
        ], order='aviso_de_noche, id', limit=LOTE_DE_LA_MANANA)
        volvieron = 0
        for conv in de_la_noche:
            # También la que sigue «con una persona» con la pausa ya vencida (el mantenimiento de cada 5 minutos todavía
            # no la devolvió al bot): si no, el reparto se la daría a alguien y enseguida volvería al asistente.
            if conv.estado == 'bot' or (conv.pausada_hasta and conv.pausada_hasta <= ahora):
                conv._poner_en_humano()
                # El Worker pregunta el estado antes de contestar; el aviso se manda en el mantenimiento.
                conv.estado_pendiente_de_avisar = True
                conv._aviso(self.env._('Abrió la tienda y este cliente espera a una persona desde la noche: vuelve al '
                                       'reparto y el asistente calla mientras tanto.'))
                conv._notificar_panel('estado')
                volvieron += 1
            if not conv.reparto_desde or conv.reparto_desde < antes_de_abrir:
                conv.reparto_desde = antes_de_abrir
        return volvieron

    @api.model
    def _soltar_lo_de_la_noche_ajeno(self):
        """Al abrir, el cliente de la noche que ya tenía a alguien sigue con esa persona solo con las reglas del día:
        es una vendedora del reparto, está disponible (no se marcó «No disponible»), con «Parejo» lo atendió dentro de
        los «Días que un cliente sigue con su vendedora» y VINO: está activa (la regla de «Recibe solo quien usó el
        sistema hace poco»). Mientras no aparezca, el cliente la espera (sin aviso); si no aparece activa dentro de esos
        minutos desde la apertura, se suelta. Lo que no cumple queda sin dueña y se reparte como de día. Devuelve
        cuántos soltó."""
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        Reparto = self.env['dcasa.reparto']
        equipo = Reparto._equipo()
        plazo = Reparto._apertura_de_hoy() + timedelta(minutes=ajustes.reparto_activa_minutos)
        soltados = 0
        for conv in self.sudo().search([
                ('aviso_de_noche', '!=', False), ('traspaso_sin_atender_desde', '!=', False),
                ('asignada_a', '!=', False), ('estado', '=', 'humano')], limit=LOTE_DE_LA_MANANA):
            duena = conv.asignada_a
            sigue = duena in equipo and duena.dcasa_disponible
            if sigue and ajustes.reparto_modo == 'parejo':
                sigue = bool(Reparto._vendedora_de_siempre(conv, duena, ajustes.reparto_dias_misma_vendedora)[0])
            activa = sigue and bool(Reparto._activas_entre(duena))
            if sigue and not activa and fields.Datetime.now() >= plazo:
                sigue = False   # no vino: como de día, no recibe
            if sigue:
                if activa:
                    # Lo recibe ella: queda en el libro como «siguió con su vendedora» (cuenta como recibido hoy, y si
                    # nadie le contesta y pasa a otra, no vuelve a ella en las horas siguientes).
                    Reparto._anotar(conv, duena, 'misma', self.env._('Sigue con %s: lo tenía de noche y vino.',
                                                                     duena.name))
                continue
            conv.asignada_a = False
            conv._aviso(self.env._('Abrió la tienda: %s no está para recibir a este cliente (no vino, no está '
                                   'disponible o no lo atendió estos días), así que se reparte.', duena.name))
            soltados += 1
        return soltados

    @api.model
    def _avisar_lo_de_la_noche(self):
        """Lo que no se avisó de noche, al abrir (lo llama el cron del reparto en cada vuelta dentro del horario):

        * El cliente que pidió una persona, con el reparto encendido: cuando ya tiene a quién (el reparto se lo dio o se
          lo quedó su vendedora), en la lista de ella; sus 15 minutos de «pasar a otra» cuentan desde este aviso.
          Mientras espera su turno (el tope), no se le avisa a nadie; si no hay NINGUNA vendedora disponible, se avisa
          una vez a las personas de siempre, como de día (y sigue esperando su turno).
        * El que no es de nadie (reparto apagado o «pasar a otra» en 0): a las personas de siempre.
        * El comprobante, la cédula o lo que Juan no leyó: a las personas de siempre, como de día (a quién le llega un
          comprobante no cambia), aunque el cliente también vaya en la lista de una vendedora.

        A cada persona le llega UN mensaje por vuelta con lo suyo (``_aviso_de_la_manana``), y a las de siempre otro con
        lo de todas. Si una vendedora no tiene Telegram, lo suyo va a las de siempre. Devuelve a cuántos destinos les
        llegó algo."""
        ahora = fields.Datetime.now()
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        if not H.dentro_de_horario(ahora, ajustes.horario()):
            return 0
        vacio = self.sudo().browse()
        por_persona, pedidos, archivos, listos, sin_nadie = self._clasificar_lo_de_la_noche(ajustes)
        llegaron = 0
        de_una_vendedora = vacio
        for usuario, suyas in por_persona.items():
            if suyas._aviso_de_la_manana(usuario):
                llegaron += 1
                de_una_vendedora |= suyas
            else:
                pedidos |= suyas   # sin Telegram vinculado: a las de siempre, como de día
        para_todas = pedidos | archivos
        if para_todas:
            llegaron += bool(para_todas._aviso_de_la_manana(None, pedidos=pedidos))
        # Lo que ya se avisó no vuelve a sonar como «un cliente te espera» enseguida; lo de una vendedora cuenta sus 15
        # minutos desde ahora (cuando se enteró).
        for conv in listos:
            valores = {**SIN_AVISOS_DE_NOCHE, 'espera_avisada_en': ahora}
            if conv in por_persona.get(conv.asignada_a, vacio):
                valores['reparto_desde'] = ahora
            conv.write(valores)
        (archivos - listos).write({'archivo_de_noche_avisado': True})
        sin_nadie.write({'aviso_de_noche_a_todas': True})
        return llegaron

    @api.model
    def _clasificar_lo_de_la_noche(self, ajustes):
        """``(por_persona, pedidos, archivos, listos, sin_nadie)`` de lo pendiente de la noche (ver
        ``_avisar_lo_de_la_noche``): ``{vendedora: sus clientes}``; los que van a las de siempre como «pide una
        persona»; aquellos cuyo archivo va a las de siempre; los que ya no quedan pendientes después de esta vuelta; y
        los que esperan turno pero se avisan a todas porque no hay ninguna vendedora disponible.

        Los que esperan turno se buscan aparte (y solo si les falta algo): nunca ocupan el lote de los que ya tienen a
        quién avisar."""
        reparte = ajustes.reparto_modo != 'manual' and ajustes.reparto_reasignar_minutos > 0
        Reparto = self.env['dcasa.reparto']
        vacio = self.sudo().browse()
        hay_algo = ['|', ('aviso_de_noche', '!=', False), ('archivo_de_noche', '!=', False)]
        sin_turno = ['|', '|', '|', ('asignada_a', '!=', False), ('aviso_de_noche', '=', False),
                     ('traspaso_sin_atender_desde', '=', False), ('estado', '=', 'cerrada')]
        resto = self.sudo().search(hay_algo + (sin_turno if reparte else []), order='id', limit=LOTE_DE_LA_MANANA)
        por_persona, pedidos, archivos, listos, sin_nadie = {}, vacio, vacio, vacio, vacio
        for conv in resto:
            espera = conv._espera_a_una_persona() and conv.estado != 'cerrada'
            if conv.archivo_de_noche and not conv.archivo_de_noche_avisado:
                archivos |= conv
            if espera and reparte:
                if not Reparto._activas_entre(conv.asignada_a):
                    continue   # su vendedora todavía no vino: el aviso le llega cuando entre (o se suelta)
                por_persona[conv.asignada_a] = por_persona.get(conv.asignada_a, vacio) | conv
            elif espera:
                pedidos |= conv
            listos |= conv
        if reparte:
            nadie = self._nadie_para_recibir(ajustes)
            pendiente = ['&', ('archivo_de_noche', '!=', False), ('archivo_de_noche_avisado', '=', False)]
            esperan = self.sudo().search([
                ('aviso_de_noche', '!=', False), ('traspaso_sin_atender_desde', '!=', False),
                ('estado', '!=', 'cerrada'), ('asignada_a', '=', False),
                *(['|', ('aviso_de_noche_a_todas', '=', False)] if nadie else []), *pendiente,
            ], order='id', limit=LOTE_DE_LA_MANANA)
            for conv in esperan:
                if conv.archivo_de_noche and not conv.archivo_de_noche_avisado:
                    archivos |= conv
                if nadie and not conv.aviso_de_noche_a_todas:
                    pedidos |= conv
                    sin_nadie |= conv
        return por_persona, pedidos, archivos, listos, sin_nadie

    @api.model
    def _nadie_para_recibir(self, ajustes):
        """¿Al abrir no hay ninguna vendedora para recibir, ya pasado el plazo para que lleguen
        (``reparto_activa_minutos`` desde la apertura)? Una mañana normal (las vendedoras entran a los pocos minutos) no
        es un aviso a todas."""
        Reparto = self.env['dcasa.reparto']
        plazo = Reparto._apertura_de_hoy() + timedelta(minutes=ajustes.reparto_activa_minutos)
        return fields.Datetime.now() >= plazo and not Reparto._disponibles()

    def _aviso_de_la_manana(self, usuario, pedidos=None):
        """Un solo mensaje para ``usuario`` (o, sin él, para las personas de siempre) con estos clientes de la noche. Si
        es uno solo, el aviso normal (con su pie para responder); si son varios, la lista con un «Atender» por cliente
        (de a ``MAX_EN_UNA_LISTA``). ``pedidos``: los que van a las de siempre como «pide una persona» (los demás, por
        lo que mandaron). Devuelve a cuántas personas les llegó el primero."""
        pedidos = self.browse() if pedidos is None else pedidos
        convs = self.sorted(lambda c: (not c.aviso_de_noche_urgente, c.aviso_de_noche or c.write_date, c.id))
        usuarios = usuario or None
        if len(convs) == 1:
            return convs._avisar_por_telegram(convs._texto_de_la_manana(usuario, pedido=convs in pedidos),
                                              usuarios=usuarios, acciones=True)
        llegaron = 0
        for inicio in range(0, len(convs), MAX_EN_UNA_LISTA):
            tramo = convs[inicio:inicio + MAX_EN_UNA_LISTA]
            texto, botones = convs._lista_de_la_manana(tramo, usuario, primera=inicio == 0, pedidos=pedidos)
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
            'documento': (self.env._('Mandó un archivo o una imagen que Juan no pudo leer: puede ser un comprobante.'),
                          self.env._('mandó un archivo o una imagen que Juan no pudo leer: puede ser un comprobante.')),
            'identidad': (self.env._('Mandó su cédula: revísala en Conversaciones.'),
                          self.env._('mandó su cédula: revísala en Conversaciones.')),
        }
        if not self.archivo_de_noche:
            return ''
        return textos[self.archivo_de_noche][1 if corto else 0]

    def _es_pedido(self, usuario, pedido):
        """¿Va como «pide una persona» (en su lista, o a las de siempre porque nadie lo tiene) o por lo que mandó?"""
        self.ensure_one()
        return self._espera_a_una_persona() and (bool(usuario) or pedido)

    def _texto_de_la_manana(self, usuario, pedido=False):
        """El aviso de UN cliente de la noche: el del traspaso (o el de lo que mandó) con «escribió de noche»."""
        self.ensure_one()
        if not self._es_pedido(usuario, pedido):
            texto = self._texto_archivo(self.archivo_de_noche, de_noche=True)
            atiende = self.sudo().asignada_a
            if atiende:
                lineas = texto.split('\n')
                return armar(*lineas[:-1], self.env._('Lo atiende %s.', atiende.name), lineas[-1])
            return texto
        texto = self._texto_traspaso(self.aviso_de_noche_motivo, self.aviso_de_noche_urgente, para_ella=bool(usuario),
                                     misma=bool(usuario) and self._es_suyo_de_antes(usuario), de_noche=True)
        mando = self._lo_que_mando_de_noche()
        if not mando:
            return texto
        # Lo que mandó va antes de «qué hacer» (la última línea).
        lineas = texto.split('\n')
        return armar(*lineas[:-1], mando, lineas[-1])

    def _renglon_de_la_manana(self, usuario, pedido=False):
        """Un renglón de la lista: quién, por dónde y qué quiere (o qué mandó)."""
        self.ensure_one()
        cliente, canal = self._aviso_cliente(), self._aviso_canal()
        atiende = self.sudo().asignada_a
        if not self._es_pedido(usuario, pedido):
            renglon = f'{cliente} ({canal}) {self._lo_que_mando_de_noche(corto=True)}'
            return f"{renglon} {self.env._('Lo atiende %s.', atiende.name)}" if atiende else renglon
        if usuario:
            partes = [f'{cliente} ({canal}):']
        else:
            partes = [self.env._('%(cliente)s (%(canal)s) pide una persona:', cliente=cliente, canal=canal)]
        partes.append(frase(self.aviso_de_noche_motivo) or self.env._('no dejó dicho qué quiere.'))
        if usuario and self._es_suyo_de_antes(usuario):
            partes.append(self.env._('Es tu cliente.'))
        if self.archivo_de_noche:
            partes.append(self._lo_que_mando_de_noche())
        if not usuario:
            partes.append(self.env._('Lo tiene %s.', atiende.name) if atiende
                          else self.env._('Nadie lo tiene todavía.'))
        renglon = ' '.join(partes)
        return f"{self.env._('🔴 URGENTE:')} {renglon}" if self.aviso_de_noche_urgente else renglon

    def _lista_de_la_manana(self, tramo, usuario, primera=True, pedidos=None):
        """``(texto, botones)`` de la lista de la mañana de ``tramo`` (varios clientes). ``pedidos``: los que van a las
        de siempre como «pide una persona» (sin ``usuario``)."""
        pedidos = self.browse() if pedidos is None else pedidos
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
        renglones = [f'{n}. {conv._renglon_de_la_manana(usuario, pedido=conv in pedidos)}'
                     for n, conv in enumerate(tramo, 1)]
        # Texto fijo (sin traducir): la consola de Telegram lo reconoce (``FRASE_DE_LA_LISTA``).
        hacer = f"{FRASE_DE_LA_LISTA} {self.env._('Te llega un mensaje: respóndele para escribirle al cliente.')}"
        botones = []
        for n, conv in enumerate(tramo, 1):
            texto_boton = f"{self.env._('Atender')} {n} · {conv._aviso_cliente()}"
            if len(texto_boton) > MAX_TEXTO_DE_BOTON:
                texto_boton = f'{texto_boton[:MAX_TEXTO_DE_BOTON - 1]}…'
            botones.append([{'text': texto_boton, 'callback_data': f'juan:t:{conv.id}'}])
        return armar(titulo, intro, *renglones, hacer), botones
