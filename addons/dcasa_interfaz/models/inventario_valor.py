"""«Valor del inventario» (pedido de la dueña, 2026-11-02): cuánto vale hoy la mercancía que hay, al costo y a precio de
venta sin ITBMS. «Esto es solo para gerencia o administración».

* **Al costo:** la valuación de Odoo (``product.product.total_value``, la misma de su reporte de valoración): las
  unidades que hay en las ubicaciones propias que se valoran (sin la mercancía de terceros), por el costo del producto
  según su método (estándar o promedio: unidades × costo; FIFO: lo que costó cada entrada que todavía queda).
* **A precio de venta sin ITBMS:** las mismas unidades por el precio de venta de cada variante (``lst_price``). Los
  precios de D'CASA ya son sin ITBMS (``dcasa_base``); si a un producto le queda un impuesto incluido en el precio, se
  le quita.
* **Ganancia esperada:** la diferencia, como si todo se vendiera a precio de lista (sin descuentos ni combos). El margen
  es sobre el precio, como «Mejor margen».
* Un producto con existencias negativas no suma (no hay mercancía que valga): se avisa aparte. Uno con existencias y
  sin costo o sin precio suma 0 en esa cifra, y también se avisa para cargarlo.
* Los productos archivados que todavía tienen existencias cuentan: siguen siendo mercancía.

Solo Gerencia y los administradores (``_ve_utilidad``): el servidor lo exige en cada llamada. Las cifras se leen con
``sudo`` después de esa revisión (la valuación de Odoo ya se calcula así); cada lista que abre una cifra corre con los
permisos de quien mira.
"""
from collections import defaultdict

from odoo import api, models
from odoo.exceptions import AccessError

from .comparar import _hora
from .tablero import _accion

# «Por tipo»: los tipos con más valor y, pasados estos, los demás juntos en «Otros» (como Estadísticas).
TIPOS_A_LA_VISTA = 8
PRODUCTOS_CON_MAS_VALOR = 10
SIN_ARCHIVO = {'active_test': False}


