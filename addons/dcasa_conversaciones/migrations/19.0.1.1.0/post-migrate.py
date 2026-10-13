"""El CRM que se ajusta solo llega a una base que ya tiene oportunidades: esas quedan en manos de las personas.

Las oportunidades de conversaciones que ya existían las movieron (o no) las vendedoras: el CRM automático no las
adopta, porque podría archivar de golpe una que alguien sigue trabajando por teléfono. Las nuevas sí nacen
automáticas. Quien quiera que Juan maneje una vieja desmarca «Una persona tomó el control» en su ficha.
"""


def migrate(cr, version):
    # Sin temperatura quedarían de primeras en la lista (PostgreSQL pone los vacíos primero al ordenar de mayor a
    # menor): se marcan «fría» con su motivo, y la persona la cambia si quiere.
    cr.execute("""
        UPDATE crm_lead SET dcasa_auto_off = TRUE,
               dcasa_temperatura = COALESCE(dcasa_temperatura, '1'),
               dcasa_temperatura_motivo = COALESCE(dcasa_temperatura_motivo, 'la maneja una persona')
         WHERE dcasa_auto_off IS NOT TRUE
           AND id IN (SELECT oportunidad_id FROM dcasa_conversacion WHERE oportunidad_id IS NOT NULL)""")
