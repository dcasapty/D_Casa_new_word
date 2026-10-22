"""Costo cerrado (etapa 1b(a), de la revisión adversarial del 2026-10-16).

El costo de un producto, lo que cobra el proveedor y el margen de los reportes de factura los ven solo quienes
controlan la tienda (``GRUPOS_COSTO``): Gerencia, administradores, contabilidad, compras e inventario (y quien
administra Ventas o crea productos, que ya ven la ganancia o cambian el costo). La Vendedora, Caja y bodega no.

Por qué no se le pone ``groups=`` al campo de Odoo: Inventario, Compras y Contabilidad leen el costo **dentro** de sus
procesos con los permisos de la persona (validar una entrega valora la mercancía con ``standard_price``; publicar una
factura arma el costo de ventas). Un ``groups`` en el campo haría fallar esas entregas y facturas de la Vendedora.

Así que se cierra donde la persona lo puede VER o PEDIR, y no donde el sistema lo usa:

* **Pantallas.** ``_get_view`` le pone el grupo a cada nodo que muestra un campo de costo (y a su etiqueta y su caja),
  y a los precios de proveedor del producto. Odoo quita esos nodos a quien no tiene el grupo, en todas las vistas
  (formulario, lista, kanban, búsqueda, pivote), también las que agreguen otros módulos.
* **Conexión de datos (RPC).** ``read`` (y con él ``web_read``, ``web_search_read``, ``web_save`` y ``onchange``),
  ``search_read``, buscar u ordenar por el costo (``_search``), agrupar o sumar (``_read_group``) y la lista de campos
  (``fields_get``: filtros, medidas del pivote, exportar) niegan esos campos a quien no tiene el grupo, igual que
  Odoo con un campo con ``groups``.
* **Lo que no cambia:** el código que corre dentro de Odoo (``producto.standard_price``) sigue leyendo el costo para
  valorar entregas, recepciones y el costo de ventas. Y lo que corre con ``sudo`` (la tienda, Juan, los procesos).

Pruebas: ``tests/test_costos_cerrados.py`` (lo que se ve y lo que se niega, por rol, y que la Vendedora y bodega
siguen recibiendo, entregando, vendiendo y facturando).
"""
from odoo import api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain

# Quienes ven el costo: Gerencia, administradores, contabilidad (lector, contador, gerente contable), compras,
# inventario (administrador), Ventas administrador (ya ve la ganancia) y quien crea productos (ya cambia el costo).
GRUPOS_COSTO = (
    'dcasa_base.group_gerencia',
    'base.group_system',
    'account.group_account_readonly',
    'account.group_account_manager',
    'purchase.group_purchase_user',
    'stock.group_stock_manager',
    'sales_team.group_sale_manager',
    'product.group_product_manager',
)
GRUPOS_COSTO_VISTA = ','.join(GRUPOS_COSTO)
# Nodos que, aunque no sean el campo, existen para mostrarlo (los precios de proveedor del producto).
NODOS_DEL_COSTO = ('seller_ids', 'variant_seller_ids')
CAJAS_DEL_COSTO = ('standard_price_uom',)


def ve_costos(env):
    """¿Quien mira puede ver costos? El sistema (``sudo``) siempre."""
    return env.su or any(env.user.has_group(grupo) for grupo in GRUPOS_COSTO)


