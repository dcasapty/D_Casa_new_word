"""Quién recibe, el teléfono de respaldo y la foto de la casa, para Juan (el asistente de clientes) y para Brian (el
del equipo, también por MCP). Lo que leen ``ubicacion_de_entrega`` (Brian) y la página del chofer sale de
``res.partner._dcasa_ubic_resumen``.

Juan:
* ``guardar_quien_recibe``: SOLO si el cliente lo dice por su cuenta («lo recibe mi mamá», «si no contesto, llamen al
  6123-4567»). No se pregunta por rutina: cada pregunta de más es fricción (el dueño, 2026-11-25). El teléfono tiene que
  estar en lo que ella escribió (un número inventado o el de la conversación no se guardan) y no vuelve al modelo.

Brian (todo el equipo; por MCP también):
* ``poner_quien_recibe``: lo mismo, cuando el cliente lo dijo por otro lado.
* ``quitar_foto_de_fachada``: quita la foto de la casa de una ficha (si el cliente lo pide o la foto no sirve).
"""
from odoo import api, models
from odoo.addons.dcasa_brian.models.registro import BrianError, herramienta
from odoo.addons.dcasa_conversaciones.models.herramientas_juan import GRUPOS, PREFIJO
from odoo.addons.dcasa_socios.models import reglas as R

from ..motor import casa

INTERNO = ('base.group_user',)
MENSAJES_DEL_CLIENTE = 40   # en cuántos de sus últimos mensajes se busca el teléfono que dijo


