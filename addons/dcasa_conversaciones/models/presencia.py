"""Quién tiene abierta la pantalla de Conversaciones y cuál conversación está viendo (o escribiéndole al cliente).

Sirve para que dos personas no le contesten a la vez al mismo cliente: en la lista y en la cabecera del hilo se ve
«Ana está viendo» o «Ana está escribiendo…». Es un dato de trabajo, no un historial: una fila por persona, que se
reemplaza con cada pulso de su pantalla (cada 20 segundos y mientras teclea) y se borra a las 24 horas.
"""
import logging
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# La pantalla avisa cada 20 s; con 50 s de margen aguanta un pulso perdido sin parpadear.
VIVA_SEGUNDOS = 50
# «Escribiendo» dura lo que se tarda en pedir el siguiente aviso al teclear (la pantalla avisa cada 4 s).
ESCRIBIENDO_SEGUNDOS = 8
CANAL_BUS = 'dcasa_conversaciones/evento'


class DcasaPresencia(models.Model):
    _name = 'dcasa.presencia'
    _description = 'Quién está viendo qué conversación'

    usuario_id = fields.Many2one('res.users', required=True, ondelete='cascade', readonly=True)
    conversacion_id = fields.Many2one('dcasa.conversacion', ondelete='cascade', index='btree_not_null', readonly=True)
    visto_en = fields.Datetime('Último pulso', required=True, readonly=True)
    escribe_hasta = fields.Datetime('Escribiendo hasta', readonly=True)

    _usuario_unico = models.Constraint('UNIQUE(usuario_id)', 'Cada persona tiene una sola presencia.')

    @api.model
    def _pulso(self, usuario, conversacion, escribiendo):
        """Anota que ``usuario`` tiene abierta ``conversacion`` (o ninguna) y avisa a las demás pantallas.

        Devuelve el mapa de quienes están ahora (menos ``usuario``): así cada pulso también refresca lo que ve esa
        pantalla, aunque se haya perdido un aviso.
        """
        ahora = fields.Datetime.now()
        fila = self.sudo().search([('usuario_id', '=', usuario.id)], limit=1)
        anterior = fila.conversacion_id.id or None
        valores = {
            'conversacion_id': conversacion.id or False, 'visto_en': ahora,
            'escribe_hasta': ahora + timedelta(seconds=ESCRIBIENDO_SEGUNDOS) if escribiendo and conversacion else False,
        }
        if fila:
            fila.write(valores)
        else:
            try:
                with self.env.cr.savepoint():
                    self.sudo().create({'usuario_id': usuario.id, **valores})
            except IntegrityError:   # otra pestaña de la misma persona se adelantó
                self.sudo().search([('usuario_id', '=', usuario.id)], limit=1).write(valores)
        self._avisar(usuario, conversacion.id or None, anterior, bool(valores['escribe_hasta']))
        return self._mapa(excepto=usuario)

    @api.model
    def _avisar(self, usuario, conversacion_id, anterior, escribiendo):
        """Por el bus, a las demás pantallas, solo ids (jamás texto). Un fallo aquí no importa."""
        carga = {'evento': 'presencia', 'usuario_id': usuario.id, 'conversacion_id': conversacion_id,
                 'anterior': anterior, 'escribiendo': escribiendo}
        try:
            with self.env.cr.savepoint():
                for otra in self.env['dcasa.conversacion']._usuarios_del_panel() - usuario:
                    otra._bus_send(CANAL_BUS, carga)
        except Exception:   # noqa: BLE001 — es un extra de la pantalla
            _logger.exception('Juan: no se pudo avisar la presencia')

    @api.model
    def _mapa(self, excepto=None):
        """``{conversacion_id: [{usuario_id, escribiendo}]}`` de quienes dieron un pulso hace poco."""
        ahora = fields.Datetime.now()
        dominio = [('conversacion_id', '!=', False), ('visto_en', '>=', ahora - timedelta(seconds=VIVA_SEGUNDOS))]
        if excepto:
            dominio.append(('usuario_id', '!=', excepto.id))
        mapa = {}
        for fila in self.sudo().search(dominio, order='visto_en desc'):
            mapa.setdefault(fila.conversacion_id.id, []).append({
                'usuario_id': fila.usuario_id.id,
                'escribiendo': bool(fila.escribe_hasta and fila.escribe_hasta > ahora),
            })
        return mapa

    @api.model
    def _limpiar(self):
        """Borra lo que lleva más de un día sin pulso (cada 5 minutos, con el mantenimiento)."""
        viejas = self.sudo().search([('visto_en', '<', fields.Datetime.now() - timedelta(hours=24))])
        viejas.unlink()
        return len(viejas)
