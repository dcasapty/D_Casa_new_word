"""A quién le toca una conversación que Juan pasa a una persona (el reparto de Ajustes de Juan).

La regla de verdad vive en ``reparto.py``; aquí está lo que hace cada conversación con ella. ``_repartir`` lo llama
``_pasar_a_vendedora`` y es lo único que cambia quién atiende: nunca falla una conversación por culpa del reparto
(si no hay nadie, queda como siempre: el responsable por defecto y el aviso a todo el equipo).

**El cliente de otra vendedora** (pedido de la dueña, 2026-11-12; «solamente es para las vendedoras»). Rige solo entre
vendedoras de piso (``dcasa.reparto._vendedoras_de_piso``: sin Caja, Contabilidad, Gerencia ni administradoras, que se
comportan como siempre) y lo decide UNA función, ``_vendedora_que_lo_atiende``, que miran todos los caminos:

* Escribirle (también programado, foto del catálogo, cotización), «Atender» o asignárselo a sí misma en «Atiende»: si
  la otra está activa (la definición del reparto), el servidor no lo hace sin ``tomar_de`` = el id de ELLA (la pantalla
  lo pregunta; si mientras tanto lo tomó otra, se vuelve a preguntar con el nombre nuevo). Queda dicho en el hilo
  («Beto tomó el cliente que atendía Ana.»), en el libro (regla ``tomada``) y, si estaba activa, le llega un Telegram.
  Si no está (faltó, almuerzo, de noche), se toma sin preguntar: cubrir a una compañera ausente es ayudar.
* Pasárselo a una tercera, dejarlo sin asignar, devolverlo al asistente o cerrarlo, si la otra está activa: no
  (``_exigir_que_no_se_lo_quite``). Pídeselo a ella o a Gerencia. Lo mismo por ``write`` (formulario o RPC).
* Un mensaje programado que al salir encuentra al cliente con otra vendedora no sale (``_programado_no_sale``), salvo
  que al programarlo se haya confirmado contra esa misma vendedora.
"""
from markupsafe import Markup, escape

from odoo import fields, models
from odoo.exceptions import UserError

from .ajustes import CANALES
from .reparto import ClienteDeOtraVendedora, Decision

CRON_DEL_REPARTO = 'dcasa_conversaciones.ir_cron_reasignar_sin_respuesta'


