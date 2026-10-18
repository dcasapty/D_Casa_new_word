# Prioridades vigentes

Puesto al día el **2026-10-16**, a partir de la tanda de pedidos que hizo el jefe ese día. Este es el orden en que se
trabaja; cada sesión lo revisa al empezar y lo actualiza al terminar (ver [LEEME_PRIMERO.md](LEEME_PRIMERO.md)). El
documento para leer con la dueña y el jefe (con explicaciones y decisiones) está en Claude Docs: «Plan de mejoras del
jefe» (<https://claude.ai/code/artifact/8ffcbb80-6521-4e46-a2a7-8ddc59cb20b2>). Aquí queda el resumen para quien retome el trabajo.

Cada etapa sale a staging para que la dueña la vea; a producción solo con su «sí» explícito (por cada etapa).

**Estado al 2026-10-17, noche:** en producción la tanda 1 (Desplegar 17: abonos, Mi cuenta, contactos, comparador,
correos apagados, tienda) y la barra del celular más el menú con esquinas suaves (Desplegar 18, PR #54). Orden de lo
que sigue, cada cosa con capturas para la dueña **antes** de staging: (1) el error de Ajustes, si se confirma (afecta
producción); (2) las reglas contables del jefe sobre permisos (`docs/DECISIONES_CONTABLES.md`); antes de encenderlas,
darle el rol Caja al jefe administrativo; (3) el Inicio de Gerencia sobre facturas; (4) Meta unido, que espera las
decisiones de la dueña y el visto bueno del abogado para la política de privacidad. Tareas de la dueña: la cuenta de
Resend con `RESEND_API_KEY` en GitHub, y las instrucciones v2 de Juan en Chrome.

**Estado al 2026-10-16, tarde:** en producción desde las 13:25 UTC (Desplegar 10, `d37af4fd…`, PR #46 en `main`) las
Etapas 1, 2 y 3, la prueba de humo del arranque, Conversaciones #25 punto 1 y el botón «Volver a una versión estable».
Desde las 15:11 UTC (Desplegar 11, `9be426a4…`) también: Inicio con las listas de cotizaciones y entregas arriba y con
acento, «Ganancia bruta», la línea que cuadra el Inicio con Contabilidad, el aviso de utilidad sin costo de ventas y
«Vencido» sin negativos (ver la bitácora). Lo que sigue: guardar la Estable 2 cuando la dueña confirme producción, ensayar la
vuelta en staging, la alerta por Telegram del arranque (rama local `alertas-local`), lo que falta de la etapa 1 (topes
de Brian: esperan cifras de la dueña) y la 1b. **Para la contadora** (de las capturas del 15–16 oct): costo de ventas en
cero, ACH Banco Nacional en negativo, saldos de Punto de venta y Yappy sin traspasar al banco, ITBMS acumulado.

**Prioridad del 2026-10-16, tarde (la dueña: «esto se superpone al resto»): hecha.** El bono por meta de ventas, los
pedidos repetidos y los avisos del chat están en producción (Desplegar 12). Siguen: (1) el equipo responde el
cuestionario «Preguntas para Juan» y, con la revisión de la dueña, se carga en la base de conocimiento (cambiar la regla
3 de Juan para entregas, flete, apartados, crédito o descuentos necesita su «sí»); (2) la dueña conecta Messenger e
Instagram con [JUAN_META.md](JUAN_META.md) (empieza por la verificación del negocio); (3) salario y fecha de inicio de
las vendedoras antes de la planilla del 1 al 15 de noviembre, que paga el primer bono (octubre).

**Pedido del 2026-10-16/17 (permisos): hecho en la rama local `permisos-vendedoras`, sin subir.** Cada vendedora ve solo
lo suyo, rol Caja y el interruptor «Cada vendedora ve solo sus documentos» para volver atrás (ver
[PERMISOS.md](PERMISOS.md)). Revisión adversarial hecha el 17 oct (dos arreglos y cinco pruebas de la rama unida; ver la
bitácora). **Encima, las reglas contables de la gerencia** (17 oct, [DECISIONES_CONTABLES.md](DECISIONES_CONTABLES.md):
A3, A5, A6, A7 y C1, hechas) y las respuestas de la dueña del punto 23 (pedidos web sin vendedora; la vendedora sigue
facturando pero no cobra). Falta: que la dueña apruebe las capturas (`capturas_permisos/` y `capturas_reglas/`), CI y
staging; producción con su visto bueno; ese día, darle Caja al jefe administrativo antes de abrir. De las
decisiones contables, esta rama no toca: crédito solo a autorizados por Gerencia (A3), «Vendido» como facturas publicadas (A1),
correo 5 días antes del vencimiento del abono (D3), comisiones del punto de venta del banco por lote (B1/C6), fondo fijo
de caja (C4), aportes y retiros de los dueños (C8), mermas con aviso del 0.5 % (F6).

## Lo que solo la dueña y el jefe pueden empezar hoy

Son los trámites largos; empiezan ya aunque el código llegue después.

1. **Verificación del negocio en Meta** (Messenger, Instagram y el plan B de WhatsApp): no se puede acelerar.
2. **Cinco preguntas para la contadora** (ver «Las ~1000 facturas…» en el documento del plan): desbloquean la carga de las
   facturas viejas y el cálculo del costo de ventas.
3. **Qué trae impreso una caja de mueble** (código de barras, referencia, nada): decide cómo el Escáner verifica el
   despacho. Y encender el QR de la nota de entrega (Ajustes › Empresas › Documentos D'CASA).
4. **Decisiones de diseño**: paleta de colores de los íconos del menú, umbral de «stock bajo» (2 o 5), quién ve la
   bitácora de bodega, si la Contabilidad la ve solo Gerencia.

## Decisiones tomadas el 2026-10-16 (la dueña aceptó las recomendaciones)

1. La ganancia y los costos los ven solo Gerencia y los administradores (contabilidad ya los ve en sus reportes).
2. Ventas, costo y ganancia **sin ITBMS**; el dinero que se mueve (por cobrar, cobrado, caja) **con ITBMS**; cada
   etiqueta lo dice y trae el desglose sin ITBMS · ITBMS · total (mejor práctica contable).
3. Íconos del menú con un color por familia: azul de la marca (Ventas, CRM, Contactos), verde petróleo (Facturación,
   Contabilidad, Nómina), naranja quemado (Inventario, Compras, Envíos), azul cielo (Sitio web, Conversaciones), índigo
   (Socios y equipo). Nunca amarillo de fondo (tocaría el blanco de la barra).
4. «Por agotarse» = 5 unidades o menos para todos al principio (parámetro, después por producto).
5. La bitácora de bodega la ve Gerencia; la Vendedora no.
6. La Vendedora no ajusta existencias a mano (hecho).
7. Encender el QR de la nota de entrega, primero en staging.
8. El tope de descuento de la Vendedora (10 %) vale también para el descuento global y el de importe fijo (hecho).
9. El tope de gasto de IA de Brian se pone con una cifra mensual por persona y otra para todos. **Falta la cifra.**
10. El texto de «Pedidos web por atender» pasa a «Compraron en la web y aún no se entregan».

**Siguen abiertas:** las tres cifras de los topes de dinero de Brian (puntos máximos por ajuste, monto máximo de una
factura que arma Brian, unidades máximas por ajuste de existencias), la cifra mensual del tope de gasto de IA, qué trae
impreso una caja de mueble, cuál es «el flujo del CRM» que querían crear, encender el QR de la nota de entrega en
staging, las cinco preguntas para la contadora y las respuestas del plan de envíos. (Estos documentos ya están en `main`,
unidos con el PR #43.)

## Orden de trabajo

| # | Etapa | Qué incluye | Depende de |
|---|---|---|---|
| 1 | **Seguridad y control primero** | Cerrar los huecos hallados el 2026-10-16: tope de descuento también para el descuento global y el de importe fijo (y al quitar o cambiar líneas después); fusión de contactos segura; que la Vendedora no ajuste existencias a mano sin motivo; topes de dinero de Brian (#26); permisos de escritura de Conversaciones (#25). Más protecciones: pruebas de humo después de producción, revisión adversarial obligatoria si el cambio toca dinero, permisos, contabilidad o Socios, una prueba por cada hueco, revisión de secretos. **Las pruebas se mantienen completas: no se recortan ni se aceleran a costa de cobertura** | Decisiones 6, 8 y 9. **Hecho (PR #43; en producción con el arreglo #97):** tope de descuento del pedido entero (global, importe fijo y líneas negativas; también con precio por contexto, al cambiar de producto o unidad), fusión de contactos segura (fusiones masivas solo del administrador), existencias solo por Gerencia, regla de revisión adversarial (plantilla del PR y `LEEME_PRIMERO.md`). **Falta:** topes de dinero de Brian (esperan las cifras de la dueña), permisos de Conversaciones (#25), pruebas de humo después de producción, revisión de secretos |
| 1b | **Costo y «vendido» más firmes** (salió de la revisión adversarial del 2026-10-16) | (a) Cerrar de verdad el campo «Costo» de la ficha del producto, el margen de los reportes de factura (`account.invoice.report`) y el precio del proveedor: solo Gerencia, administradores, contabilidad, compras e inventario; con pruebas de que recibir, entregar y comprar siguen andando para la Vendedora y para bodega. (b) Que «Vendido» y la ganancia salgan de las líneas de las **facturas publicadas** y no del pedido (así cuadran con Contabilidad si se corrige la factura en caja y las notas de crédito parciales restan solo lo devuelto). **En el Inicio de Gerencia y en Brian para Gerencia, hecho en la rama `inicio-facturado`** (2026-10-17); el Inicio de la vendedora y Estadísticas siguen con los pedidos. (c) Pendientes menores: fusión (`company_ids` de usuarios si hay varias empresas; fichas de usuarios/empleados), `_ganancia_de` con `sudo` si algún día hay varias empresas | Pruebas de Inventario, Compras y Contabilidad |
| 2 | **Inicio nuevo con utilidad** (**hecho**, PR #43; en producción con el arreglo #97) | Costo guardado al confirmar la venta y ganancia (solo Gerencia); selector Hoy / Semana / Mes / rango; ITBMS claro por mejor práctica contable (ventas, costo y ganancia sin ITBMS; dinero que se mueve con ITBMS; cada etiqueta lo dice y trae el desglose); Cotizaciones y Entregas lado a lado; botones azules (quitar «Nueva factura» y «Ver en el celular»); franja de atención; Estadísticas del negocio; íconos del menú con color; categoría «Envíos — En desarrollo»; **cerrar el hueco del tope de descuento** (el botón Descuento global y de importe fijo no pasa por el tope de la vendedora una vez que existe el producto de descuento; verificado el 2026-10-16) | Costos cargados; paleta de colores |
| 3 | **Clientes y proveedores limpios** (los usuarios y empleados del sistema no se tocan) | Encontrar por qué una misma persona aparece 5 veces al cotizar, con el mismo correo y celular, pese a los candados (el candado no cuenta usuarios, empleados ni direcciones hijas; hay que mirar «Posibles duplicados»); **arreglar la fusión** (Gerencia no tiene permiso para el asistente; no copia los datos de Socios de la ficha que se borra; destino = la más vieja); avisar al cotizar cuando hay otros contactos con el mismo correo o celular y mostrarlos en el selector; buscar antes de crear una ficha desde una conversación o Telegram | Mirar los datos reales |
| 4 | **Bodega** | Escáner › Despachar (QR de la nota → verificar cada artículo); Bitácora de bodega (antes → después, motivo); alertas diarias por Telegram (stock bajo, ajustes grandes, cierre de mes); cerrar el hueco del Inventario físico para la Vendedora | Etiquetas o códigos en cajas; umbral |
| 5 | **Contabilidad propia** | Menú raíz «Contabilidad» (reportes, bancos, cierre de mes), tablero, arqueo de diarios con comprobantes, toma de inventario, ITBMS claro en todos los resúmenes | Respuestas de la contadora |
| 6 | **Conversaciones** | Encender Messenger e Instagram (el código ya existe), probar en staging con mensajes reales; después las ideas de CRM fase 2 que elijan | Meta: verificación, app y tres secretos |
| 7 | **Facturas del sistema anterior** | Informe de cuadre por mes (archivo contra lo cargado); carga en staging con la contadora | Respuesta 1 de la contadora |
| 8 | **Brian sin huecos** | Descuentos (% por línea, global, importe fijo), facturar desde una cotización, fusionar contactos, margen por producto, recibir compras; archivo de cobertura que obligue a que toda función nueva tenga su herramienta | Etapas 2 a 4 |

## Pedidos del jefe del 2026-10-16 y su estado

| Pedido | Estado | Etapa |
|---|---|---|
| Utilidad en el Inicio (Hoy / Semana / Mes con rango) | Hecho (PR #43; en producción con el arreglo #97). Ganancia sin ITBMS solo para Gerencia y administradores | 2 |
| Rediseño del Inicio | Hecho (PR #43; en producción con el arreglo #97) | 2 |
| Contabilidad con menú y tablero propios | Por construir | 5 |
| Que el contexto no se pierda entre sesiones | Hecho (este archivo y `LEEME_PRIMERO.md`) | 0 |
| Estado de los issues y prioridades | Hecho (ver abajo) | 0 |
| Conversaciones: Instagram, Messenger, WhatsApp | Código listo; falta Meta | 6 |
| Error de despacho en bodega (verificar con escáner) | Por construir | 4 |
| Contactos duplicados | La herramienta de fusión ya sirve a Gerencia y no pierde los datos de Socios (en producción, PR #43). Falta lo de la etapa 3: por qué una persona sale 5 veces al cotizar, avisar al cotizar y limpiar los duplicados viejos de clientes y proveedores | 3 |
| ~1000 facturas del sistema anterior | Importador listo; falta la contadora | 7 |
| Alertas de fin de mes y de mercancía agotándose | Por construir | 4 |
| Bitácora de bodega | Por construir | 4 |
| Brian sin limitaciones | Auditado; huecos listados | 8 |
| Menos fallas y más seguridad (la velocidad de las pruebas no es prioridad) | En marcha: la etapa 1 está en producción con revisión adversarial y pruebas completas; falta lo que dice la etapa 1 | 1 |
| Descuentos (por línea, global, importe fijo) | Cerrado el hueco del tope en producción (PR #43): global, importe fijo y líneas negativas también respetan el 10 % de la Vendedora. Brian aún no los maneja (etapa 8) | 2 |
| ITBMS claro en los resúmenes | Decidido por mejor práctica contable. Inicio y Brian hechos y en producción (etapa 2); falta Contabilidad (etapa 5) | 2 y 5 |
| Estadísticas del negocio (menú) | Hecho (PR #43; en producción con el arreglo #97) | 2 |
| Íconos del menú con color | Hecho, en producción (2026-10-16, PR #43; paleta aceptada) | 2 |
| Categoría «Envíos — En desarrollo» | Hecho (PR #43; en producción con el arreglo #97) | 2 |
| Meta de la vendedora en el Inicio: solo porcentaje, barra, frases y «Ver mis ventas» (sin cifras de dinero) | En producción (Desplegar 14) | — |
| Juan: crédito, entregas y descuentos desde su conocimiento; inglés; domingo hasta las 5 | En producción (Desplegar 14 y Worker de Juan). Falta que la dueña corra las instrucciones v2 con la extensión de Chrome | — |
| Inicio de Gerencia contra el mes pasado; precio y cámara en el Escáner | En producción (Desplegar 15) | — |
| Comparador de ventas del Inicio de Gerencia (números, no frases), interruptor «Completadas / Con abonos», selector y lista por vendedora; Brian `comparar_ventas` | En producción (Desplegar 17). Sigue: el Inicio de Gerencia sobre facturas (Facturado · Con abonos · Completadas) y las notas a un ícono ⓘ | — |
| Inicio de Gerencia sobre las **facturas** (A1/A2 del jefe): interruptor Facturado · Con abonos · Completadas, «N de M salieron de un pedido», notas de crédito que restan, ganancia de facturas sin pedido con el costo de hoy, la semana y lo más vendido con la misma base, notas largas en un ícono ⓘ; Brian igual | Hecho y probado en la rama `inicio-facturado` (local, sin subir). Falta: capturas → visto bueno de la dueña → staging → su «sí» | — |
| Abonos: el papel dice «Abono» con el saldo; condiciones en dos hojas; el cliente ve lo que le falta | En producción (Desplegar 17): papel «ABONO» y condiciones en dos hojas. Sigue: abono mínimo 50 % y 30 días (reglas del jefe, `DECISIONES_CONTABLES.md`) | — |
| Panel del cliente «Mi cuenta» | En producción (Desplegar 17); falta la ronda de pulido de la auditoría visual | — |
| Permisos: cada vendedora ve solo lo suyo, con interruptor; rol Caja | Hecho y revisado en la rama `permisos-vendedoras` (sin subir); faltan capturas aprobadas, CI y staging | — |
| Reglas contables de la gerencia: cobro solo en Caja, anular/notas/devoluciones solo Gerencia, abono a 30 días y primer abono del 50 %, Tafi y Crediviva; pedidos web sin vendedora | Hecho en la misma rama (2026-10-17); faltan capturas aprobadas, CI y staging | — |
| Correos con Resend (factura/abono al pagar, bienvenida, cotizaciones) y teléfono+correo obligatorios | En producción y apagado (Desplegar 17): falta que la dueña cree la cuenta de Resend y ponga `RESEND_API_KEY` en GitHub | — |
| Meta: catálogo, píxel y Conversions API | Construido y apagado (ramas `meta-catalogo` y `meta-eventos`); se están uniendo con revisión adversarial y capturas. Falta: decisiones de la dueña, texto de privacidad aprobado por el abogado, píxel y token en Meta Business | — |

## Issues abiertos (revisados el 2026-10-16: 16 abiertos, 3 cerrados)

| Issues | Qué son | Prioridad |
|---|---|---|
| #9, #10, #12 | Lectores y etiquetas de códigos de barras: faltan las pruebas con los aparatos y las etiquetas del proveedor | Alta: sin esto el despacho no se puede verificar (etapa 4) |
| #27 | Puerta del equipo: que el personal entre por `/master`; futuro | Media; antes de traspasar el dominio |
| #25 | Conversaciones: permisos de escritura y seguimiento por persona | Media-alta (seguridad, antes de abrir al público) |
| #26 | Brian: topes de dinero (`ajustar_puntos`, `crear_factura`, `ajustar_existencias` sin tope). El tope de gasto de IA ya existe pero de fábrica está en 0, o sea sin tope | Media-alta; poner las cifras |
| #23, #22 | Privacidad (Ley 81): lo que «Eliminar conversación» no borra | Media; antes de abrir al público |
| #24 | Hallazgos de Juan que quedaron para después | Media |
| #15 y sus hijos #16 a #21 | CRM fase 2: seguimiento de cotizaciones sin respuesta (#16), cotizaciones fuera de la conversación (#21), posventa (#18), invitar a la tienda (#17), perder oportunidades (#20), Brian y oportunidades (#19) | Se eligen con la dueña en la etapa 6; #16 y #21 son los de más valor |

Cerrados: #11, #13 y #14 (códigos de barras, conteo con lector, pantalla de bodega).

## Pendientes viejos que siguen en pie

- **#92** (antes de traspasar el dominio): que `/master` funcione y que «Iniciar sesión» de la web no lleve al panel.
- ~~**#97**: por qué el primer despliegue de una versión deja la base sin actualizar.~~ Resuelto el 2026-10-16
  (Desplegar 9): la imagen decide por la huella de su código, no por la variable `APP_VERSION`.
- Estudio de envíos para La Chorrera: entregado; esperan sus respuestas (ver el documento en Claude Docs).
- Lo que le toca a la dueña: [PENDIENTES_DUENA.md](PENDIENTES_DUENA.md).
