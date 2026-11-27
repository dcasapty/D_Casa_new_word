"""La ubicación de entrega para Juan (el asistente de clientes) y para Brian (el del equipo, también por MCP).

Juan:
* ``enlace_de_ubicacion``: el enlace de un solo uso para que la clienta marque su punto (Instagram, Messenger, o si no
  puede compartir su ubicación). Cuando lo confirma, Juan le escribe con la zona y el precio.
* ``cotizar_envio`` sin lugar: si la clienta ya tiene un punto de entrega confirmado, cotiza con ese punto.

Brian (todo el equipo; por MCP también):
* ``ubicacion_de_entrega``: el punto de entrega de una venta (zona, referencia, de dónde salió, Waze y Google Maps).
* ``enlace_de_ubicacion_para_cliente``: el mismo enlace de un solo uso, para mandarlo a mano.
* ``poner_ubicacion_de_entrega``: guarda el punto de un enlace de Google Maps o Waze (o coordenadas) que la clienta
  mandó por otro lado.

Las coordenadas nunca salen en lo que ve el modelo de IA: solo la zona y los botones.
"""
from odoo import api, models
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.addons.dcasa_conversaciones.models.herramientas_juan import GRUPOS, PREFIJO
from odoo.addons.dcasa_conversaciones.models.sale_origen import hoy_en_panama

from ..motor import enlaces_mapa, geo
from .zona import UbicacionInvalida

INTERNO = ('base.group_user',)


