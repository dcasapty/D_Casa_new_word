# Sofía, la asistente del CRM (`dcasa_sofia`)

Pedido de la dueña (2026-11-05): un agente independiente para el CRM, como Brian lo es del administrador. Que reparta,
proponga mensajes y seguimientos según el estado de cada cliente, mantenga el CRM al día y diga las prioridades del día,
**sin dañar el proceso de respuesta de Juan**. Decisiones de la dueña:

* **Propone y una persona aprueba.** Sofía no cambia nada por su cuenta.
* **Con un botón y cada mañana.** «Organizar con Sofía» arriba del tablero (y de la lista) del CRM, y una revisión
  automática media hora después de abrir.
* **Gerencia ve y aprueba todo; cada vendedora lo suyo**, con un resumen por Telegram cada mañana.
* **Campaña de datos** (mismo día): a los tibios y calientes que llegaron por WhatsApp o redes con un emoji, una frase o
  una empresa como nombre, o sin correo, un mensaje profesional que les pide su nombre y apellido y su correo para
  avisarles de promociones, del programa Socios y de los beneficios de cumpleaños.

## Dónde está

* **CRM › Sofía** (y el botón «Organizar con Sofía» del tablero y de la lista del CRM, que revisa al entrar).
* **CRM › Configuración › Sofía**: «Mensajes de Sofía» (los textos, los cambia Gerencia) e «Historial de Sofía» (qué
  propuso, quién lo aprobó o descartó y qué pasó).
* **Conversaciones › Configuración › Ajustes de Juan**, grupo «Sofía»: revisar cada mañana (sí), resumen por Telegram
  (sí), lo descartado no vuelve en (7 días), no volver a pedir sus datos en (30 días).

## Qué propone (en este orden; un solo mensaje por cliente por revisión)

| Tipo | Cuándo | Qué se aprueba |
|---|---|---|
| Contestarle | Una vendedora tiene el chat y el cliente le escribió hace más de 1 hora (y menos de 7 días) sin respuesta. | Abrir el chat. |
| Su cotización vence | Cotización sin confirmar (borrador o enviada) que vence hoy o mañana y el cliente tiene chat. | Mensaje de recordatorio (abrir el chat con él, enviarlo ya o crear tarea). |
| Escribirle | Tibio o caliente al que ninguna vendedora le escribió en 24 horas («A quién escribirle hoy»). | Mensaje de seguimiento según su estado: tiene cotización, dijo para cuándo, o le interesó algo. |
| Pedir sus datos | Tibio o caliente cuya ficha no tiene nombre y apellido de verdad o no tiene correo. Si además toca escribirle, va al final del mismo mensaje. | El mensaje que pide los datos. |
| Guardar su correo | El cliente escribió su correo en el chat (últimos 30 días) y su ficha no tiene. | Guardarlo en su ficha. |
| Llamarlo | Por WhatsApp oficial, Messenger o Instagram ya pasaron 24 horas desde su último mensaje (Meta no deja escribirle) y tiene celular. | Crear una tarea de llamada. |
| Darle una vendedora (Gerencia) | Tibia o caliente sin vendedora: a su vendedora de siempre (los días del reparto de Juan) o a quien lleva menos oportunidades abiertas. | Asignar la oportunidad. |
| Poner a su vendedora en la oportunidad (Gerencia) | La vendedora que atiende su chat no es la de la oportunidad. | Asignar la oportunidad. |

Prioridad: «Hoy sin falta» (contestar, cotización que vence hoy, escribirle a un caliente, repartir un caliente), «Hoy»
y «Cuando puedas». La pantalla las ordena así; por tipo muestra hasta 150 (las demás se cuentan y Gerencia lo ve).

### Qué es «sin nombre de verdad»

Reglas fijas (`models/reglas.py`, `falta_el_nombre`): sin nombre o el provisional del canal; solo emojis o símbolos;
con emojis o números; más de 5 palabras (una frase); palabras de frase o de empresa («Dios», «bendiga», «amor»,
«tienda», «S.A.»…, lista corta y prudente: «Jesús», «Luz» o «Paz» son nombres); o un solo nombre (falta el apellido).
El saludo usa el nombre de pila solo si es un nombre: nunca «Hola 🙏».

