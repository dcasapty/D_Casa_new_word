from . import controllers, models, report, wizard


def _dcasa_contabilidad_post_init(env):
    env['dcasa.reporte.contable']._dcasa_configurar_contabilidad()
