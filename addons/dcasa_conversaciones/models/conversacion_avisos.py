"""Los textos de los avisos de Juan por Telegram, todos con la misma forma (pedido de la dueña, 2026-11-13: «mejorar
el entendimiento en los textos de las notificaciones sería muy bueno»):

1. Un emoji y un título corto que dice qué pasa («🟢 Cliente nuevo para ti», «⏰ Un cliente te espera»).
2. Quién y por dónde («Ana te escribe por WhatsApp.»).
3. Qué quiere o qué pasó, si se sabe (lo que anotó Juan, cuánto espera, de quién era).
4. Qué hacer («Toca «Atender» para contestarle.»).

Los de un cliente llevan además el botón «Atender» y el pie para responder (``PIE_DE_AVISO``): los pone
``_avisar_por_telegram``. Telegram va en texto plano (sin formato que escapar). Tuteo, frases cortas y la voz de la
marca: nada de «¡¡», ni de frases técnicas como «Fuera del horario laboral». Lo urgente se nota en el título.

Aquí viven los textos de una conversación; los de Gerencia que nacen en otro lado (WhatsApp que no entrega, una queja en
un comentario, un cliente que pasó a otra vendedora) siguen la misma forma en su archivo.
"""
from odoo import models

from .ajustes import CANALES
from .avisos_texto import armar, frase


