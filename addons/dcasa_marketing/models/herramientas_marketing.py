"""Brian y Marketing: «¿qué productos están más quietos esta semana?», «¿qué se movió más en el mes?» y «¿qué productos
no tienen foto?».

Las mismas cifras de la pantalla Marketing (``dcasa.marketing``): nada se calcula con el modelo de IA. Solo lectura.
``movimiento_de_productos`` es de Gerencia y administradores (las ventas de toda la tienda, como la pantalla);
``fotos_que_faltan`` es de cualquiera que vea productos.
"""
from odoo import models
from odoo.addons.dcasa_brian.models import herramientas_comun as c
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta, normalizar

from .marketing import FILTROS_DE_FOTOS, GRUPOS, PERIODOS

INTERNO = ('base.group_user',)
QUE_VER = ('mas_movimiento', 'quietos', 'mas_vendidos', 'todo')
MAX_FILAS = 20


class BrianHerramientasMarketing(models.AbstractModel):
    _inherit = 'brian.herramientas'

    def _mk_categoria(self, categoria):
        """El «tipo» (categoría de primer nivel, el de la pantalla) que nombró la persona, o ``None``."""
        if not categoria:
            return None
        buscada = normalizar(str(categoria)).strip()
        tipos = self.env['dcasa.marketing']._lista_de_categorias()
        iguales = [t for t in tipos if normalizar(t['nombre']) == buscada]
        parecidos = iguales or [t for t in tipos if buscada and buscada in normalizar(t['nombre'])]
        if len(parecidos) == 1:
            return parecidos[0]
        opciones = ', '.join(t['nombre'] for t in tipos[:12])
        raise BrianError(f'No encontré la categoría «{categoria}». Las que hay: {opciones}.')

    @staticmethod
    def _mk_producto(fila):
        datos = {'producto': fila['nombre'], 'codigo': fila['codigo'], 'categoria': fila['categoria']}
        if fila.get('stock') is not None:
            datos['stock'] = c.cantidad(fila['stock'])
        return datos

    @herramienta(
        nombre='movimiento_de_productos',
        descripcion='Lo mismo que la pantalla Marketing: los productos con más movimiento (lo vendido o entregado), '
                    'los más quietos (con stock y sin ventas ni entregas) y los más vendidos (unidades facturadas) '
                    'en la semana, 15 días o el mes (días corridos, hoy incluido). Opcional: una categoría.',
        parametros={
            'periodo': {'type': 'string', 'enum': list(PERIODOS),
                        'description': '«semana» (7 días, por defecto), «15_dias» o «mes» (30 días).'},
            'que': {'type': 'string', 'enum': list(QUE_VER),
                    'description': 'Qué lista: mas_movimiento, quietos, mas_vendidos o todo (por defecto).'},
            'categoria': {'type': 'string', 'description': 'Solo una categoría, p. ej. «Salas». Opcional.'},
            'limite': {'type': 'integer', 'description': f'Cuántos por lista (1 a {MAX_FILAS}). Por defecto 8.'},
        },
        nivel='lectura', categoria='catalogo', grupos=(GRUPOS,),
        ejemplos=['¿qué productos están más quietos esta semana? → que=quietos, periodo=semana',
                  '¿qué se movió más este mes en salas? → que=mas_movimiento, periodo=mes, categoria=Salas',
                  'lo más vendido en 15 días → que=mas_vendidos, periodo=15_dias'],
    )
    def _h_movimiento_de_productos(self, periodo='semana', que='todo', categoria=None, limite=8):
        Marketing = self.env['dcasa.marketing']
        Marketing._exigir()
        if que not in QUE_VER:
            raise BrianError('«que» es mas_movimiento, quietos, mas_vendidos o todo.')
        try:
            limite = max(1, min(int(limite or 8), MAX_FILAS))
        except (TypeError, ValueError):
            limite = 8
        tipo = self._mk_categoria(categoria)
        rango = Marketing._rango(periodo or 'semana')
        _tipo, filtro = Marketing._categoria_pedida(tipo['id'] if tipo else None)
        datos = Marketing._movimiento(rango, filtro, limite=limite)
        respuesta = {
            'periodo': rango['etiqueta'],
            'categoria': tipo['nombre'] if tipo else 'todas',
            'como_se_cuenta': 'Vendidas: facturas publicadas del periodo (las notas de crédito restan), como el '
                              'Inicio. Entregadas: salidas de la bodega a clientes. Movimiento: lo mayor de las dos '
                              '(una venta facturada y entregada cuenta una vez). Quietos: con stock y sin ventas ni '
                              'entregas en el periodo, primero los que nunca se vendieron.',
        }
        if que in ('mas_movimiento', 'todo'):
            respuesta['mas_movimiento'] = [
                {**self._mk_producto(f), 'movimiento': c.cantidad(f['movimiento']),
                 'vendidas': c.cantidad(f['vendidas']), 'entregadas': c.cantidad(f['entregadas'])}
                for f in datos['mas_movimiento']]
        if que in ('mas_vendidos', 'todo'):
            respuesta['mas_vendidos'] = [{**self._mk_producto(f), 'unidades': c.cantidad(f['unidades'])}
                                         for f in datos['mas_vendidos']]
        if que in ('quietos', 'todo'):
            respuesta['quietos_total'] = datos['quietos_total']
            respuesta['quietos'] = [
                {**self._mk_producto(f),
                 'ultima_venta': c.fecha(f['ultima_venta']) if f['ultima_venta'] else 'nunca (en las facturas de Odoo)',
                 'dias_sin_vender': f['dias_sin_vender']}
                for f in datos['quietos']]
        if not any(respuesta.get(clave) for clave in ('mas_movimiento', 'mas_vendidos', 'quietos')):
            respuesta['mensaje'] = 'No hay productos que mostrar con eso en este periodo.'
        return respuesta

    @herramienta(
        nombre='fotos_que_faltan',
        descripcion='Productos a la venta sin foto o con una sola foto (la principal sin fotos extra), con cuántas '
                    'tiene cada uno. Se puede buscar por nombre o código y filtrar por categoría. Las fotos se suben '
                    'en Marketing › Fotos o tocando la foto del producto.',
        parametros={
            'estado': {'type': 'string', 'enum': list(FILTROS_DE_FOTOS),
                       'description': 'faltan (sin foto o con una sola, por defecto), sin_foto, una_foto o todos.'},
            'texto': {'type': 'string', 'description': 'Nombre, código o código de barras. Opcional.'},
            'categoria': {'type': 'string', 'description': 'Solo una categoría, p. ej. «Colchones». Opcional.'},
            'limite': c.PARAM_LIMITE,
        },
        nivel='lectura', categoria='catalogo', grupos=INTERNO,
        ejemplos=['¿qué productos no tienen foto? → estado=sin_foto',
                  '¿a qué colchones les faltan fotos? → categoria=Colchones'],
    )
    def _h_fotos_que_faltan(self, estado='faltan', texto=None, categoria=None, limite=10):
        if estado not in FILTROS_DE_FOTOS:
            raise BrianError('«estado» es faltan, sin_foto, una_foto o todos.')
        tipo = self._mk_categoria(categoria)
        resultado = self.env['dcasa.marketing']._buscar_fotos(texto or '', estado, tipo['id'] if tipo else None,
                                                              limite=c.limite(limite))
        conteo = resultado['conteo']
        return {
            'categoria': tipo['nombre'] if tipo else 'todas',
            'sin_foto': conteo['sin_foto'],
            'con_una_sola_foto': conteo['una_foto'],
            'encontrados': resultado['total'],
            'productos': [{**self._mk_producto(f), 'fotos': f['fotos']} for f in resultado['productos']],
            'donde_subirlas': 'Marketing › Fotos (busca el producto y súbele varias de una vez) o tocando la foto en '
                              'la ficha del producto.',
        }
