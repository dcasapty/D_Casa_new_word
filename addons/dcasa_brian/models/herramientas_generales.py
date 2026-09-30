"""Herramientas generales de Brian: pantalla actual y ayuda.

(Otras herramientas generales pueden agregarse al final de este archivo.)
"""
from odoo import api, models
from odoo.exceptions import AccessError

from .politica import MODELOS_TECNICOS
from .registro import CATEGORIAS, BrianError, herramienta


class BrianHerramientasGenerales(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    @herramienta(
        nombre='pantalla_actual',
        descripcion='Dice en qué pantalla está el usuario y qué registro tiene abierto.',
        nivel='lectura',
        categoria='general',
        ejemplos=['¿qué estoy viendo?', 'explícame esta pantalla', 'esta factura'],
    )
    def _h_pantalla_actual(self):
        contexto = self.env.context.get('brian_contexto') or {}
        if not contexto:
            return {'pantalla': 'No sé en qué pantalla estás (este canal no la envía).'}
        datos = {
            'menu': contexto.get('accion') or '',
            'modelo': contexto.get('modelo') or '',
            'vista': contexto.get('vista') or '',
        }
        modelo, res_id = contexto.get('modelo'), contexto.get('res_id')
        if modelo and res_id and modelo in self.env and modelo not in MODELOS_TECNICOS:
            registro = self.env[modelo].browse(int(res_id)).exists()
            try:
                if registro:
                    registro.check_access('read')
                    datos['registro'] = registro.display_name
                    datos['tipo'] = self.env['ir.model'].sudo()._get(modelo).name
            except AccessError:
                datos['registro'] = 'Un registro que no tienes permiso de ver.'
        elif contexto.get('nombre'):
            datos['registro'] = contexto['nombre']
        return datos

    @api.model
    @herramienta(
        nombre='ayuda',
        descripcion='Lista lo que Brian puede hacer para ti, por área.',
        parametros={'area': {'type': 'string', 'enum': list(CATEGORIAS),
                             'description': 'Opcional: general, ventas, catalogo, clientes, contabilidad o usuarios.'}},
        nivel='lectura',
        categoria='general',
        ejemplos=['¿qué puedes hacer?', 'ayuda con contabilidad'],
    )
    def _h_ayuda(self, area=None):
        if area and area not in CATEGORIAS:
            raise BrianError(f'Área desconocida. Usa una de: {", ".join(CATEGORIAS)}.')
        areas = {}
        for esquema in self.catalogo():
            if area and esquema['categoria'] != area:
                continue
            grupo = areas.setdefault(esquema['categoria'], {
                'area': CATEGORIAS[esquema['categoria']], 'herramientas': []})
            etiqueta = {'lectura': 'consulta', 'construccion': 'crea/edita',
                        'sensible': 'pide tu confirmación'}[esquema['nivel']]
            grupo['herramientas'].append(f"{esquema['name']}: {esquema['description'].split(' Ejemplos:')[0]}"
                                         f" ({etiqueta})")
        return {'areas': list(areas.values()),
                'nota': 'Nunca borro registros contables ni del libro de puntos, ni toco contraseñas o '
                        'configuración técnica.'}


# ----------------------------------------------------------------------
# Búsqueda global y navegación (herramientas de dominio)
# ----------------------------------------------------------------------

# tipo → (modelo, etiqueta, dominio base)
ABRIBLES = {
    'producto': ('product.template', 'Productos', []),
    'cliente': ('res.partner', 'Contactos', [('parent_id', '=', False)]),
    'venta': ('sale.order', 'Ventas', []),
    'factura': ('account.move', 'Facturas', [('move_type', 'in', ('out_invoice', 'out_refund', 'in_invoice',
                                                                  'in_refund'))]),
    'usuario': ('res.users', 'Usuarios', [('share', '=', False)]),
}
LISTAS = {
    'cotizaciones_abiertas': ('sale.order', 'Cotizaciones abiertas', [('state', 'in', ('draft', 'sent'))]),
    'ventas_confirmadas': ('sale.order', 'Ventas confirmadas', [('state', '=', 'sale')]),
    'facturas_por_cobrar': ('account.move', 'Facturas por cobrar', [
        ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]),
    'facturas_por_pagar': ('account.move', 'Facturas por pagar', [
        ('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]),
    'facturas_borrador': ('account.move', 'Facturas en borrador', [
        ('move_type', 'in', ('out_invoice', 'in_invoice')), ('state', '=', 'draft')]),
    'productos_agotados': ('product.template', 'Productos agotados', [
        ('is_storable', '=', True), ('qty_available', '<=', 0)]),
}


class BrianHerramientasGeneralesDominio(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    def _b_buscar_tipo(self, modelo, dominio, limite):
        Modelo = self.env[modelo]
        if not Modelo.has_access('read'):
            return None
        return Modelo.search(dominio, limit=limite)

    @herramienta(
        nombre='buscar_en_todo',
        descripcion='Busca un texto a la vez en productos, clientes/proveedores, ventas y facturas. Úsala cuando no '
                    'sepas de qué tipo es lo que te piden.',
        parametros={'texto': {'type': 'string', 'description': 'Nombre, código, número o celular, p. ej. «S00012», '
                                                               '«Ana» o «6123-4567».'}},
        requeridos=['texto'],
        nivel='lectura', categoria='general',
        ejemplos=['busca «roble»', '¿qué es INV/2026/00012?'],
    )
    def _h_buscar_en_todo(self, texto):
        from . import herramientas_comun as c
        texto = (texto or '').strip()
        if len(texto) < 2:
            raise BrianError('Escribe al menos 2 letras o números para buscar.')
        resultados = []
        productos = self._b_buscar_tipo('product.product', [('display_name', 'ilike', texto)], 20)
        for plantilla in (productos.product_tmpl_id[:5] if productos else []):
            resultados.append({'tipo': 'producto', 'nombre': plantilla.display_name,
                               'detalle': f'{plantilla.default_code or "sin código"} · '
                                          f'{c.moneda(plantilla.list_price)}'})
        for partner in self._b_buscar_tipo('res.partner', [('parent_id', '=', False), '|', '|',
                                                           ('display_name', 'ilike', texto), ('vat', 'ilike', texto),
                                                           ('email', 'ilike', texto)], 5) or []:
            resultados.append({'tipo': 'cliente', 'nombre': partner.display_name,
                               'detalle': partner.phone or partner.vat or partner.email or ''})
        for orden in self._b_buscar_tipo('sale.order', ['|', ('name', 'ilike', texto), ('partner_id', 'ilike', texto)],
                                         5) or []:
            resultados.append({'tipo': 'venta', 'nombre': orden.name,
                               'detalle': f'{orden.partner_id.display_name} · {c.moneda(orden.amount_total)} · '
                                          f'{self._b_estado_venta(orden)}'})
        for factura in self._b_buscar_tipo('account.move', ABRIBLES['factura'][2] + [
                '|', '|', ('name', 'ilike', texto), ('ref', 'ilike', texto), ('partner_id', 'ilike', texto)], 5) or []:
            resultados.append({'tipo': 'factura', 'nombre': self._b_numero_factura(factura),
                               'detalle': f'{factura.partner_id.display_name} · {c.moneda(factura.amount_total)} · '
                                          f'{self._b_estado_factura(factura)}'})
        if not resultados:
            return {'resultados': [], 'mensaje': f'No encontré nada con «{texto}».'}
        return {'resultados': resultados, 'total': len(resultados)}

    @herramienta(
        nombre='abrir',
        descripcion='Abre en pantalla un registro (producto, cliente, venta, factura, usuario) o una lista '
                    '(cotizaciones abiertas, facturas por cobrar…).',
        parametros={
            'que': {'type': 'string', 'enum': list(ABRIBLES) + list(LISTAS),
                    'description': 'Qué abrir: un tipo de registro o una lista.'},
            'referencia': {'type': 'string', 'description': 'Para un registro: nombre, código o número, '
                                                            'p. ej. «S00012». Sin referencia abre la lista.'},
        },
        requeridos=['que'],
        nivel='lectura', categoria='general',
        ejemplos=['abre la factura INV/2026/00012', 'llévame a las cotizaciones abiertas'],
    )
    def _h_abrir(self, que, referencia=None):
        if que in LISTAS:
            modelo, titulo, dominio = LISTAS[que]
            if not self.env[modelo].has_access('read'):
                raise BrianError('No tienes permiso para ver esa lista.')
            return {'abrir': {'modelo': modelo, 'dominio': dominio, 'titulo': titulo}}
        if que not in ABRIBLES:
            raise BrianError(f'No sé abrir «{que}». Opciones: {", ".join(list(ABRIBLES) + list(LISTAS))}.')
        modelo, titulo, dominio = ABRIBLES[que]
        if modelo in MODELOS_TECNICOS or not self.env[modelo].has_access('read'):
            raise BrianError('No tienes permiso para ver eso.')
        if not referencia:
            return {'abrir': {'modelo': modelo, 'dominio': dominio, 'titulo': titulo}}
        registro = {
            'producto': self._b_plantilla,
            'cliente': self._b_contacto,
            'venta': self._b_venta,
            'factura': self._b_factura,
            'usuario': self._b_usuario,
        }[que](referencia)
        nombre = self._b_numero_factura(registro) if que == 'factura' else registro.display_name
        return {'abrir': {'modelo': modelo, 'res_id': registro.id, 'titulo': nombre}}
