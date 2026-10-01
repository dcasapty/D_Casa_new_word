# Ronda 4 · Brian — borrar conversaciones desde el historial del chat

> Auditoría (solo lectura) del reporte del dueño: «En el historial del chat no hay botón para
> borrar una conversación. Para borrarla tengo que ir a Menú › Brian › Conversaciones (lista),
> borrar ahí, y el panel del chat no se actualiza al momento.» Fecha: 2026-10-01.
> Todo lo citado es `addons/dcasa_brian/…` salvo que se indique otra ruta.

## 0. Resumen

| Punto del reporte | Veredicto | Evidencia |
|---|---|---|
| (a) No hay borrar en el historial del panel | **Confirmado.** Cada fila es un solo `<button>` que abre la conversación; no hay ni borrar, ni archivar, ni renombrar. El backend ya tiene `archivar()` pero ninguna interfaz lo llama. | `static/src/xml/brian_panel.xml:67-78`; `models/conversacion.py:249-252`; `grep archivar static/` = 0 |
| (b) Borrar en la lista no se refleja en el chat abierto | **Confirmado, con matiz.** La lista del historial se vuelve a pedir **cada vez** que se pulsa el reloj (`verHistorial`), así que reabrirla sí la corrige. Lo que queda viejo es: (1) el historial si ya estaba en pantalla, (2) la conversación abierta en el chat (id y mensajes en memoria). No hay bus, ni recarga al enfocar, ni nada que avise. | `static/src/js/brian_panel.js:262-272`, `:120-134`; manifiesto sin uso de `bus_service` |
| ¿Qué hace «borrar» hoy? | `unlink` real (el modelo no tiene `active`; usa `activo` propio). Mensajes y adjuntos se van; el registro de acciones queda con la conversación en blanco. | §3 |
| Permisos | Cada usuario interno borra **solo las suyas**; nadie (ni el administrador) ve o borra las ajenas desde la interfaz. | `security/ir.model.access.csv:5`, `security/brian_security.xml:4-9`, `tests/test_nucleo.py:177-191` |

Arreglo propuesto (talla **M**): botones «Renombrar» y «Borrar» por fila del historial, con
confirmación; `unlink` sobrescrito en `brian.conversacion` que cierra las acciones pendientes y
avisa por el bus al propio usuario; el panel escucha el bus y además se resincroniza al volver a
la pestaña. Detalle en §5.

## 1. Cómo funciona hoy el chat

### 1.1 Componentes (OWL)

- **Servicio `dcasa_brian`** — `static/src/js/brian_servicio.js:631-667`: solo guarda `estado.abierto` y el atajo Ctrl + J. No guarda datos.
- **`BrianPanel`** — `static/src/js/brian_panel.js:105-608`, registrado como *main component* (`:621`): vive todo el tiempo que dura la pestaña, por encima del action manager. Por eso puede estar abierto al lado de la lista «Conversaciones» mientras se borra ahí.
- **`BrianSystray`** — `brian_panel.js:611-622`, solo abre/cierra.
- Plantillas: `static/src/xml/brian_panel.xml` (`dcasa_brian.Brian` `:9-150`, historial `:62-79`).
- `addons/dcasa_interfaz` no tiene ninguna interfaz de chat de Brian (`grep -ril brian addons/dcasa_interfaz` = 0).

### 1.2 Estado y carga

Estado local del panel (`brian_panel.js:120-134`): `vista` (`chat`|`historial`), `conversaciones`,
`conversacionId`, `titulo`, `mensajes`, `adjuntos`…

| Momento | Qué se llama | Dónde |
|---|---|---|
| Primera apertura | `estado_proveedor()` (solo eso) | `brian_panel.js:141-146`, `:244-251` |
| Pulsar el reloj «Conversaciones anteriores» | `mis_conversaciones(limite=30)` — **se pide de nuevo cada vez** | `brian_panel.js:262-272`; botón `brian_panel.xml:43-46` |
| Pulsar una fila | `historial(id)` y reemplaza `mensajes` | `brian_panel.js:274-289`; `brian_panel.xml:69-72` |
| Primer envío o primer adjunto | `nueva(canal='chat')` | `brian_panel.js:253-260` |
| Enviar | `enviar([[id], texto], {adjunto_ids, contexto})` | `brian_panel.js:327-363` |
| Adjuntar | `orm.create('ir.attachment', {res_model:'brian.conversacion', res_id})` | `brian_panel.js:465-505` |
| Confirmar / cancelar tarjeta | `confirmar_accion` / `rechazar_accion` | `brian_panel.js:582-607` |

