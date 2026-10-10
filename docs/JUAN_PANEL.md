# Juan — el panel de conversaciones dentro de Odoo

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
* **Reparto por turnos** (Ajustes de Juan → «Reparto de conversaciones»; apagado por defecto). Cuando el asistente pasa una conversación a una
  persona y nadie la tenía, le toca a quien lleva más tiempo sin recibir una, entre quienes están **disponibles** (cada quien lo marca arriba
  de la lista, solo se ve con el reparto por turnos). Se le asigna, se le deja la actividad y el aviso de Telegram va a ella. Si nadie está
  disponible, todo sigue como siempre (responsable por defecto y aviso a todas).
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
