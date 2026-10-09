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

## Pruebas

```bash
DB_NAME=dcasa_t_conversaciones HTTP_PORT=8192 scripts/test.sh dcasa_conversaciones
```
