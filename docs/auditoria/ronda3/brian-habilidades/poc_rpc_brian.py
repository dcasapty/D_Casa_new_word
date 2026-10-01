# ruff: noqa: F821  (`env` lo inyecta `odoo-bin shell`)
"""PoC de la superficie RPC de Brian (ronda 3, r3-brian-habilidades). Corrido el 2026-10-01.

Uso (sobre una COPIA de la base; todo termina en rollback):
    createdb -T dcasa_test r3_hab_poc
    python3 vendor/odoo/odoo-bin shell --addons-path=vendor/odoo/addons,vendor/odoo/odoo/addons,addons \
        -d r3_hab_poc --no-http < docs/auditoria/ronda3/brian-habilidades/poc_rpc_brian.py
    dropdb r3_hab_poc

`odoo.service.model.call_kw` es la misma puerta que `/web/dataset/call_kw`: rechaza métodos privados
(`_…`) y deja pasar los públicos. Resultado esperado HOY: 5 ALCANZABLE + 1 BLOQUEADO (el privado).
Tras la Fase 0, todos deben salir BLOQUEADO.
"""
import os

from odoo.service.model import call_kw

os.environ['BRIAN_API_KEY'] = 'sk-SECRETO-DE-PRUEBA'
env['ir.config_parameter'].sudo().set_param('dcasa_brian.proveedor', 'anthropic')
grupos = [env.ref('base.group_user').id, env.ref('sales_team.group_sale_salesman').id]
vendedora = env['res.users'].create({'name': 'Vendedora PoC', 'login': 'vpoc@x.pa', 'group_ids': [(6, 0, grupos)]})
venv = env(user=vendedora.id)


def prueba(nombre, modelo, metodo, args, kwargs=None):
    try:
        resultado = call_kw(venv[modelo], metodo, args, kwargs or {})
        print('ALCANZABLE', nombre, '->', str(resultado)[:160])
    except Exception as error:  # noqa: BLE001
        print('BLOQUEADO ', nombre, '->', type(error).__name__, str(error)[:120])


configuracion = call_kw(venv['brian.proveedores'], 'configuracion', [], {})
print('ALCANZABLE B-02 configuracion() -> api_key =', configuracion.get('api_key'))
prueba('B-04 ejecutar(confirmado=True) salta la confirmación', 'brian.herramientas', 'ejecutar',
       ['cancelar_cotizacion', {'venta': 'S99999'}], {'confirmado': True})
prueba('B-04 control: sin confirmado pide confirmación', 'brian.herramientas', 'ejecutar',
       ['cancelar_cotizacion', {'venta': 'S99999'}])
prueba('S-09 catalogo() del abstracto', 'brian.herramientas', 'catalogo', [])
prueba('B-03 registrar() crea auditoría falsa', 'brian.accion', 'registrar',
       [{'nombre': 'cambiar_rol_usuario', 'nivel': 'sensible', 'categoria': 'usuarios', 'descripcion': 'x'},
        {'usuario': 'Admin'}])
prueba('control: método privado _todas', 'brian.herramientas', '_todas', [])
env.cr.rollback()

# Salida obtenida el 2026-10-01 (Odoo 19, copia de dcasa_test):
#   B-02: la vendedora lee api_key = sk-SECRETO-DE-PRUEBA
#   ALCANZABLE B-04 ejecutar(confirmado=True) -> {'ok': False, 'error': 'No encontré ningún venta con «S99999»…'}
#   ALCANZABLE B-04 control -> {'ok': False, 'requiere_confirmacion': True, 'accion_id': 136, …}
#   ALCANZABLE S-09 catalogo() -> [{'name': 'buscar_productos', …}]
#   ALCANZABLE B-03 registrar() -> [137]
#   BLOQUEADO  control: _todas -> AccessError Private methods … cannot be called remotely.
