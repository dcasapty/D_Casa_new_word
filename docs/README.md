# Documentación de D'CASA

Índice de todo lo que está en `docs/`. Puesto al día el 2026-10-12.

## Si eres la dueña o parte del equipo

| Quiero… | Leer |
|---|---|
| Retomar el trabajo sin empezar de cero (cómo se trabaja, qué necesita mi «sí», bitácora de sesiones) | [LEEME_PRIMERO.md](LEEME_PRIMERO.md) |
| Qué falló antes, por qué y cómo se arregló (incidentes, despliegues, CI, trampas) | [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md) |
| A qué versión segura volver si algo se rompe, y cómo | [VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md) |
| Saber qué sigue y en qué orden | [PRIORIDADES.md](PRIORIDADES.md) |
| Saber qué falta decidir o hacer yo | [PENDIENTES_DUENA.md](PENDIENTES_DUENA.md) |
| Saber cómo estaba todo el 11 de octubre, con nota y fallas (es una foto, no el estado de hoy) | [ESTADO.md](ESTADO.md) |
| Operar el sitio: costos, respaldos, qué hacer si se cae, cómo subir fotos | [OPERACION.md](OPERACION.md) |
| Usar el Escáner de códigos de barras y las etiquetas | [BARRAS.md](BARRAS.md) |
| Atender conversaciones con Juan (bandeja, traspaso a una vendedora) | [JUAN_ODOO.md](JUAN_ODOO.md) |
| Entender o vincular el WhatsApp de Juan (puente QR) y el plan B oficial | [JUAN_PUENTE.md](JUAN_PUENTE.md) · [JUAN_PLAN_B.md](JUAN_PLAN_B.md) |
| Conectar Facebook (Messenger) e Instagram a Juan | [JUAN_META.md](JUAN_META.md) |
| Activar el doble factor y la puerta del equipo | [SEGURIDAD_ACCESO.md](SEGURIDAD_ACCESO.md) |
| Usar Brian, el asistente del panel | [BRIAN.md](BRIAN.md) |
| Mandarles a los clientes su factura, su abono y la bienvenida por correo (Resend): crear la clave, dónde pegarla y cómo encenderlo | [CORREO.md](CORREO.md) |
| Saber qué ve un cliente en «Mi cuenta» (sus compras, cuánto le falta de un abono, sus puntos) | [SOCIOS.md › Mi cuenta](SOCIOS.md#mi-cuenta) |
| Crear o ubicar al equipo en Odoo (sin invitaciones por error) | [EQUIPO.md](EQUIPO.md) |
| Saber qué ve y qué no ve cada rol (vendedora, contador, Gerencia): nómina y contabilidad de un jefe | [PERMISOS.md](PERMISOS.md) |

## Por módulo (`addons/`)

| Módulo | Documento |
|---|---|
| `dcasa_base`, `dcasa_invoice` | [PLAN.md](PLAN.md) (decisiones) · roles y permisos: [PERMISOS.md](PERMISOS.md) · factura de muestra en [auditoria/ronda7/factura.md](auditoria/ronda7/factura.md) |
| `dcasa_socios` | [SOCIOS.md](SOCIOS.md) · programa de vendedores: [VENDEDORES.md](VENDEDORES.md) |
| `dcasa_mi_cuenta` | [SOCIOS.md › Mi cuenta](SOCIOS.md#mi-cuenta): el panel del cliente en `/mi-cuenta` (compras, lo que falta de cada abono, entregas, puntos y datos) |
| `dcasa_contactos` | [CONTACTOS.md](CONTACTOS.md) |
| `dcasa_catalogo` | [CATALOGO.md](CATALOGO.md) · [CATALOGO_REVISAR.md](CATALOGO_REVISAR.md) *(generado)* |
| `dcasa_barras` | [BARRAS.md](BARRAS.md) |
| `dcasa_contabilidad` | [CONTABILIDAD.md](CONTABILIDAD.md) · auditoría de los reportes (hallazgos y preguntas para la contadora): [AUDITORIA_CONTABLE.md](AUDITORIA_CONTABLE.md) · respuestas de la gerencia: [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md) |
| `dcasa_consolidacion` | [CONSOLIDACION.md](CONSOLIDACION.md) |
| `dcasa_nomina` | [NOMINA.md](NOMINA.md) |
| `dcasa_guia` | [GUIA.md](GUIA.md) · «¿Qué necesitas hacer hoy?»: atajos en palabras sencillas para quien administra |
| `dcasa_equipo` | [EQUIPO.md](EQUIPO.md) |
| `dcasa_migracion` | [MIGRACION.md](MIGRACION.md) |
| `dcasa_fe_pa` (factura electrónica, apagado) | [FACTURA_ELECTRONICA.md](FACTURA_ELECTRONICA.md) |
| `dcasa_brian` | [BRIAN.md](BRIAN.md) |
| `dcasa_correo` (correo a clientes por Resend, apagado de fábrica) | [CORREO.md](CORREO.md) |
| `dcasa_conversaciones` y el Worker `juan/` | [JUAN.md](JUAN.md) (contrato) · [JUAN_ODOO.md](JUAN_ODOO.md) · [JUAN_WORKER.md](JUAN_WORKER.md) · [CRM_AUTOMATICO.md](CRM_AUTOMATICO.md) |
| `puente-wa/` | [JUAN_PUENTE.md](JUAN_PUENTE.md) |
| `dcasa_seguridad`, `dcasa_sesiones` | [SEGURIDAD_ACCESO.md](SEGURIDAD_ACCESO.md) |
| `dcasa_adjuntos_r2`, `dcasa_tienda_borde`, `edge/`, `docker/` | [ARQUITECTURA.md](ARQUITECTURA.md) · [DESPLIEGUE.md](DESPLIEGUE.md) · [`edge/CONTRATO_CONTENEDOR.md`](../edge/CONTRATO_CONTENEDOR.md) |
| `website_dcasa`, `dcasa_interfaz` | [REDISENO.md](REDISENO.md) · [auditoria/ronda6/panel.md](auditoria/ronda6/panel.md) |

## Si programas u operas el sistema

0. [LEEME_PRIMERO.md](LEEME_PRIMERO.md) y [PRIORIDADES.md](PRIORIDADES.md): lo primero que se lee al empezar una sesión.
1. [ARQUITECTURA.md](ARQUITECTURA.md): las piezas, cómo se hablan y por qué así.
2. [DESPLIEGUE.md](DESPLIEGUE.md): CI/CD, secretos y variables, cómo se despliega y cómo se vuelve atrás.
3. [PLAN.md](PLAN.md): decisiones y en qué va cada fase.
4. Las reglas del repositorio están en [`CLAUDE.md`](../CLAUDE.md).

## Registros históricos (no se editan: se cierran con fecha)

Documentos que describen un momento. Siguen aquí porque el código y otros documentos los citan; si algo ya
cambió, la fuente de verdad es el documento vigente de arriba.

| Documento | Qué es |
|---|---|
| [auditoria/](auditoria/README.md) | Las auditorías por rondas, la bitácora y la decisión de arquitectura. |
| [AUDITORIA_UX.md](AUDITORIA_UX.md) | 100 problemas de experiencia de usuario encontrados el 2026-09-29 (la mayoría ya corregidos). |
| [REDISENO.md](REDISENO.md) | Diagnóstico y diseño del sitio v2. |
| [JUAN_PANEL.md](JUAN_PANEL.md) | Especificación de la pantalla de Conversaciones, que ya está construida (ver [JUAN_ODOO.md](JUAN_ODOO.md)). |
| [inventario-anterior-informe.md](inventario-anterior-informe.md) y su `.xlsx` | Informe de la carga del inventario del sistema anterior (lo genera `scripts/inventario_anterior_informe.py`). |
| `gerencia/` | Informes en PDF para la dueña (estado del sistema, cómo ver y probar a Juan). La fuente del primero es `fuente-informe.html`. |
| `img/` | Capturas que usa el [README](../README.md) principal. |

## Cómo se mantiene

- **Una sola fuente por tema.** Si un dato aparece en dos documentos, uno debe enlazar al otro.
- **Lo generado no se edita a mano:** `CATALOGO_REVISAR.md`, `inventario-anterior-informe.md` y `up media/RESUMEN.md` los
  escriben scripts; se corrige la fuente y se vuelve a generar.
- **Los datos de las personas** (nombres, correos y celulares del equipo y de los clientes) viven solo en Odoo, nunca aquí.
- **Cifras con fecha.** Todo número que cambia (productos, pruebas, costos) lleva su fecha o se dice dónde mirarlo.
- **Lo que se hizo y ya no se usa se cierra, no se borra:** el historial explica por qué el sistema es como es.
- Al terminar un trabajo, anotar lo que queda pendiente de la dueña en [PENDIENTES_DUENA.md](PENDIENTES_DUENA.md) y
  cerrar el issue con un comentario que diga qué se hizo y dónde está documentado.
