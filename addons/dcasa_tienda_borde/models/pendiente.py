"""Marcas de «página pendiente de regenerar» y aviso al Worker.

Cualquier cambio que se vea en el sitio público (precio, nombre, publicación, fotos, existencias,
una venta confirmada, una factura) llama a ``_dcasa_marcar`` con los productos afectados. Las
marcas se juntan en la transacción (``cr.precommit``) y se escriben de una vez al confirmarla, y
el cron ``cron_avisar_borde`` se dispara a los pocos segundos: le manda al Worker la lista de
productos y el Worker vuelve a leer el catálogo (``/dcasa/tienda/feed``) y regenera lo que cambió.

Si el Worker no responde, las marcas se quedan y el cron reintenta en su intervalo. Sin secreto
configurado (TIENDA_FEED_TOKEN) no hay a quién avisar: las marcas se descartan.
"""
import hmac
import logging
import os
from datetime import timedelta

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Clave del acumulador en cr.precommit.data.
CLAVE_PRECOMMIT = 'dcasa_tienda_borde.pendientes'
# Producto «0» = regenerar todo (categorías, ajustes del sitio).
TODO = 0
# Pausa entre el cambio y el aviso: junta los cambios de una misma operación.
PAUSA_AVISO = timedelta(seconds=20)
# Máximo de marcas por aviso (el resto va en la siguiente corrida).
LOTE = 2000
TIEMPO_ESPERA = 60
LARGO_MINIMO_TOKEN = 32


def token_configurado():
    """El secreto compartido con el Worker; '' si falta o es demasiado corto."""
    token = (os.environ.get('TIENDA_FEED_TOKEN') or '').strip()
    return token if len(token) >= LARGO_MINIMO_TOKEN else ''


def token_valido(recibido):
    """Comparación en tiempo constante contra el secreto configurado."""
    esperado = token_configurado()
    return bool(esperado) and hmac.compare_digest((recibido or '').strip().encode(), esperado.encode())


def url_aviso():
    """``TIENDA_AVISO_URL`` o, por defecto, ``https://<CANONICAL_HOST>/__edge/tienda/regenerar``."""
    url = (os.environ.get('TIENDA_AVISO_URL') or '').strip()
    if url:
        return url
    host = (os.environ.get('CANONICAL_HOST') or '').strip()
    return f'https://{host}/__edge/tienda/regenerar' if host else ''


class DcasaTiendaPendiente(models.Model):
    _name = 'dcasa.tienda.pendiente'
    _description = 'Página de la tienda del borde pendiente de regenerar'
    _order = 'id'
    _log_access = False

    producto_id = fields.Integer(
        string='Producto (plantilla)', index=True, readonly=True,
        help='ID de product.template (sin llave foránea: un producto borrado también se avisa). '
             '0 = regenerar todo.')
    motivo = fields.Char(readonly=True)
    creado = fields.Datetime(default=fields.Datetime.now, readonly=True)

    @api.model
    def _dcasa_marcar(self, plantilla_ids, motivo):
        """Anota productos cuyo HTML público cambió. Barato: solo acumula en memoria.

        :param plantilla_ids: ids de product.template (o ``[TODO]``).
        """
        ids = {int(i) for i in plantilla_ids if i is not None and int(i) >= 0}
        if not ids:
            return
        cr = self.env.cr
        pendientes = cr.precommit.data.get(CLAVE_PRECOMMIT)
        if pendientes is None:
            pendientes = cr.precommit.data[CLAVE_PRECOMMIT] = {}
            cr.precommit.add(self._dcasa_escribir_marcas)
        for producto_id in ids:
            pendientes.setdefault(producto_id, motivo)

    @api.model
    def _dcasa_escribir_marcas(self):
        """precommit: escribe las marcas juntas y dispara el aviso (una vez por lote)."""
        pendientes = self.env.cr.precommit.data.pop(CLAVE_PRECOMMIT, None)
        if not pendientes:
            return
        # sudo: tabla interna (sin ACL para usuarios); no devuelve datos a quien hizo el cambio.
        Pendiente = self.sudo()
        habia = Pendiente.search_count([], limit=1)
        Pendiente.create([{'producto_id': pid, 'motivo': (motivo or '')[:64]} for pid, motivo in pendientes.items()])
        if not habia:
            cron = self.env.ref('dcasa_tienda_borde.cron_avisar_borde', raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger(fields.Datetime.now() + PAUSA_AVISO)

    @api.model
    def _dcasa_avisar_borde(self):
        """Cron: manda al Worker los productos pendientes; si responde 2xx, borra esas marcas."""
        marcas = self.sudo().search([], limit=LOTE)
        if not marcas:
            return False
        token, url = token_configurado(), url_aviso()
        if not (token and url):
            _logger.info('Tienda del borde sin configurar (TIENDA_FEED_TOKEN/CANONICAL_HOST): '
                         '%s marcas descartadas.', len(marcas))
            marcas.unlink()
            return False
        productos = sorted(set(marcas.mapped('producto_id')))
        cuerpo = {
            'todo': TODO in productos,
            'productos': [p for p in productos if p != TODO],
            'motivos': sorted(set(filter(None, marcas.mapped('motivo')))),
        }
        try:
            respuesta = requests.post(url, json=cuerpo, timeout=TIEMPO_ESPERA, headers={
                'Authorization': f'Bearer {token}',
                'User-Agent': 'dcasa-tienda-borde/1',
            })
        except requests.RequestException as error:
            _logger.warning('Tienda del borde: el Worker no respondió (%s). Se reintenta.', error)
            return False
        if not 200 <= respuesta.status_code < 300:
            _logger.warning('Tienda del borde: el Worker respondió %s. Se reintenta.', respuesta.status_code)
            return False
        marcas.unlink()
        _logger.info('Tienda del borde: aviso entregado (%s productos, todo=%s).',
                     len(cuerpo['productos']), cuerpo['todo'])
        return True