class DcasaTableroInventario(models.AbstractModel):
    _inherit = 'dcasa.tablero'

    @api.model
    def valor_del_inventario(self):
        """El valor de la mercancía que hay hoy: al costo, a precio de venta sin ITBMS y la diferencia, por tipo de
        producto, los productos con más dinero y lo que falta cargar. Solo lectura; solo Gerencia y administradores."""
        if not self._ve_utilidad():
            raise AccessError(self.env._('El valor del inventario es solo para Gerencia y los administradores.'))
        return self._valor_del_inventario()

    @api.model
    def _precio_sin_itbms(self, producto):
        """El precio de venta de una variante sin ITBMS. Los de D'CASA ya lo son; si le queda un impuesto incluido en el
        precio (de antes del 2026-10-01), se le quita."""
        precio = producto.lst_price
        impuestos = producto.taxes_id._filter_taxes_by_company(self.env.company)
        if precio and any(impuestos.mapped('price_include')):
            return impuestos.compute_all(precio, currency=self.env.company.currency_id, product=producto)[
                'total_excluded']
        return precio

    @api.model
    def _clave_de_tipo(self, categoria):
        """El tipo de un producto: su categoría de primer nivel (debajo de «Todos»), como «Por tipo» de Estadísticas."""
        camino = [int(i) for i in (categoria.parent_path or '').split('/') if i]
        return camino[1] if len(camino) > 1 else (camino[0] if camino else False)

    @api.model
    def _existencias_valoradas(self):
        """``[(variante, unidades, costo, precio_sin_itbms)]`` de los productos rastreados con existencias distintas de
        cero (también los archivados), con la valuación de Odoo."""
        Producto = self.env['product.product'].sudo().with_context(**SIN_ARCHIVO)
        productos = Producto.search([('is_storable', '=', True),
                                     ('company_id', 'in', [False] + self.env.companies.ids)])
        filas = []
        for producto in productos._with_valuation_context():
            unidades = producto.qty_available
            if producto.uom_id.is_zero(unidades):
                continue
            filas.append((producto, unidades, producto.total_value, self._precio_sin_itbms(producto)))
        return filas

    @api.model
    def _valor_del_inventario(self):
        redondear = self.env.company.currency_id.round
        moneda = self.env.company.currency_id
        con_mercancia, sin_costo, sin_precio, negativos = [], [], [], []
        por_tipo = defaultdict(lambda: {'costo': 0.0, 'venta': 0.0, 'unidades': 0.0, 'ids': []})
        for producto, unidades, costo, precio in self._existencias_valoradas():
            if unidades < 0:
                negativos.append((producto, unidades))
                continue
            venta = unidades * precio
            con_mercancia.append((producto, unidades, costo, venta))
            if costo <= 0:
                sin_costo.append((producto, unidades, venta))
            if precio <= 0:
                sin_precio.append((producto, unidades, costo))
            tipo = por_tipo[self._clave_de_tipo(producto.categ_id)]
            tipo['costo'] += costo
            tipo['venta'] += venta
            tipo['unidades'] += unidades
            tipo['ids'].append(producto.id)

        costo_total = redondear(sum(costo for _p, _u, costo, _v in con_mercancia))
        venta_total = redondear(sum(venta for _p, _u, _c, venta in con_mercancia))
        ganancia = redondear(venta_total - costo_total)
        ahora = self._ahora_en_panama()
        return {
            'moneda': {'simbolo': moneda.symbol, 'antes': moneda.position == 'before'},
            'hora': _hora(ahora),
            'total': {
                'costo': costo_total,
                'venta': venta_total,
                'ganancia': ganancia,
                'margen': round(ganancia / venta_total * 100, 1) if venta_total > 0 else None,
                'productos': len(con_mercancia),
                'unidades': round(sum(unidades for _p, unidades, _c, _v in con_mercancia), 2),
                'accion': self._accion_de_productos(self.env._('Mercancía en existencia'),
                                                    [p.id for p, _u, _c, _v in con_mercancia]),
            },
            'tipos': self._tipos_del_inventario(por_tipo, redondear),
            'productos': [{
                'id': producto.id, 'nombre': producto.display_name, 'unidades': round(unidades, 2),
                'costo': redondear(costo), 'venta': redondear(venta),
                'imagen': f'/web/image/product.product/{producto.id}/image_128',
            } for producto, unidades, costo, venta in sorted(
                con_mercancia, key=lambda fila: (-fila[2], -fila[3], fila[0].id))[:PRODUCTOS_CON_MAS_VALOR]],
            'avisos': {
                'sin_costo': self._aviso(self.env._('Con existencias y sin costo'), sin_costo, redondear, 'venta'),
                'sin_precio': self._aviso(self.env._('Con existencias y sin precio de venta'), sin_precio, redondear,
                                          'costo'),
                'negativos': self._aviso(self.env._('Existencias negativas'),
                                         [(p, -u, 0.0) for p, u in negativos], redondear, None),
            },
        }

    @api.model
    def _tipos_del_inventario(self, por_tipo, redondear):
        """Una fila por tipo (de más a menos valor al costo); pasados ``TIPOS_A_LA_VISTA``, los demás en «Otros»."""
        nombres = {categoria.id: categoria.name for categoria in
                   self.env['product.category'].sudo().browse([clave for clave in por_tipo if clave])}
        filas = sorted(({
            'nombre': nombres.get(clave) or self.env._('Sin categoría'), 'costo': datos['costo'],
            'venta': datos['venta'], 'unidades': datos['unidades'], 'ids': datos['ids'],
        } for clave, datos in por_tipo.items()), key=lambda fila: (-fila['costo'], -fila['venta'],
                                                                   fila['nombre'].lower()))
        if len(filas) > TIPOS_A_LA_VISTA:
            resto = filas[TIPOS_A_LA_VISTA:]
            filas = filas[:TIPOS_A_LA_VISTA] + [{
                'nombre': self.env._('Otros'), 'costo': sum(f['costo'] for f in resto),
                'venta': sum(f['venta'] for f in resto), 'unidades': sum(f['unidades'] for f in resto),
                'ids': [i for f in resto for i in f['ids']]}]
        return [{
            'nombre': fila['nombre'], 'costo': redondear(fila['costo']), 'venta': redondear(fila['venta']),
            'unidades': round(fila['unidades'], 2), 'productos': len(fila['ids']),
            'accion': self._accion_de_productos(fila['nombre'], fila['ids']),
        } for fila in filas]

    @api.model
    def _aviso(self, nombre, filas, redondear, monto):
        """Lo que falta cargar: cuántos productos, cuántas unidades, el dinero que sí contó (``monto``) y su lista."""
        return {
            'cuantos': len(filas),
            'unidades': round(sum(unidades for _p, unidades, _m in filas), 2),
            'monto': redondear(sum(m for _p, _u, m in filas)) if monto else None,
            'accion': self._accion_de_productos(nombre, [p.id for p, _u, _m in filas]),
        }

    @api.model
    def _accion_de_productos(self, nombre, ids):
        """La lista de las variantes que explican una cifra (también las archivadas que tienen existencias)."""
        accion = _accion(nombre, 'product.product', [('id', 'in', ids)])
        accion['contexto'] = SIN_ARCHIVO
        return accion
