"""El pie del correo de la factura y de la bienvenida: «¿Te avisamos de lo nuevo? Sí, quiero».

Un enlace firmado (HMAC con el secreto de la base) que lleva a una página con la marca: allí la persona toca «Sí,
quiero» y queda el permiso con la fecha, por dónde y a qué correo. Solo va:

* en los correos que arma D'CASA con ``_postear`` y son la **factura** (también la de un abono) o la **bienvenida**:
  nunca en el recordatorio del abono (decisión de la dueña), ni en la cotización, ni en un correo del asistente
  genérico «Enviar» o del chatter, ni a seguidores;
* cuando el correo va a **una sola persona y es la ficha comercial firmada**, con el mismo correo (``_enlace_si``): si
  la factura va a un contacto hijo, el enlace de la empresa no le llega a él;
* con el interruptor de Gerencia encendido (Marketing › Camila; de fábrica, encendido).

``_postear`` deja una marca en el contexto (qué registro y a quién); al pintar el correo, el layout solo pone la línea
si la marca coincide con ese registro y con los destinatarios del mensaje, y si lo envía el equipo o el sistema (el
chatter del portal deja pasar el contexto del navegador). Un error aquí NUNCA tumba el correo: se arma en un savepoint
y, si falla, el correo sale sin la línea.
"""
import logging

from odoo import SUPERUSER_ID, api, models

_logger = logging.getLogger(__name__)

MARCA_PIE = 'dcasa_camila_pie'
TIPOS_CON_LINEA = frozenset({'factura', 'abono', 'bienvenida'})


class DcasaCorreo(models.AbstractModel):
    _inherit = 'dcasa.correo'

    @api.model
    def _postear(self, registro, plantilla, destino, adjuntos=(), tipo='factura', titular=None):
        if tipo in TIPOS_CON_LINEA and registro and len(registro) == 1 and destino and len(destino) == 1:
            registro = registro.with_context(**{MARCA_PIE: (registro._name, registro.id, destino.id)})
        return super()._postear(registro, plantilla, destino, adjuntos=adjuntos, tipo=tipo, titular=titular)

    @api.model
    def _contexto_layout(self, registro=None, message=None, company=None):
        contexto = super()._contexto_layout(registro, message, company)
        contexto['novedades'] = None
        marca = self.env.context.get(MARCA_PIE)
        if not marca or not registro or not isinstance(marca, (list, tuple)) or len(marca) != 3 \
                or (registro._name, registro.id) != (marca[0], marca[1]):
            return contexto   # solo lo que armó _postear para ESTE registro
        if not (self.env.uid == SUPERUSER_ID or self.env.user._is_internal()):
            return contexto
        self.env.cr.flush()   # lo pendiente de quien manda el correo, AFUERA del try: un error suyo no se traga
        try:
            with self.env.cr.savepoint():
                destino = self.env['res.partner'].sudo().browse(marca[2]).exists()
                if message is not None and message.sudo().partner_ids != destino:
                    return contexto   # el mensaje va a alguien más (o a más de uno)
                contexto['novedades'] = self.env['dcasa.camila'].sudo()._enlace_si(registro, destino)
        except Exception:   # el correo de la factura sale igual, sin la línea
            _logger.warning('Camila: no se pudo armar el enlace «Sí, quiero» del pie', exc_info=True)
        return contexto
