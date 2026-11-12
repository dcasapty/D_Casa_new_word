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
* Un lugar «Por revisar» (lo agregó alguien del equipo y Gerencia todavía no lo revisó; revisión adversarial I7) no
  tiene precio para el cliente: «el costo te lo confirma una vendedora» (estado ``aparte``) y no se suma.
* Revisión adversarial del 2026-11-12: el lugar «claro» se decide con TODAS las coincidencias, no solo con las que se
  muestran (M3); dos lugares que el cliente ve iguales y no cuestan lo mismo nunca dan un precio (I4); con más de una
  cotización abierta, ``cotizar_envio`` no mide la promoción con ninguna y ``agregar_envio`` pregunta a cuál (I6); y
  ``agregar_envio`` solo suma un lugar cuyo precio dio ``cotizar_envio`` en ESTA conversación (M5: lo dice la
  auditoría de herramientas, ``brian.accion``).
* La dirección exacta del cliente no se guarda (issue #25): la API la quita antes de ejecutar (y de la auditoría) y
  aquí se vuelve a quitar. Juan busca con el barrio, el PH o el punto de referencia.

Los nombres de las cifras no dicen «precio» a propósito: el Worker le pone «+ ITBMS» a todo número que venga en un
campo «precio» (los de los productos). El del envío lleva ITBMS solo si el producto del transportista lo tiene (con la
posición fiscal de la venta), y la frase ya lo dice. ``respaldo_envio`` (que el modelo no ve) le dice a la guardia del
Worker cada cifra del envío con su papel y su lugar (revisión adversarial I1, I2, I5, M1, M2).
"""
import json

from odoo import api, models
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.addons.dcasa_envios.motor import buscador
from odoo.addons.dcasa_envios.motor import tarjeta as motor_tarjeta
from odoo.addons.dcasa_envios.motor.promocion import con_el_precio_normal, respaldo, tiene_beneficio
from odoo.addons.dcasa_envios.motor.tarifa import Tarifa
from odoo.addons.dcasa_envios.motor.texto import dinero

from . import crm_reglas as R
from .herramientas_juan import GRUPOS, PREFIJO

MAX_LUGAR = 120
MAX_OPCIONES = 5
MAX_PARECIDOS = 3
# Para decidir si el lugar es claro se miran todas las coincidencias (hasta el máximo de la búsqueda); se muestran 5.
MAX_COINCIDENCIAS = 200
MAX_COTIZACIONES = 5
MAX_COTIZADOS = 50          # cuántas llamadas a cotizar_envio de la conversación se miran en la auditoría
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
    def _j_cotizaciones_de_la_conversacion(self, conv, estados=('draft', 'sent'), limite=None):
        """Las cotizaciones de ESTA conversación, la más reciente primero: del cliente y armadas para ella (Juan o una
        vendedora desde la pantalla las crean con el origen «Conversación …»; las demás quedan ligadas a su oportunidad
        al mandarlas)."""
        partner = conv.partner_id.sudo()
        if not partner:
            return self.env['sale.order']
        dominio = [('partner_id', 'child_of', partner.commercial_partner_id.id), ('state', 'in', list(estados))]
        de_la_conversacion = [('origin', '=', self.env._('Conversación %s', conv.name or conv.id_externo))]
        if conv.oportunidad_id:
            de_la_conversacion = ['|', ('opportunity_id', '=', conv.oportunidad_id.id)] + de_la_conversacion
        return self.env['sale.order'].sudo().search(dominio + de_la_conversacion, order='id desc', limit=limite)

    @api.model
    def _j_cotizacion_de_la_conversacion(self, conv, estados=('draft', 'sent')):
        """La cotización más reciente de ESTA conversación."""
        return self._j_cotizaciones_de_la_conversacion(conv, estados, limite=1)

    @api.model
    def _j_cotizaciones_para_preguntar(self, ordenes):
        """Las cotizaciones abiertas para que el cliente diga a cuál (número y total, como en su PDF)."""
        return [{'numero': orden.name, 'total_texto': dinero(orden.amount_total)} for orden in ordenes]

    @api.model
    def _j_envio_cotizado_en_la_conversacion(self, conv, lugar_id):
        """¿``cotizar_envio`` le dio al cliente el precio de este lugar en ESTA conversación (estado «precio»)? Lo dice
        la auditoría de herramientas (``brian.accion``), que guarda lo que devolvió cada llamada."""
        acciones = self.env['brian.accion'].sudo().search([
            ('herramienta', '=', PREFIJO + 'cotizar_envio'), ('dcasa_conversacion_id', '=', conv.id),
            ('estado', '=', 'hecha')], order='id desc', limit=MAX_COTIZADOS)
        for accion in acciones:
            try:
                datos = json.loads(accion.resultado or '{}')
            except ValueError:
                continue
            if isinstance(datos, dict) and datos.get('estado') == 'precio' \
                    and (datos.get('lugar') or {}).get('lugar_id') == lugar_id:
                return True
        return False

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
        return dict(motor_tarjeta.tarjeta(datos, tarifa), id=lugar.id, prov=datos['prov'], dist=datos['dist'],
                    corr=datos['corr'])

    @api.model
    def _j_envio_aparte(self, tarjeta):
        por_que = ', '.join(c['texto'] for c in tarjeta['chips'] if c['clase'] == 'aparte') or 'se cotiza aparte'
        return {
            'estado': 'aparte', 'motivo': 'aparte', 'lugar': {'nombre': tarjeta['nombre'], 'zona': tarjeta['zona']},
            'por_que': por_que,
            'frase_para_el_cliente': f'El envío a {tarjeta["nombre"]} se cotiza aparte: te lo confirma una vendedora.',
            'instruccion': f'Este envío no tiene precio en la tabla ({por_que}): no des ninguna cifra. {A_VENDEDORA}',
        }

    @api.model
    def _j_envio_sin_revisar(self, tarjeta):
        """Un lugar que agregó alguien del equipo y Gerencia todavía no revisó: sin precio para el cliente."""
        return {
            'estado': 'aparte', 'motivo': 'sin_revisar',
            'lugar': {'nombre': tarjeta['nombre'], 'zona': tarjeta['zona']},
            'por_que': 'lugar agregado hace poco, todavía sin revisar por Gerencia',
            'frase_para_el_cliente': f'El costo del envío a {tarjeta["nombre"]} te lo confirma una vendedora.',
            'instruccion': 'Ese lugar lo agregó hace poco alguien del equipo y Gerencia todavía no lo revisó: no des '
                           'ninguna cifra. ' + A_VENDEDORA,
        }

    @api.model
    def _j_envio_con_promocion(self, conv, tarjeta, orden=None, resultado=None):
        """El precio normal, la promoción y la frase. La promoción se aplica a la cotización de esta conversación si hay
        una (con su compra y la fecha de la cotización, como al sumar el envío); si no, con la fecha de hoy y sin compra
        (las condiciones). ``resultado``: el que ya usó ``_dcasa_envio_poner`` al sumar el envío."""
        if orden is None:
            orden = self._j_cotizacion_de_la_conversacion(conv)
        if resultado is None:
            compra = orden._dcasa_envio_compra() if orden else None
            fecha = orden._dcasa_promocion_fecha() if orden else None
            resultado, _promocion = self.env['dcasa.envio.promocion'].sudo()._aplicar(
                tarjeta['total'], tarjeta['prov'], tarjeta['dist'], compra, fecha=fecha)
        # El ITBMS del envío: el del producto del transportista con la posición fiscal de la venta (M2).
        lleva_itbms = (orden or self.env['sale.order'])._dcasa_envio_lleva_itbms()
        itbms = ' Al envío se le suma el ITBMS.' if lleva_itbms else ''
        if tiene_beneficio(resultado):
            # (1) el precio normal dicho como normal, (2) lo que D'CASA resta con la promoción, (3) hasta cuándo.
            frase = con_el_precio_normal(resultado, self._j_envio_como_lo_ve(tarjeta),
                                         self._j_envio_desglose(tarjeta) + itbms.strip())
        else:
            frase = ' '.join(p for p in (tarjeta['texto_cliente'] + itbms, resultado['frase']) if p)
        datos = {
            'estado': 'precio',
            'lugar': {'lugar_id': tarjeta['id'], 'nombre': tarjeta['nombre'], 'zona': tarjeta['zona']},
            'envio_normal': tarjeta['total'], 'envio_normal_texto': tarjeta['total_txt'],
            'envio_lleva_itbms': lleva_itbms,
            'promocion': self._j_promocion_como_dict(resultado) if resultado['hay_promocion'] else None,
            'frase_para_el_cliente': frase,
            'respaldo_envio': self._j_envio_respaldo(tarjeta, resultado, lleva_itbms),
        }
        return datos, orden, resultado

    @staticmethod
    def _j_envio_respaldo(tarjeta, resultado, lleva_itbms, total=None):
        """Lo que la guardia del Worker deja decir del envío (el modelo no lo ve): las cifras de ESTE lugar, cada una
        con su papel (ver ``motor/promocion.respaldo``), y el total de la cotización si se acaba de sumar el envío."""
        cargos = []
        if tarjeta.get('extras'):        # el desglose que dice la frase: «Tarifa $45 + peaje $5.»
            cargos = [{'nombre': 'tarifa', 'monto': tarjeta['base']}] + [
                {'nombre': c['nombre'].lower(), 'monto': c['monto']} for c in tarjeta['extras']]
        lugar = respaldo(resultado, nombres=(tarjeta['nombre'], tarjeta.get('corr'), tarjeta.get('dist')),
                         cargos=cargos, lleva_itbms=lleva_itbms)
        return {'lugares': [lugar], 'total': total}

    @staticmethod
    def _j_envio_desglose(tarjeta):
        """«Tarifa $45 + peaje $5.» si el envío tiene cargos aparte (lo mismo que dice «Copiar el precio»), o «»."""
        if not tarjeta.get('extras'):
            return ''
        cargos = ' + '.join(f"{c['nombre'].lower()} {dinero(c['monto'])}" for c in tarjeta['extras'])
        return f"Tarifa {dinero(tarjeta['base'])} + {cargos}. "

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
    def _j_envio_gemelo_con_otro_precio(self, tarjeta):
        """¿Hay otro lugar que el cliente ve igual (mismo nombre, corregimiento y distrito) y que no cuesta lo mismo?
        Entonces el cliente no puede decir cuál es y no se da ningún precio (I4)."""
        lugar = self.env['dcasa.envio.lugar'].sudo().browse(tarjeta['id'])
        patron = (lugar.name or '').replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        otros = self.env['dcasa.envio.lugar'].sudo().search(
            [('name', '=ilike', patron), ('dist', '=', lugar.dist), ('id', '!=', lugar.id)], limit=MAX_OPCIONES)
        como_lo_ve = self._j_envio_como_lo_ve(tarjeta)
        for otro in otros:
            gemela = self._j_envio_tarjeta(otro)
            if self._j_envio_como_lo_ve(gemela) == como_lo_ve and \
                    (gemela['con_precio'], gemela.get('total')) != (tarjeta['con_precio'], tarjeta.get('total')):
                return True
        return False

    @staticmethod
    def _j_envio_mismo_nombre(tarjeta):
        return {
            'estado': 'no_encontrado', 'motivo': 'mismo_nombre', 'parecidos': [],
            'frase_para_el_cliente': f'Hay más de un lugar llamado «{tarjeta["nombre"]}» en esa zona. ¿Me dices un '
                                     'punto de referencia cercano, como un súper, una iglesia o un PH?',
            'instruccion': 'Hay dos lugares con el mismo nombre y la misma zona y no cuestan lo mismo: no des ningún '
                           'precio. Pídele un punto de referencia cercano (nunca la dirección exacta) y vuelve a '
                           'llamar. Si no lo sabe, ' + A_VENDEDORA_SEGUIDO,
        }

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
            tarjeta = self._j_envio_buscar(lugar)
            if 'estado' in tarjeta:              # no encontrado, varios o dos iguales con otro precio
                return tarjeta
        sin_precio = self._j_envio_sin_precio_para_el_cliente(tarjeta)
        if sin_precio:
            return sin_precio
        abiertas = self._j_cotizaciones_de_la_conversacion(conv, limite=MAX_COTIZACIONES + 1)
        # Con más de una cotización abierta no se sabe de cuál habla el cliente: la promoción se dice con sus
        # condiciones (sin «tu compra pasa de…») y, para sumar el envío, se le pregunta a cuál (I6).
        datos, orden, resultado = self._j_envio_con_promocion(
            conv, tarjeta, orden=abiertas if len(abiertas) == 1 else abiertas.browse())
        datos.update(self._j_envio_que_sigue(tarjeta, abiertas, orden))
        if resultado['condicional'] or resultado['aplica']:
            datos['instruccion'] += ' No calcules nada: las cifras de la promoción son las de la frase.'
        return datos

    @api.model
    def _j_envio_buscar(self, lugar):
        """El lugar claro (su tarjeta) o la respuesta que toca: no encontrado, varios o dos iguales con otro precio."""
        texto = R.quitar_direccion_exacta(' '.join(str(lugar or '').split()))[:MAX_LUGAR]
        if not buscador.tokens(texto):
            raise BrianError('Pregúntale al cliente a dónde va el envío: el barrio, el PH o un punto de referencia '
                             'cercano (nunca la dirección exacta).')
        # Todas las coincidencias (M3): con solo las 5 primeras, un sexto lugar con el mismo nombre en otra zona no se
        # vería y el lugar parecería claro.
        datos = self.env['dcasa.envio.lugar'].sudo().buscar_para_cotizar(texto, limite=MAX_COINCIDENCIAS)
        if not datos['total']:
            return {
                'estado': 'no_encontrado',
                'parecidos': [s['nombre'] for s in datos['sugerencias']][:MAX_PARECIDOS],
                'frase_para_el_cliente': f'No encontré «{texto}» en nuestra tabla de envíos. ¿Me dices un punto de '
                                         'referencia cercano, como un barrio, un PH, un súper o una iglesia?',
                'instruccion': 'No está en la tabla. Si alguno de «parecidos» parece ser lo que quiso decir, '
                               'pregúntale si es ese. Si no, pídele un punto de referencia cercano (nunca la dirección '
                               'exacta) y vuelve a llamar. Si ya lo intentaste o no lo sabe, ' + A_VENDEDORA_SEGUIDO,
            }
        grupos = self._j_envio_grupos(datos['resultados'])
        completos = len(datos['resultados']) >= datos['total']
        tarjeta, mismo_precio = self._j_envio_claro(texto, grupos) if completos else (None, None)
        if tarjeta is not None:
            return tarjeta if mismo_precio else self._j_envio_mismo_nombre(tarjeta)
        # Se muestran los primeros. Dos que el cliente ve iguales son UNA opción (con el id del primero): si no cuestan
        # lo mismo, al elegirla se le pide un punto de referencia (``_j_envio_sin_precio_para_el_cliente``).
        mostrados = grupos[:MAX_OPCIONES]
        nombres = '; '.join(self._j_envio_como_lo_ve(g[0]) for g in mostrados)
        return {
            'estado': 'varios',
            'opciones': [{'lugar_id': g[0]['id'], 'nombre': g[0]['nombre'], 'zona': g[0]['zona']} for g in mostrados],
            'frase_para_el_cliente': f'Encontré varios lugares parecidos: {nombres}. ¿Cuál es el tuyo?',
            'instruccion': 'Pregúntale cuál es (con el nombre y la zona, sin precios) y vuelve a llamar a '
                           'cotizar_envio con el lugar_id que elija. Si no es ninguno, pídele un punto de referencia.',
        }

    @api.model
    def _j_envio_sin_precio_para_el_cliente(self, tarjeta):
        """``None`` si se le puede dar al cliente el precio de este lugar; si no, la respuesta: dos lugares que ve
        iguales y no cuestan lo mismo (I4), se cotiza aparte, o lo agregó el equipo y Gerencia no lo revisó (I7)."""
        if self._j_envio_gemelo_con_otro_precio(tarjeta):
            return self._j_envio_mismo_nombre(tarjeta)
        if not tarjeta['con_precio']:
            return self._j_envio_aparte(tarjeta)
        if not self.env['dcasa.envio.lugar'].sudo().browse(tarjeta['id']).revisado:
            return self._j_envio_sin_revisar(tarjeta)
        return None

    @api.model
    def _j_envio_que_sigue(self, tarjeta, abiertas, orden):
        """``{cotizacion, instruccion}`` (y ``cotizaciones`` si hay que preguntar a cuál) después de dar el precio."""
        dilo = 'Dile al cliente la frase tal cual (puedes acortarla, sin cambiar ninguna cifra ni la condición). '
        if len(abiertas) > 1:
            return {
                'cotizacion': None,
                'cotizaciones': self._j_cotizaciones_para_preguntar(abiertas[:MAX_COTIZACIONES]),
                'instruccion': dilo + 'Tiene más de una cotización abierta: la promoción se confirma con la compra '
                               'de la cotización a la que se sume el envío. Si quiere que se lo sumes, pregúntale a '
                               'cuál (con su número y su total, de «cotizaciones») y llama a agregar_envio con '
                               f'lugar_id={tarjeta["id"]} y cotizacion=<el número que elija>. ' + FECHA_DE_ENTREGA,
            }
        if orden:
            ya = orden.order_line.filtered(lambda linea: linea.dcasa_envio_lugar_id.id == tarjeta['id'])
            return {
                'cotizacion': {'numero': orden.name, 'envio_ya_sumado': bool(ya)},
                'instruccion': dilo + ('Ese envío ya está en su cotización. ' if ya else
                                       'Después pregúntale: «¿Quieres que te lo sume a la cotización?». Solo si dice '
                                       f'que sí, llama a agregar_envio con lugar_id={tarjeta["id"]}. ')
                + FECHA_DE_ENTREGA,
            }
        return {
            'cotizacion': None,
            'instruccion': dilo + 'Todavía no hay una cotización en esta conversación: si el cliente quiere '
                           'cotizar, arma la cotización con cotizar y después pregúntale si le sumas el envío. La '
                           'promoción solo se confirma con la compra de la cotización. ' + FECHA_DE_ENTREGA,
        }

    # ------------------------------------------------------------------
    # agregar_envio
    # ------------------------------------------------------------------

    @herramienta(
        nombre=PREFIJO + 'agregar_envio',
        descripcion='Suma el envío (y su promoción) a la cotización de ESTA conversación y rearma el PDF, que sale con '
                    'tu respuesta. Solo si el cliente dijo que sí, con el lugar_id de cotizar_envio. No confirma '
                    'ninguna venta.',
        parametros={
            'lugar_id': {'type': 'integer', 'description': 'El lugar_id que devolvió cotizar_envio.'},
            'cotizacion': {'type': 'string', 'description': 'Solo si tiene más de una cotización abierta: el número '
                                                            'de la que eligió el cliente (p. ej. S00042).'},
        },
        requeridos=['lugar_id'], nivel='construccion', categoria='ventas', grupos=GRUPOS,
        ejemplos=['«sí, súmalo» (después de cotizar_envio) → agregar_envio(lugar_id=…)'],
    )
    def _juan_agregar_envio(self, lugar_id, cotizacion=None):
        conv = self._j_conversacion()
        apagado = self._j_envios_encendidos()
        if apagado:
            return dict(apagado, sumado=False, motivo=apagado['estado'])
        lugar = self._j_envio_lugar(lugar_id)
        orden, no = self._j_envio_cotizacion_elegida(conv, cotizacion)
        if no:
            return no
        tarjeta = self._j_envio_tarjeta(lugar)
        sin_precio = self._j_envio_sin_precio_para_el_cliente(tarjeta)
        if sin_precio:                           # su ``motivo``: mismo_nombre, aparte o sin_revisar
            return dict(sin_precio, sumado=False)
        if not self._j_envio_cotizado_en_la_conversacion(conv, lugar.id):
            return _no_sumado('sin_cotizar_envio', 'No le has dado al cliente el precio de ese lugar: no sumé nada. '
                                                   'Llama primero a cotizar_envio con el lugar que dijo el cliente, '
                                                   'dile la frase y, si quiere, suma el envío con el lugar_id que '
                                                   'devuelva.')
        puesto = orden._dcasa_envio_poner(lugar, tarjeta['total'])
        if not puesto['puesto']:
            if puesto['motivo'] == 'ajeno':
                return _no_sumado('ya_tiene_envio', 'Esa cotización ya tiene un envío que puso una vendedora: no lo '
                                                    'cambio. ' + A_VENDEDORA)
            if puesto['motivo'] == 'confirmada':
                return _no_sumado('confirmada', 'Esa compra ya no es una cotización abierta. ' + A_VENDEDORA)
            return _no_sumado(puesto['motivo'], 'No pude sumar el envío. ' + A_VENDEDORA)
        # La frase con lo que de verdad quedó en la cotización (el mismo resultado del motor que puso las líneas).
        datos, _orden, _resultado = self._j_envio_con_promocion(conv, tarjeta, orden=orden,
                                                                resultado=puesto['resultado'])
        cotizacion = self._j_cotizacion_como_dict(orden)
        respaldo_envio = dict(datos['respaldo_envio'], total=cotizacion['total'])     # «el total queda en $X» (M1)
        respuesta = {
            'sumado': True, 'cotizacion': cotizacion, 'respaldo_envio': respaldo_envio,
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
    def _j_envio_cotizacion_elegida(self, conv, cotizacion):
        """``(orden, None)`` con la cotización abierta a la que se suma el envío, o ``(vacía, respuesta)`` si no hay,
        ya está confirmada, el número no es de las suyas o hay varias y no dijo cuál (I6)."""
        Orden = self.env['sale.order']
        abiertas = self._j_cotizaciones_de_la_conversacion(conv)
        if not abiertas:
            if self._j_cotizacion_de_la_conversacion(conv, estados=('sale',)):
                return Orden, _no_sumado('confirmada', 'La compra de este cliente ya está confirmada: el envío lo '
                                                       'agrega una vendedora. ' + A_VENDEDORA)
            return Orden, _no_sumado('sin_cotizacion', 'No hay una cotización abierta en esta conversación. Si el '
                                                       'cliente quiere, ármala primero con cotizar y después suma el '
                                                       'envío.')
        numero = ' '.join(str(cotizacion or '').split()).upper()
        if not numero and len(abiertas) == 1:
            return abiertas, None
        orden = abiertas.filtered(lambda o: (o.name or '').upper() == numero) if numero else Orden
        if orden:
            return orden, None
        cuales = self._j_cotizaciones_para_preguntar(abiertas[:MAX_COTIZACIONES])
        if numero:
            return Orden, _no_sumado('cotizacion_no_encontrada', f'«{numero}» no es una de sus cotizaciones abiertas: '
                                     'no sumé nada. Pregúntale a cuál le sumo el envío (con su número y su total, de '
                                     '«cotizaciones») y vuelve a llamar.', cotizaciones=cuales)
        return Orden, _no_sumado('cual_cotizacion', 'Tiene más de una cotización abierta y no sé a cuál sumarle el '
                                 'envío: no sumé nada. Pregúntale a cuál (con su número y su total, de «cotizaciones») '
                                 'y vuelve a llamar a agregar_envio con cotizacion=<el número que elija>.',
                                 cotizaciones=cuales)

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
