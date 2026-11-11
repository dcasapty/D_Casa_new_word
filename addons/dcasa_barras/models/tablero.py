"""Bodega en el Inicio: su acceso y el panel «Entregas pendientes», los dos con las mismas entregas.

Para quien despacha (el mismo permiso que su menú de Inventario). El acceso «Bodega» y la pantalla Bodega cuentan solo
las entregas de pedidos con pago o abono (decisión de la dueña, 2026-10-22: «solo pueden ver el pedido si pagaron o
abonaron»); el panel «Entregas pendientes» del Inicio contaba todas las salidas pendientes, y los dos números podían
no coincidir («2 entregas pendientes» junto a «Bodega: nada por despachar»). Desde el 2026-11-11 el panel y su cifra
muestran las mismas entregas que Bodega, en su mismo orden, y debajo un renglón dice cuántas más esperan pago o abono
y abre esa lista: los números coinciden y Gerencia no pierde de vista las demás.
"""
from odoo import models
from odoo.addons.dcasa_interfaz.models.tablero import CAMPOS_DE_ENTREGA, FILAS_DE_LISTA, _accion


class DcasaTablero(models.AbstractModel):
    _inherit = 'dcasa.tablero'

    def _despacha_en_bodega(self):
        """Quien puede abrir Bodega: usuario de Inventario, con la pantalla instalada."""
        return self.env.user.has_group('stock.group_stock_user') \
            and bool(self.env.ref('dcasa_barras.accion_bodega', raise_if_not_found=False))

    def _atajos(self, permisos):
        """Bodega va justo antes del Escáner, con cuántas entregas esperan (las mismas del panel)."""
        atajos = super()._atajos(permisos)
        if not self._despacha_en_bodega():
            return atajos
        cuantas = len(self.env['dcasa.bodega']._despachables())   # las mismas del panel: con pago o abono
        if not cuantas:
            detalle = 'Nada por despachar'
        else:
            detalle = '1 entrega por despachar' if cuantas == 1 else f'{cuantas} entregas por despachar'
        bodega = {
            'clave': 'bodega', 'titulo': 'Bodega', 'detalle': detalle, 'icono': 'fa-truck',
            'accion': 'dcasa_barras.accion_bodega', 'vista': None, 'cuenta': cuantas,
        }
        posicion = next((i for i, atajo in enumerate(atajos) if atajo['clave'] == 'escaner'), len(atajos))
        atajos.insert(posicion, bodega)
        return atajos

    def _entregas(self, datos, hoy):
        """El panel «Entregas pendientes» y su cifra, con las mismas entregas que Bodega y en su mismo orden.

        ``super()`` deja todas las salidas pendientes (lo que el Inicio contaba antes). Aquí quedan solo las que Bodega
        puede despachar (``dcasa.bodega._despachables``) y las demás pasan a ``esperan``: cuántas son, la frase del
        renglón y la lista que abre. Las listas («Ver las N», la cifra) abren exactamente las que se cuentan.
        """
        super()._entregas(datos, hoy)
        if not self._despacha_en_bodega():
            return
        Bodega = self.env['dcasa.bodega']
        despachables = Bodega._despachables()

        def orden(entrega):
            """El de las tarjetas de Bodega (``pendientes``): por su fecha (la prometida o, si no, la programada)."""
            fecha = Bodega._fecha(entrega, entrega.sudo().sale_id)[0]
            return (fecha.isoformat() if fecha else '9999', entrega.id)

        primeras = despachables.sorted(orden)[:FILAS_DE_LISTA]
        leidas = {p['id']: p for p in primeras.read(CAMPOS_DE_ENTREGA)}
        todas = datos['entregas']['accion']['domain']
        accion = _accion('Entregas pendientes', 'stock.picking', [('id', 'in', despachables.ids)])
        datos['entregas'].update({
            'cantidad': len(despachables),
            'accion': accion,
            'filas': [self._fila_de_entrega(leidas[entrega.id], hoy) for entrega in primeras],
        })
        for cifra in datos['cifras']:
            if cifra['clave'] == 'entregas':
                cifra.update({'valor': len(despachables), 'accion': accion})
        # Las demás: las que esperan pago o abono (y, si las hubiera, las que no son de un pedido de venta o no van a
        # un cliente: Bodega tampoco las muestra). Con una sola de las dos clases, la frase nombra solo esa.
        dominio = todas + [('id', 'not in', despachables.ids)]
        resto = self.env['stock.picking'].search(dominio)
        if not resto:
            return
        pagos = Bodega._pagos_de_pedidos(resto.sudo().sale_id)
        sin_pago = len(resto.filtered(lambda entrega: pagos.get(entrega.sudo().sale_id.id) == 'sin_pago'))
        datos['entregas']['esperan'] = {
            'cantidad': len(resto),
            'texto': self._texto_de_las_que_esperan(sin_pago, len(resto) - sin_pago, bool(despachables)),
            'accion': _accion('Entregas que esperan pago o abono' if sin_pago == len(resto)
                              else 'Entregas pendientes que no salen en Bodega', 'stock.picking', dominio),
        }

    @staticmethod
    def _texto_de_las_que_esperan(sin_pago, otras, hay_despachables):
        """«2 más esperan pago o abono»: el renglón de las entregas pendientes que Bodega todavía no despacha.

        ``otras``: las que no vienen de un pedido de venta o no van a un cliente (Bodega tampoco las muestra). «más»
        solo si arriba hay entregas por despachar."""
        mas = ' más' if hay_despachables else ''
        partes = []
        if sin_pago:
            partes.append(f'{sin_pago}{mas} ' + ('espera' if sin_pago == 1 else 'esperan') + ' pago o abono')
        if otras:
            partes.append(f'{otras}' + ('' if partes else mas) + ' ' + ('no sale' if otras == 1 else 'no salen')
                          + ' en Bodega')
        return ' y '.join(partes)
