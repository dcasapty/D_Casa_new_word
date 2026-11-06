"""Brian y Meta (Facebook e Instagram) — 2026-11-06, «Brian al día».

Dos módulos que ``dcasa_brian`` no exige (si uno no está instalado, la respuesta lo dice):

* ``dcasa_meta_catalogo`` (docs/META_CATALOGO.md): el catálogo de la tienda por una dirección secreta que Meta lee para
  los anuncios. Apagado de fábrica. Brian dice si está encendido y cuántos productos entran y cuántos quedan fuera
  (sin foto, sin precio, marcados «No anunciar»), las mismas cuentas de *Sitio web › Configuración › Anuncios en Meta*.
* ``dcasa_meta_eventos`` (docs/META_EVENTOS.md): el píxel con consentimiento y las ventas pagadas por la Conversions
  API. Brian dice qué interruptores están encendidos, si la clave de Meta está cargada (nunca su valor) y cómo va la
  cola.

Solo lectura y como quien pregunta: Gerencia de ventas o administradores (los que ven esas pantallas). Ni la dirección
secreta del catálogo ni la clave salen nunca en la respuesta. Brian no enciende ni apaga nada: eso es de Ajustes.
"""
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError

from .registro import herramienta

GERENCIA_O_ADMIN = (('sales_team.group_sale_manager', 'base.group_system'),)
DIAS_EVENTOS = 30
MAX_ERROR = 200


class BrianHerramientasMeta(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    def _b_meta_catalogo(self):
        if 'product.feed' not in self.env or 'dcasa_activo' not in self.env['product.feed']._fields:
            return {'instalado': False, 'nota': 'El catálogo para Meta no está instalado (dcasa_meta_catalogo).'}
        feeds = self.env['product.feed'].search([('target', '=', 'meta')])
        if not feeds:
            return {'instalado': True, 'encendido': False,
                    'nota': 'Todavía no hay un catálogo para Meta creado (Sitio web › Configuración › Anuncios en '
                            'Meta › Catálogo para Meta).'}
        filas = []
        for feed in feeds:
            filas.append({
                'nombre': feed.name or '',
                'encendido': feed.dcasa_activo,
                'en_el_catalogo': feed.dcasa_meta_en_catalogo,
                'fuera_sin_foto': feed.dcasa_meta_fuera_sin_foto,
                'fuera_sin_precio': feed.dcasa_meta_fuera_sin_precio,
                'fuera_marcados_no_anunciar': feed.dcasa_meta_fuera_marcados,
            })
        return {'instalado': True, 'encendido': any(f['encendido'] for f in filas), 'catalogos': filas,
                'donde': 'Sitio web › Configuración › Anuncios en Meta › Catálogo para Meta'}

    @api.model
    def _b_meta_eventos(self):
        if 'dcasa.meta.evento' not in self.env:
            return {'instalado': False,
                    'nota': 'El píxel y las ventas a Meta no están instalados (dcasa_meta_eventos).'}
        # Solo si el módulo está instalado.
        from odoo.addons.dcasa_meta_eventos.models import meta_api, meta_evento
        config = meta_evento.leer_config(self.env)
        Evento = self.env['dcasa.meta.evento']
        desde = fields.Datetime.now() - timedelta(days=DIAS_EVENTOS)
        estados = dict(Evento._fields['estado'].selection)
        cuentas = {estados.get(estado, estado): n for estado, n in Evento._read_group(
            [('create_date', '>=', desde), ('es_prueba', '=', False)], ['estado'], ['__count'])}
        ultimo = Evento.search([('estado', '=', 'error')], limit=1)
        rechazada = self.env['ir.config_parameter'].sudo().get_param(meta_evento.PARAM_TOKEN_RECHAZADO)
        clave = 'falta' if not meta_api.token() else ('cargada, pero Meta la rechazó' if rechazada else 'cargada')

        def interruptor(valor):
            return 'encendido' if valor else 'apagado'
        datos = {
            'instalado': True,
            'pixel': interruptor(config['pixel_activo'] and config['pixel_id']),
            'ventas_de_la_web': interruptor(config['capi_web']),
            'ventas_de_la_tienda': interruptor(config['capi_tienda']),
            'clave_de_meta': clave,
            'es_produccion': meta_api.es_produccion(),
            f'eventos_ultimos_{DIAS_EVENTOS}_dias': cuentas,
            'pendientes_ahora': Evento.search_count([('estado', '=', 'pendiente')]),
            'donde': 'Sitio web › eCommerce › Eventos enviados a Meta; los interruptores, en Sitio web › '
                     'Configuración › Meta: píxel y ventas (administradores)',
        }
        if ultimo:
            datos['ultimo_error'] = {'cuando': ultimo.create_date.strftime('%d/%m/%Y'),
                                     'motivo': (ultimo.ultimo_error or ultimo.motivo or '')[:MAX_ERROR]}
        return datos

    @api.model
    @herramienta(
        nombre='estado_de_meta',
        descripcion='Cómo va Meta (Facebook e Instagram): si el catálogo para anuncios está encendido y cuántos '
                    'productos entran o quedan fuera; el píxel y las ventas que se reportan a Meta, y sus errores.',
        nivel='lectura', categoria='catalogo', grupos=GERENCIA_O_ADMIN,
        ejemplos=['¿cómo va Meta?', '¿cuántos productos hay en el catálogo de Facebook?',
                  '¿se están reportando las ventas a Meta?'],
    )
    def _h_estado_de_meta(self):
        def leer(parte):
            try:
                return parte()
            except AccessError:
                return {'nota': 'No tienes permiso para ver esta parte (la ve Gerencia de ventas o un administrador).'}
        return {
            'catalogo': leer(self._b_meta_catalogo),
            'pixel_y_ventas': leer(self._b_meta_eventos),
            'nota': 'Brian no enciende ni apaga nada de Meta: eso lo hace Gerencia o un administrador en Ajustes, con '
                    'el visto bueno del abogado. La clave de Meta nunca se muestra.',
        }
