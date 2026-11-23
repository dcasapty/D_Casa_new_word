"""Brian y Marketing: «¿qué productos están más quietos esta semana?», «¿qué se movió más en el mes?», «¿qué productos
no tienen foto?», «¿qué lleva más de 90 días sin venderse y cuánto capital hay parado?» y «¿qué subió o bajó este mes
frente al anterior?».

Las mismas cifras de las pantallas Marketing, Rotación y Movimiento (``dcasa.marketing``, ``dcasa.rotacion``,
``dcasa.movimiento_productos``): nada se calcula con el modelo de IA. Solo lectura. ``movimiento_de_productos``,
``rotacion_de_inventario`` y ``comparar_movimiento`` son de Gerencia, administradores y el rol Marketing (los mismos de
la pantalla; el dinero, solo de Gerencia y administradores); ``fotos_que_faltan`` es de cualquiera que vea productos.
"""
from odoo import models
from odoo.addons.dcasa_brian.models import herramientas_comun as c
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta, normalizar
from odoo.exceptions import UserError

from .marketing import FILTROS_DE_FOTOS, GRUPOS, PERIODOS
from .movimiento import CLAVES_DE_PERIODO, CLAVES_DE_VISTA
from .rotacion import ORDENES, VISTAS

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
        descripcion='Como la pantalla Marketing: productos con más movimiento (vendido o entregado), los más quietos '
                    '(con stock, sin ventas ni entregas) y los más vendidos en la semana, 15 días o el mes. Opcional: '
                    'una categoría.',
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
        nombre='rotacion_de_inventario',
        descripcion='Rotación del inventario: productos con 30, 60, 90 o 180 días o más sin venderse, nunca '
                    'vendidos, nuevos, con pedido abierto o ancla, con sus ventas y cuántos días alcanza lo que hay. '
                    'Gerencia ve el capital parado y simula rebajas.',
        parametros={
            'grupo': {'type': 'string', 'enum': list(VISTAS),
                      'description': 'Qué ver: mas_de_30, mas_de_60, mas_de_90 (por defecto), mas_de_180 (días sin '
                                     'vender), nunca, nuevo, abierto, ancla o todos. Solo Gerencia: estrella (se '
                                     'vende bien y deja buen margen), trafico (vende mucho, deja poco), oportunidad '
                                     '(buen margen, se mueve poco) o revisar (ni se mueve ni deja margen).'},
            'categoria': {'type': 'string', 'description': 'Solo una categoría, p. ej. «Salas». Opcional.'},
            'orden': {'type': 'string', 'enum': list(ORDENES),
                      'description': 'capital, dias, rotacion, margen, cobertura o nombre. Sin dinero no hay capital '
                                     'ni margen. Por defecto, el que más capital tiene parado.'},
            'rebaja': {'type': 'number', 'description': 'Un descuento en % (1 a 95) para simular. Solo Gerencia.'},
            'limite': {'type': 'integer',
                       'description': f'Cuántos productos listar (1 a {MAX_FILAS}). Por defecto 10.'},
        },
        nivel='lectura', categoria='catalogo', grupos=(GRUPOS,),
        ejemplos=['¿qué lleva más de 90 días sin venderse? → grupo=mas_de_90',
                  '¿cuánto capital tengo parado en salas? → grupo=mas_de_90, categoria=Salas',
                  '¿cuáles son mis productos ancla? → grupo=ancla',
                  'si rebajo 20 % lo que lleva 60 días sin venderse, ¿cuánto entra? → grupo=mas_de_60, rebaja=20'],
    )
    def _h_rotacion_de_inventario(self, grupo='mas_de_90', categoria=None, orden=None, rebaja=None, limite=10):
        Rotacion = self.env['dcasa.rotacion']
        Rotacion._exigir()
        if grupo not in VISTAS:
            raise BrianError('«grupo» es mas_de_30, mas_de_60, mas_de_90, mas_de_180, nunca, nuevo, abierto, ancla, '
                             'todos o (solo Gerencia) estrella, trafico, oportunidad o revisar.')
        try:
            limite = max(1, min(int(limite or 10), MAX_FILAS))
        except (TypeError, ValueError):
            limite = 10
        tipo = self._mk_categoria(categoria)
        try:
            datos = Rotacion._datos(grupo, tipo['id'] if tipo else None, '', orden, rebaja)
        except UserError as error:
            raise BrianError(str(error)) from error
        con_dinero = datos['con_dinero']
        resumen = datos['resumen']
        respuesta = {
            'al_dia': datos['hoy'],
            'categoria': tipo['nombre'] if tipo else 'todas',
            'viendo': next((v['nombre'] for v in datos['vistas'] if v['clave'] == grupo), grupo),
            'productos_con_existencias': resumen['productos'],
            'parados_90_dias_o_mas': resumen['parados_90'],
            'productos_ancla': resumen['ancla'],
            'por_grupo': [{'grupo': t['nombre'], 'productos': t['productos'], 'unidades': c.cantidad(t['unidades']),
                           **({'capital_al_costo': t['capital']} if con_dinero else {})} for t in datos['tarjetas']],
            'en_esta_lista': datos['total'],
            'productos': [self._mk_rotacion_producto(fila, con_dinero) for fila in datos['productos'][:limite]],
            'como_se_cuenta': ' '.join(datos['como_se_cuenta'].values()),
        }
        if con_dinero:
            respuesta['capital_en_inventario'] = resumen['capital']
            respuesta['capital_parado_90_dias_o_mas'] = resumen['capital_parado_90']
            if datos.get('cortes'):
                respuesta['cortes_de_margen_y_rotacion'] = datos['cortes']['texto']
            respuesta['parte_del_capital_parada'] = resumen['parte_parada_90']
            if resumen['sin_costo']:
                respuesta['aviso'] = (f"{resumen['sin_costo']} productos con existencias no tienen costo cargado: su "
                                      f"capital no suma.")
        if datos.get('simulacion'):
            respuesta['simulacion_de_rebaja'] = datos['simulacion']
        if not datos['productos']:
            respuesta['mensaje'] = 'No hay productos con eso.'
        return respuesta

    @staticmethod
    def _mk_rotacion_producto(fila, con_dinero):
        datos = {
            'producto': fila['nombre'], 'codigo': fila['codigo'], 'categoria': fila['categoria'],
            'existencias': c.cantidad(fila['stock']),
            'ultima_venta': (c.fecha(fila['ultima_venta']) if fila['ultima_venta']
                             else 'nunca (en las facturas de Odoo)'),
            'dias_sin_vender': fila['dias_sin_vender'],
            'vendidas_30_60_90_dias': [c.cantidad(fila['vendidas_30']), c.cantidad(fila['vendidas_60']),
                                       c.cantidad(fila['vendidas_90'])],
            'alcanza_para_dias': fila['cobertura_dias'], 'ancla': fila['ancla'],
        }
        if fila['pedido_abierto']:
            datos['pedido_abierto_unidades'] = c.cantidad(fila['pedido_abierto'])
        if con_dinero:
            datos.update(capital_al_costo=fila['capital'], precio_sin_itbms=fila['precio_unitario'],
                         margen_porcentaje=fila['margen'],
                         margen_y_rotacion=fila.get('nombre_cuadrante') or 'sin costo o sin precio')
            if 'precio_rebaja' in fila:
                datos['precio_con_rebaja'] = fila['precio_rebaja']
                datos['bajo_el_costo'] = fila.get('bajo_costo', False)
        return datos

    @herramienta(
        nombre='comparar_movimiento',
        descripcion='Compara las ventas de dos periodos por producto: cuáles subieron, bajaron, se enfriaron o están '
                    'quietos, con unidades, pedidos y cuántos días alcanza lo que hay. Sirve para elegir qué anunciar. '
                    'Dinero solo para Gerencia.',
        parametros={
            'periodo': {'type': 'string', 'enum': [p for p in CLAVES_DE_PERIODO if p != 'fechas'],
                        'description': '«7», «15», «30» (por defecto), «60» o «90» días, «este_mes» o «mes_pasado».'},
            'contra': {'type': 'string', 'enum': ['anterior', 'anio'],
                       'description': 'Con qué compararlo: «anterior» (el tramo de justo antes, por defecto) o «anio» '
                                      '(el mismo tramo del año pasado).'},
            'vista': {'type': 'string', 'enum': [v for v in CLAVES_DE_VISTA],
                      'description': 'venden (por defecto), subieron, bajaron, enfriaron, quietos o todos.'},
            'categoria': {'type': 'string', 'description': 'Solo una categoría, p. ej. «Salas». Opcional.'},
            'limite': {'type': 'integer',
                       'description': f'Cuántos productos listar (1 a {MAX_FILAS}). Por defecto 10.'},
        },
        nivel='lectura', categoria='catalogo', grupos=(GRUPOS,),
        ejemplos=['¿qué subió este mes frente al mes pasado? → periodo=este_mes, vista=subieron',
                  '¿qué se enfrió en los últimos 30 días? → periodo=30, vista=enfriaron',
                  '¿qué vendíamos más el año pasado en este tramo? → contra=anio, vista=venden'],
    )
    def _h_comparar_movimiento(self, periodo='30', contra='anterior', vista='venden', categoria=None, limite=10):
        Movimiento = self.env['dcasa.movimiento_productos']
        Movimiento._exigir()
        if periodo not in CLAVES_DE_PERIODO or periodo == 'fechas':
            raise BrianError('«periodo» es 7, 15, 30, 60, 90, este_mes o mes_pasado.')
        if contra not in ('anterior', 'anio'):
            raise BrianError('«contra» es anterior o anio.')
        if vista not in CLAVES_DE_VISTA:
            raise BrianError('«vista» es venden, subieron, bajaron, enfriaron, quietos o todos.')
        try:
            limite = max(1, min(int(limite or 10), MAX_FILAS))
        except (TypeError, ValueError):
            limite = 10
        tipo = self._mk_categoria(categoria)
        try:
            datos = Movimiento._datos(periodo, contra, None, None, None, None, vista, tipo['id'] if tipo else None)
        except UserError as error:
            raise BrianError(str(error)) from error
        con_dinero = datos['con_dinero']
        resumen = datos['resumen']
        respuesta = {
            'este_periodo': f"{datos['este']['etiqueta']} ({datos['este']['dias']} días)",
            'comparado_con': f"{datos['otro']['etiqueta']} ({datos['otro']['dias']} días)",
            'categoria': tipo['nombre'] if tipo else 'todas',
            'viendo': next((v['nombre'] for v in datos['vistas'] if v['clave'] == vista), vista),
            'unidades': {'este_periodo': c.cantidad(resumen['unidades']['a']),
                         'antes': c.cantidad(resumen['unidades']['b']),
                         'cambio_porcentaje': resumen['unidades']['pct']},
            'pedidos': {'este_periodo': resumen['pedidos']['a'], 'antes': resumen['pedidos']['b'],
                        'cambio_porcentaje': resumen['pedidos']['pct']},
            'por_lista': {v['nombre']: v['productos'] for v in datos['vistas']},
            'en_esta_lista': datos['total'],
            'productos': [self._mk_movimiento_producto(fila, con_dinero) for fila in datos['productos'][:limite]],
            'como_se_cuenta': ' '.join(datos['como_se_cuenta'].values()),
        }
        if con_dinero:
            respuesta['vendido_sin_itbms'] = {'este_periodo': resumen['monto']['a'], 'antes': resumen['monto']['b'],
                                              'cambio_porcentaje': resumen['monto']['pct']}
        if resumen['sin_ventas_de_comparacion']:
            respuesta['aviso'] = 'En el periodo de comparación no hay ventas registradas: todo aparece como «Despertó».'
        if not datos['productos']:
            respuesta['mensaje'] = 'No hay productos con eso.'
        return respuesta

    @staticmethod
    def _mk_movimiento_producto(fila, con_dinero):
        datos = {
            'producto': fila['nombre'], 'codigo': fila['codigo'], 'categoria': fila['categoria'],
            'estado': fila['nombre_estado'],
            'vendidas_este_periodo': c.cantidad(fila['vendidas_este']),
            'vendidas_antes': c.cantidad(fila['vendidas_otro']),
            'cambio': c.cantidad(fila['cambio']), 'cambio_porcentaje': fila['cambio_pct'],
            'pedidos_este_periodo': fila['pedidos_este'], 'pedidos_antes': fila['pedidos_otro'],
            'existencias': c.cantidad(fila['stock']) if fila['stock'] is not None else None,
            'alcanza_para_dias': fila['cobertura_dias'], 'ancla': fila['ancla'], 'tiene_foto': fila['con_foto'],
        }
        if con_dinero:
            datos.update(vendido_este_periodo=fila['vendido_este'], vendido_antes=fila['vendido_otro'])
        return datos

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