class BrianHerramientasCasa(models.AbstractModel):
    _inherit = 'brian.herramientas'

    @api.model
    def _casa_telefono(self, telefono):
        """El teléfono de respaldo ya leído (``casa.telefono_de_respaldo``), ``None`` si no vino, o ``BrianError``."""
        if telefono is None or not str(telefono).strip():
            return None
        numero = casa.telefono_de_respaldo(str(telefono))
        if not numero:
            raise BrianError('Ese no es un teléfono de Panamá (un celular de 8 números, como 6123-4567, o un fijo de '
                             '7, como 234-5678). Pídeselo otra vez.')
        return numero

    @api.model
    def _casa_lo_escribio_el_cliente(self, conv, numero):
        """¿Ese número está en lo que escribió el cliente en esta conversación? (Con o sin 507, guiones o espacios.)"""
        mensajes = self.env['dcasa.mensaje'].sudo().search(
            [('conversacion_id', '=', conv.id), ('autor', '=', 'cliente'), ('tipo', '=', 'mensaje')],
            order='id desc', limit=MENSAJES_DEL_CLIENTE)
        return any(numero['nacional'] in R.solo_digitos(mensaje.texto) for mensaje in mensajes)

    @api.model
    def _casa_aviso(self, recibe, numero):
        partes = []
        if recibe:
            partes.append(self.env._('👤 Recibe: %s.', recibe))
        if numero:
            partes.append(self.env._('📞 Otro teléfono para el chofer: %s.', numero['guardar']))
        return ' '.join(partes)

    # ------------------------------------------------------------------
    # Juan: guardar_quien_recibe
    # ------------------------------------------------------------------

    @herramienta(
        nombre=PREFIJO + 'guardar_quien_recibe',
        descripcion='Guarda quién recibe el pedido (si no es el cliente) y/o un teléfono de respaldo de Panamá para el '
                    'chofer. Úsala SOLO si el cliente lo dice por su cuenta; nunca lo preguntes por rutina.',
        parametros={
            'nombre': {'type': 'string', 'description': 'Quién recibe, como lo dijo (p. ej. «Rosa, mi mamá»), hasta 60 '
                                                        'letras.'},
            'telefono': {'type': 'string', 'description': 'Otro teléfono de Panamá por si no contesta, tal cual lo '
                                                          'escribió el cliente.'},
        },
        nivel='construccion', categoria='ventas', grupos=GRUPOS,
        ejemplos=['«lo recibe mi mamá Rosa» → guardar_quien_recibe(nombre=Rosa, mi mamá)',
                  '«si no contesto, llamen a mi esposo al 6123-4567» → '
                  'guardar_quien_recibe(nombre=su esposo, telefono=6123-4567)'],
        privado=True,
    )
    def _juan_guardar_quien_recibe(self, nombre=None, telefono=None):
        conv = self._j_conversacion()
        partner = conv._dcasa_ubic_destino() if conv.partner_id else conv.partner_id.sudo()
        if not partner:
            raise BrianError('Esta conversación todavía no tiene ficha de cliente.')
        recibe = casa.recibe_limpio(nombre) if isinstance(nombre, str) else ''
        numero = self._casa_telefono(telefono)
        if not recibe and not numero:
            raise BrianError('Dime quién recibe o el teléfono de respaldo, tal cual lo dijo el cliente.')
        if numero and not self._casa_lo_escribio_el_cliente(conv, numero):
            raise BrianError('Ese número no aparece en lo que escribió el cliente: guarda solo el que él dijo, tal '
                             'cual. Si no lo dijo, no lo guardes.')
        mismo = bool(numero) and casa.mismo_telefono(numero['guardar'], partner.phone or conv.id_externo or '')
        if mismo:
            numero = None
        partner._dcasa_poner_quien_recibe(recibe=recibe or None, telefono=numero['guardar'] if numero else None)
        aviso = self._casa_aviso(recibe, numero)
        if aviso:
            conv._aviso(aviso)
        instruccion = 'Confírmale en una línea que quedó anotado para el chofer (sin repetir el número).'
        if mismo:
            instruccion = ('Ese teléfono es el mismo de su ficha: no hace falta como respaldo. ' + instruccion)
        # El teléfono no vuelve al modelo: solo si quedó guardado.
        return {'guardado': True, 'recibe': recibe, 'telefono_de_respaldo': bool(numero), 'instruccion': instruccion}

    # ------------------------------------------------------------------
    # Brian (equipo y MCP)
    # ------------------------------------------------------------------

    @herramienta(
        nombre='poner_quien_recibe',
        descripcion='Guarda en la ficha del cliente quién recibe el pedido y/o un teléfono de respaldo de Panamá para '
                    'el chofer (salen en la página del QR y en el comprobante). Vacío borra ese dato.',
        parametros={
            'cliente': {'type': 'string', 'description': 'Nombre, celular o correo del cliente.'},
            'nombre': {'type': 'string', 'description': 'Quién recibe (hasta 60 letras). Vacío lo borra.'},
            'telefono': {'type': 'string', 'description': 'Otro teléfono de Panamá (6123-4567 o 234-5678). Vacío lo '
                                                          'borra.'},
        },
        requeridos=['cliente'], nivel='construccion', categoria='ventas', grupos=INTERNO,
        ejemplos=['«el pedido de Ana lo recibe su mamá Rosa, 6123-4567» → '
                  'poner_quien_recibe(cliente=Ana, nombre=Rosa (su mamá), telefono=6123-4567)'],
        privado=True,
    )
    def _brian_poner_quien_recibe(self, cliente, nombre=None, telefono=None):
        partner = self._ubic_cliente(cliente)
        partner.check_access('write')
        if nombre is None and telefono is None:
            raise BrianError('Dime quién recibe o el teléfono de respaldo (o vacío para borrarlo).')
        if telefono is not None and str(telefono).strip():
            numero = self._casa_telefono(telefono)
            telefono = numero['guardar']
        try:
            partner._dcasa_poner_quien_recibe(recibe=None if nombre is None else str(nombre),
                                              telefono=None if telefono is None else str(telefono))
        except casa.TelefonoInvalido as error:
            raise BrianError(str(error.args[0])) from None
        resumen = partner._dcasa_ubic_resumen()
        return {'cliente': partner.name, 'recibe': resumen['recibe'] or '(nadie anotado)',
                'telefono_respaldo': resumen['telefono_respaldo'] or '(ninguno)'}

    @herramienta(
        nombre='quitar_foto_de_fachada',
        descripcion='Quita la foto de la casa (la fachada para el chofer) de la ficha de un cliente, si la pide '
                    'borrar o no sirve.',
        parametros={'cliente': {'type': 'string', 'description': 'Nombre, celular o correo del cliente.'}},
        requeridos=['cliente'], nivel='construccion', categoria='clientes', grupos=INTERNO,
        ejemplos=['«borra la foto de la casa de Ana» → quitar_foto_de_fachada(cliente=Ana)'],
        privado=True,
    )
    def _brian_quitar_foto_de_fachada(self, cliente):
        partner = self._ubic_cliente(cliente)
        partner.check_access('write')
        quitada = partner._dcasa_quitar_fachada()
        return {'cliente': partner.name, 'quitada': quitada,
                'mensaje': 'Listo: ya no tiene foto de la casa.' if quitada else 'No tenía foto de la casa.'}
