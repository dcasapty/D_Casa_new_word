"""Prueba de humo del arranque (incidente del 2026-10-16, #97).

Producción quedó con el código nuevo sobre la base sin actualizar: Odoo contestaba y el despliegue dijo «sano», pero el
Inicio, las cotizaciones y las conversaciones fallaban con ``column sale_order.dcasa_utilidad does not exist``. Esta
revisión lo detecta sin depender de números de versión:

* **Columnas:** cada campo guardado del código tiene su columna en la base. Si falta alguna, el arranque
  (``docker/entrypoint.sh``) vuelve a actualizar los módulos y revisa otra vez.
* **Pantallas:** se arma el Inicio de verdad y se leen las columnas de las listas de cotizaciones y conversaciones,
  como el administrador (solo lo que la lista muestra: no las firmas ni las fotos, que viven en R2).

El resultado queda en ``dcasa.humo`` (JSON); ``/dcasa/salud`` lo informa y el despliegue exige ``ok``. Solo lee: lo
que arman las pantallas se descarta (savepoint).
"""
import json
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

PARAM_HUMO = 'dcasa.humo'
MAXIMO_EN_EL_INFORME = 20


class _Descartar(Exception):
    """Para deshacer lo que arme una pantalla de prueba."""


class DcasaHumo(models.AbstractModel):
    _name = 'dcasa.humo'
    _description = 'Prueba de humo del arranque'

    @api.model
    def _columnas_faltantes(self):
        """``modelo.campo`` de cada campo guardado sin columna en la base (vacío si todo coincide)."""
        return [nombre for nombre, _modulo in self._campos_sin_columna()]

    @api.model
    def _modulos_de(self, faltantes):
        """Los módulos que definen esos campos: el arranque los actualiza aunque no sean de D'CASA (p. ej. tras
        cambiar la versión de Odoo, ``-u dcasa_*`` no crea una columna nueva de ``sale``)."""
        return sorted({modulo for _nombre, modulo in faltantes if modulo})

    @api.model
    def _campos_sin_columna(self):
        """``(modelo.campo, módulo que lo define)`` de cada campo guardado sin columna en la base."""
        self.env.cr.execute("""
            SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = current_schema()
        """)
        columnas = set(self.env.cr.fetchall())
        faltan = []
        for nombre in sorted(self.env.registry):
            modelo = self.env[nombre]
            if modelo._abstract or not modelo._auto:
                continue
            for campo in modelo._fields.values():
                if campo.store and campo.column_type and (modelo._table, campo.name) not in columnas:
                    faltan.append((f'{nombre}.{campo.name}', campo._module))
        return faltan

    @api.model
    def _pruebas_de_pantallas(self):
        pruebas = []
        if 'dcasa.tablero' in self.env:
            pruebas.append(('Inicio', lambda env: env['dcasa.tablero'].obtener_datos()))
        pruebas.append(('Cotizaciones', lambda env: self._leer_la_lista(env, 'sale.order')))
        if 'dcasa.conversacion' in self.env:
            pruebas.append(('Conversaciones', lambda env: self._leer_la_lista(env, 'dcasa.conversacion')))
        return pruebas

    @api.model
    def _leer_la_lista(self, env, modelo):
        """Lo que muestra la lista de ``modelo``: sus columnas, de los 5 primeros registros."""
        Modelo = env[modelo]
        vista = Modelo.get_views([(False, 'list')])
        campos = [campo for campo in vista['models'].get(modelo, {}).get('fields', {}) if campo in Modelo._fields]
        return Modelo.search_read([], campos or ['display_name'], limit=5)

    @api.model
    def _pantallas(self):
        """Los errores de las pantallas principales armadas como el administrador (vacío si todas abren)."""
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        env = self.env(user=admin.id) if admin else self.env
        errores = []
        for nombre, prueba in self._pruebas_de_pantallas():
            try:
                with self.env.cr.savepoint():
                    prueba(env)
                    env.flush_all()
                    raise _Descartar
            except _Descartar:
                pass
            except Exception as error:  # noqa: BLE001 - se informa: es lo que la prueba busca
                primera = (str(error).splitlines() or [''])[0]
                errores.append(f'{nombre}: {type(error).__name__}: {primera[:200]}')
            finally:
                env.invalidate_all()
        return errores

    @api.model
    def _revisar(self):
        """Corre la prueba, guarda el resultado en ``dcasa.humo`` y lo devuelve."""
        sin_columna = self._campos_sin_columna()
        faltan = [nombre for nombre, _modulo in sin_columna]
        # Con columnas faltantes las pantallas fallan seguro: primero se actualiza la base.
        errores = [] if faltan else self._pantallas()
        resultado = {
            'ok': not faltan and not errores,
            'columnas_faltantes': faltan[:MAXIMO_EN_EL_INFORME],
            'modulos': self._modulos_de(sin_columna),
            'errores': errores[:MAXIMO_EN_EL_INFORME],
        }
        if not resultado['ok']:
            # warning y no error: las pruebas de Odoo cuentan cada error del log como falla; el arranque lo
            # imprime igual con ✖ y el despliegue no lo da por sano.
            _logger.warning('DCASA_HUMO con problemas: %s', json.dumps(resultado, ensure_ascii=False))
        self.env['ir.config_parameter'].sudo().set_param(PARAM_HUMO, json.dumps(resultado, ensure_ascii=False))
        return resultado