No hay ninguna suscripción: el único `useBus` escucha `ACTION_MANAGER:UI-UPDATED` para recalcular la
pantalla actual (`brian_panel.js:137`). No hay `bus_service`, ni `visibilitychange`/`focus`, ni
sondeo. El módulo depende de `mail` (`__manifest__.py:15`), así que el bus de Odoo **ya está
disponible** sin dependencias nuevas.

### 1.3 Backend

- `brian.conversacion` — `models/conversacion.py:141-565`. API pública documentada en `:1-63`:
  `estado_proveedor` `:163`, `mis_conversaciones` `:170-174` (filtra `usuario_id = uid` y
  `activo = True`), `nueva` `:176-178`, `historial` `:180-187` (vía `_propia` `:507-512`),
  `enviar` `:189-214`, `confirmar_accion` `:216-231`, `rechazar_accion` `:233-247`,
  **`archivar` `:249-252`** (pone `activo=False`; nadie lo usa).
- Campo de archivo propio `activo` `:155` (no es `active`): Odoo no ofrece «Archivar» en la lista
  y la acción del menú no filtra por él.
- `brian.mensaje` — `:568-659`, `conversacion_id … ondelete='cascade'` `:573`,
  `adjunto_ids` Many2many a `ir.attachment` `:580`, `accion_id` `ondelete='set null'` `:586`,
  `accion_ids` Many2many `:587`.
- `brian.accion` (auditoría inmutable) — `models/accion.py:37-125`:
  `conversacion_id … ondelete='set null'` `:54`; `unlink` bloqueado salvo desinstalación `:111-114`.
- `brian.telegram.enlace.conversacion_id … ondelete='set null'` — `models/telegram.py:128`.
- No existe `brian.uso` (ni ningún registro de tokens): `grep -rn brian.uso addons` = 0.

### 1.4 Vistas y menú del «registro de conversaciones»

- Lista `brian_conversacion_view_list` — `views/brian_views.xml:108-119`: `create="0"`, borrar
  **permitido** (no lleva `delete="0"`); `activo` oculto opcional.
- Formulario — `:121-165`: deja editar `titulo` y `activo`; muestra mensajes visibles y acciones.
- Acción `brian_conversacion_action` — `:167-176`, dominio `[('usuario_id','=',uid)]`, sin filtro
  por `activo` (salen también las archivadas) y sin vista de búsqueda propia.
- Menú Brian › Conversaciones — `:237-240` (todo `base.group_user`).

## 2. Las dos quejas, contra el código

### (a) No se puede borrar desde el historial — CONFIRMADO

`brian_panel.xml:68-77`: cada `<li>` contiene un único `<button class="o_brian_conv">` con icono,
título y fecha, y `t-on-click` → `abrirConversacion`. No hay otro control. En `brian_panel.js` no
existe ningún método que borre o archive (los únicos `orm` son los de la tabla §1.2). El backend
expone `archivar()` (`conversacion.py:249`) y está en la lista blanca RPC
(`addons/dcasa_base/tests/test_superficie_rpc.py:102`), pero ninguna interfaz lo invoca, así que
hoy es código muerto.

### (b) El panel no se entera del borrado — CONFIRMADO (con matiz)

- El historial **sí** se refresca al reabrirlo: `verHistorial` siempre llama a
  `mis_conversaciones` (`brian_panel.js:262-272`). Si el panel estaba mostrando el historial
  mientras se borraba en la lista (el panel es un *main component* y puede quedar abierto al lado),
  la fila borrada sigue ahí hasta volver al chat y pulsar el reloj otra vez. Al pulsarla,
  `historial()` lanza `AccessError` «Esa conversación no existe o no es tuya»
  (`conversacion.py:507-512`), que sí se muestra tal cual (`brian_panel.js:97-103`).
- La **conversación abierta** queda en memoria: `conversacionId` y `mensajes` no se invalidan
  nunca. Al escribir, `enviar([[id_borrado], …])` hace `browse` de un id inexistente y
  `_verificar_duenio` (`conversacion.py:514-517`) lee `usuario_id` → `MissingError`. Su
  `data.name` es `odoo.exceptions.MissingError`, que **no** casa con
  `/UserError|AccessError|ValidationError/` (`brian_panel.js:99`), así que la persona ve el
  genérico «Brian no está disponible en este momento» y su texto se devuelve a la caja
  (`:353-357`). Se queda trabada hasta que pulse «Nueva conversación». Lo mismo con una tarjeta
  «Confirmar» de la conversación borrada (`:582-599`).
