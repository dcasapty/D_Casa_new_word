# Juan — el panel de conversaciones dentro de Odoo

> **Especificación histórica: la pantalla ya está construida.** Lo que ves y haces en ella está en
> [JUAN_ODOO.md](JUAN_ODOO.md); este documento queda como el diseño del que salió.

Especificación de la interfaz que usa el equipo de D'CASA para atender con Juan. Sale de lo que
ya funciona y gusta en el CRM de Baby Caleb (su panel `/admin`: 7.167 líneas, `src/admin/views/`),
**mejorado**, y vive **dentro de Odoo**: un solo inicio de sesión (con la verificación en dos
pasos), un solo cliente (la ficha del contacto), y todo conectado con el catálogo, Socios,
el CRM y la contabilidad.

Es una pantalla propia (acción de cliente OWL) del módulo `dcasa_conversaciones`, con el sistema
de diseño de `dcasa_interfaz` (barra lateral, colores, íconos). Mismo patrón técnico que la
conciliación bancaria de `dcasa_contabilidad`.

## De Baby Caleb a D'CASA (qué se conserva)

| Panel de Baby Caleb | Pantalla en Odoo | Cambio |
|---|---|---|
| Resumen (mensajes de hoy, clientes únicos, resueltas sin humano, costo del mes) | **Resumen** | Mismos indicadores, más: oportunidades creadas, ventas atribuidas (facturas pagadas de clientes que hablaron con el bot), tiempo de primera respuesta. |
| Conversaciones (lista + hilo + pausar/continuar/responder/sugerir) | **Conversaciones** (la pantalla principal) | Lo mismo, más adjuntos, etiquetas, fotos del catálogo, respuestas rápidas, notas internas, búsqueda. Abajo. |
| Leads | **Oportunidades** (CRM de Odoo) | Ya existe: el interés se vuelve `crm.lead`; el panel muestra el enlace y el estado. |
| Tickets | Actividades de Odoo | «Pasar a vendedora» crea una actividad con fecha; no hay otro sistema de tickets. |
| Conocimiento (KB) | **Conocimiento del bot** | Mismo flujo: título + contenido; sin vectores (búsqueda por palabras). |
| Mejoras (sugerencias + lecciones) | **Preguntas sin respuesta** + **Lecciones** | Lo que el bot no supo se agrupa; con un botón la dueña lo convierte en conocimiento o lección. |
| Costos | **Costos de IA** | Gasto del mes, tope, proyección «terminarás el mes en…», por modelo y por día. |
| Conexiones (QR, Telegram, Meta, diagnóstico) | **Conexiones** | Estado de cada canal en vivo; QR para vincular; botón «Reiniciar» y «Desvincular» con confirmación; qué clave falta (solo el nombre). |
| Campañas | **No en la Fase 1** | Las masivas quedan fuera a propósito (riesgo de bloqueo del número). |
| Flujo/agente (canvas) | Herramientas activas | Un interruptor por herramienta del bot; el flujo es fijo. |

## Pantalla «Conversaciones» (lo central)

Tres columnas en escritorio, una a la vez en celular (las vendedoras la usarán en el teléfono):

1. **Lista** (izquierda): foto o iniciales, nombre, canal (ícono), último mensaje, hora, etiqueta
   de estado (Bot / Una vendedora / Cerrada / Necesita atención), contador de no leídos, punto
   verde si el bot está atendiendo. Filtros: canal, estado, etiqueta, asignada a mí, sin leer,
   con oportunidad. Búsqueda por nombre, celular o texto. Paginada de 30 en 30 con carga al bajar.
2. **Hilo** (centro): burbujas con hora y autor (cliente / el bot / vendedora con su nombre),
   fotos y documentos dentro del hilo (miniatura, clic para ampliar, descarga), notas internas
   con otro color (el cliente nunca las ve), avisos del sistema («el bot pasó la conversación a
   una vendedora», «se creó la oportunidad»), indicador «escribiendo». Tiempo real con el bus de Odoo.
3. **Ficha** (derecha): cliente (con enlace a su contacto), si es Socio y su saldo de puntos (solo
   lectura), oportunidades abiertas, compras recientes, etiquetas, asignación, notas y «Qué sabe
   el bot de esta persona».

**Caja de respuesta** (la mejora principal):

- **Atender / Devolver al bot**: «Atender» pausa al bot (con vencimiento visible); «Devolver»
  pide una nota opcional para el bot. Si una vendedora escribe desde el teléfono, el panel lo
  muestra y el bot calla.
- **Adjuntar**: foto, documento (PDF, Word, Excel) o varios a la vez, arrastrando, con vista
  previa y límite de tamaño; se envía por el canal como imagen o documento.
- **Foto del catálogo**: botón que abre un buscador de productos (nombre o código, con foto,
  precio «+ ITBMS» y disponibilidad); al elegir, manda la foto con un pie armado (nombre, precio
  + ITBMS, medidas, enlace). Varias fotos del mismo producto (galería) con un clic.
