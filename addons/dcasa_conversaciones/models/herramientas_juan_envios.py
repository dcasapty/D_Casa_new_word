"""Juan y los envíos: cuánto cuesta el envío, sumarlo a la cotización si el cliente quiere y la promoción del mes.

Pedido de la dueña (2026-11-12): «¿Ya Juan puede hacer los cálculos y preguntar bien … cuánto cobrar por estos envíos
para añadirlos a la cotización…?». Lo acordado: Juan pide el barrio o un punto de referencia, busca el lugar en la
tabla de la calculadora, dice el precio si hay uno claro, pregunta cuál si hay varios parecidos y pasa a una vendedora
si no lo encuentra o se cotiza aparte; la fecha de entrega la sigue confirmando una vendedora. Y ella: «me parecería
bien si Juan pregunta si quiere que le sume a la cotización el envío … tienes mi sí».

* ``cotizar_envio`` (lectura): el precio de la calculadora (``dcasa_envios``: la misma tabla, la misma tarifa, el mismo
  texto de «Copiar el precio») y la promoción vigente, aplicada a la cotización de ESTA conversación si hay una. Un
  solo estado por respuesta (``precio``, ``varios``, ``no_encontrado``, ``aparte``, ``en_revision`` o ``apagado``),
  cada uno con la frase lista para el cliente y lo que el modelo tiene que hacer.
* ``agregar_envio`` (construcción): suma o reemplaza el envío en la cotización de ESTA conversación (borrador o
  enviada, nunca una venta confirmada) por el mismo camino que «Agregar envío» (``sale.order._dcasa_envio_poner``) y
  vuelve a armar el PDF como ``cotizar``.
* Ninguna cuenta la hace el modelo de IA: el precio sale del motor de la tarifa y la promoción del motor de promociones.
* Sin la tarifa aprobada por Gerencia (o con «Juan cotiza envíos» apagado en Ajustes de Juan) no hay precios: pasa a
  una vendedora.
* La dirección exacta del cliente no se guarda (issue #25): la API la quita antes de ejecutar (y de la auditoría) y
  aquí se vuelve a quitar. Juan busca con el barrio, el PH o el punto de referencia.

Los nombres de las cifras no dicen «precio» a propósito: el Worker le pone «+ ITBMS» a todo número que venga en un
campo «precio» (los de los productos). El del envío lleva ITBMS solo si el producto del transportista lo tiene, y la
frase ya lo dice.
"""
from odoo import api, models
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.addons.dcasa_envios.motor import buscador
from odoo.addons.dcasa_envios.motor import tarjeta as motor_tarjeta
from odoo.addons.dcasa_envios.motor.promocion import respaldo
from odoo.addons.dcasa_envios.motor.tarifa import Tarifa
from odoo.addons.dcasa_envios.motor.texto import dinero

from . import crm_reglas as R
from .herramientas_juan import GRUPOS, PREFIJO

MAX_LUGAR = 120
MAX_OPCIONES = 5
MAX_PARECIDOS = 3
A_VENDEDORA = 'Llama a pasar_a_vendedora y dile al cliente exactamente el texto que devuelva.'
A_VENDEDORA_SEGUIDO = 'llama a pasar_a_vendedora y dile al cliente exactamente el texto que devuelva.'
FECHA_DE_ENTREGA = 'Si pregunta qué día le llega, la fecha de entrega se la confirma una vendedora.'


def _no_sumado(motivo, mensaje, **extra):
    return {'sumado': False, 'motivo': motivo, 'instruccion': mensaje, **extra}