class DcasaConversacionAvisos(models.Model):
    _inherit = 'dcasa.conversacion'

    # ------------------------------------------------------------------
    # Las piezas
    # ------------------------------------------------------------------

    def _aviso_cliente(self):
        """El nombre del cliente como lo ve el equipo (o su número, si todavía no hay nombre)."""
        self.ensure_one()
        return self.sudo().partner_id.display_name or self.id_externo

    def _aviso_canal(self):
        """Por dónde escribe, como lo dice la gente: «WhatsApp» (sin «QR» ni «API oficial»), «Instagram»…"""
        self.ensure_one()
        return dict(CANALES).get(self.canal, self.canal or '').split(' (')[0]

    def _cuanto_tiempo(self, minutos):
        """«1 minuto», «15 minutos», «2 horas»: lo que lleva esperando, en palabras."""
        minutos = max(int(minutos or 0), 0)
        if minutos < 60:
            return self.env._('1 minuto') if minutos == 1 else self.env._('%s minutos', minutos)
        horas = minutos // 60
        return self.env._('1 hora') if horas == 1 else self.env._('%s horas', horas)

    # ------------------------------------------------------------------
    # Un cliente que pide una persona (``_pasar_a_vendedora``)
    # ------------------------------------------------------------------

    def _texto_traspaso(self, motivo, urgente, para_ella, misma=False, sin_nadie=False, cuando=None, de_noche=False):
        """El aviso de un cliente que Juan pasa a una persona.

        ``para_ella``: va a la vendedora a quien le tocó (si no, a las de siempre). ``misma``: le tocó porque ya lo
        atendió antes. ``sin_nadie``: no había ninguna vendedora disponible para dárselo. ``cuando``: escribió con la
        tienda cerrada (y sin «De noche nadie recibe clientes»): lo que Juan le prometió («mañana a primera hora…»).
        ``de_noche``: es el cliente de la noche que se avisa al abrir."""
        self.ensure_one()
        cliente, canal = self._aviso_cliente(), self._aviso_canal()
        titulo = self._titulo_traspaso(urgente, para_ella, misma)
        if para_ella:
            quien = self.env._('%(cliente)s te escribe por %(canal)s.', cliente=cliente, canal=canal)
            if misma:
                quien = f"{quien} {self.env._('Ya lo atendiste antes.')}"
        else:
            quien = self.env._('%(cliente)s escribe por %(canal)s.', cliente=cliente, canal=canal)
        anoto = self.env._('Juan anotó: %s', frase(motivo)) if frase(motivo) else ''
        if de_noche:
            contexto = self.env._('Escribió de noche, con la tienda cerrada.')
        elif cuando:
            contexto = self.env._('Escribió con la tienda cerrada: Juan le dijo que le escriben %s.', cuando)
        else:
            contexto = ''
        if para_ella:
            hacer = self.env._('Toca «Atender» para contestarle.')
        elif sin_nadie:
            hacer = self.env._('No había ninguna vendedora disponible para dárselo. Toca «Atender» si lo vas a '
                               'contestar tú.')
        elif self.sudo().asignada_a:
            hacer = self.env._('Lo tiene %s. Si hace falta, toca «Atender» para contestarle tú.',
                               self.sudo().asignada_a.name)
        else:
            hacer = self.env._('Nadie lo tiene todavía: toca «Atender» si lo vas a contestar tú.')
        return armar(titulo, quien, anoto, contexto, hacer)

    def _titulo_traspaso(self, urgente, para_ella, misma):
        if para_ella and misma:
            return self.env._('🔴 URGENTE: volvió un cliente tuyo') if urgente else self.env._(
                '🟢 Volvió un cliente tuyo')
        if para_ella:
            return self.env._('🔴 URGENTE: cliente nuevo para ti') if urgente else self.env._(
                '🟢 Cliente nuevo para ti')
        return self.env._('🔴 URGENTE: un cliente pide una persona') if urgente else self.env._(
            '🙋 Un cliente pide una persona')

    # ------------------------------------------------------------------
    # Un cliente que espera respuesta (``_avisar_clientes_esperando``)
    # ------------------------------------------------------------------

    def _texto_espera(self, minutos, para_quien_lo_tiene):
        self.ensure_one()
        cliente, canal, cuanto = self._aviso_cliente(), self._aviso_canal(), self._cuanto_tiempo(minutos)
        if para_quien_lo_tiene:
            return armar(
                self.env._('⏰ Un cliente te espera'),
                self.env._('%(cliente)s te escribe por %(canal)s y lleva %(cuanto)s sin respuesta.',
                           cliente=cliente, canal=canal, cuanto=cuanto),
                self.env._('Toca «Atender» para contestarle.'))
        atiende = self.sudo().asignada_a
        return armar(
            self.env._('⏰ Un cliente espera respuesta'),
            self.env._('%(cliente)s escribe por %(canal)s y lleva %(cuanto)s sin respuesta.',
                       cliente=cliente, canal=canal, cuanto=cuanto),
            self.env._('Lo atiende %s.', atiende.name) if atiende else self.env._('Nadie lo tiene todavía.'),
            self.env._('Toca «Atender» si lo vas a contestar tú.'))

    # ------------------------------------------------------------------
    # Lo que mandó el cliente (``_avisar_archivos_del_cliente``)
    # ------------------------------------------------------------------

    def _que_archivo(self, mime):
        """«un archivo PDF», «una imagen como archivo» o «un archivo»: lo que mandó, en palabras."""
        mime = (mime or '').lower()
        if mime == 'application/pdf':
            return self.env._('un archivo PDF')
        if mime.startswith('image/'):
            return self.env._('una imagen como archivo')
        return self.env._('un archivo')

    def _texto_archivo(self, que, mime=None, de_noche=False):
        """``que``: ``comprobante``, ``identidad``, ``documento`` (un archivo que Juan no lee) o ``foto``."""
        self.ensure_one()
        cliente, canal = self._aviso_cliente(), self._aviso_canal()
        noche = self.env._('Llegó de noche, con la tienda cerrada.') if de_noche else ''
        intervenir = self.env._('Si quieres intervenir, toca «Atender».')
        if que == 'comprobante':
            return armar(
                self.env._('💵 Posible comprobante de pago'),
                self.env._('%(cliente)s mandó por %(canal)s algo que parece un comprobante de pago. Juan sigue '
                           'atendiendo.', cliente=cliente, canal=canal),
                noche,
                f"{self.env._('Verifica el pago en el banco antes de entregar nada.')} {intervenir}")
        if que == 'identidad':
            return armar(
                self.env._('🪪 Mandó su cédula'),
                self.env._('%(cliente)s mandó por %(canal)s un documento de identidad. Juan sigue atendiendo y no lo '
                           've.', cliente=cliente, canal=canal),
                noche,
                f"{self.env._('Revísalo en Conversaciones.')} {intervenir}")
        if que == 'documento':
            return armar(
                self.env._('📎 Mandó un archivo'),
                self.env._('%(cliente)s mandó por %(canal)s %(que)s. Juan no puede leerlo: puede ser un comprobante.',
                           cliente=cliente, canal=canal, que=self._que_archivo(mime)),
                noche,
                self.env._('Revísalo en Conversaciones. Si es un pago, verifícalo en el banco antes de entregar nada.'))
        return armar(
            self.env._('🖼️ Mandó una foto'),
            self.env._('%(cliente)s mandó una foto o un video por %(canal)s. Juan sigue atendiendo.',
                       cliente=cliente, canal=canal),
            intervenir)

    # ------------------------------------------------------------------
    # Una nota que menciona a alguien (``_avisar_mencion``)
    # ------------------------------------------------------------------

    def _texto_mencion(self, autora, nota):
        self.ensure_one()
        return armar(
            self.env._('💬 Te mencionaron'),
            self.env._('%(autora)s te mencionó en una nota del chat de %(cliente)s (%(canal)s):',
                       autora=autora, cliente=self._aviso_cliente(), canal=self._aviso_canal()),
            f'«{frase(nota, 400, punto=False)}»' if frase(nota) else '',
            self.env._('Ábrelo en Conversaciones para verlo completo.'))