- Causa: no hay notificación del servidor (bus) ni recarga al enfocar; el estado del panel solo se
  carga por acción explícita del usuario (§1.2).

## 3. Qué hace realmente el borrado de hoy (lista del backend → `unlink`)

`brian.conversacion` no sobrescribe `unlink`, así que es el `unlink` estándar del ORM:

| Dato | Qué pasa | Evidencia |
|---|---|---|
| Conversación | Se borra (no se archiva: el modelo no tiene `active`). | `conversacion.py:155` |
| Mensajes `brian.mensaje` | Se borran por la FK `ON DELETE CASCADE` en PostgreSQL. El usuario no tiene `perm_unlink` sobre mensajes (`ir.model.access.csv:6`), pero la cascada SQL no pasa por el ACL: funciona. | `conversacion.py:573` |
| Tablas Many2many de mensajes (`adjunto_ids`, `accion_ids`) | Las filas de relación caen en cascada con el mensaje. | `conversacion.py:580,587` |
| Adjuntos `ir.attachment` con `res_model='brian.conversacion', res_id=<id>` | **Se borran**: el `unlink` del ORM busca y borra (con `sudo`) los adjuntos del registro. Aplica a los del panel (`brian_panel.js:484-492`), a los de Telegram (`telegram.py:401-405`) y a los que `enviar` re-ancla (`conversacion.py:209-210`). | `vendor/odoo/odoo/orm/models.py:4229-4264, 4332-4333` |
| Adjuntos que la persona subió a OTRO registro y referenció en el chat (`_adjuntos_validos` acepta los creados por ella, `conversacion.py:462-466`) | Se conservan (pertenecen al otro registro). Correcto. | — |
| Adjuntos subidos al panel y quitados antes de enviar (`quitarAdjunto` solo los quita de la vista, `brian_panel.js:507-515`) | Siguen anclados a la conversación y se borran con ella. Mientras la conversación viva, quedan como basura (menor). | — |
| Auditoría `brian.accion` | **Se conserva** con `conversacion_id = NULL`. Argumentos, resultado, usuario y canal quedan intactos; es inmutable. | `accion.py:54, 100-114` |
| Acciones `por_confirmar` de esa conversación | Quedan **pendientes y huérfanas**. Por Telegram, un botón viejo «Confirmar» cae en la rama «acción sin conversación» y la **ejecuta** (`telegram.py:461-476`). Es la propia persona confirmando, pero sobre una conversación que ella pidió borrar. | `telegram.py:442-476` |
| Enlace de Telegram con esa conversación activa | `conversacion_id = NULL`; el siguiente mensaje crea una conversación nueva. Sin errores. | `telegram.py:128, 377-385` |
| Uso/tokens | No existe ningún registro de uso (`brian.uso`) que limpiar. | `grep` = 0 |

### Quién puede borrar

- ACL: `base.group_user` tiene `1,1,1,1` sobre `brian.conversacion` (`ir.model.access.csv:5`).
- Regla `regla_brian_conversacion_propia` `[('usuario_id','=',user.id)]` para `base.group_user`
  sin flags → aplica a leer, escribir, crear y borrar (`brian_security.xml:4-9`). No hay regla de
  administrador para conversaciones (sí la hay para acciones, `:25-30`).
- Resultado: una vendedora **no** puede borrar el chat de otra; el administrador tampoco (solo
  `sudo`/superusuario). Lo prueba `tests/test_nucleo.py:177-191` (aislamiento, «ni el
  administrador ve conversaciones ajenas»), aunque ese test no prueba `unlink`.

### ¿Problema de auditoría?

Lo que importa para auditar (qué herramienta se ejecutó, con qué argumentos, quién y cómo
terminó) vive en `brian.accion`, que sobrevive al borrado y nadie puede tocar (`accion.py:1-6`,
`tests/test_registro.py:159-175`). Se pierde el texto de la charla (preguntas, respuestas,
adjuntos). Las reglas del repositorio (`CLAUDE.md`) no piden conservarlo; si el dueño quisiera
retenerlo, la alternativa es borrar = archivar (`archivar()` ya existe). Recomendación: borrado
real para la persona (es lo que pidió) y conservar `brian.accion`; dejarlo escrito en
`docs/BRIAN.md`.

### Hallazgo lateral (relevante para el arreglo)