class DcasaConversacionReparto(models.Model):
    _inherit = 'dcasa.conversacion'

    reparto_desde = fields.Datetime(
        'La tiene el reparto desde', readonly=True, copy=False, index='btree_not_null',
        help='Cuándo el reparto automático se la dio a quien la tiene (o la dejó sin dueña porque no había nadie '
             'activa). Se borra en cuanto alguien del equipo le escribe al cliente, la toma, la asigna o la deja sin '
             'asignar a mano, o vuelve al asistente: desde ahí es de una persona y «pasar a otra si no contesta» no la '
             'toca (revisión adversarial, 2026-11-03).')

    def _repartir(self):
        """Decide a quién le toca (ver ``_decidir_reparto``) y, con el reparto encendido, anota desde cuándo la tiene el
        reparto: con eso ``dcasa.reparto._cron_reasignar`` sabe si nadie le contestó."""
        decision = self._decidir_reparto()
        if self.env['dcasa.juan.ajustes'].obtener().reparto_modo != 'manual':
            self.sudo().reparto_desde = fields.Datetime.now()
        return decision

    def _decidir_reparto(self):
        """Según «Reparto de conversaciones» en Ajustes de Juan, le asigna esta conversación a una persona.

        * ``manual``: a nadie (la toma quien quiera).
        * ``turnos``: a quien lleva más tiempo sin recibir una (el reparto de siempre).
        * ``parejo``: su vendedora de siempre o, si no, a quien lleva menos hoy.

        Devuelve una ``Decision``: a quién (vacío = a nadie), por qué (frase para el hilo) y si faltó gente disponible.
        """
        self.ensure_one()
        vacio = self.env['res.users']
        modo = self.env['dcasa.juan.ajustes'].obtener().reparto_modo
        if modo == 'parejo':
            return self._repartir_parejo()
        if modo == 'turnos' and not self._tiene_duena_que_recibe():
            elegida = self._asignar_por_turno()
            if not elegida:
                return Decision(vacio, sin_nadie=True)
            self.env['dcasa.reparto']._anotar(self, elegida, 'turno')
            return Decision(elegida, self.env._('Le tocó a %s por turno.', elegida.name), 'turno')
        return Decision(vacio)

    def _tiene_duena_que_recibe(self):
        """¿Ya la atiende una vendedora (de las que reciben)? Si la tenía Gerencia o una administradora, que intervino y
        la devolvió al asistente, no cuenta: el reparto no se las pasa a ellas."""
        self.ensure_one()
        return bool(self.asignada_a) and self.asignada_a in self.env['dcasa.reparto']._vendedoras()

    def _repartir_parejo(self):
        Reparto = self.env['dcasa.reparto']
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        hoy = Reparto._hoy()
        candidatas = Reparto._disponibles(hoy)
        if not candidatas:
            return Decision(self.env['res.users'], sin_nadie=True)
        # 1) Su vendedora de siempre, si está disponible (aunque tenga clientes esperándole: el cliente es suyo).
        elegida, momento = Reparto._vendedora_de_siempre(self, candidatas, ajustes.reparto_dias_misma_vendedora)
        if elegida:
            regla = 'misma'
            razon = self.env._('Sigue con %(quien)s: ya atendió a este cliente %(cuando)s.',
                               quien=elegida.name, cuando=Reparto._hace_cuanto(momento))
        else:
            # 2) Quien lleva menos hoy, entre las que no tienen ya el máximo de clientes esperándole (si todas lo
            # tienen, entre todas: de día el cliente nunca se queda sin dueña por el tope).
            candidatas = Reparto._con_lugar(candidatas, excepto=self) or candidatas
            cuentas = Reparto._cuentas(candidatas, hoy, hoy, excepto=self)
            ordenadas = Reparto._ordenar(candidatas, cuentas)
            elegida, regla = ordenadas[0], 'parejo'
            razon = self.env._('Le tocó a %(quien)s. %(por_que)s', quien=elegida.name,
                               por_que=Reparto._por_que_le_toco(ordenadas, cuentas))
        antes = self.asignada_a
        if antes and antes != elegida:
            razon = f"{razon} {self.env._('Antes la tenía %s.', antes.name)}"
        self.sudo().asignada_a = elegida
        if Reparto._anotar(self, elegida, regla, razon, hoy):
            # El turno también se gasta aquí: es el último desempate, y así quien acaba de recibir pasa al final de la
            # fila. (Escribirlo además frena a dos conversaciones que eligieran a la misma persona al mismo tiempo: la
            # segunda espera, vuelve a empezar y ya ve la cuenta al día.)
            elegida.dcasa_turno = max(Reparto._equipo(hoy).mapped('dcasa_turno') or [0]) + 1
        return Decision(elegida, razon, regla)

    def _registrar_asignacion_a_mano(self, usuario, anterior=None):
        """Una persona de Gerencia o de ventas eligió a quién atiende: queda anotado (sirve para «su vendedora de
        siempre») pero no cuenta como una conversación que Juan pasó. ``anterior``: quién lo tenía (para «Clientes que
        cambiaron de mano», en la pantalla Reparto)."""
        self.ensure_one()
        if usuario:
            self.env['dcasa.reparto']._anotar(self, usuario, 'manual', self.env._('Asignada a mano.'),
                                              anterior=anterior)

    # ------------------------------------------------------------------
    # El cliente de otra vendedora
    # ------------------------------------------------------------------

    def _vendedora_que_lo_atiende(self, usuario):
        """¿Le aplica a ``usuario`` la regla de «el cliente de otra vendedora» en esta conversación? Devuelve la
        vendedora que lo atiende y a quien ``usuario`` se lo quitaría; vacío si no aplica. LA función de esa regla: la
        miran escribir, «Atender», «Atiende», ``write``, devolver, cerrar y el programado.

        Solo entre vendedoras de piso (``dcasa.reparto._vendedoras_de_piso``): si ``usuario`` es Gerencia,
        administradora, Caja o Contabilidad, o lo atiende alguien así, todo sigue como siempre. «Lo atiende» = la
        conversación está con una persona (``humano``) a su nombre; si volvió al asistente o se cerró, ya no lo atiende
        nadie."""
        self.ensure_one()
        conv = self.sudo()
        anterior = conv.asignada_a
        vacio = self.env['res.users']
        if conv.estado != 'humano' or not anterior or not usuario or anterior == usuario:
            return vacio
        de_piso = self.env['dcasa.reparto']._vendedoras_de_piso()
        if usuario not in de_piso or anterior not in de_piso:
            return vacio
        return anterior

    def _vendedora_activa_que_lo_atiende(self, usuario):
        """La vendedora de ``_vendedora_que_lo_atiende``, solo si está activa (la definición del reparto)."""
        duena = self._vendedora_que_lo_atiende(usuario)
        return duena if duena and self.env['dcasa.reparto']._esta_activa(duena) else self.env['res.users']

    def _exigir_confirmacion_para_tomar(self, usuario, tomar_de=None):
        """El servidor no le quita a una vendedora activa su cliente sin que quien escribe lo haya confirmado CONTRA
        ELLA: ``tomar_de`` es el id de la vendedora por la que se preguntó. Sin él, o si ahora lo atiende otra (lo tomó
        alguien mientras se decidía), ``ClienteDeOtraVendedora`` con el nombre de quien lo atiende ahora (la pantalla
        lo convierte en la pregunta). Si la otra no está activa, no hace falta confirmar."""
        sin_confirmar = tomar_de is None or tomar_de is False
        if not sin_confirmar and (isinstance(tomar_de, bool) or not isinstance(tomar_de, int) or tomar_de < 1):
            raise UserError(self.env._('«tomar_de» es el número de la persona a quien le tomas el cliente.'))
        for conv in self:
            duena = conv._vendedora_activa_que_lo_atiende(usuario)
            if duena and duena.id != tomar_de:
                raise ClienteDeOtraVendedora(self.env._(
                    'Este cliente lo atiende %s, que está trabajando ahora. Para quedarte con él, confírmalo en la '
                    'pantalla de Conversaciones (allí te lo pregunta); si no, déjale una nota en el chat.', duena.name),
                    duena)

    def _exigir_que_no_se_lo_quite(self, usuario, que):
        """Pasarle a una tercera, dejar sin asignar, devolver al asistente o cerrar el cliente que atiende otra
        vendedora activa: no (revisión adversarial, 2026-11-12). ``que``: lo que se quiso hacer, para el mensaje. Si la
        otra no está activa, se puede (cubrir a una compañera ausente)."""
        for conv in self:
            duena = conv._vendedora_activa_que_lo_atiende(usuario)
            if duena:
                raise UserError(self.env._(
                    'Este cliente lo atiende %(duena)s, que está trabajando ahora: no puedes %(que)s. Pídeselo a '
                    '%(duena)s o a Gerencia. Si lo vas a atender tú, toca «Atender».', duena=duena.name, que=que))

    def _revisar_asignacion_a_mano(self, nuevo_id):
        """``write({'asignada_a': …})`` de una vendedora de piso (formulario o RPC): la misma regla que la pantalla.
        Asignárselo a sí misma pide la confirmación (en el contexto, ``dcasa_tomar_de``: el formulario no pregunta, así
        que ahí no se puede); pasárselo a otra o dejarlo sin dueña, no. Devuelve ``{conversación: anterior}`` de lo que
        cambia de mano, para dejarlo dicho después de escribir."""
        usuario = self.env.user
        nuevo = nuevo_id if isinstance(nuevo_id, models.BaseModel) else self.env['res.users'].browse(nuevo_id or [])
        tomas = {}
        for conv in self:
            if conv.sudo().asignada_a == nuevo:
                continue
            if nuevo == usuario:
                tomar_de = self.env.context.get('dcasa_tomar_de')
                conv._exigir_confirmacion_para_tomar(usuario, tomar_de if isinstance(tomar_de, int) else None)
                anterior = conv._vendedora_que_lo_atiende(usuario)
                if anterior:
                    tomas[conv] = anterior
            else:
                conv._exigir_que_no_se_lo_quite(usuario, self.env._('pasárselo a otra persona') if nuevo
                                                else self.env._('dejarlo sin asignar'))
        return tomas

    def _programado_no_sale(self, mensaje):
        """Llegó la hora de un mensaje programado y el cliente ahora lo atiende otra vendedora (de piso) distinta de
        quien lo programó: no sale (revisión adversarial, 2026-11-12). Salvo que al programarlo se haya confirmado
        quitárselo a esa misma vendedora (``toma_confirmada_de``). Queda dicho en el hilo y se le avisa a quien lo
        programó (Odoo y Telegram). Devuelve True si no salió."""
        self.ensure_one()
        quien = mensaje.usuario_id
        duena = self._vendedora_que_lo_atiende(quien)
        if not duena or duena == mensaje.toma_confirmada_de:
            return False
        texto = (mensaje.texto or self.env._('(adjunto)'))[:120]
        aviso = self.env._('No salió el mensaje que %(quien)s dejó programado («%(texto)s»): el cliente ahora lo '
                           'atiende %(duena)s.', quien=quien.name, texto=texto, duena=duena.name)
        mensaje.adjunto_ids.sudo().unlink()
        mensaje.sudo().unlink()
        self._aviso(aviso)
        cliente = self.sudo().partner_id.display_name or self.id_externo
        para_ti = self.env._('No salió el mensaje que dejaste programado para %(cliente)s («%(texto)s»): ahora lo '
                             'atiende %(duena)s. Si hace falta, déjale una nota en el chat.', cliente=cliente,
                             texto=texto, duena=duena.name)
        try:
            with self.env.cr.savepoint():
                self.sudo().message_post(body=Markup('<p>%s</p>') % escape(para_ti), partner_ids=quien.partner_id.ids,
                                         subtype_xmlid='mail.mt_note', message_type='comment')
        except Exception:   # noqa: BLE001 — el aviso en Odoo es un extra
            pass
        self._avisar_por_telegram(para_ti, usuarios=quien)
        self._notificar_panel('estado')
        return True

    def _cambio_de_mano(self, anterior, usuario, forma):
        """``usuario`` (vendedora) se quedó con el cliente que atendía ``anterior`` (otra vendedora): la línea
        ``tomada`` en el libro y, si ``anterior`` estaba activa, un aviso por Telegram para ella (si no estaba, nada:
        cubrir a una compañera ausente es ayudar). Devuelve la frase para el hilo. Nunca falla lo que se estaba
        haciendo (Telegram ya es a prueba de fallos)."""
        self.ensure_one()
        frase = self.env._('%(quien)s tomó el cliente que atendía %(antes)s.', quien=usuario.name, antes=anterior.name)
        como = dict(self.env['dcasa.reparto']._fields['forma'].selection).get(forma, '')
        self.env['dcasa.reparto']._anotar(self, usuario, 'tomada', f'{frase} {como}.', anterior=anterior, forma=forma)
        if self.env['dcasa.reparto']._esta_activa(anterior):
            cliente = self.sudo().partner_id.display_name or self.id_externo
            canal = dict(CANALES).get(self.canal, self.canal)
            self._avisar_por_telegram(
                self.env._('%(quien)s tomó a tu cliente %(cliente)s (%(canal)s).', quien=usuario.name,
                           cliente=cliente, canal=canal), usuarios=anterior)
        return frase

    def _dejar_dicho_el_cambio(self, tomas):
        """Después de un ``write`` permitido: lo que cambió de mano queda dicho como al tomarlo desde la pantalla."""
        for conv, anterior in tomas.items():
            conv._aviso(conv._cambio_de_mano(anterior, self.env.user, 'asignar'))
            conv._notificar_panel('asignacion')

    def _adelantar_reparto(self):
        """Una vendedora acaba de contestarle (o de tomar) a un cliente que el reparto le había dado: queda lugar para
        otro. Si hay clientes que el reparto dejó sin dueña esperando y el tope está puesto, la próxima vuelta de
        «pasar a otra» se adelanta a ahora (``ir.cron._trigger``) en vez de esperar hasta 5 minutos."""
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        if ajustes.reparto_modo == 'manual' or ajustes.reparto_max_esperando <= 0:
            return
        if not self.sudo().search_count([('estado', '=', 'humano'), ('reparto_desde', '!=', False),
                                         ('asignada_a', '=', False)], limit=1):
            return
        cron = self.env.ref(CRON_DEL_REPARTO, raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()


class DcasaMensajeReparto(models.Model):
    _inherit = 'dcasa.mensaje'

    toma_confirmada_de = fields.Many2one(
        'res.users', 'Confirmó quitárselo a', readonly=True, ondelete='set null',
        help='En un mensaje programado: la vendedora a quien quien lo programó confirmó quitarle el cliente. Si al '
             'salir el cliente lo atiende otra, no sale.')
