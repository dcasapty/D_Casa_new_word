"""Lo que Sofía propone y una persona aprueba (o descarta). Un libro: lo resuelto no se borra ni se edita por RPC.

* Cada propuesta tiene una ``clave`` («escribir:lead:12»): mientras está pendiente no se repite, y una nueva revisión la
  pone al día en vez de crear otra. Lo que alguien descartó no vuelve en unos días (Ajustes de Juan › Sofía).
* ``usuario_id`` es para quién es: cada vendedora ve SOLO las suyas (regla de registro); Gerencia las ve todas, y las
  de repartir (``solo_gerencia``) solo Gerencia.
* Nadie la escribe por RPC (el ACL es de solo lectura): la crean y la resuelven los métodos de ``dcasa.sofia``, que
  comprueban el grupo y el permiso ANTES de tocar nada.
"""
from odoo import fields, models
from odoo.addons.dcasa_conversaciones.models import crm_reglas as CRM

from . import reglas as R

TIPOS = [
    ('contestar', 'Contestarle'),
    ('vence', 'Su cotización vence'),
    ('escribir', 'Escribirle'),
    ('llamar', 'Llamarlo'),
    ('pedir_datos', 'Pedir sus datos'),
    ('guardar_correo', 'Guardar su correo'),   # antes de «Guardar sus datos»: queda en el historial
    ('guardar_datos', 'Guardar sus datos'),
    ('asignar', 'Darle una vendedora'),
    ('sincronizar', 'Poner a su vendedora en la oportunidad'),
]
NOMBRE_TIPO = dict(TIPOS)
# Cómo se agrupan en la pantalla.
GRUPO_DEL_TIPO = {
    'contestar': 'escribir', 'escribir': 'escribir', 'vence': 'mantener', 'llamar': 'mantener',
    'pedir_datos': 'datos', 'guardar_correo': 'datos', 'guardar_datos': 'datos',
    'asignar': 'repartir', 'sincronizar': 'repartir',
}
SOLO_GERENCIA = frozenset({'asignar', 'sincronizar'})
CON_MENSAJE = frozenset({'vence', 'escribir', 'pedir_datos'})
# Lo que se puede hacer con cada tipo (además de descartar).
ACCIONES = {
    'contestar': ('chat',),
    'vence': ('chat', 'enviar', 'tarea'),
    'escribir': ('chat', 'enviar', 'tarea'),
    'pedir_datos': ('chat', 'enviar'),
    'llamar': ('tarea',),
    'guardar_correo': ('guardar',),
    'guardar_datos': ('guardar',),
    'asignar': ('asignar',),
    'sincronizar': ('asignar',),
}
ESTADOS = [
    ('pendiente', 'Pendiente'),
    ('aplicada', 'Aprobada'),
    ('descartada', 'Descartada'),
    ('vencida', 'Ya no hacía falta'),
]


class SofiaPropuesta(models.Model):
    _name = 'dcasa.sofia.propuesta'
    _description = 'Propuesta de Sofía (CRM)'
    _order = 'prioridad desc, temperatura desc nulls last, id'
    _rec_name = 'titulo'

    clave = fields.Char(required=True, index=True, readonly=True)
    tipo = fields.Selection(TIPOS, 'Qué propone', required=True, readonly=True, index=True)
    estado = fields.Selection(ESTADOS, default='pendiente', required=True, readonly=True, index=True)
    prioridad = fields.Integer('Prioridad', readonly=True, help='3 = hoy sin falta, 2 = hoy, 1 = cuando puedas.')
    usuario_id = fields.Many2one('res.users', 'Para', readonly=True, index=True, ondelete='set null')
    solo_gerencia = fields.Boolean('Solo Gerencia', readonly=True)
    lead_id = fields.Many2one('crm.lead', 'Oportunidad', readonly=True, index='btree_not_null', ondelete='cascade')
    conversacion_id = fields.Many2one('dcasa.conversacion', 'Conversación', readonly=True, index='btree_not_null',
                                      ondelete='cascade')
    partner_id = fields.Many2one('res.partner', 'Cliente', readonly=True, index='btree_not_null', ondelete='cascade')
    orden_id = fields.Many2one('sale.order', 'Cotización', readonly=True, ondelete='cascade')
    destino_id = fields.Many2one('res.users', 'Dársela a', readonly=True, ondelete='cascade')
    temperatura = fields.Selection(CRM.TEMPERATURAS, 'Temperatura', readonly=True)
    titulo = fields.Char('Propuesta', readonly=True)
    motivo = fields.Char('Por qué', readonly=True)
    plantilla = fields.Char('Plantilla', readonly=True)
    pide_datos = fields.Boolean('Pide sus datos', readonly=True,
                                help='El mensaje le pide su nombre y apellido o su correo (campaña de datos).')
    datos = fields.Json('Datos', readonly=True)
    corrida_id = fields.Many2one('dcasa.sofia.corrida', 'Revisión', readonly=True, ondelete='set null')
    resuelta_por = fields.Many2one('res.users', 'Resuelta por', readonly=True, ondelete='set null')
    resuelta_en = fields.Datetime('Resuelta el', readonly=True, index='btree_not_null')
    resultado = fields.Char('Qué pasó', readonly=True)
    accion = fields.Char('Cómo se aprobó', readonly=True,
                         help='chat (abrió el chat con el mensaje), enviar, tarea, guardar o asignar.')

    _clave_pendiente_unica = models.UniqueIndex(
        "(clave) WHERE estado = 'pendiente'", 'Sofía ya tiene esa propuesta pendiente.')

    def _resolver(self, estado, resultado, usuario=None, accion=None):
        """La deja aprobada, descartada o vencida (con sudo: quien llama ya comprobó el permiso)."""
        self.sudo().write({'estado': estado, 'resultado': (resultado or '')[:300], 'resuelta_en': fields.Datetime.now(),
                           'resuelta_por': usuario.id if usuario else False, 'accion': accion or False})

    def _prioridad_nombre(self):
        return dict((int(k), v) for k, v in R.PRIORIDADES).get(self.prioridad, '')