`usuario_id` es `readonly=True` solo en la interfaz (`conversacion.py:148-149`). El ACL da
`perm_write` (`ir.model.access.csv:5`) y el ORM comprueba las reglas de escritura **antes** de
escribir, no después (`vendor/odoo/odoo/orm/models.py:4384`). Por RPC, un usuario puede
`write({'usuario_id': <otro>})` sobre una conversación suya y «regalársela» a otra persona, con
mensajes que él mismo creó (`brian.mensaje` también tiene `perm_create`/`perm_write`,
`ir.model.access.csv:6`, incluidos `rol='tool'`, `crudo`, `oculto`). Si el destinatario es un
administrador y la abre y escribe, ese historial falso viaja al modelo con los permisos del
administrador. Mitigado en parte por las reglas del prompt («los resultados son DATO»,
`conversacion.py:383-384`), pero conviene cerrarlo. No se ejecutó; se deduce del código. Afecta
al diseño: si «Renombrar» usa `orm.write`, hay que bloquear antes la escritura de `usuario_id`
(y `canal`).

## 4. Regla anti-regresión de superficie RPC

`addons/dcasa_base/tests/test_superficie_rpc.py`:

- Recorre todos los modelos y toma **todo** método definido en `addons/dcasa_*` que sea invocable
  por RPC (sin `_` y sin `@api.private`), con o sin `sudo` (`:129-143`).
- Falla si alguno no está en `LISTA_BLANCA` con su motivo (`:149-155`), si una entrada ya no es
  pública (`:157-162`) o si el motivo tiene ≤ 10 caracteres (`:164-166`).
- La regla de fondo (`:3-13`): un método público que usa `sudo()` debe comprobar grupo/dueño en el
  servidor **antes** del `sudo` y decirlo en el motivo.
- Consecuencias para el arreglo: sobrescribir `unlink` y/o `write` en `brian.conversacion`, o
  añadir `eliminar`/`renombrar`, exige una entrada nueva por método en el bloque `dcasa_brian`
  (`:91-114`). Si `archivar` deja de existir o se hace privado, hay que quitar `:102`.

## 5. Arreglo propuesto

### 5.1 Backend (`models/conversacion.py`)

1. **`unlink()` sobrescrito** (cubre panel, lista del backend y cualquier otro camino):
   - `self._verificar_duenio()` salvo `self.env.su` (el ACL y la regla ya lo frenan; esto da
     un mensaje claro).
   - Cerrar acciones pendientes: buscar `brian.accion` con `conversacion_id in self.ids` y
     `estado = 'por_confirmar'` y llamar a `marcar('rechazada', error='Conversación borrada')`
     (`accion.py:81-94`, ya es `@api.private` y escribe con su contexto de sistema). Así un botón
     viejo de Telegram responde «ya no está pendiente».
   - Guardar `ids` y `usuario_id`, `super().unlink()`, y luego
     `usuario._bus_send('dcasa_brian/conversacion_borrada', {'ids': ids})` por cada dueño
     (`bus.listener.mixin`, `vendor/odoo/addons/bus/models/bus_listener_mixin.py:15`; `res.users`
     ya lo hereda en `bus/models/res_users.py:8`).
   - Lista blanca: `('dcasa_brian','brian.conversacion','unlink')`: «Sobrescribe unlink: valida
     dueño antes de cerrar con sudo las acciones pendientes; el borrado corre sin sudo (ACL +
     regla).»
2. **`write()` sobrescrito**: rechazar `usuario_id` y `canal` salvo `env.su` (cierra §3 lateral);
   tras escribir `titulo`/`activo`, `_bus_send('dcasa_brian/conversacion_cambiada', …)`.
   Lista blanca: «Sobrescribe write: impide cambiar el dueño o el canal; sin sudo.»
3. Opcional y más limpio para la interfaz: **`renombrar(titulo)`** (dueño, recorta a 60, no vacío)
   en vez de `orm.write` directo; entra a la lista blanca como `SIN_SUDO`.
4. Decidir el destino de `archivar()`: o se usa (si el dueño prefiere «ocultar» además de
   «borrar») o se hace privado y se quita de la lista blanca.

### 5.2 Interfaz (`static/src/js/brian_panel.js`, `static/src/xml/brian_panel.xml`, `scss`)

- En cada fila del historial (`brian_panel.xml:68-77`): la fila pasa a contenedor con el botón
  actual + dos `o_brian_icono_btn` («Renombrar» `fa-pencil`, «Borrar» `fa-trash`) con
  `aria-label` que incluya el título; visibles siempre en móvil y al pasar/enfocar en escritorio.
