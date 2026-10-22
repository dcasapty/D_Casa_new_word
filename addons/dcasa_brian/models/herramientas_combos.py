"""Herramientas de combos cama + colchón que se arman en la venta (pedido de la dueña, 2026-10-22).

Las reglas viven en dcasa_catalogo (``models/combo_armable.py``): el colchón va a su «precio en combo» (el que puso
Gerencia, por medida) solo si en la misma venta va una cama de su misma medida; sin precio en combo, a precio normal.
Brian usa el mismo panel que la vendedora (``dcasa_combo_*`` de la cotización) y corre como quien le habla: el tope de
descuento y «cada vendedora ve solo lo suyo» le valen igual.
"""
from odoo import api, models

from . import herramientas_comun as c
from .herramientas_ventas import GERENCIA, PARAM_VENTA, VENDEDOR
from .registro import BrianError, herramienta

PARAM_CAMA = {'type': 'string',
              'description': 'La cama: nombre o código, con su medida si tiene varias, p. ej. «cama tapizada king» '
                             'o «908K».'}
PARAM_COLCHON = {'type': 'string',
                 'description': 'El colchón con su medida: nombre o código, p. ej. «colchón flex king» o «T112».'}


class BrianHerramientasCombos(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    def _b_cama_o_colchon(self, texto, tipo):
        etiqueta = 'cama' if tipo == 'cama' else 'colchón'
        return self._b_resolver('product.product', texto, etiqueta, exactos=('default_code', 'barcode'),
                                dominio=[('dcasa_tipo_combo', '=', tipo), ('sale_ok', '=', True)])

    @api.model
    def _b_fila_colchon(self, colchon):
        fila = {'colchon': colchon.display_name, 'codigo': colchon.default_code or '',
                'medida': colchon.dcasa_medida or 'falta la medida', 'precio_normal': c.moneda(colchon.lst_price)}
        precio = colchon.dcasa_precio_combo
        if precio and precio < colchon.lst_price:
            fila.update({'precio_en_combo': c.moneda(precio), 'ahorro': c.moneda(colchon.lst_price - precio)})
        else:
            fila['precio_en_combo'] = 'sin precio en combo: va a precio normal'
        if colchon.is_storable:
            fila['disponibles'] = c.cantidad(colchon.free_qty)
        return fila

    @api.model
    def _b_resumen_combo(self, orden, mensaje):
        respuesta = {'mensaje': mensaje, **self._b_resumen_orden(orden)}
        ahorro = orden._dcasa_ahorro_combos()
        if ahorro:
            respuesta['el_cliente_ahorra_sin_itbms'] = c.moneda(ahorro)
        respuesta['abrir'] = {'modelo': 'sale.order', 'res_id': orden.id, 'titulo': orden.name}
        return respuesta

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    @herramienta(
        nombre='colchones_para_cama',
        descripcion='Los colchones de la misma medida de una cama (con existencia), para armar un combo cama + '
                    'colchón: precio normal, precio en combo (el que puso Gerencia) y lo que ahorra el cliente.',
        parametros={'cama': PARAM_CAMA,
                    'todos': {'type': 'boolean', 'description': 'También los agotados. Por defecto, solo con '
                                                                'existencia.'}},
        requeridos=['cama'],
        nivel='lectura', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['¿qué colchones le van a la cama tapizada king?', 'colchones para la 908K con su precio en combo'],
    )
    def _h_colchones_para_cama(self, cama, todos=False):
        variante = self._b_cama_o_colchon(cama, 'cama')
        if not variante.dcasa_medida:
            raise BrianError(f'«{variante.display_name}» no tiene medida: Gerencia la pone en Ventas › Productos › '
                             'Precios en combo (filtro «Camas»).')
        colchones = variante._dcasa_combo_colchones(todos=bool(todos))
        filas = sorted((self._b_fila_colchon(colchon) for colchon in colchones),
                       key=lambda f: ('ahorro' not in f, f['colchon']))
        return {'cama': variante.display_name, 'medida': variante.dcasa_medida,
                'precio_cama': c.moneda(variante.lst_price), 'encontrados': len(filas),
                'colchones': filas[:c.MAX_FILAS],
                'nota': 'Precios sin ITBMS. El precio en combo se cobra solo si el colchón va en la misma venta '
                        'con una cama de su medida.'}

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    @herramienta(
        nombre='armar_combo',
        descripcion='Arma un combo cama + colchón en una cotización: agrega la cama y el colchón de su misma medida; '
                    'el colchón va a su precio en combo si Gerencia se lo puso. Sin «venta», crea una cotización '
                    'nueva para «cliente».',
        parametros={'venta': PARAM_VENTA,
                    'cliente': {'type': 'string', 'description': 'Para una cotización nueva: nombre, celular o RUC.'},
                    'cama': PARAM_CAMA, 'colchon': PARAM_COLCHON,
                    'cantidad': {'type': 'integer', 'description': 'Cuántos combos (1 a 20). Por defecto 1.'}},
        requeridos=['cama', 'colchon'],
        nivel='construccion', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['agrega a S00012 la cama 908K con el colchón Flex king → venta=S00012, cama=908K, '
                  'colchon=colchón flex king',
                  'cotiza a 6123-4567 la cama tapizada queen con colchón Dulces Sueños queen'],
    )
    def _h_armar_combo(self, cama, colchon, venta=None, cliente=None, cantidad=1):
        variante_cama = self._b_cama_o_colchon(cama, 'cama')
        variante_colchon = self._b_cama_o_colchon(colchon, 'colchon')
        if venta:
            orden = self._b_cotizacion_editable(venta)
        elif cliente:
            orden = self.env['sale.order'].create({'partner_id': self._b_contacto(cliente).id})
        else:
            raise BrianError('Dime la cotización («venta», p. ej. S00012) o el «cliente» para una nueva.')
        orden.dcasa_combo_agregar(cama_id=variante_cama.id, colchon_id=variante_colchon.id, cantidad=cantidad or 1)
        return self._b_resumen_combo(orden, f'Combo agregado a {orden.name}.')

    @herramienta(
        nombre='cambiar_combo',
        descripcion='Cambia la cama o el colchón de un combo cama + colchón de una cotización; el precio se vuelve a '
                    'calcular. Si cambias la cama por otra medida, di también el colchón nuevo.',
        parametros={'venta': PARAM_VENTA,
                    'cama_nueva': PARAM_CAMA, 'colchon_nuevo': PARAM_COLCHON,
                    'cama_actual': {'type': 'string',
                                    'description': 'Solo si la cotización tiene varios combos: la cama del combo que '
                                                   'se cambia.'}},
        requeridos=['venta'],
        nivel='construccion', categoria='ventas', grupos=VENDEDOR,
        ejemplos=['en S00012 cámbiale el colchón al combo por el First Class king → colchon_nuevo=first class king'],
    )
    def _h_cambiar_combo(self, venta, cama_nueva=None, colchon_nuevo=None, cama_actual=None):
        if not cama_nueva and not colchon_nuevo:
            raise BrianError('Dime qué cambiar: «cama_nueva», «colchon_nuevo» o los dos.')
        orden = self._b_cotizacion_editable(venta)
        combos = orden.dcasa_combo_panel()['combos']
        if cama_actual:
            texto = c.normalizar_texto(cama_actual)
            combos = [x for x in combos if texto in c.normalizar_texto(x['cama']['nombre'])
                      or texto == c.normalizar_texto(x['cama']['codigo'])]
        if not combos:
            raise BrianError(f'{orden.name} no tiene ese combo cama + colchón.' if cama_actual
                             else f'{orden.name} no tiene combos cama + colchón: ármalo con armar_combo.')
        if len(combos) > 1:
            raise BrianError(f'{orden.name} tiene varios combos: dime cuál con «cama_actual» ('
                             + '; '.join(x['cama']['nombre'] for x in combos) + ').')
        combo = combos[0]
        orden.dcasa_combo_cambiar(
            combo['cama']['linea_id'],
            cama_id=self._b_cama_o_colchon(cama_nueva, 'cama').id if cama_nueva else False,
            colchon_id=self._b_cama_o_colchon(colchon_nuevo, 'colchon').id if colchon_nuevo else False)
        return self._b_resumen_combo(orden, f'Combo de {orden.name} cambiado.')

    @herramienta(
        nombre='poner_precio_en_combo',
        descripcion='Pone o quita (con 0) el precio en combo de un colchón en una medida: el precio sin ITBMS al '
                    'que se cobra cuando va en la misma venta con una cama de su medida. Menor que el precio normal.',
        parametros={'colchon': PARAM_COLCHON,
                    'precio': {'type': 'number',
                               'description': 'Precio en combo sin ITBMS, p. ej. 299.99. 0 lo quita (precio normal).'}},
        requeridos=['colchon', 'precio'],
        nivel='construccion', categoria='catalogo', grupos=GERENCIA,
        ejemplos=['el colchón Flex king en combo a 299.99 → colchon=colchón flex king, precio=299.99'],
    )
    def _h_poner_precio_en_combo(self, colchon, precio):
        variante = self._b_cama_o_colchon(colchon, 'colchon')
        try:
            nuevo = float(str(precio).replace('$', '').replace(',', '').strip())
        except ValueError as error:
            raise BrianError(f'«{precio}» no es un precio. Escríbelo como 299.99 (0 para quitarlo).') from error
        anterior = variante.dcasa_precio_combo
        variante.dcasa_precio_combo = nuevo
        antes = c.moneda(anterior) if anterior else 'sin precio en combo'
        despues = c.moneda(nuevo) if nuevo else 'sin precio en combo'
        return {'mensaje': f'Precio en combo de «{variante.display_name}»: {antes} → {despues}.',
                **self._b_fila_colchon(variante)}