class BrianHerramientasUbicacion(models.AbstractModel):
    _inherit = 'brian.herramientas'

    # ------------------------------------------------------------------
    # Juan: cotizar_envio sin lugar (con el punto guardado)
    # ------------------------------------------------------------------

    @api.model
    def _j_cotizar_envio(self, lugar=None, lugar_id=None):
        sin_lugar = lugar_id is None and not (isinstance(lugar, str) and lugar.strip())
        conv = self._j_conversacion_opcional() if sin_lugar else None
        destino = conv._dcasa_ubic_destino() if conv else None
        if not conv:
            return super()._j_cotizar_envio(lugar=lugar, lugar_id=lugar_id)
        apagado = self._j_envios_encendidos()
        if apagado:
            return dict(apagado, por_ubicacion=True)
        if not destino or not destino._dcasa_ubic_punto():
            # Sin lugar y sin punto guardado no es un error (Juan lo llama primero para ofrecer «como la vez pasada»):
            # que le pida su ubicación como dice su guía para el canal.
            return {
                'estado': 'sin_ubicacion',
                'instruccion': 'Todavía no tenemos su ubicación (no es un error): pídesela como dice tu guía para este '
                               'canal o con enlace_de_ubicacion. Nunca le pidas la dirección exacta escrita.',
            }
        if not destino.dcasa_ubic_lugar_id:
            return self._j_envio_sin_lugar_cerca()
        datos = super()._j_cotizar_envio(lugar_id=destino.dcasa_ubic_lugar_id.id)
        datos['por_ubicacion'] = True
        if destino.dcasa_ubic_zona:
            datos['ubicacion_guardada'] = destino.dcasa_ubic_zona
        return datos

    # ------------------------------------------------------------------
    # Juan: enlace_de_ubicacion
    # ------------------------------------------------------------------

    @herramienta(
        nombre=PREFIJO + 'enlace_de_ubicacion',
        descripcion='Enlace de un solo uso (24 horas) para que el cliente marque su casa en un mapa. Al confirmarlo, '
                    'la tienda le escribe sola con la zona y el precio del envío: no le pidas que copie ni pegue '
                    'nada.',
        parametros={'para_otra_casa': {'type': 'boolean', 'description': 'true si el pedido va a otra persona u otro '
                                                                         'lugar (un regalo, la abuela, el trabajo), no '
                                                                         'a donde está el cliente ahora.'}},
        nivel='construccion', categoria='ventas', grupos=GRUPOS,
        ejemplos=['«¿cómo le paso mi dirección?» en Instagram → enlace_de_ubicacion()',
                  '«es para mi mamá, vive en Arraiján» → enlace_de_ubicacion(para_otra_casa=true)'],
        privado=True,
    )
    def _juan_enlace_de_ubicacion(self, para_otra_casa=False):
        conv = self._j_conversacion()
        partner = conv.partner_id.sudo()
        if not partner:
            raise BrianError('Esta conversación todavía no tiene ficha de cliente.')
        otra_casa = para_otra_casa is True or str(para_otra_casa).strip().lower() == 'true'
        # Si hoy se le avisó por el chat que su pedido sale («🚚 Sale hoy», models/avisos.py) y quiere cambiar el
        # lugar, el enlace va ligado a esa venta: el punto queda en su dirección de entrega y el equipo lo ve ahí.
        orden = None if otra_casa else self._ubic_venta_avisada_hoy(partner)
        destino = (orden.partner_shipping_id or orden.partner_id).sudo() if orden else partner
        _enlace, url = self.env['dcasa.ubicacion.enlace']._crear(destino, conversacion=conv, creado_por='juan',
                                                                  orden=orden or None, para_otra_casa=otra_casa)
        # Tres pasos con íconos (el dueño, 2026-11-25): se entiende sin leer, uno por línea (el Worker conserva así sus
        # íconos). WhatsApp muestra la vista previa con un pin en un mapa (og:image de la página). Para otra casa, «Mi
        # ubicación» marcaría donde está el teléfono: se busca la barriada o se mueve el mapa.
        paso_2 = '2️⃣ Busque la barriada o mueva el mapa hasta esa casa' if otra_casa \
            else '2️⃣ Toque «Mi ubicación» y permita'
        frase = (f'📍 Para llevárselo exacto:\n1️⃣ Abra este enlace: {url}\n{paso_2}\n'
                 '3️⃣ Escriba el número de casa y toque «Sí, aquí es»')
        datos = {
            'enlace': url,
            'vence_en_horas': 24,
            'frase_para_el_cliente': frase,
            'instruccion': 'Mándale la frase tal cual (no cambies el enlace ni los pasos). Cuando marque su punto, la '
                           'tienda le escribe sola con la zona y el precio del envío.',
        }
        if conv.canal == 'whatsapp_cloud' and not otra_casa:
            # El Worker manda además el botón nativo «Enviar ubicación» de WhatsApp (location_request_message). Para
            # otra casa no: mandaría la ubicación del teléfono.
            datos['boton_whatsapp'] = True
        return datos

    @api.model
    def _ubic_venta_avisada_hoy(self, partner):
        """La venta confirmada de esta clienta a la que hoy se le avisó por el chat que sale, o un registro vacío."""
        return self.env['sale.order'].sudo().search([
            ('state', '=', 'sale'), ('dcasa_aviso_sale_hoy_el', '=', hoy_en_panama()),
            ('dcasa_aviso_sale_hoy_por', '=', 'chat'),
            '|', ('partner_id', '=', partner.id), ('partner_shipping_id', '=', partner.id)], order='id desc', limit=1)

    # ------------------------------------------------------------------
    # Juan: guardar_indicaciones
    # ------------------------------------------------------------------

    @herramienta(
        nombre=PREFIJO + 'guardar_indicaciones',
        descripcion='Guarda el número de casa y las indicaciones para el motorizado que dio el cliente («casa 24, '
                    'portón negro, frente al súper»). Úsala apenas las diga, después de tener su ubicación.',
        parametros={'texto': {'type': 'string', 'description': 'El número de casa y las indicaciones, como las dijo '
                                                              '(hasta 200 letras).'}},
        requeridos=['texto'], nivel='construccion', categoria='ventas', grupos=GRUPOS,
        ejemplos=['«es la casa 24, la del portón negro» → guardar_indicaciones(texto=casa 24, portón negro)'],
        privado=True,
    )
    def _juan_guardar_indicaciones(self, texto):
        conv = self._j_conversacion()
        partner = conv._dcasa_ubic_destino() if conv.partner_id else conv.partner_id.sudo()
        if not partner:
            raise BrianError('Esta conversación todavía no tiene ficha de cliente.')
        limpio = geo.texto_corto(texto, geo.MAX_REFERENCIA)
        if not limpio:
            raise BrianError('Pídele al cliente el número de casa y cómo reconocer el sitio.')
        partner.write({'dcasa_referencia': limpio})
        partner._dcasa_ubic_al_dia_en_ventas()
        conv._aviso(self.env._('🏠 Indicaciones para el motorizado: %s.', limpio))
        return {
            'guardado': True, 'indicaciones': limpio,
            'instruccion': 'Confírmale en una línea que quedó anotado (sin repetir coordenadas ni datos de más).'
                           + ('' if partner._dcasa_ubic_punto() else ' Todavía no tenemos su ubicación: pídesela '
                              'con enlace_de_ubicacion.'),
        }

    # ------------------------------------------------------------------
    # Brian (equipo y MCP)
    # ------------------------------------------------------------------

    @api.model
    def _ubic_venta(self, venta):
        texto = str(venta or '').strip()
        if not texto:
            raise BrianError('Dime el número de la venta (p. ej. S00042).')
        orden = self.env['sale.order'].search([('name', '=ilike', texto)], limit=1)
        if not orden:
            raise BrianError(f'No encuentro la venta «{texto[:40]}».')
        return orden

    @api.model
    def _ubic_cliente(self, cliente):
        texto = str(cliente or '').strip()
        if not texto:
            raise BrianError('Dime el cliente (nombre, celular o correo).')
        Partner = self.env['res.partner']
        encontrados = Partner.search(['|', '|', ('name', 'ilike', texto), ('phone', 'ilike', texto),
                                      ('email', '=ilike', texto)], limit=6)
        if not encontrados:
            raise BrianError(f'No encuentro a «{texto[:40]}».')
        if len(encontrados) > 1:
            nombres = '; '.join(f'{p.name} ({p.phone or p.email or "sin contacto"})' for p in encontrados[:5])
            raise BrianError(f'Hay varios: {nombres}. Dime el celular para saber cuál.')
        return encontrados

    @herramienta(
        nombre='ubicacion_de_entrega',
        descripcion='El punto de entrega de una venta: la zona, la dirección, la referencia, de dónde salió el punto '
                    '(GPS, mapa, chat, enlace o escrita) y un botón para abrir la venta con la ruta del motorizado.',
        parametros={'venta': {'type': 'string', 'description': 'El número de la venta (p. ej. S00042).'}},
        requeridos=['venta'], nivel='lectura', categoria='ventas', grupos=INTERNO,
        ejemplos=['«¿a dónde va el pedido S00042?» → ubicacion_de_entrega(venta=S00042)'],
        privado=True, texto_externo=True,
    )
    def _brian_ubicacion_de_entrega(self, venta):
        orden = self._ubic_venta(venta)
        destino = orden.partner_shipping_id or orden.partner_id
        resumen = destino._dcasa_ubic_resumen()
        # Ni las coordenadas (van en los enlaces de Waze y Google Maps) ni el secreto de la página del motorizado van
        # al modelo de IA (auditoría 1): la persona los abre desde la venta, con el botón «Ruta del motorizado».
        resumen.pop('enlaces', None)
        resumen['venta'] = orden.name
        resumen['va_a_domicilio'] = orden._dcasa_va_a_domicilio()
        resumen['abrir'] = {'modelo': 'sale.order', 'res_id': orden.id,
                            'titulo': self.env._('Abrir %s (Ruta del motorizado)', orden.name)}
        if not resumen['tiene_punto']:
            resumen['aviso'] = 'Sin punto en el mapa: el motorizado tiene que llamar antes de salir.'
        elif not resumen['confiable']:
            resumen['aviso'] = 'El punto es aproximado: conviene confirmarlo con la clienta.'
        return resumen

    @herramienta(
        nombre='enlace_de_ubicacion_para_cliente',
        descripcion='Crea un enlace de un solo uso (vence en 24 horas) para que el cliente marque su punto de entrega '
                    'en un mapa. Es para mandarlo a mano (por WhatsApp, correo…); cuando lo marque, queda en su ficha.',
        parametros={'cliente': {'type': 'string', 'description': 'Nombre, celular o correo del cliente.'}},
        requeridos=['cliente'], nivel='construccion', categoria='ventas', grupos=INTERNO,
        ejemplos=['«mándale a Ana el enlace para que ponga su ubicación» → '
                  'enlace_de_ubicacion_para_cliente(cliente=Ana)'],
        privado=True,
    )
    def _brian_enlace_de_ubicacion_para_cliente(self, cliente):
        partner = self._ubic_cliente(cliente)
        partner.check_access('write')
        _enlace, url = self.env['dcasa.ubicacion.enlace']._crear(partner.sudo(), creado_por='equipo')
        return {'cliente': partner.name, 'enlace': url, 'vence_en_horas': 24,
                'texto_para_mandar': f'📍 Toque aquí y marque su casa en el mapa: {url}'}

    @herramienta(
        nombre='poner_ubicacion_de_entrega',
        descripcion='Guarda el punto de entrega de un cliente a partir de un enlace de Google Maps o Waze que mandó (o '
                    'de coordenadas). Deduce la zona con la tabla de envíos.',
        parametros={
            'cliente': {'type': 'string', 'description': 'Nombre, celular o correo del cliente.'},
            'enlace_mapa': {'type': 'string', 'description': 'El enlace de Google Maps, Waze o Apple Maps.'},
            'latitud': {'type': 'number', 'description': 'Solo si no hay enlace.'},
            'longitud': {'type': 'number', 'description': 'Solo si no hay enlace.'},
            'referencia': {'type': 'string', 'description': 'Cómo reconocer el sitio (opcional).'},
        },
        requeridos=['cliente'], nivel='construccion', categoria='ventas', grupos=INTERNO,
        ejemplos=['«guarda esta ubicación de Ana: https://maps.app.goo.gl/…» → poner_ubicacion_de_entrega(cliente=Ana, '
                  'enlace_mapa=…)'],
        privado=True,
    )
    def _brian_poner_ubicacion_de_entrega(self, cliente, enlace_mapa=None, latitud=None, longitud=None,
                                          referencia=None):
        partner = self._ubic_cliente(cliente)
        partner.check_access('write')
        if enlace_mapa:
            punto = enlaces_mapa.coordenadas(enlace_mapa, resolver_cortos=True)
            if not punto:
                raise BrianError('Ese enlace no trae el punto (puede ser una búsqueda por nombre). Pídele al cliente '
                                 'que comparta su ubicación o mándale el enlace de un solo uso.')
            origen = 'enlace'
        elif latitud is not None and longitud is not None:
            punto, origen = (latitud, longitud), 'pin'
        else:
            raise BrianError('Necesito el enlace del mapa o la latitud y la longitud.')
        try:
            zona = partner._dcasa_poner_ubicacion(*punto, origen, referencia=referencia, confirmada=True)
        except UbicacionInvalida as error:
            raise BrianError(str(error.args[0])) from None
        precio = self.env['dcasa.ubicacion']._precio(zona['lugar'])
        return {'cliente': partner.name, 'zona': zona['texto'] or 'sin lugar de la tabla cerca',
                'origen': geo.etiqueta(origen),
                'envio': precio['total_txt'] if precio['con_precio'] else 'por cotizar'}