- **Borrar**: `ConfirmationDialog` de `@web/core/confirmation_dialog/confirmation_dialog`
  («¿Borrar «{título}»? Se borran sus mensajes y archivos. El registro de acciones se conserva.»,
  botón «Borrar»), luego `orm.unlink('brian.conversacion', [id])`, quitar la fila de
  `state.conversaciones` y, si era la abierta, `nuevaConversacion()`. Si falla, notificación y la
  fila se queda.
- **Renombrar**: edición en línea (input en la fila, Enter guarda, Esc cancela; ojo con
  `alTeclaPanel`, `brian_panel.js:389-399`, que hoy con Esc vuelve al chat) → `renombrar` y
  actualizar `state.titulo` si es la abierta.
- **Sincronía**: `useService("bus_service")` y `subscribe('dcasa_brian/conversacion_borrada', …)`
  / `…_cambiada` → quitar/actualizar filas y, si borraron la abierta, limpiar el chat con un aviso
  «Esa conversación se borró». Cubre la lista del backend y otras pestañas (el bus entrega al
  `res.partner` del usuario en todas sus pestañas).
- Red de seguridad (por si el bus está caído o el websocket no conecta en Cloudflare): al abrir el
  panel y en `visibilitychange` → si la vista es historial, `verHistorial()`; si hay conversación
  abierta, comprobarla (p. ej. `mis_conversaciones` y ver si su id sigue).
- `mensajeDeError` (`brian_panel.js:97-103`): añadir `MissingError` para que no diga «no
  disponible», y ante `MissingError` en `enviar`, pasar a conversación nueva conservando el texto.
- Diseño: botón borrar en azul/navy sobre blanco (nunca amarillo sobre blanco), sin sombras;
  textos con tuteo.

### 5.3 Vistas (`views/brian_views.xml`)

- Lista y formulario: el borrado ya existe; añadir vista de búsqueda con filtro por defecto
  `activo = True` (o quitar `activo` si se elimina el archivado) para que la lista coincida con
  el historial del panel.

### 5.4 Pruebas

En `tests/test_nucleo.py` (TransactionCase, `post_install`):

1. Borrar propia: mensajes y `ir.attachment` (res_model/res_id) desaparecen; `brian.accion` sigue
   con `conversacion_id` vacío.
2. Acción `por_confirmar` pasa a `rechazada` al borrar; `Herramientas.confirmar` posterior no la
   ejecuta.
3. Otro usuario (vendedora y administrador sin sudo) no puede `unlink` ni `renombrar` la ajena
   (`AccessError`).
4. `write({'usuario_id': otro})` y `write({'canal': …})` → `AccessError`; `titulo` sí.
5. Bus: tras `unlink`, existe un `bus.bus` con tipo `dcasa_brian/conversacion_borrada` para el
   partner del dueño (patrón `self.assertBus` de `bus.tests` o búsqueda en `bus.bus`).
6. Telegram: conversación activa del enlace borrada → el siguiente mensaje crea una nueva
   (`tests/test_telegram.py`).

En `tests/test_interfaz_brian.py` (HttpCase `browser_js`, mismo estilo que `:40-85`): abrir panel,
enviar, ir al historial, borrar con confirmación → la fila desaparece y el chat queda vacío;
borrar otra por RPC (`orm.unlink` desde la consola del tour) con el historial abierto → la fila
desaparece sin recargar.

En `addons/dcasa_base/tests/test_superficie_rpc.py`: entradas para `unlink`, `write`
(y `renombrar` si se crea); ajustar `archivar`.

### 5.5 Tamaño y archivos

**Talla M** (≈ 1-1,5 días con pruebas): poco backend, la mayor parte es la interfaz y el tour.

| Archivo | Cambio |
|---|---|
| `addons/dcasa_brian/models/conversacion.py` | `unlink`, `write`, `renombrar`; docstring de la API (`:1-63`) |
| `addons/dcasa_brian/static/src/js/brian_panel.js` | borrar/renombrar, `bus_service`, `visibilitychange`, `MissingError` |
| `addons/dcasa_brian/static/src/xml/brian_panel.xml` | fila del historial con acciones |
| `addons/dcasa_brian/static/src/scss/brian_panel.scss` | estilos de la fila y botones |
| `addons/dcasa_brian/views/brian_views.xml` | búsqueda/filtro `activo` |
| `addons/dcasa_brian/tests/test_nucleo.py`, `test_interfaz_brian.py`, `test_telegram.py` | pruebas §5.4 |
| `addons/dcasa_base/tests/test_superficie_rpc.py` | lista blanca |
| `docs/BRIAN.md` | qué se borra y qué queda en la auditoría |

`__manifest__.py` no cambia (`mail` ya trae `bus`).
