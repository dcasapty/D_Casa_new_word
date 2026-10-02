"""Marcas de «página pendiente de regenerar» y aviso al Worker.

Cualquier cambio que se vea en el sitio público (precio, nombre, publicación, fotos, existencias,
una venta confirmada, una factura, categorías, ajustes, plantillas, menú, tarifas, Black Weekend)
llama a ``_dcasa_marcar`` con los productos afectados. Las marcas se juntan en la transacción
(``cr.precommit``) y se escriben de una vez al confirmarla, y el cron ``cron_avisar_borde`` se
dispara a los pocos segundos: le avisa al Worker, que da por viejas TODAS las páginas que guardó
del HTML de Odoo (edge/src/tienda/paginas.ts) y vuelve a pedirle a Odoo las principales y las
fichas de los productos que cambiaron (``rutas``); el resto, con la primera visita.

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

# Último estado de Black Weekend que se avisó al Worker (ver _dcasa_vigilar_black_weekend).
PARAM_BW_PUBLICADO = 'dcasa_tienda_borde.black_weekend_publicado'
# Clave del acumulador en cr.precommit.data.
CLAVE_PRECOMMIT = 'dcasa_tienda_borde.pendientes'
# Producto «0» = regenerar todo (categorías, ajustes del sitio).
TODO = 0
# Pausa entre el cambio y el aviso: junta los cambios de una misma operación.
PAUSA_AVISO = timedelta(seconds=20)
# Máximo de marcas por aviso (el resto va en la siguiente corrida).
LOTE = 2000
# Fichas que el Worker vuelve a pedir enseguida (las demás, con la primera visita).
MAX_RUTAS = 30
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
    def _dcasa_vigilar_black_weekend(self):
        """Cron horario: si la campaña Black Weekend se encendió o se apagó sola (empieza o termina
        su ventana, en hora de Panamá) o porque el arranque del contenedor cambió sus parámetros
        por SQL, marca «regenerar todo» y borra el sitemap guardado de Odoo (si no, /black-weekend
        seguiría o faltaría en /sitemap.xml hasta 12 h). Devuelve True si hubo cambio.
        """
        param = self.env['ir.config_parameter'].sudo()
        activo = '1' if self.env['website']._dcasa_black_weekend_activo() else '0'
        if param.get_param(PARAM_BW_PUBLICADO) == activo:
            return False
        param.set_param(PARAM_BW_PUBLICADO, activo)
        self.env['ir.attachment'].sudo().search([
            ('type', '=', 'binary'), ('url', '=like', '/sitemap-%.xml')]).unlink()
        self._dcasa_marcar([TODO], 'black weekend ' + ('empieza' if activo == '1' else 'termina'))
        _logger.info('Black Weekend: la campaña pasa a %s; se regenera la tienda.',
                     'activa' if activo == '1' else 'inactiva')
        return True

    @api.model
    def _dcasa_rutas_de(self, plantilla_ids):
        """URL públicas (``website_url``) de los productos publicados, para precalentar en el borde."""
        productos = self.env['product.template'].sudo().browse(plantilla_ids).exists()
        return sorted({p.website_url for p in productos if p.is_published and p.website_url})

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
        ids = [p for p in productos if p != TODO]
        cuerpo = {
            'todo': TODO in productos,
            'productos': ids,
            'motivos': sorted(set(filter(None, marcas.mapped('motivo')))),
            'rutas': self._dcasa_rutas_de(ids[:MAX_RUTAS]),
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
