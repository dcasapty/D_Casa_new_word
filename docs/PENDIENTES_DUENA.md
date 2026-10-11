# Pendientes de la dueña (recordar al final de la sesión)

Decisiones que la dueña pidió dejar fuera por ahora (2026-10-03) y que se le recuerdan al cerrar:

1. **Inventario anterior — 23 precios del catálogo que cambia el inventario** (regla «el inventario
   manda»), 3 del pedido LTSC-07 (p. ej. Y0300200 $129.99 → $159.99). Lista en
   `docs/inventario-anterior-informe.md`.
2. **XXI070507**: dos productos distintos con el mismo código en el sistema anterior; entró el primero.
3. **Bases N-F10018 King y Twin**: entraron como productos aparte (códigos distintos) aunque el
   catálogo las tenía como tallas de la misma base.
4. **11 lecturas dudosas** de las capturas (columna `dudas` del CSV y el informe).
5. **Textos de la factura** (aprobados por la dueña, editables cuando quiera): se pusieron textos propuestos (garantía 30 días, cambios 7 días,
   términos); revisarlos con un abogado y ajustarlos en Ajustes → Empresas → Documentos D'CASA.
6. **Política de privacidad del sitio y el chat** (revisar con el abogado, Ley 81 de 2019): debe decir que el asistente guarda las
   conversaciones y **la foto de perfil** del cliente (reducida, solo para atenderlo, sin mandarla a la IA, se borra con la
   conversación), que lee las imágenes que manda (capturas de productos) con un servicio de IA de Cloudflare, que transcribe notas de
   voz, que a petición de una vendedora la IA resume una conversación (solo los mensajes con el cliente, nunca las notas internas), y —si se eligen modelos «contributor»— que esa IA puede entrenar con las conversaciones. La foto de perfil se apaga en
   Conversaciones › Configuración › Ajustes de Juan › Privacidad de los clientes.
7. **Buscar en el conocimiento por significado** (opcional, apagado): está construido y probado con vectores de mentira, pero **nadie ha
   visto todavía cuánto se parecen de verdad dos frases reales** con el modelo de Cloudflare. Para probarlo en staging: encender el ajuste,
   esperar una hora (o ejecutar la tarea «Juan: calcular la huella de significado del conocimiento»), preguntarle al bot algo con otras
   palabras que las de una entrada, y mirar en el registro de Odoo la línea «lo más parecido a la pregunta es … (coseno …)». Si salen
   respuestas que no vienen al caso, se sube el umbral (`UMBRAL_SIGNIFICADO`, hoy 0.6); si no encuentra nada, se baja.
8. **Plan B de WhatsApp (cuenta oficial de Meta):** empezar ya la **verificación del negocio** en Meta Business (es lo único que no se
   puede acelerar el día que se necesite). Pasos completos y qué hay que confirmar en Meta: `docs/JUAN_PLAN_B.md`.
9. **Puerta del equipo (Cloudflare Access):** staging está en modo «avisar» (2026-10-10). Falta que las 4 personas entren
   por `/master` con Google Authenticator; tras 1 o 2 días sin accesos «sin puerta» en Odoo › Accesos al panel, pasar a
   modo `"1"` (con su visto bueno) y, si se quiere, `DCASA_PUERTA_EXIGIR_CORREO`. Producción sigue sin la puerta.
10. **Nómina — lo que valida el contador** (docs/NOMINA.md, checklist): tasas de seguro social (la cuota patronal sube por
    pasos hasta 2029), seguro educativo, **riesgo profesional** (queda vacío a propósito), tramos y método del ISR, aportes
    del **décimo tercer mes** (vacíos a propósito), cuentas contables, provisión mensual del décimo, promedio de vacaciones
    y prima. Sin esa validación una planilla se calcula como borrador pero **no se confirma**. También hay que cargar las
    **fichas de los colaboradores** (salario mensual, fecha de ingreso, cédula, seguro social, cuenta bancaria).
11. **Contactos sin duplicados:** al desplegar, abrir **Socios › Configuración › Posibles duplicados** y fusionar lo que ya
    estaba repetido (el candado impide que crezca). Los puntos por WhatsApp siguen pidiendo el PIN de Socios (decisión
    de la dueña si algún día se quiere que baste el número: docs/CONTACTOS.md).
12. **Consolidación:** nada que hacer hoy (D'CASA tiene una sola empresa); cuando haya una segunda, el contador revisa el
    mapa de cuentas y lo que la guía deja como «requiere contador» (docs/CONSOLIDACION.md).
13. **Factura electrónica DGI** sigue en desarrollo (necesita elegir el PAC: docs/FACTURA_ELECTRONICA.md).
14. **Equipo:** las 7 personas ya están en Odoo (staging) como usuarios y empleados, sin invitación enviada. Falta
    (a) armar la **jerarquía** (departamentos con su gerente y superior; el campo Gerente de cada ficha; ver
    `docs/EQUIPO.md`), (b) confirmar el rol de cada quien, (c) enviar la invitación cuando alguien deba entrar (Ajustes ›
    Usuarios › Enviar correo de invitación, con su correo ya en Cloudflare Access) y (d) pasarme el **esquema de ejemplo**
    de cómo debe organizarse el alta del equipo: la pantalla de alta por texto se retiró (2026-10-11).
