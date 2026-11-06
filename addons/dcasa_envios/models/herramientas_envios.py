"""Brian y los envíos: «¿cuánto cuesta el envío a Villa Lucre?», «¿y a 34 km con peaje?».

Las mismas cifras de la calculadora (el motor de ``dcasa_envios``): nada lo calcula el modelo de IA. Solo lectura y
para todo el equipo. Mientras Gerencia no apruebe la tarifa, la respuesta lo dice («tarifa en revisión: estos precios
todavía no se usan con clientes»).
"""
from odoo import models
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta

INTERNO = ('base.group_user',)
MAX_LUGARES = 5


class BrianHerramientasEnvios(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @staticmethod
    def _envio_tarifa(estado):
        if estado['aprobada']:
            return 'aprobada por Gerencia'
        if estado['configurada']:
            return 'en revisión: estos precios todavía no se usan con clientes'
        return 'todavía no hay tarifa cargada (Gerencia la carga en Envíos › Tarifa)'

    @staticmethod
    def _envio_precio(datos):
        fila = {'total': datos['total_txt'], 'km': datos['km_txt'],
                'desglose': ', '.join(f"{d['texto']} {d['monto']}" for d in datos['desglose'])}
        if datos.get('texto_cliente'):
            fila['texto_para_el_cliente'] = datos['texto_cliente']
        return fila

    @herramienta(
        nombre='cotizar_envio',
        descripcion='Cuánto cuesta un envío desde la tienda (La Chorrera): busca el lugar como lo dice el cliente '
                    '(barrio, urbanización, PH, corregimiento o un lugar conocido) o recibe los km por carretera. '
                    'Devuelve el precio con su desglose y dice si la tarifa está aprobada o en revisión.',
        parametros={
            'lugar': {'type': 'string', 'description': 'A dónde va, como lo escribe el cliente: «Villa Lucre», '
                                                       '«cerca del hospital de Chorrera», «urb. Costa Verde».'},
            'km': {'type': 'number', 'description': 'Kilómetros por carretera desde la tienda, si ya los midieron en '
                                                    'Google Maps (en vez de «lugar»).'},
            'peaje': {'type': 'boolean', 'description': 'Con «km»: la ruta pasa por peaje.'},
            'distrito': {'type': 'string', 'description': 'Opcional, con «lugar»: solo ese distrito o provincia.'},
            'limite': {'type': 'integer', 'description': f'Con «lugar»: cuántos parecidos (1 a {MAX_LUGARES}). '
                                                         'Por defecto 3.'},
        },
        nivel='lectura', categoria='ventas', grupos=INTERNO,
        ejemplos=['¿cuánto cuesta el envío a Villa Lucre? → lugar=Villa Lucre',
                  '¿cuánto sale mandar a 34 km con peaje? → km=34, peaje=true',
                  'envío cerca del hospital de Chorrera → lugar=cerca del hospital de Chorrera'],
    )
    def _h_cotizar_envio(self, lugar=None, km=None, peaje=False, distrito=None, limite=3):
        if km is None and not (lugar or '').strip():
            raise BrianError('Dime a dónde va el envío («lugar») o los km por carretera desde la tienda («km»).')
        if km is not None:
            try:
                km = float(km)
            except (TypeError, ValueError) as error:
                raise BrianError('«km» es un número: los kilómetros por carretera desde la tienda.') from error
            datos = self.env['dcasa.envio.tarifa'].cotizar_km(km, bool(peaje))
            respuesta = {'tarifa': self._envio_tarifa(datos['tarifa'])}
            if not datos['con_precio']:
                respuesta['sin_precio'] = datos['mensaje']
                return respuesta
            respuesta.update(self._envio_precio(datos), peaje='sí' if peaje else 'no')
            if datos.get('aviso_lejos'):
                respuesta['aviso'] = datos['aviso_lejos']
            return respuesta
        try:
            limite = max(1, min(int(limite or 3), MAX_LUGARES))
        except (TypeError, ValueError):
            limite = 3
        datos = self.env['dcasa.envio.lugar'].buscar_para_cotizar(lugar, distrito=distrito, limite=limite)
        respuesta = {'tarifa': self._envio_tarifa(datos['tarifa']), 'encontrados': datos['total']}
        if not datos['total']:
            respuesta['no_encontrado'] = (f'No encontré «{lugar}». Si es un lugar nuevo, mídelo en Google Maps («Cómo '
                                          'llegar» en carro desde D\'CASA) y pásame los km, o agrégalo en Envíos › '
                                          'Calculadora.')
            if datos['sugerencias']:
                respuesta['quisiste_decir'] = [s['nombre'] for s in datos['sugerencias']]
            return respuesta
        lugares = []
        for tarjeta in datos['resultados']:
            fila = {'lugar': tarjeta['nombre'], 'zona': tarjeta['zona']}
            if tarjeta['con_precio']:
                fila.update(self._envio_precio(tarjeta))
            else:
                fila['precio'] = 'se cotiza aparte (' + ', '.join(c['texto'] for c in tarjeta['chips']
                                                                  if c['clase'] == 'aparte') + ')'
            lugares.append(fila)
        respuesta['lugares'] = lugares
        return respuesta
