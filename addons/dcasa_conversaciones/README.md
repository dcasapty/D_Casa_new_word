# D'CASA Panamá — Conversaciones (bandeja de Juan)

La parte de Odoo de **Juan**, el asistente que atiende a los clientes por WhatsApp, Telegram, Messenger e Instagram
con el nombre público «el equipo de D'CASA». El contrato completo con el Worker `juan` está en
[`docs/JUAN.md`](../../docs/JUAN.md); la guía para la dueña, en [`docs/JUAN_ODOO.md`](../../docs/JUAN_ODOO.md).

## Qué trae

| Pieza | Dónde |
|---|---|
| Conversaciones y mensajes (idempotentes por `id_mensaje`) | `models/conversacion.py`, `models/mensaje.py` |
| Ficha del cliente (celular = llave, sin duplicar) | `models/res_partner.py`, `models/celulares.py` |
| Ajustes que edita la dueña (un solo registro) | `models/ajustes.py` |
| API `/dcasa/juan/v1/*` para el Worker | `controllers/juan.py` |
| Herramientas del asistente (vista pública) en el registro de Brian | `models/herramientas_juan.py`, `models/brian_juan.py` |
| Horario de Panamá y fechas de seguimiento (funciones puras) | `models/horario.py` |
| Reglas de Socios para el cliente (solo desde `puntos.json`) | `models/reglas_clientes.py` |
| Odoo → Worker (enviar, tomar/devolver, seguimiento) | `models/cliente_worker.py` |
| Bandeja: kanban, lista, formulario-chat, ajustes | `views/`, `static/src/scss/chat.scss` |
| Base de conocimiento, preguntas sin respuesta y lecciones | `models/conocimiento.py`, `models/conocimiento_texto.py`, `data/conocimiento_data.xml` |
| Etiquetas, respuestas rápidas y lectura por persona (sin leer) | `models/etiquetas.py`, `data/etiquetas_data.xml` |
| API de la pantalla «Conversaciones» (lista, hilo, ficha, enviar…) | `models/conversacion_panel.py` |
| Pantalla OWL «Conversaciones» (lista, chat, ficha, caja, catálogo, cotización) | `static/src/js`, `static/src/xml`, `static/src/scss/panel.scss` |
| Resumen, Costos de IA y Conexiones (acciones de cliente) | `models/panel_juan.py`, `models/panel_calculos.py`, `models/cliente_worker_panel.py`, `static/src/js/{resumen,costos,conexiones}.js` |
| Subir adjuntos, sugerir respuesta, catálogo y cotización para la pantalla | `models/conversacion_panel_extra.py`, `models/conversacion_panel_catalogo.py` |
| Adjuntos con URL firmada de vida corta | `models/firma.py`, `controllers/adjuntos.py` |
| Datos de la tienda (dirección, horario, WhatsApp) | `models/tienda.py` |

## Reglas que no se rompen

* El usuario técnico `juan` es de **portal**, con el grupo propio `group_juan` y **sin** ningún grupo interno ni contraseña.
  Sus herramientas llevan el prefijo `juan_` en Brian y se publican sin él (`buscar_productos`, …).
* Solo productos **publicados**; existencias **solo como etiqueta** (`disponible`/`pocas`/`agotado`); precio **«+ ITBMS»**; nada de costos.
* Ninguna herramienta escribe puntos, precios, stock, facturas ni pagos, ni lee datos de otros clientes: el cliente sale
  de la conversación (`juan_conversacion_id`), nunca de un argumento.
* Cifras de Socios **solo** de `dcasa_socios/data/puntos.json`; un `null`/`PENDIENTE` no se rellena.
* **Secretos**: `JUAN_ODOO_TOKEN` y `JUAN_WORKER_TOKEN` se leen de variables de entorno del contenedor (o, como
  alternativa, de un parámetro del sistema). Nunca están en el repositorio, ni en un registro, ni en la pantalla.
  `JUAN_URL` (no secreta) o el parámetro `dcasa_conversaciones.juan_url` dicen dónde está el Worker `juan`.
  Sin `JUAN_ODOO_TOKEN` (de 32 caracteres o más) la API responde **503**.

* **El bus no lleva texto**: los avisos a las pantallas (`dcasa_conversaciones/evento`) llevan solo ids y estado.
* **Adjuntos**: el puente los baja con una URL firmada (HMAC con `database.secret`) que vale 15 minutos y deja de valer si el
  archivo cambia; solo sirve adjuntos de mensajes de conversaciones.
* **Las claves de la IA no se guardan en Odoo** (viven en el Worker `juan`); Odoo solo guarda proveedor, modelos y precios
  (los precios van vacíos: no se inventa ninguno). Un modelo con «contributor» en el nombre avisa en los ajustes.
* **Etiquetas**: el asistente solo pone las que ya existen; no crea etiquetas.

## La pantalla (panel)

La pantalla de [`docs/JUAN_PANEL.md`](../../docs/JUAN_PANEL.md) es una acción de cliente OWL (`dcasa_conversaciones`), con tres
hermanas: `dcasa_juan_resumen`, `dcasa_juan_costos` y `dcasa_juan_conexiones`. Todo el JS vive en `static/src/js` (un almacén reactivo
compartido, `almacen.js`, y un componente por zona), las plantillas en `static/src/xml` y los estilos en `static/src/scss/panel*.scss`
(prefijos `o_dcj_` y `o_dcj_p_`; sistema plano con los tokens de `dcasa_interfaz`). El servidor es `models/conversacion_panel*.py` y
`models/panel_juan.py`; está documentado en `docs/JUAN_ODOO.md` (lo que ve la dueña y la API). El bus avisa con
`dcasa_conversaciones/evento` solo ids y estado, nunca texto.

**Disposición compacta** (laptops de 1366 × 768 y menos): el hilo es lo único que se estira. La ficha del cliente nace cerrada (abierta solo
en pantallas de 1500 × 800 o más) y se abre con el botón «Cliente»; la lista puede reducirse a las fotos; la caja es una franja y una línea
(íconos con nombre + menú «Más»); los avisos son de una línea. Qué se ve a cada tamaño y cómo se recuerda la preferencia por persona
(`localStorage`, envuelto en try/catch) está en `static/src/js/preferencias.js`; los límites de pantalla de ese archivo son los mismos
de los `@media` de `panel.scss`. Medidas y explicación para la dueña: «Tamaños probados» en `docs/JUAN_ODOO.md`.

Pruebas de la pantalla: `tests/test_panel_interfaz.py` (Chrome, escritorio y celular de 390 px), `tests/test_panel_disposicion.py`
(la disposición compacta a siete tamaños de ventana, con el JavaScript de `tests/disposicion.js`) y `tests/test_panel_visual.py`
(contrato visual con referencias en `tests/referencia/`; se regeneran con `scripts/actualizar_referencias_visuales_juan.sh`).

## Pruebas

```bash
DB_NAME=dcasa_t_conversaciones HTTP_PORT=8192 scripts/test.sh dcasa_conversaciones
```
