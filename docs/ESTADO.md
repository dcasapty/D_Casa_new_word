# Estado del sistema: evaluación y prioridades

> **Foto del 2026-10-11, no el estado de hoy.** Varias cosas cambiaron desde entonces: ya hay producción (primer
> despliegue el 2026-10-13 y varios desde entonces), el programa de vendedores, la Guía, el importador de facturas y la
> nómina están construidos. Lo vigente es [LEEME_PRIMERO.md](LEEME_PRIMERO.md) (cómo se trabaja y la bitácora de
> sesiones) y [PRIORIDADES.md](PRIORIDADES.md) (el orden de lo que sigue). Las 20 fallas de abajo sirven de lista de
> riesgos; revisar cuál sigue en pie antes de citarla.

Evaluación hecha el 2026-10-11 (con el Escáner de códigos de barras ya en staging) a partir de lo que hay
en el repositorio, las auditorías y los resultados de las pruebas. **Es un juicio, no una medición**: no
corrió una auditoría nueva y lo que dice «no vi» puede estar resuelto sin que conste aquí. Lo que se
resuelva se tacha en [PENDIENTES_DUENA.md](PENDIENTES_DUENA.md) y en los issues del repositorio.

## Nota: 68 de 100

Como código está muy bien (cerca de 85); como negocio listo para operar, todavía no (cerca de 50).
Casi nada de lo que baja la nota es un error de programación: son cosas por decidir, validar o conectar.

| Área | Nota | Por qué |
|---|---|---|
| Calidad del código y pruebas | 85 | Más de 2,100 pruebas de Odoo más las del bot y del borde; revisiones adversariales; las correcciones se prueban rompiéndolas a propósito. |
| Seguridad | 72 | Se cerró la superficie de llamadas remotas, hay puerta del equipo y doble factor, pero en producción siguen apagados. |
| Resistencia y respaldos | 65 | Respaldo continuo a R2 y simulacro de restauración en CI. Una sola máquina; la restauración con R2 real nunca se midió. |
| Funciones del negocio | 50 | Faltan la factura electrónica, los costos reales, el cobro y el inventario verificado. |
| Enfoque | 55 | Gran parte del esfuerzo fue el bot y el CRM, mientras el núcleo (facturar legalmente, costos, cobro) sigue incompleto. |

## Puntos fuertes

- Marca y sitio web respetan las reglas de D'CASA; sin precios ni cifras inventadas; ITBMS bien tratado.
- El libro de puntos de Socios no se edita y sus reglas están protegidas con pruebas.
- Respaldos automáticos y cifrados, con restauración ensayada.
- Casi todo cambio lleva su prueba; documentación en español sencillo y decisiones por escrito.
- El panel tiene puerta, doble factor y aviso por cada acceso; las acciones de Brian piden confirmación.

## Las 20 fallas más críticas

1. **Producción no tiene nada de lo nuevo.** La rama de trabajo lleva más de 200 cambios que `main` no tiene.
2. **No hay factura electrónica de la DGI** (módulo listo y apagado, sin PAC; falta confirmar la fecha con el contador).
3. **Existencias sin verificar**: salen de capturas del sistema anterior y no hay conteo físico completo.
4. **Costos y margen no confiables**; no hay ciclo de compras con valoración.
5. **No se puede cobrar con el sistema**: sin punto de venta, sin pasarela de pago, sin envío en la tienda.
6. **Una sola máquina con la base adentro**; el tiempo real de volver con R2 no se midió.
7. **Doble factor y puerta del equipo apagados en producción**; el equipo aún no entra por `/master`.
8. **WhatsApp depende de un puente no oficial**; la verificación del negocio en Meta no ha empezado.
9. **Nómina y contabilidad sin validar por el contador.**
10. **Textos legales sin abogado** (privacidad, Ley 81, garantía y cambios de la factura).
11. **Ninguna revisión humana externa** (prueba de penetración, de código, contable).
12. **Sistema grande para mantener**: el bot, el CRM y Brian son más de la mitad del código.
13. **La IA toca datos reales** (Brian escribe en el sistema, Juan habla con clientes); hay topes y confirmaciones, pero el riesgo no desaparece.
14. **Equipo sin configurar ni capacitar** (jerarquía, roles).
15. **Catálogo con decisiones pendientes** (23 precios que cambia el inventario, bases King y Twin, un código repetido).
16. **Datos heredados sin cerrar** (contactos duplicados, socios de DCasa-Referidos, facturas del sistema anterior).
17. **Sin ciclo de compras, recepción, entregas ni garantías.**
18. **Alertas de caída** dependen de una configuración opcional que no se vio puesta.
19. **Costos de nube e IA sin medir con facturas reales.**
20. **Nunca se ensayó una venta de punta a punta** (vender, cobrar, facturar, entregar, descontar stock) con personal real.

## Qué atender primero

**Esta semana** (casi nada requiere código):
1. Hablar con el contador sobre la fecha de la factura electrónica y elegir el PAC (el trámite más lento).
2. Iniciar la verificación de negocio en Meta (no se puede acelerar cuando haga falta).
3. Contar con el lector y asignar las etiquetas ([BARRAS.md](BARRAS.md)).
4. Que las personas del equipo entren por `/master` para poder pasar la puerta a modo «1».

**Siguientes 2 o 3 semanas:** cargar costos reales y proveedores; ensayar una venta de punta a punta con dos
vendedoras en staging; medir la restauración con R2 real y probar las alertas; pasar a producción por etapas,
con doble factor y puerta ya encendidos.

**Con terceros:** el contador valida nómina y contabilidad; un abogado revisa privacidad y textos de la
factura; una revisión externa de seguridad antes de abrir al público.

**Después:** pasarela de pago o punto de venta, compras y entregas, y simplificar lo que no se use.
