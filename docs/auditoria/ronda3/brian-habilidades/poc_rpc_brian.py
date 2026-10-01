# Se corre dentro de `odoo-bin shell`: `env` existe. Nada se confirma (rollback al final).
import os
from odoo.service.model import call_kw  # misma puerta que /web/dataset/call_kw
os.environ['BRIAN_API_KEY'] = 'sk-SECRETO-DE-PRUEBA'
env['ir.config_parameter'].sudo().set_param('dcasa_brian.proveedor', 'anthropic')
vend = env['res.users'].create({'name': 'Vendedora PoC', 'login': 'vpoc@x.pa',
    'group_ids': [(6, 0, [env.ref('base.group_user').id, env.ref('sales_team.group_sale_salesman').id])]})
venv = env(user=vend.id)
def prueba(nombre, modelo, metodo, args, kwargs=None):
    try:
        r = call_kw(venv[modelo], metodo, args, kwargs or {})
        print('ALCANZABLE', nombre, '->', str(r)[:160])
    except Exception as e:
        print('BLOQUEADO ', nombre, '->', type(e).__name__, str(e)[:120])
r = call_kw(venv['brian.proveedores'], 'configuracion', [], {}); print('B-02 api_key leída por la vendedora =', r.get('api_key'))
prueba('B-04 ejecutar(confirmado=True) salta confirmación', 'brian.herramientas', 'ejecutar', ['cancelar_cotizacion', {'venta': 'S99999'}], {'confirmado': True}); prueba('B-04 control sin confirmado', 'brian.herramientas', 'ejecutar', ['cancelar_cotizacion', {'venta': 'S99999'}])
prueba('S-09 catalogo() abstracto', 'brian.herramientas', 'catalogo', [])
acc = env['brian.accion'].sudo().search([], limit=1)
prueba('B-03 registrar() crea auditoría falsa', 'brian.accion', 'registrar', [{'nombre': 'cambiar_rol_usuario', 'nivel': 'sensible', 'categoria': 'usuarios', 'descripcion': 'x'}, {'usuario': 'Admin'}])
prueba('control: método privado _todas', 'brian.herramientas', '_todas', [])
env.cr.rollback()
