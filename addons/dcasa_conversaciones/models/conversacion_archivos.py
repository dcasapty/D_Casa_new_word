"""Los avisos de lo que manda el cliente (fotos, archivos, comprobantes), EN PARALELO: el asistente sigue atendiendo y
quien recibe el aviso decide si interviene.

Pedido de la dueña (2026-11-13): «la gente envía fotos de Instagram y el sistema puede determinar que es una factura»;
solo se avisa de comprobantes de pago de verdad y de cédulas; las demás fotos se ven en el chat. Y de lo que Juan no
leyó (revisión adversarial, 2026-11-13), porque puede ser un comprobante:

* un archivo que no es imagen ni video (un PDF puede ser el del banco);
* una imagen que el lector intentó leer y no pudo (``fallo``) o que no se lee (``ilegible``);
* una imagen que Juan no leyó porque ya iban muchas, por el cupo de IA o el anti-spam (``tope``), o porque el lector
  está apagado (``apagado``): solo si el cliente habla de pago en ese envío o en sus últimos mensajes; si no, a lo más
  un aviso por conversación al día (con el lector caído, cada captura de Instagram avisaría).

Una imagen sin clase y sin porqué (un Juan viejo) se toma como ``fallo``. Si el lector está apagado o falla seguido
(``FALLOS_SEGUIDOS`` mensajes en ``VENTANA_DE_FALLOS``), Gerencia recibe UN aviso al día.
"""
import logging
import re
import unicodedata
from datetime import timedelta

from odoo import fields, models

from . import horario as H
from .avisos_texto import armar
from .conversacion import PAUSA_ENTRE_AVISOS_DE_ARCHIVO
from .mensaje import CLAVE_SISTEMA

_logger = logging.getLogger(__name__)

# El cliente habla de pago (texto sin tildes ni mayúsculas).
PALABRAS_DE_PAGO = re.compile(
    r'\b(pagos?|pague|pagado|pagamos|yappy|transferencias?|transferi|depositos?|deposite|abonos?|abone|'
    r'comprobantes?|ach)\b')
# «Sus últimos mensajes»: los del cliente en esta conversación en este rato (hasta ``MAX_MENSAJES_RECIENTES``).
MINUTOS_DE_TEXTO_RECIENTE = 30
MAX_MENSAJES_RECIENTES = 5
# Una imagen que Juan no leyó por tope o con el lector apagado, sin hablar de pago: a lo más un aviso en este tiempo.
PAUSA_SIN_LEER_SIN_PAGO = timedelta(hours=24)
# «Falla seguido»: tantos mensajes de clientes con imágenes que el lector no pudo leer en esta ventana. Tres en una
# hora: un fallo suelto (una imagen rara, un segundo de más) no es una alarma; tres seguidos dicen que está caído.
FALLOS_SEGUIDOS = 3
VENTANA_DE_FALLOS = timedelta(hours=1)
PARAMETRO_AVISO_DEL_LECTOR = 'dcasa_conversaciones.aviso_lector_dia'
AVISO_LECTOR_LLAVE = 7303   # llave del candado (pg_try_advisory_xact_lock) del aviso del lector a Gerencia


def normalizar(texto):
    """Minúsculas y sin tildes (para buscar palabras de pago)."""
    texto = unicodedata.normalize('NFKD', (texto or '').lower())
    return ''.join(c for c in texto if not unicodedata.combining(c))