## Lo que no hace (y por qué)

* **No toca el proceso de Juan.** Revisar no escribe en conversaciones ni en oportunidades. No se mete con un cliente que
  está conversando con Juan ahora (escribió hace menos de 2 horas y lo atiende Juan), ni con quien Juan está por
  mandarle su seguimiento automático (en las próximas 2 horas, o ya lo está mandando). Si Juan lo tenía para más
  adelante, la propuesta lo dice: al escribirle una persona, la conversación pasa a ella y ese seguimiento ya no sale
  (como siempre que una vendedora escribe). Repartir asigna la **oportunidad**, nunca el chat.
* **No escribe sola.** «Enviar ya» manda el mensaje por la misma ruta que la pantalla de Conversaciones
  (`enviar_respuesta`), con quien lo aprueba como autora: la conversación pasa a ella y Juan calla, como siempre.
  «Abrir el chat con este mensaje» deja el texto escrito en la caja del chat, sin enviarlo.
* **No inventa cifras.** Los mensajes salen de plantillas (CRM › Configuración › Sofía) con datos que Odoo ya sabe: el
  nombre de pila, lo que le interesó, el número de su cotización y hasta cuándo vale. Una plantilla no acepta claves
  que Sofía no sabe llenar. Sin precios ni cifras del programa Socios: eso lo confirma la vendedora.
* **No escribe a quien pidió que no lo contacten**, ni a empleados, usuarios o la empresa propia. Fuera de las 24 horas
  de Meta no ofrece escribir (Meta lo rechazaría): propone llamar.
* **No gasta IA.** Esta etapa es de reglas y plantillas. Para un mensaje más a la medida está el botón «Sugerir» del
  chat (lo redacta Juan).

## Seguridad

* `dcasa.sofia.propuesta` y `dcasa.sofia.corrida` son de solo lectura por RPC (ACL). Regla de registro: la vendedora
  solo ve las propuestas que son para ella y nunca las de repartir; Gerencia ve todas.
* Los métodos de la pantalla (`panel`, `analizar`, `aplicar`, `descartar`) exigen el grupo de ventas en el servidor,
  leen la propuesta como el usuario (la regla de registro manda), la bloquean antes de resolverla (`FOR UPDATE NOWAIT`)
  y validan cada argumento. Cada acción corre con los permisos de quien la aprueba (sin `sudo`): asignar exige
  Gerencia; guardar el correo pasa por las reglas de Contactos (sin repetir el correo de otra ficha).
* Antes de hacer algo se revisa que todavía haga falta (la oportunidad sigue abierta, nadie cambió la vendedora, la
  ficha sigue sin correo, el cliente no pidió que no lo contacten). Si no, la propuesta queda «Ya no hacía falta».
* Una sola revisión a la vez (candado de la base) y el botón no vuelve a revisar si alguien lo hizo hace menos de un
  minuto.

## Cada mañana

El cron «Sofía: revisión del CRM de cada mañana» corre cada 30 minutos y solo hace algo una vez al día: dentro del
horario de Ajustes de Juan, media hora después de abrir. Si «Resumen por Telegram» está encendido, cada vendedora con
Telegram vinculado recibe cuántas cosas tiene y las 5 más urgentes, y Gerencia el resumen (lo de repartir y cuántas
tiene cada vendedora). El aviso nunca hace fallar la revisión.

## Pruebas

`addons/dcasa_sofia/tests/`: reglas puras (`test_reglas.py`), motor, permisos, aprobar cada acción, lo que ya no hace
falta, descartar, la revisión de la mañana y Telegram (`test_sofia.py`), y en el navegador revisar, descartar y abrir el
chat con el mensaje escrito (`test_sofia_navegador.py`).

## Siguientes etapas (ideas, sin hacer)

* Mensajes redactados con IA a partir de la conversación (con tope de gasto propio y sin cifras).
* Plantillas aprobadas de WhatsApp para escribir fuera de las 24 horas.
* Leer el nombre que el cliente contesta y proponer corregir su ficha.
