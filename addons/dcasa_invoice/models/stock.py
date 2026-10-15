"""La nota de entrega con el código público (solo con el interruptor de la empresa encendido; apagado, todo igual).

La nota de entrega imprime el nombre de cada producto («[referencia] Nombre») y, debajo, la descripción de la entrega
que Odoo guardó al crearla, que casi siempre es ese mismo nombre con la referencia del proveedor. Con el interruptor
encendido ``o`` se arma con el contexto ``dcasa_codigo_publico``: el nombre sale con el código público y la descripción
se limpia de la referencia del proveedor, así esta nunca aparece en el papel.
"""
from odoo import fields, models
from odoo.tools.image import image_data_uri

from . import entrega_facil, lineas
from .producto import CLAVE_CONTEXTO


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _dcasa_para_imprimir(self):
        """La entrega tal como se imprime: con el código público en vez de la referencia, si la empresa lo pide."""
        self.ensure_one()
        if self.company_id.dcasa_mostrar_codigo_publico:
            return self.with_context(**{CLAVE_CONTEXTO: True, 'display_default_code': False})
        return self

    # --- La nota de entrega fácil de leer (interruptor de la empresa; ver ``entrega_facil.py``) -------------------

    def _dcasa_entrega_facil_activa(self):
        self.ensure_one()
        return bool(self.company_id.dcasa_entrega_facil)

    def _dcasa_lineas_entrega_facil(self, pendientes=False):
        """Las líneas de la nota de entrega fácil de leer, una por producto (lo repetido se suma).

        ``pendientes``: en vez de esta entrega, lo que falta por entregar (las entregas pendientes que quedaron de
        ella). Una entrega sin terminar muestra lo que hay que sacar de bodega; una terminada, lo que salió.
        Cada línea: producto, nombre limpio, código (el del proveedor o, si la empresa lo pide, el público), foto
        grande y chica (o ``False``: se pinta «Sin foto»), cantidad, texto de la cantidad, cuántos dibujitos y
        lo que falta por entregar de ese producto (en una entrega ya hecha a medias).
        """
        self.ensure_one()
        if pendientes:
            entregas = self.backorder_ids.filtered(lambda entrega: entrega.state not in ('done', 'cancel'))
        else:
            entregas = self
        hecha = (self.state == 'done') and not pendientes
        por_producto = {}
        for movimiento in entregas.move_ids:
            if movimiento.state == 'cancel' or not movimiento.product_uom_qty:
                continue
            cantidad = movimiento.quantity if hecha else movimiento.product_uom_qty
            if not cantidad:
                continue
            clave = (movimiento.product_id.id, movimiento.product_uom.id)
            linea = por_producto.setdefault(clave, {
                'producto': movimiento.product_id, 'uom': movimiento.product_uom, 'cantidad': 0.0,
                'movimiento': movimiento})
            linea['cantidad'] += cantidad
        # Al validar a medias Odoo deja en esta entrega lo que salió y manda el resto a la entrega pendiente: lo que
        # «falta» de cada producto es lo que está esperando ahí.
        esperando = {}
        if hecha:
            for pendiente in self.backorder_ids.filtered(lambda entrega: entrega.state not in ('done', 'cancel')):
                for movimiento in pendiente.move_ids.filtered(lambda m: m.state != 'cancel'):
                    clave = (movimiento.product_id.id, movimiento.product_uom.id)
                    esperando[clave] = esperando.get(clave, 0.0) + movimiento.product_uom_qty
        empresa = self.company_id
        la_unidad = self.env.ref('uom.product_uom_unit', raise_if_not_found=False)
        lineas_listas = []
        for clave, linea in por_producto.items():
            producto = linea['producto']
            nombre = producto.with_context(display_default_code=False, **{CLAVE_CONTEXTO: False}).display_name
            codigo = lineas.codigo_a_imprimir(empresa, producto, producto.default_code)
            descripcion = linea['movimiento']._get_report_description_picking()
            if descripcion and descripcion.strip() in (nombre, producto.name):
                descripcion = ''
            iconos, hay_mas = entrega_facil.iconos_de_cantidad(linea['cantidad'])
            lineas_listas.append({
                'producto': producto,
                'nombre': nombre,
                'codigo': codigo or '',
                'descripcion': (descripcion or '').strip(),
                'foto': image_data_uri(producto.image_256) if producto.image_256 else False,
                'foto_chica': image_data_uri(producto.image_128) if producto.image_128 else False,
                'cantidad': linea['cantidad'],
                'texto_cantidad': entrega_facil.texto_cantidad(linea['cantidad']),
                'unidad': entrega_facil.texto_unidad(bool(la_unidad) and linea['uom'] == la_unidad, linea['uom'].name),
                'iconos': iconos,
                'hay_mas': hay_mas,
                'falta': (entrega_facil.texto_cantidad(esperando[clave]) if esperando.get(clave) else ''),
            })
        return lineas_listas

    @staticmethod
    def _dcasa_total_piezas_entrega_facil(lineas_de_la_nota):
        return entrega_facil.total_de_piezas(lineas_de_la_nota)

    def _dcasa_fecha_para_entrega(self):
        """«14/10/2026»: el día de salida (si ya salió) o el programado, a la hora de Panamá."""
        self.ensure_one()
        fecha = self.date_done if self.state == 'done' else self.scheduled_date
        if not fecha:
            return ''
        return fields.Datetime.context_timestamp(self.with_context(tz='America/Panama'), fecha).strftime('%d/%m/%Y')

    def _dcasa_facturas_para_entrega(self):
        """Los números de las facturas publicadas del pedido de esta entrega (para compararla con la factura)."""
        self.ensure_one()
        pedido = self.sale_id
        if not pedido:
            return []
        return [factura.name for factura in pedido.invoice_ids.filtered(
            lambda factura: factura.state == 'posted' and factura.move_type == 'out_invoice')]


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _get_report_description_picking(self):
        """La descripción de la entrega sin repetir el nombre; con el código público activo, sin la referencia."""
        if not self.env.context.get(CLAVE_CONTEXTO):
            return super()._get_report_description_picking()
        self.ensure_one()
        producto = self.product_id
        # La descripción trae el nombre con la referencia del proveedor («[IM-2001] …», si se guardó así) o con el
        # código público («[DC-K7M4PX] …», si se calculó ahora): se quita lo que haya y después el nombre repetido.
        descripcion = lineas.quitar_referencia_delante(self.description_picking, producto.default_code)
        descripcion = lineas.quitar_referencia_delante(descripcion, producto.dcasa_codigo_publico)
        nombre = producto.name or ''
        if nombre and descripcion.startswith(nombre):
            descripcion = descripcion.removeprefix(nombre).strip()
        return descripcion


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _get_aggregated_properties(self, move_line=False, move=False):
        propiedades = super()._get_aggregated_properties(move_line=move_line, move=move)
        if self.env.context.get(CLAVE_CONTEXTO):
            propiedades['description'] = (move or move_line.move_id)._get_report_description_picking()
        return propiedades