class BrianHerramientasJuanEnvios(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Lo común
    # ------------------------------------------------------------------

    @api.model
    def _j_envios_encendidos(self):
        """``None`` si Juan puede dar precios de envío; si no, la respuesta que corresponde (apagado o en revisión)."""
        if not self.env['dcasa.juan.ajustes'].obtener().cotizar_envios:
            return {'estado': 'apagado',
                    'frase_para_el_cliente': 'El costo del envío te lo confirma una vendedora.',
                    'instruccion': 'Los envíos los cotiza una vendedora. ' + A_VENDEDORA}
        if not self.env['dcasa.envio.tarifa'].sudo()._estado_publico()['aprobada']:
            return {'estado': 'en_revision',
                    'frase_para_el_cliente': 'El costo del envío te lo confirma una vendedora.',
                    'instruccion': 'La tarifa de envíos todavía no está aprobada por Gerencia: no des ningún precio de '
                                   'envío. ' + A_VENDEDORA + ' En el motivo pon a dónde va el envío (sin la dirección '
                                   'exacta).'}
        return None

    @api.model
    def _j_cotizacion_de_la_conversacion(self, conv, estados=('draft', 'sent')):
        """La cotización más reciente de ESTA conversación: del cliente y armada para ella (Juan o una vendedora desde
        la pantalla la crean con el origen «Conversación …»; las demás quedan ligadas a su oportunidad al mandarlas)."""
        partner = conv.partner_id.sudo()
        if not partner:
            return self.env['sale.order']
        dominio = [('partner_id', 'child_of', partner.commercial_partner_id.id), ('state', 'in', list(estados))]
        de_la_conversacion = [('origin', '=', self.env._('Conversación %s', conv.name or conv.id_externo))]
        if conv.oportunidad_id:
            de_la_conversacion = ['|', ('opportunity_id', '=', conv.oportunidad_id.id)] + de_la_conversacion
        return self.env['sale.order'].sudo().search(dominio + de_la_conversacion, order='id desc', limit=1)

    @api.model
    def _j_envio_lugar(self, lugar_id):
        if isinstance(lugar_id, str) and lugar_id.strip().isdigit():
            lugar_id = int(lugar_id.strip())
        if isinstance(lugar_id, float) and lugar_id.is_integer():
            lugar_id = int(lugar_id)
        if isinstance(lugar_id, bool) or not isinstance(lugar_id, int) or lugar_id <= 0:
            raise BrianError('«lugar_id» es el número del lugar que devolvió cotizar_envio.')
        lugar = self.env['dcasa.envio.lugar'].sudo().browse(lugar_id).exists()
        if not lugar or not lugar.active:
            raise BrianError('Ese lugar ya no está en la tabla de envíos: vuelve a buscarlo con cotizar_envio.')
        return lugar

    @api.model
    def _j_envio_tarjeta(self, lugar):
        """Lo que la calculadora muestra de ese lugar (precio, zona, chips, texto de «Copiar el precio»)."""
        tarifa = self.env['dcasa.envio.tarifa'].sudo()._vigente_motor() or Tarifa({})
        datos = lugar._como_motor()
        return dict(motor_tarjeta.tarjeta(datos, tarifa), id=lugar.id, prov=datos['prov'], dist=datos['dist'])

    @api.model
    def _j_envio_aparte(self, tarjeta):
        por_que = ', '.join(c['texto'] for c in tarjeta['chips'] if c['clase'] == 'aparte') or 'se cotiza aparte'
        return {
            'estado': 'aparte', 'lugar': {'nombre': tarjeta['nombre'], 'zona': tarjeta['zona']}, 'por_que': por_que,
            'frase_para_el_cliente': f'El envío a {tarjeta["nombre"]} se cotiza aparte: te lo confirma una vendedora.',
            'instruccion': f'Este envío no tiene precio en la tabla ({por_que}): no des ninguna cifra. {A_VENDEDORA}',
        }

    @api.model
    def _j_envio_con_promocion(self, conv, tarjeta):
        """El precio normal, la promoción (aplicada a la cotización de esta conversación si hay una) y la frase."""
        orden = self._j_cotizacion_de_la_conversacion(conv)
        compra = orden._dcasa_envio_compra() if orden else None
        resultado, promocion = self.env['dcasa.envio.promocion'].sudo()._aplicar(
            tarjeta['total'], tarjeta['prov'], tarjeta['dist'], compra)
        lleva_itbms = self.env['sale.order']._dcasa_envio_lleva_itbms()
        frase = tarjeta['texto_cliente'] + (' Al envío se le suma el ITBMS.' if lleva_itbms else '')
        if resultado['frase']:
            frase += ' ' + resultado['frase']
        datos = {
            'estado': 'precio',
            'lugar': {'lugar_id': tarjeta['id'], 'nombre': tarjeta['nombre'], 'zona': tarjeta['zona']},
            'envio_normal': tarjeta['total'], 'envio_normal_texto': tarjeta['total_txt'],
            'envio_lleva_itbms': lleva_itbms,
            'promocion': self._j_promocion_como_dict(resultado) if resultado['hay_promocion'] else None,
            'frase_para_el_cliente': frase,
            'respaldo_envio': respaldo(resultado),
        }
        return datos, orden, resultado, promocion

    @staticmethod
    def _j_promocion_como_dict(resultado):
        fila = {'nombre': resultado['nombre'], 'aplica': resultado['aplica'], 'motivo': resultado['motivo'],
                'condicional': resultado['condicional']}
        if resultado['aplica']:
            fila.update(envio_con_promocion=resultado['precio_final'],
                        envio_con_promocion_texto=dinero(resultado['precio_final']),
                        ahorro=resultado['ahorro'], ahorro_texto=dinero(resultado['ahorro']))
        if resultado['compra_medida'] is not None:
            fila['compra_medida_texto'] = dinero(resultado['compra_medida'])
        return fila

    # ------------------------------------------------------------------
    # cotizar_envio
    # ------------------------------------------------------------------

    @staticmethod
    def _j_envio_como_lo_ve(tarjeta):
        """«Inversiones Ensayo (Los Ensayos, La Chorrera)»: el lugar como se lo nombra al cliente (el corregimiento y el
        distrito, como en «Copiar el precio»), sin «Zona:» ni «(aprox.)»."""
        return motor_tarjeta.lugar_con_zona(tarjeta)

    @classmethod
    def _j_envio_grupos(cls, resultados):
        """Los encontrados juntados por lo que ve el cliente (nombre y zona): ``[(tarjeta, mismo_precio)]``.

        Dos lugares que el cliente no puede distinguir (el archivo real trae casos con el mismo nombre en la misma zona)
        son uno solo si cuestan lo mismo; si no cuestan lo mismo, ``mismo_precio`` es falso y no se puede preguntar
        cuál: se pide un punto de referencia."""
        grupos = {}
        for tarjeta in resultados:
            grupos.setdefault(cls._j_envio_como_lo_ve(tarjeta), []).append(tarjeta)
        return [(grupo[0], len({(t['con_precio'], t.get('total')) for t in grupo}) == 1) for grupo in grupos.values()]

    @api.model
    def _j_envio_claro(self, texto, grupos):
        """El lugar claro: si hay uno solo, o si uno (y solo uno) se llama exactamente como lo escribió el cliente (sin
        tildes, abreviaturas ni palabras de relleno). ``(tarjeta, mismo_precio)``, o ``(None, None)`` si hay que
        preguntar cuál."""
        if len(grupos) == 1:
            return grupos[0]
        buscado = list(dict.fromkeys(buscador.tokens(texto)))
        iguales = [g for g in grupos if buscado and list(dict.fromkeys(buscador.tokens(g[0]['nombre']))) == buscado]
        return iguales[0] if len(iguales) == 1 else (None, None)

    @herramienta(
        nombre=PREFIJO + 'cotizar_envio',
        descripcion='Cuánto cuesta el envío a donde dice el cliente (barrio, PH o punto de referencia; nunca la '
                    'dirección exacta), con la promoción vigente. Devuelve el estado, la frase para el cliente y qué '
                    'hacer. Esas cifras solo salen de aquí.',
        parametros={
            'lugar': {'type': 'string', 'description': 'A dónde va, como lo escribe el cliente: «Villa Lucre», «PH '
                                                       'Ocean Park», «cerca del hospital de Chorrera». Sin número de '
                                                       'casa, apartamento ni piso.'},
            'lugar_id': {'type': 'integer', 'description': 'Solo si el cliente eligió uno de la lista que devolvió '
                                                           'antes esta herramienta (estado «varios»): su lugar_id.'},
        },
        nivel='lectura', categoria='ventas', grupos=GRUPOS,
        ejemplos=['«¿cuánto cuesta el envío a Villa Lucre?» → cotizar_envio(lugar=Villa Lucre)',
                  'eligió «el de San Miguelito» de la lista → cotizar_envio(lugar_id=…)'],
    )
    def _juan_cotizar_envio(self, lugar=None, lugar_id=None):
        conv = self._j_conversacion()
        apagado = self._j_envios_encendidos()
        if apagado:
            return apagado
        if lugar_id is not None:
            tarjeta = self._j_envio_tarjeta(self._j_envio_lugar(lugar_id))
        else:
            texto = R.quitar_direccion_exacta(' '.join(str(lugar or '').split()))[:MAX_LUGAR]
            if not buscador.tokens(texto):
                raise BrianError('Pregúntale al cliente a dónde va el envío: el barrio, el PH o un punto de referencia '
                                 'cercano (nunca la dirección exacta).')
            datos = self.env['dcasa.envio.lugar'].sudo().buscar_para_cotizar(texto, limite=MAX_OPCIONES)
            if not datos['total']:
                return {
                    'estado': 'no_encontrado',
                    'parecidos': [s['nombre'] for s in datos['sugerencias']][:MAX_PARECIDOS],
                    'frase_para_el_cliente': f'No encontré «{texto}» en nuestra tabla de envíos. ¿Me dices un punto de '
                                             'referencia cercano, como un barrio, un PH, un súper o una iglesia?',
                    'instruccion': 'No está en la tabla. Si alguno de «parecidos» parece ser lo que quiso decir, '
                                   'pregúntale si es ese. Si no, pídele un punto de referencia cercano (nunca la '
                                   'dirección exacta) y vuelve a llamar. Si ya lo intentaste o no lo sabe, '
                                   + A_VENDEDORA_SEGUIDO,
                }
            grupos = self._j_envio_grupos(datos['resultados'])
            tarjeta, mismo_precio = self._j_envio_claro(texto, grupos)
            if tarjeta is not None and not mismo_precio:
                return {
                    'estado': 'no_encontrado', 'motivo': 'mismo_nombre', 'parecidos': [],
                    'frase_para_el_cliente': f'Hay más de un lugar llamado «{tarjeta["nombre"]}» en esa zona. '
                                             '¿Me dices un punto de referencia cercano, como un súper, una iglesia o '
                                             'un PH?',
                    'instruccion': 'Hay dos lugares con el mismo nombre y la misma zona y no cuestan lo mismo: no des '
                                   'ningún precio. Pídele un punto de referencia cercano (nunca la dirección exacta) y '
                                   'vuelve a llamar. Si no lo sabe, ' + A_VENDEDORA_SEGUIDO,
                }
            if tarjeta is None:
                opciones = [{'lugar_id': g[0]['id'], 'nombre': g[0]['nombre'], 'zona': g[0]['zona']} for g in grupos]
                nombres = '; '.join(self._j_envio_como_lo_ve(g[0]) for g in grupos)
                return {
                    'estado': 'varios', 'opciones': opciones,
                    'frase_para_el_cliente': f'Encontré varios lugares parecidos: {nombres}. ¿Cuál es el tuyo?',
                    'instruccion': 'Pregúntale cuál es (con el nombre y la zona, sin precios) y vuelve a llamar a '
                                   'cotizar_envio con el lugar_id que elija. Si no es ninguno, pídele un punto de '
                                   'referencia.',
                }
        if not tarjeta['con_precio']:
            return self._j_envio_aparte(tarjeta)
        datos, orden, resultado, _promocion = self._j_envio_con_promocion(conv, tarjeta)
        if orden:
            ya = orden.order_line.filtered(lambda linea: linea.dcasa_envio_lugar_id.id == tarjeta['id'])
            datos['cotizacion'] = {'numero': orden.name, 'envio_ya_sumado': bool(ya)}
            datos['instruccion'] = (
                'Dile al cliente la frase tal cual (puedes acortarla, sin cambiar ninguna cifra ni la condición). '
                + ('Ese envío ya está en su cotización. ' if ya else
                   'Después pregúntale: «¿Quieres que te lo sume a la cotización?». Solo si dice que sí, llama a '
                   f'agregar_envio con lugar_id={tarjeta["id"]}. ') + FECHA_DE_ENTREGA)
        else:
            datos['cotizacion'] = None
            datos['instruccion'] = (
                'Dile al cliente la frase tal cual (puedes acortarla, sin cambiar ninguna cifra ni la condición). '
                'Todavía no hay una cotización en esta conversación: si el cliente quiere cotizar, arma la cotización '
                'con cotizar y después pregúntale si le sumas el envío. La promoción solo se confirma con la compra '
                'de la cotización. ' + FECHA_DE_ENTREGA)
        if resultado['condicional'] or resultado['aplica']:
            datos['instruccion'] += ' No calcules nada: las cifras de la promoción son las de la frase.'
        return datos

    # ------------------------------------------------------------------
    # agregar_envio
    # ------------------------------------------------------------------

    @herramienta(
        nombre=PREFIJO + 'agregar_envio',
        descripcion='Suma el envío (y su promoción) a la cotización de ESTA conversación y rearma el PDF, que sale con '
                    'tu respuesta. Solo si el cliente dijo que sí, con el lugar_id de cotizar_envio. No confirma '
                    'ninguna venta.',
        parametros={'lugar_id': {'type': 'integer', 'description': 'El lugar_id que devolvió cotizar_envio.'}},
        requeridos=['lugar_id'], nivel='construccion', categoria='ventas', grupos=GRUPOS,
        ejemplos=['«sí, súmalo» (después de cotizar_envio) → agregar_envio(lugar_id=…)'],
    )
    def _juan_agregar_envio(self, lugar_id):
        conv = self._j_conversacion()
        apagado = self._j_envios_encendidos()
        if apagado:
            return dict(apagado, sumado=False, motivo=apagado['estado'])
        lugar = self._j_envio_lugar(lugar_id)
        orden = self._j_cotizacion_de_la_conversacion(conv)
        if not orden:
            if self._j_cotizacion_de_la_conversacion(conv, estados=('sale',)):
                return _no_sumado('confirmada', 'La compra de este cliente ya está confirmada: el envío lo agrega una '
                                                'vendedora. ' + A_VENDEDORA)
            return _no_sumado('sin_cotizacion', 'No hay una cotización abierta en esta conversación. Si el cliente '
                                                'quiere, ármala primero con cotizar y después suma el envío.')
        tarjeta = self._j_envio_tarjeta(lugar)
        if not tarjeta['con_precio']:
            return dict(self._j_envio_aparte(tarjeta), sumado=False, motivo='aparte')
        datos, _orden, resultado, promocion = self._j_envio_con_promocion(conv, tarjeta)
        puesto = orden._dcasa_envio_poner(lugar, tarjeta['total'], resultado, promocion)
        if not puesto['puesto']:
            if puesto['motivo'] == 'ajeno':
                return _no_sumado('ya_tiene_envio', 'Esa cotización ya tiene un envío que puso una vendedora: no lo '
                                                    'cambio. ' + A_VENDEDORA)
            if puesto['motivo'] == 'confirmada':
                return _no_sumado('confirmada', 'Esa compra ya no es una cotización abierta. ' + A_VENDEDORA)
            return _no_sumado(puesto['motivo'], 'No pude sumar el envío. ' + A_VENDEDORA)
        cotizacion = self._j_cotizacion_como_dict(orden)
        respuesta = {
            'sumado': True, 'cotizacion': cotizacion, 'respaldo_envio': datos['respaldo_envio'],
            'envio_normal_texto': datos['envio_normal_texto'], 'promocion': datos['promocion'],
            'frase_para_el_cliente': (f'Listo, te sumé el envío a la cotización {orden.name}. '
                                      f'{datos["frase_para_el_cliente"]} El total de la cotización queda en '
                                      f'{cotizacion["total_texto"]}.'),
        }
        pdf = self._j_pdf_de_cotizacion(orden)
        if not pdf:
            conv._aviso(self.env._('Juan sumó el envío a la cotización %s pero no pudo generar el PDF. Ábrela en '
                                   'Ventas y mándala a mano.', orden.name))
            return dict(respuesta, pdf_adjunto=False,
                        instruccion='Sumé el envío pero no pude preparar el PDF. Dile al cliente la frase y que una '
                                    'vendedora le manda el documento. ' + A_VENDEDORA)
        aviso = self.env._('Juan sumó el envío a %(lugar)s a la cotización %(n)s (total %(total)s) y se la manda al '
                           'cliente en PDF. Está en Ventas sin confirmar.',
                           lugar=tarjeta['nombre'], n=orden.name, total=cotizacion['total_texto'])
        respuesta['documento'] = self._j_dejar_pdf_en_el_hilo(conv, orden, pdf, cotizacion['total_texto'], aviso=aviso)
        if orden.state == 'draft':
            orden.sudo().action_quotation_sent()
        respuesta['instruccion'] = ('Dile al cliente la frase tal cual (puedes acortarla, sin cambiar ninguna cifra) y '
                                    'que el PDF va adjunto. Es una cotización: no es una venta ni reserva nada. '
                                    + FECHA_DE_ENTREGA)
        return respuesta

    @api.model
    def _j_envio_como_dict(self, orden):
        """El envío de la cotización (si tiene), sin la palabra «precio» en las claves (ver arriba)."""
        envio = orden.order_line.filtered(lambda linea: not linea.display_type and linea._dcasa_es_envio())
        if not envio:
            return None
        return {
            'lineas': [{'descripcion': linea.name.split('\n')[0], 'monto_texto': dinero(linea.price_subtotal)
                        if linea.price_subtotal >= 0 else '−' + dinero(-linea.price_subtotal)} for linea in envio],
            'total_envio_texto': dinero(sum(envio.mapped('price_subtotal'))),
        }