class DcasaCostoCerrado(models.AbstractModel):
    """Se mezcla en los modelos que tienen campos de costo; ``_dcasa_campos_costo`` dice cuáles."""
    _name = 'dcasa.costo.cerrado'
    _description = 'Campos de costo solo para quien controla la tienda'

    _dcasa_campos_costo = ()

    @api.model
    def _dcasa_cerrados(self):
        """Los campos de costo que existen en este modelo (otros módulos pueden no estar instalados)."""
        return frozenset(nombre for nombre in self._dcasa_campos_costo if nombre in self._fields)

    @api.model
    def _dcasa_exigir_costos(self, nombres):
        """Niega (como Odoo con un campo con ``groups``) si se piden campos de costo sin el grupo.

        ``nombres``: campos, ``campo:agregado``, ``campo:mes`` o rutas ``campo.otro``; se mira el primer tramo."""
        if ve_costos(self.env):
            return
        pedidos = {str(nombre).split(':')[0].split('.')[0].strip().split(' ')[0] for nombre in nombres or () if nombre}
        prohibidos = sorted(pedidos & self._dcasa_cerrados())
        if prohibidos:
            raise AccessError(self.env._(
                'El costo y el precio del proveedor los ven solo Gerencia, contabilidad, compras e inventario '
                '(campo «%(campo)s» de %(modelo)s).', campo=prohibidos[0], modelo=self._description))

    # ------------------------------------------------------------------
    # Pantallas
    # ------------------------------------------------------------------

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        cerrados = self._dcasa_cerrados()
        if cerrados:
            self._dcasa_cerrar_nodos(arch, cerrados)
        return arch, view

    @api.model
    def _dcasa_cerrar_nodos(self, arch, cerrados):
        """Le pone el grupo del costo a los nodos de esos campos, a su etiqueta y a la caja que solo los contiene.

        La vista se guarda en la caché igual para todos; Odoo quita después los nodos con grupo a quien no lo tiene
        (``_postprocess_access_rights``). Así no queda un ``<label>`` «Costo» vacío ni una caja sin nada."""
        nombres = set(cerrados) | {n for n in NODOS_DEL_COSTO if n in self._fields}
        for nodo in arch.iter('field'):
            nombre = nodo.get('name')
            if nombre not in nombres:
                continue
            # Un campo dentro de la lista de otro (p. ej. el precio dentro de los proveedores) es de otro modelo: lo
            # cierra su propio campo padre (seller_ids), que también recibe el grupo.
            if any(ancestro.tag == 'field' for ancestro in nodo.iterancestors()):
                continue
            nodo.set('groups', GRUPOS_COSTO_VISTA)
            caja = nodo
            padre = caja.getparent()
            while padre is not None and padre.tag in ('div', 'span') and all(
                    hijo.get('name') in nombres for hijo in padre.iter('field')):
                caja = padre
                padre = caja.getparent()
            if caja is not nodo:
                caja.set('groups', GRUPOS_COSTO_VISTA)
        for etiqueta in arch.iter('label'):
            if etiqueta.get('for') in nombres:
                etiqueta.set('groups', GRUPOS_COSTO_VISTA)
        # La caja del costo del formulario del producto lleva además la unidad («por Unidades»).
        for caja in arch.iter('div'):
            if caja.get('name') in CAJAS_DEL_COSTO:
                caja.set('groups', GRUPOS_COSTO_VISTA)

    # ------------------------------------------------------------------
    # Conexión de datos (RPC)
    # ------------------------------------------------------------------

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        """Sin el grupo, los campos de costo no existen: no salen en filtros, medidas del pivote ni exportar."""
        resultado = super().fields_get(allfields, attributes)
        if not ve_costos(self.env):
            for nombre in self._dcasa_cerrados():
                resultado.pop(nombre, None)
        return resultado

    def read(self, fields=None, load='_classic_read'):
        if fields:
            self._dcasa_exigir_costos(fields)
        return super().read(fields, load=load)

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **read_kwargs):
        if fields:
            self._dcasa_exigir_costos(fields)
        return super().search_read(domain, fields, offset=offset, limit=limit, order=order, **read_kwargs)

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        """Buscar u ordenar por el costo también lo revela («productos con costo mayor que 100»)."""
        if not bypass_access and not ve_costos(self.env) and self._dcasa_cerrados():
            nombres = [condicion.field_expr for condicion in Domain(domain or []).iter_conditions()
                       if isinstance(condicion.field_expr, str)]
            # El orden de fábrica del modelo (el de los precios de proveedor lleva «price») lo pone Odoo al leer una
            # relación por dentro; solo cuenta un orden que pidió alguien.
            if order and order != self._order:
                nombres += order.replace(',', ' ').split()
            self._dcasa_exigir_costos(nombres)
        return super()._search(domain, offset=offset, limit=limit, order=order, active_test=active_test,
                               bypass_access=bypass_access)

    @api.model
    def _read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        """Sumar el margen o agrupar por el costo (pivote, gráfica, totales de una lista)."""
        if not ve_costos(self.env) and self._dcasa_cerrados():
            self._dcasa_exigir_costos(list(groupby) + list(aggregates)
                                      + (order or '').replace(',', ' ').split())
        return super()._read_group(domain, groupby=groupby, aggregates=aggregates, having=having, offset=offset,
                                   limit=limit, order=order)


class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = ['product.template', 'dcasa.costo.cerrado']
    _dcasa_campos_costo = ('standard_price', 'avg_cost', 'total_value')


class ProductProduct(models.Model):
    _name = 'product.product'
    _inherit = ['product.product', 'dcasa.costo.cerrado']
    _dcasa_campos_costo = ('standard_price', 'avg_cost', 'total_value')


class ProductSupplierinfo(models.Model):
    _name = 'product.supplierinfo'
    _inherit = ['product.supplierinfo', 'dcasa.costo.cerrado']
    _dcasa_campos_costo = ('price', 'price_discounted', 'discount')


class AccountInvoiceReport(models.Model):
    _name = 'account.invoice.report'
    _inherit = ['account.invoice.report', 'dcasa.costo.cerrado']
    _dcasa_campos_costo = ('price_margin', 'inventory_value')