class DcasaConversacionArchivos(models.Model):
    _inherit = 'dcasa.conversacion'

    def _avisar_archivos_del_cliente(self, adjuntos, mensaje=None):
        """Avisa por Telegram de lo que mandó el cliente. Un aviso por mensaje, por lo más importante: comprobante >
        cédula > lo que Juan no leyó > otra foto.

        * Comprobante y cédula: con «Avisar de comprobantes y documentos», siempre (a quién le llega no cambia).
        * Lo que Juan no leyó: también con ese ajuste, a lo más uno cada 10 minutos por conversación (las imágenes sin
          leer por tope o con el lector apagado, ver el docstring del archivo).
        * Otra foto o video: solo con «Avisar de fotos y archivos», a lo más uno cada 10 minutos.

        Si ya la atiende una persona, no se avisa (ya la está viendo). De noche, con «De noche nadie recibe clientes»,
        no sale nada: el comprobante, la cédula o lo que Juan no leyó se avisan al abrir (``_avisar_lo_de_la_noche``).
        ``mensaje``: el ``dcasa.mensaje`` que trajo los archivos (su texto dice si habla de pago). Nunca rompe el
        registro del mensaje.
        """
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                archivos = [a for a in adjuntos if a.get('tipo') in ('imagen', 'documento', 'video')]
                if not archivos:
                    return
                motivos = [self._motivo_sin_leer(a) for a in archivos]
                self._vigilar_el_lector(motivos, mensaje)
                if not self._controla_bot():
                    return
                ajustes = self.env['dcasa.juan.ajustes'].obtener()
                que, adjunto, diario = self._que_avisar_de_los_archivos(archivos, motivos, ajustes, mensaje)
                if not que:
                    return
                ahora = fields.Datetime.now()
                if self._es_de_noche(ajustes=ajustes):
                    if que != 'foto':
                        self._anotar_archivo_de_noche(que)
                        if diario:
                            self.sudo().ultimo_aviso_sin_leer_en = ahora
                    return
                if diario:
                    self.sudo().write({'ultimo_aviso_sin_leer_en': ahora, 'ultimo_aviso_archivo_en': ahora})
                elif que in ('documento', 'foto'):
                    if self.ultimo_aviso_archivo_en and \
                            ahora - self.ultimo_aviso_archivo_en < PAUSA_ENTRE_AVISOS_DE_ARCHIVO:
                        return
                    self.sudo().ultimo_aviso_archivo_en = ahora
                self._avisar_por_telegram(self._texto_archivo(que, adjunto), acciones=True)
        except Exception:   # noqa: BLE001
            _logger.exception('Juan: no se pudo avisar del archivo del cliente en la conversación %s', self.id)

    @staticmethod
    def _motivo_sin_leer(adjunto):
        """Por qué Juan no leyó esta imagen (``None`` si la leyó o no es una imagen). Sin clase ni porqué (un Juan
        viejo, o una clase que este Odoo no conoce): ``fallo``."""
        if adjunto.get('tipo') != 'imagen':
            return None
        if adjunto.get('clase') == 'sin_leer':
            return adjunto.get('sin_leer') or 'fallo'
        return None if adjunto.get('clase') else 'fallo'

    def _que_avisar_de_los_archivos(self, archivos, motivos, ajustes, mensaje):
        """``(que, adjunto, diario)``: de qué se avisa (``comprobante``, ``identidad``, ``documento``, ``foto`` o
        ``None``), por cuál archivo (para el texto) y si gasta el aviso del día de las imágenes sin leer sin pago."""
        clases = {a.get('clase') for a in archivos}
        if ajustes.avisar_comprobantes:
            if 'comprobante' in clases:
                return 'comprobante', None, False
            if 'identidad' in clases:
                return 'identidad', None, False
            urgentes = [a for a, m in zip(archivos, motivos, strict=True)
                        if a.get('tipo') == 'documento' or m in ('fallo', 'ilegible')]
            if urgentes:
                return 'documento', urgentes[0], False
            suaves = [a for a, m in zip(archivos, motivos, strict=True) if m in ('tope', 'apagado')]
            if suaves:
                if self._habla_de_pago(mensaje):
                    return 'documento', suaves[0], False
                ultimo = self.ultimo_aviso_sin_leer_en
                if not ultimo or fields.Datetime.now() - ultimo >= PAUSA_SIN_LEER_SIN_PAGO:
                    return 'documento', suaves[0], True
        if ajustes.avisar_archivos:
            return 'foto', None, False
        return None, None, False

    def _habla_de_pago(self, mensaje=None):
        """¿El cliente habla de pago en este envío o en sus últimos mensajes (los de ``MINUTOS_DE_TEXTO_RECIENTE``)?"""
        self.ensure_one()
        textos = [mensaje.texto] if mensaje else []
        recientes = self.env['dcasa.mensaje'].sudo().search([
            ('conversacion_id', '=', self.id), ('autor', '=', 'cliente'), ('tipo', '=', 'mensaje'),
            ('ts', '>=', fields.Datetime.now() - timedelta(minutes=MINUTOS_DE_TEXTO_RECIENTE))],
            order='ts desc, id desc', limit=MAX_MENSAJES_RECIENTES)
        textos += recientes.mapped('texto')
        return any(PALABRAS_DE_PAGO.search(normalizar(t)) for t in textos if t)

    # ------------------------------------------------------------------
    # El lector de imágenes apagado o fallando: un aviso al día a Gerencia
    # ------------------------------------------------------------------

    def _vigilar_el_lector(self, motivos, mensaje):
        """Anota en ``mensaje`` por qué Juan no leyó sus imágenes y, si el lector está apagado o falla seguido, le avisa
        a Gerencia (una vez al día)."""
        presentes = [m for m in motivos if m]
        if not presentes:
            return
        orden = ('apagado', 'fallo', 'ilegible', 'tope')
        peor = min(presentes, key=orden.index)
        if mensaje:
            mensaje.with_context(**{CLAVE_SISTEMA: True}).sudo().imagen_sin_leer = peor
        if peor == 'apagado':
            self._avisar_del_lector_a_gerencia('apagado')
        elif peor == 'fallo' and mensaje:
            fallos = self.env['dcasa.mensaje'].sudo().search_count([
                ('imagen_sin_leer', '=', 'fallo'), ('autor', '=', 'cliente'),
                ('ts', '>=', fields.Datetime.now() - VENTANA_DE_FALLOS)])
            if fallos >= FALLOS_SEGUIDOS:
                self._avisar_del_lector_a_gerencia('fallo', fallos)

    def _avisar_del_lector_a_gerencia(self, que, fallos=0):
        """«⚠️ Para Gerencia: Juan no está leyendo las fotos», una vez al día (día de Panamá). De noche, con «De noche
        nadie recibe clientes», espera a que abran (la próxima imagen sin leer lo manda). A Gerencia o, si a nadie de
        Gerencia le llega, a las personas de siempre."""
        ajustes = self.env['dcasa.juan.ajustes'].obtener()
        if self._es_de_noche(ajustes=ajustes):
            return
        hoy = H.a_local(fields.Datetime.now(), ajustes.horario()).date().isoformat()
        self.env.cr.execute('SELECT pg_try_advisory_xact_lock(%s, 1)', [AVISO_LECTOR_LLAVE])
        if not self.env.cr.fetchone()[0]:
            return   # otra petición lo está mandando ahora mismo
        # Leído de la tabla (no de la caché de parámetros): con el candado puesto, lo que dice es lo último.
        self.env.cr.execute('SELECT value FROM ir_config_parameter WHERE key = %s', [PARAMETRO_AVISO_DEL_LECTOR])
        fila = self.env.cr.fetchone()
        if fila and fila[0] == hoy:
            return
        self.env['ir.config_parameter'].sudo().set_param(PARAMETRO_AVISO_DEL_LECTOR, hoy)
        if que == 'apagado':
            que_pasa = self.env._('El lector de imágenes de Juan está apagado: las fotos de los clientes llegan sin '
                                  'leer y Juan no reconoce solo un comprobante ni una cédula.')
            hacer = self.env._('Mientras tanto, revisa las fotos en Conversaciones y pide que lo enciendan en el '
                               'Worker de Juan.')
        else:
            que_pasa = self.env._('En la última hora Juan no pudo leer las fotos de %s mensajes de clientes: el lector '
                                  'de imágenes está fallando.', fallos)
            hacer = self.env._('Mientras tanto, revisa las fotos en Conversaciones; si sigue, pide que revisen el '
                               'Worker de Juan.')
        texto = armar(self.env._('⚠️ Para Gerencia: Juan no está leyendo las fotos'), que_pasa, hacer,
                      self.env._('Este aviso llega una vez al día.'))
        gerencia = self.env['dcasa.reparto']._gerencia_que_recibe_avisos()
        if not (gerencia and self._avisar_por_telegram(texto, usuarios=gerencia)):
            self._avisar_por_telegram(texto)