- **Cotización en PDF**: botón que genera la cotización de Odoo del cliente (o crea una borrador
  con líneas del catálogo) y la envía como documento.
- **Respuestas rápidas**: atajos con `/` (p. ej. `/horario`, `/ubicacion`, `/socios`) que la dueña
  edita en un menú; admiten el nombre del cliente.
- **Respuesta sugerida por IA**: botón «Sugerir» que redacta un borrador para la vendedora, con
  el contexto de la conversación y las mismas reglas de marca (la vendedora lo edita y envía).
- **Etiquetas**: de colores, creadas por la dueña («Apartado», «Pidió precio», «Comprobante
  recibido», «Entrega»…); el bot también etiqueta según lo que entiende.
- **Notas internas**: entre vendedoras, con mención (@) y actividad opcional.
- **Comprobantes de pago**: llegan marcados («Comprobante: lo revisa una vendedora»), nunca se
  le muestran a la IA; con un botón se adjuntan a la factura o al pedido.
- **Mensajes programados** y **seguimiento** visibles: «Seguimiento 1 pendiente para el
  jueves 8:00 a. m.», con opción de cancelarlo.

## Trabajo en equipo

* **Cliente esperando.** Si una persona tiene la conversación y el cliente lleva más de `aviso_espera_minutos` (10 por defecto; 0 = apagado)
  sin respuesta, la lista dice «Espera N min» (en marino con amarillo pasado el umbral) y el mantenimiento de cada 5 minutos avisa **una vez
  por espera** por Telegram a quien la atiende (si nadie o no tiene Telegram, a las personas de siempre). Solo en horario laboral (se puede
  cambiar) y no avisa de esperas de más de un día. Si el cliente vuelve a escribir y nadie contesta, avisa otra vez.
* **«Ana está viendo» / «Ana está escribiéndole al cliente…».** Cada pantalla da un pulso cada 20 s con la conversación que tiene abierta
  (y mientras teclea una respuesta, cada 4 s). En la lista aparece un chip con el nombre y en el hilo una franja; desaparece a los ~55 s
  sin pulso. Una nota interna no cuenta como «escribiendo».
* **Reparto de conversaciones** (Ajustes de Juan → «Reparto de conversaciones»; **apagado por defecto**, también en instalaciones nuevas: lo
  enciende Gerencia desde la pantalla «Reparto» o desde Ajustes). Cuando el asistente pasa una conversación a una persona y nadie la tenía:
  * **Nadie** (`manual`): no se asigna; la toma quien quiera y la tarea queda con el responsable por defecto.
  * **Parejo** (`parejo`, el recomendado): entre las **vendedoras disponibles** (no están marcadas «No disponible» y Gerencia no las sacó del reparto),
    1) si el cliente habló con una de ellas (o se la asignaron) en los últimos **14 días** (se cambia en Ajustes; 0 = sin memoria), vuelve con
    ella; 2) si no, le toca a quien **lleva menos conversaciones recibidas hoy** (día de Panamá); con empate, a quien **menos clientes tiene
    esperándole**; con empate, a quien **lleva más tiempo sin recibir una**. Una misma conversación el mismo día cuenta una sola vez.
  * **Por turnos** (`turnos`): a quien lleva más tiempo sin recibir una, sin mirar cuántas lleva (el reparto de antes).
  En los dos últimos se le asigna, se le deja la actividad y el aviso de Telegram va a ella («Te tocó a ti» o «Es un cliente tuyo»), y en el hilo
  queda por qué le tocó. **Si nadie está disponible**: la conversación queda sin asignar, la tarea va al responsable por defecto y el aviso por
  Telegram sale a todo el equipo diciendo «Nadie estaba disponible». Cada vendedora se marca «Disponible / No disponible» arriba de la lista
  (almuerzo, fin del día); **Gerencia saca a una vendedora del reparto** (vacaciones, ausencia) desde «Reparto» sin quitarle permisos ni sus
  conversaciones, con un día de regreso opcional. Cada decisión queda en el libro `dcasa.reparto` (no se edita).
  **Quiénes reciben (decisión de la dueña):** solo las **vendedoras**, o sea, personas internas con el grupo de ventas que **no** son Gerencia de
  ventas (`sales_team.group_sale_manager`) ni administradoras (`base.group_system`). Gerencia y administradoras ven todo, pueden tomar cualquier
  conversación y escribir (conservan todos sus permisos y su visibilidad), pero el reparto nunca se las pasa, aunque estén «disponibles»; en la
  pantalla «Reparto» salen aparte, en «No reciben». Ese conjunto es solo del reparto (`dcasa.reparto._vendedoras`): quién ve, a quién se le asigna a mano,
  a quién se le menciona y a quién le llegan los avisos sigue siendo `_usuarios_del_panel`. Si no hay ninguna vendedora disponible, todo sigue como siempre
  (sin dueña, tarea al responsable, aviso a todas). *Borde:* una persona con el rol de vendedora que además tenga el de Gerencia (o sea administradora)
  **deja de recibir**; la pantalla la muestra en «No reciben» y, si no debía ser gerente, se le quita ese rol. Una conversación que Gerencia tomó y devolvió
  al asistente se reparte a una vendedora la próxima vez que Juan la pase.
