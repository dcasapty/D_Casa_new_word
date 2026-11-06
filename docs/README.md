# Documentación de D'CASA

Índice de todo lo que está en `docs/`. Puesto al día el 2026-11-06.

> **¿Vas a instalar este sistema para otro negocio?** [REPLICAR.md](REPLICAR.md): cómo instalar este sistema para otra
> empresa, con sus dos anexos: [replicar/VALORES_DE_LA_EMPRESA.md](replicar/VALORES_DE_LA_EMPRESA.md) y
> [replicar/CUENTAS_Y_SECRETOS.md](replicar/CUENTAS_Y_SECRETOS.md).

## Si eres la dueña o parte del equipo

| Quiero… | Leer |
|---|---|
| Retomar el trabajo sin empezar de cero (cómo se trabaja, qué necesita mi «sí», bitácora de sesiones) | [LEEME_PRIMERO.md](LEEME_PRIMERO.md) |
| Saber cómo está todo hoy, qué sigue y en qué orden, y **qué me falta decidir o hacer** | [PRIORIDADES.md](PRIORIDADES.md) |
| Qué falló antes, por qué y cómo se arregló (incidentes, despliegues, CI, trampas) | [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md) |
| A qué versión segura volver si algo se rompe, y cómo (ojo: las dos guardadas son viejas) | [VERSIONES_ESTABLES.md](VERSIONES_ESTABLES.md) |
| Operar el sitio: costos, respaldos, qué hacer si se cae, cómo subir fotos | [OPERACION.md](OPERACION.md) |
| Usar el Escáner de códigos de barras y las etiquetas | [BARRAS.md](BARRAS.md) |
| Dar de baja mermas, daños, muestras y regalos; ver la bitácora de bodega; encender las alertas de bodega por Telegram | [EXISTENCIAS.md](EXISTENCIAS.md) |
| Atender conversaciones con Juan: la bandeja, el reparto entre vendedoras, el CRM que se ajusta solo | [JUAN_ODOO.md](JUAN_ODOO.md) |
| Los canales de Juan: WhatsApp por la API oficial, Telegram, conectar Messenger e Instagram | [JUAN_CANALES.md](JUAN_CANALES.md) |
| Usar a Sofía, la asistente del CRM (propone a quién escribirle; una persona aprueba) | [SOFIA.md](SOFIA.md) |
| Usar Brian, el asistente del panel | [BRIAN.md](BRIAN.md) |
| La puerta del equipo `/master` (cómo comprobarla y cuándo encenderla) | [PUERTA_MASTER.md](PUERTA_MASTER.md) |
| Activar el doble factor y entender la puerta del equipo | [SEGURIDAD_ACCESO.md](SEGURIDAD_ACCESO.md) |
| El correo a los clientes (factura, abono, bienvenida) por Resend | [CORREO.md](CORREO.md) |
| Anunciar los productos en Facebook e Instagram: el catálogo que lee Meta y las campañas | [META_CATALOGO.md](META_CATALOGO.md) |
| Medir los anuncios de Meta: el píxel, las ventas que se le reportan y el consentimiento del cliente | [META_EVENTOS.md](META_EVENTOS.md) |
| Las fotos de los productos en grande y la app Marketing | [MARKETING.md](MARKETING.md) |
| Saber qué ve un cliente en «Mi cuenta» (sus compras, cuánto le falta de un abono, sus puntos) | [SOCIOS.md › Mi cuenta](SOCIOS.md#mi-cuenta) |
| Crear o ubicar al equipo en Odoo (sin invitaciones por error) | [EQUIPO.md](EQUIPO.md) |
| Saber qué ve y qué no ve cada rol (vendedora, Caja, Gerencia, Marketing, contador), los interruptores y dónde viven las políticas del sitio | [PERMISOS.md](PERMISOS.md) |
| Las reglas contables que decidió la gerencia | [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md) |
| Copiar el sistema para otra empresa | [REPLICAR.md](REPLICAR.md) |

## Por módulo (`addons/`)

`addons/` tiene **29 módulos**; el contenedor instala 28 (todos menos `dcasa_fe_pa`, a propósito). Resumen de cada uno
(para qué, dependencias, modelos, menús, herramientas de Brian, qué viene apagado): [MODULOS.md](MODULOS.md).

| Módulo | Documento |
|---|---|
| `dcasa_base`, `dcasa_invoice` | Roles y permisos: [PERMISOS.md](PERMISOS.md) · decisiones de fondo: [ARQUITECTURA.md](ARQUITECTURA.md#decisiones-de-fondo) · factura de muestra en [auditoria/ronda7/factura.md](auditoria/ronda7/factura.md) |
| `dcasa_abonos` | [MODULOS.md](MODULOS.md#dcasa_abonos--condiciones-de-abono) · reglas del abono: [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md) |
| `dcasa_socios` | [SOCIOS.md](SOCIOS.md) · programa de vendedores: [VENDEDORES.md](VENDEDORES.md) |
| `dcasa_mi_cuenta` | [SOCIOS.md › Mi cuenta](SOCIOS.md#mi-cuenta): el panel del cliente en `/mi-cuenta` |
| `dcasa_contactos` | [CONTACTOS.md](CONTACTOS.md) |
| `dcasa_catalogo` | [CATALOGO.md](CATALOGO.md) · [CATALOGO_REVISAR.md](CATALOGO_REVISAR.md) *(generado)* |
| `dcasa_barras` | [BARRAS.md](BARRAS.md) |
| `dcasa_existencias` | [EXISTENCIAS.md](EXISTENCIAS.md) |
| `dcasa_contabilidad` | [CONTABILIDAD.md](CONTABILIDAD.md) · respuestas de la gerencia: [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md) · preguntas abiertas para la contadora: [PRIORIDADES.md](PRIORIDADES.md#para-la-contadora-y-la-gerencia) · auditoría de los reportes (registro): [historico/AUDITORIA_CONTABLE.md](historico/AUDITORIA_CONTABLE.md) |
| `dcasa_consolidacion` | [CONSOLIDACION.md](CONSOLIDACION.md) |
| `dcasa_nomina` | [NOMINA.md](NOMINA.md) |
| `dcasa_guia` | [GUIA.md](GUIA.md) · «¿Qué necesitas hacer hoy?»: atajos en palabras sencillas para quien administra |
| `dcasa_marketing` | [MARKETING.md](MARKETING.md) |
| `dcasa_equipo` | [EQUIPO.md](EQUIPO.md) |
| `dcasa_migracion` | [MIGRACION.md](MIGRACION.md) |
| `dcasa_fe_pa` (factura electrónica, apagado y sin instalar) | [FACTURA_ELECTRONICA.md](FACTURA_ELECTRONICA.md) |
| `dcasa_brian` | [BRIAN.md](BRIAN.md) |
| `dcasa_correo` (correo a clientes por Resend; encendido en producción desde el 2026-10-27) | [CORREO.md](CORREO.md) |
| `dcasa_meta_catalogo` (catálogo para Meta por URL, apagado de fábrica) | [META_CATALOGO.md](META_CATALOGO.md) |
| `dcasa_meta_eventos` (píxel y Conversions API de Meta, apagados de fábrica) | [META_EVENTOS.md](META_EVENTOS.md) |
| `dcasa_conversaciones` y el Worker `juan/` | [JUAN.md](JUAN.md) (contrato y el Worker por dentro) · [JUAN_ODOO.md](JUAN_ODOO.md) (bandeja, reparto, CRM) · [JUAN_CANALES.md](JUAN_CANALES.md) (canales) |
| `dcasa_sofia` (Sofía, la asistente del CRM) | [SOFIA.md](SOFIA.md) |
| `puente-wa/` (WhatsApp por QR, nunca desplegado) | [JUAN_PUENTE.md](JUAN_PUENTE.md) · [JUAN_CANALES.md](JUAN_CANALES.md#4-el-puente-de-whatsapp-por-qr-no-se-usa-en-producción) |
| `dcasa_seguridad`, `dcasa_sesiones` | [SEGURIDAD_ACCESO.md](SEGURIDAD_ACCESO.md) · [PUERTA_MASTER.md](PUERTA_MASTER.md) |
| `dcasa_adjuntos_r2`, `dcasa_tienda_borde`, `edge/`, `docker/` | [ARQUITECTURA.md](ARQUITECTURA.md) · [DESPLIEGUE.md](DESPLIEGUE.md) · [`edge/CONTRATO_CONTENEDOR.md`](../edge/CONTRATO_CONTENEDOR.md) |
| `website_dcasa`, `dcasa_interfaz` | [OPERACION.md › El sitio se edita por código](OPERACION.md#el-sitio-se-edita-por-código) · [auditoria/ronda6/panel.md](auditoria/ronda6/panel.md) · diseño del sitio (registro): [historico/REDISENO.md](historico/REDISENO.md) |

## Si programas u operas el sistema

0. [LEEME_PRIMERO.md](LEEME_PRIMERO.md) y [PRIORIDADES.md](PRIORIDADES.md): lo primero que se lee al empezar una sesión.
1. [ARQUITECTURA.md](ARQUITECTURA.md): las decisiones de fondo, cada pieza de Cloudflare (Workers, Containers, Durable
   Objects, KV, R2), sus tablas, la base de Odoo, las variables y secretos por entorno y los flujos de despliegue.
2. [MODULOS.md](MODULOS.md): cada módulo de `addons/`.
3. [PERMISOS.md](PERMISOS.md): roles, interruptores, superficie RPC, privacidad y políticas del sitio.
4. [DESPLIEGUE.md](DESPLIEGUE.md): **la receta de producción** (la única), CI/CD, secretos y variables, cómo se vuelve
   atrás. Antes de desplegar: [CONTEXTO_AGENTICO.md](CONTEXTO_AGENTICO.md).
5. [JUAN.md](JUAN.md): el contrato de Juan con Odoo y cómo funciona su Worker.
6. [REPLICAR.md](REPLICAR.md): instalar el sistema para otra empresa, de punta a punta.
7. Las reglas del repositorio están en [`CLAUDE.md`](../CLAUDE.md); la portada, en el [README](../README.md).

## Registros históricos (no se editan: se cierran con fecha)

Documentos que describen un momento. Siguen en el repositorio porque el código y otros documentos los citan; si algo ya
cambió, la fuente de verdad es el documento vigente de arriba.

| Documento | Qué es |
|---|---|
| [historico/](historico/README.md) | Lo archivado el 2026-11-06: la bitácora vieja, la lista vieja de pendientes de la dueña, el plan, la foto del 11 de octubre, el traslado del dominio, las auditorías contable y de experiencia de usuario, el rediseño del sitio y los documentos de Juan que se unieron (Worker, panel, CRM automático, plan B, Meta). Cada uno con su aviso y adónde pasó lo vigente. |
| [auditoria/](auditoria/README.md) | Las auditorías por rondas, su bitácora y la decisión de arquitectura. |
| `gerencia/` | Informes en PDF para la dueña (estado del sistema, cómo ver y probar a Juan) de octubre de 2026. La fuente del primero es `fuente-informe.html`. |
| [inventario-anterior-informe.md](inventario-anterior-informe.md) y su `.xlsx` | Informe de la carga del inventario del sistema anterior (lo genera `scripts/inventario_anterior_informe.py`). |
| `img/` | Capturas que usa el [README](../README.md) principal. |

## Cómo se mantiene

- **Una sola fuente por tema.** Si un dato aparece en dos documentos, uno debe enlazar al otro (la receta de producción
  vive solo en DESPLIEGUE.md; el estado del día, solo en PRIORIDADES.md).
- **Lo generado no se edita a mano:** `CATALOGO_REVISAR.md`, `inventario-anterior-informe.md` y `up media/RESUMEN.md` los
  escriben scripts; se corrige la fuente y se vuelve a generar.
- **Los datos de las personas** (nombres, correos y celulares del equipo y de los clientes) viven solo en Odoo, nunca aquí.
  El repositorio es público.
- **Cifras con fecha.** Todo número que cambia (productos, pruebas, costos, tiempos) lleva su fecha o se dice dónde mirarlo.
- **Lo que se hizo y ya no se usa se archiva, no se borra:** va a [historico/](historico/README.md) con `git mv` y un aviso.
- Al terminar un trabajo, anotar lo que queda pendiente de la dueña en [PRIORIDADES.md › Lo que falta de la
  dueña](PRIORIDADES.md#lo-que-falta-de-la-dueña) y cerrar el issue con un comentario que diga qué se hizo y dónde está
  documentado.