* **«No disponible» se reinicia cada mañana.** La acción planificada **«Juan: volver a poner «Disponible» a las vendedoras cada mañana»**
  (`dcasa.reparto._cron_reiniciar_disponibilidad`, cada hora) mira si ya pasó el **corte de hoy: dos horas antes de abrir la tienda**, hora de
  Panamá (6:00 a. m. con el horario de 8:00 de Ajustes de Juan; si cambian la apertura, el corte se mueve; nunca antes de medianoche). Pasado el corte, deja
  «Disponible» a toda vendedora que se marcó «No disponible» **antes** del corte (`res.users.dcasa_no_disponible_desde`, que anota cuándo se marcó). No toca a quien
  Gerencia sacó con «Dejar de asignarle» (vacaciones y ausencias siguen hasta el día de regreso o hasta que Gerencia la vuelva a meter; el día que
  vuelve, la primera pasada la deja disponible), ni a Gerencia ni a administradoras, ni lo que se marcó **después** del corte (si el contenedor durmió y la
  acción corre tarde, la pausa de hace un rato se respeta). Idempotente. *Qué la dispara:* el hilo de acciones planificadas de Odoo
  (`max_cron_threads = 1`, `workers = 0` en `docker/entrypoint.sh`); en producción el contenedor está encendido 24/7 (el cron horario del Worker lo enciende
  si se cae), así que corre sola. En staging, que duerme tras 1 h sin visitas, no corre mientras duerme: al despertar Odoo hace la pasada atrasada, y por el
  guarda de «antes del corte» no borra pausas recientes.
* **Pantalla «Reparto».** Cada vendedora ve **solo lo suyo** («Mis conversaciones de hoy»: cuántas le pasó Juan, cuántos clientes le esperan ahora, la
  última y la lista, con «Abrir»). Gerencia ve además a todo el equipo: estado, recibidas en el periodo (barra), clientes esperando, la última
  que le tocó, y cuántas conversaciones esperan sin dueña; puede sacar a alguien del reparto, volverla a meter y encender o apagar el reparto.
  El servidor solo manda los números de las demás a Gerencia.
* **Resumir.** Botón «Resumir lo que pasó» en conversaciones con 4 mensajes o más: unas viñetas hechas por la IA (modelo económico) con los
  mensajes que viajaron por el canal; las notas internas nunca. Se guarda en la conversación y se vuelve a pedir solo con «Actualizar».
* **Por persona (Gerencia).** En Resumen: mensajes, conversaciones, cuánto tarda en contestar y cuántas le esperan, por persona.

## Rendimiento y calidad

- Cargar la lista en menos de 0,25 s con 5.000 conversaciones (medido: ~0,03 s; índices, paginación, sin cargar hilos
  completos): el hilo se trae por tramos de 50 mensajes, hacia atrás. La búsqueda por lo que se dijo usa un índice de trigramas
  sobre el texto de los mensajes (`pg_trgm`; sin la extensión se busca igual, más lento) y mira los mensajes UNA sola vez.
  En `dcasa.mensaje` solo quedan los índices que se usan (el hilo, la restricción única, la fecha, el cliente, lo programado,
  el parcial de «por enviar / fallido» y el de trigramas): Odoo no borra solo un índice al quitarlo del campo, así que el
  modelo los borra en `init()` al actualizar.
- Imágenes: miniaturas WebP al ancho justo (el mismo servicio `/dcasa/img` del sitio), carga
  diferida; documentos solo al abrirlos.
- Tiempo real con el bus de Odoo (un solo canal por usuario), sin sondeo. El punto «En vivo» solo está encendido si la conexión
  lo está de verdad (se apaga al caerse y se enciende al conectar). Al **reconectar**, al **volver a ver la pestaña** (si pasaron
  más de 20 s) y al volver la red, la pantalla se pone al día sola; y mientras no haya conexión en vivo se revisa cada 30 s: nadie
  se queda sin ver un mensaje por tener que «recargar la página».
- Funciona en celular (390 px) y con el pulgar: botones de al menos 44 px, caja de respuesta fija
  abajo, la lista y el hilo como pantallas separadas.
- Accesible (teclado, foco visible, etiquetas), sin degradados ni sombras dramáticas (regla de
  marca: azul `#1340B1`, amarillo `#FED00F` nunca sobre blanco).
- Pruebas: de modelo (rápidas), de controladores y de interfaz con Chrome (como las demás
  pantallas OWL del repo) y contrato visual en celular y escritorio.

## Lo que el bot sabe de cada cliente (para la ficha)

Nombre, celular, canal, si es Socio, productos por los que preguntó, oportunidad abierta, etiquetas,
última vez que habló y si hay seguimiento pendiente. Nada de saldos con detalle ni de datos de
otros clientes.
