# Prioridades vigentes

Puesto al día el **2026-10-16**, a partir de la tanda de pedidos que hizo el jefe ese día. Este es el orden en que se
trabaja; cada sesión lo revisa al empezar y lo actualiza al terminar (ver [LEEME_PRIMERO.md](LEEME_PRIMERO.md)). El
documento para leer con la dueña y el jefe (con explicaciones y decisiones) está en Claude Docs: «Plan de mejoras del
jefe» (<https://claude.ai/code/artifact/8ffcbb80-6521-4e46-a2a7-8ddc59cb20b2>). Aquí queda el resumen para quien retome el trabajo.

Cada etapa sale a staging para que la dueña la vea; a producción solo con su «sí» explícito (por cada etapa).

**Estado al 2026-10-27:** **`dcasapty.com` ya es el sistema nuevo** (Desplegar 31, `741930d`, sano y confirmado
00:42 UTC; workers.dev sigue respondiendo). Correo: dominio verificado en Resend, `RESEND_API_KEY` pegada por la
dueña en el panel de Cloudflare del Worker `dcasa` (no en GitHub), Email Routing de Cloudflare reenvía `info@` y
cualquier otra dirección @dcasapty.com al Gmail de la empresa (Zoho ya no recibe) y ese Gmail responde como
`info@dcasapty.com` por el SMTP de Resend. Orden: (1) encender en Odoo › Correo a clientes (remitente
`ventas@dcasapty.com`, respuestas a `info@dcasapty.com`, correo de prueba, interruptor); (2) Brian › Telegram ›
«Registrar webhook» (paso 10 del traslado); (3) decidir `app.dcasapty.com` (A a la IP del sistema anterior, en gris);
(4) Google Search Console, Meta y lo impreso (pasos 13-15 de TRASLADO_DOMINIO); (5) lo pendiente del 23 oct (abajo).

**Estado al 2026-10-23, tarde:** en producción (Desplegar 27, PR #62) el arreglo de la lentitud (Bodega/Inicio sin
mirar pagos factura por factura), el reintento del borde ante «Network connection lost.», la nota de entrega sin el
producto repetido y el scroll de Marketing; y (Desplegar 28, PR #63) los combos con el descuento en su propio renglón
y los 4 descuentos aprobados, más lo que hallaron las dos revisiones. Orden: (1) que la dueña mire una cotización con
uno de los 4 colchones; (2) que diga si el sistema se siente más rápido; (3) con la contadora: revisar las cuentas
de los diarios nuevos Visa, Mastercard, American Express, Clave y KrediYa (111.011-111.015), la forma de pago DGI de
KrediYa y Crediviva, y cuándo archivar «Tarjeta» (y si «Punto de venta BN» sigue en uso); (4) seguimiento de velocidad
sin urgencia: `/web/image` lee el
archivo de R2 antes de contestar «no cambió» (304), el ZIP de comprobantes ocupa la CPU seguido mientras se prepara
(pedirlo fuera de horario) y el costo de lo vendido hoy se busca producto por producto en el Inicio; (5) lo de la
lista de abajo. Pendiente menor de la revisión: `abrir` de Bodega no exige pago a una entrega en borrador (muestra
teléfono y dirección); hoy no hay entregas de venta en borrador.

**Estado al 2026-10-23:** en producción también los datos limpios (Desplegar 26, PR #61): nombres en formato
título para el cliente, clave de descuento por Telegram (D1) y abonos por vencer (D3). Orden de lo que sigue: (1) lo
que falta de la dueña para usar lo nuevo (abajo, punto 2 del 22 oct); (2) averiguar por qué Odoo de producción estaba
apagado a las 06:38 UTC del 23 oct si debe estar encendido 24/7 (sin confirmar: registros de Cloudflare del contenedor
de esa hora); (3) encender la portada guardada en el borde en producción (`tienda` sale «falta»: `TIENDA_FEED_TOKEN` y
`TIENDA_ESTATICA`, docs/OPERACION.md); (4) el trabajo contable cuando lleguen las 14 respuestas del jefe; (5) el
traslado del dominio, al final.

**Estado al 2026-10-22, noche:** en producción la tanda del 22 oct (Desplegar 24, PR #60): bodega, Reponer con
llegada, estadísticas por día, Marketing, combos cama + colchón y detalles. Orden de lo que sigue: (1) unir
`datos-clientes` (F5 nombres en formato título para el cliente y MAYÚSCULAS por dentro, decisión de la dueña; 1b(a);
D1 clave por Telegram y centavos; D3 recordatorio de abono), corrida completa, CI, staging y producción; (2) lo que
falta de la dueña para usar lo nuevo: asignar el rol Marketing, el tiempo de llegada de cada proveedor (en el precio de
proveedor), encender las alertas de bodega con sus umbrales, el «precio en combo» de cada colchón (o su «sí,
cárgalos» para los tres del Excel) y las preguntas de combos (tienda en línea, camarotes, combos viejos); (3) el trabajo
contable cuando lleguen las 14 respuestas del jefe; (4) el traslado del dominio, al final.

**Estado al 2026-10-22 (jueves):** la dueña pidió una tanda grande y lo pendiente del jueves. Ocho agentes en paralelo,
cada uno en su worktree (`/home/user/wt-<rama>`, sin `fuentes/`), con las reglas comunes en el scratchpad
(`reglas_agentes.md`): `panel-bodega` (panel de bodega para tablet con QR de la nota), `reponer-llegada` (buscador de
proveedores, ritmo de venta, tiempo de llegada, cuánto pedir, Excel), `estadisticas-dia` (ventas y facturación por día,
estadísticas claras, movimientos de inventario en palabras), `fotos-marketing` (visor y galería de fotos, botón
Marketing), `detalles-contactos` (teléfono fijo de 7 dígitos, íconos de copiar, ícono de la pantalla de inicio = logo,
aviso «Se facturó tu venta…», «Subir» oculto a la vendedora), `combos-armables` (**decisión de la dueña: precio en
combo por colchón y medida**, lo pone Gerencia; sin él, precio normal), `datos-clientes` (F5 mayúsculas y repetidos,
1b(a) costo cerrado, lo que falte de la etapa 3, D1 clave de autorización por Telegram y centavos, D3 recordatorio de
abono) y `planilla-mermas` (F6 mermas con aviso del 0.5 %, bitácora y alertas de bodega, hueco de inventario físico,
G4 comprobante de planilla, G7 adelantos, I6 ZIP de comprobantes). Sigue: integrar, capturas a la dueña, su visto
bueno, CI, staging y producción. La pantalla de entrada de Cloudflare se personaliza en el panel (nombre, logo,
textos, color de fondo; no rediseño completo): lo hace la dueña. El trabajo contable espera las 14 respuestas del jefe.

**Estado al 2026-10-19:** en producción el lote 4 (Desplegar 22): las vendedoras ya no hacen facturas sueltas
(cotizan; la factura sale del pedido y Caja la encuentra), la cámara del lector de códigos se ve en el celular, y
Compras › Reponer para el jefe. Falta que la dueña pruebe la cámara en su iPhone con Chrome y lo confirme. Orden de lo
que sigue (jueves, cuando se renuevan los créditos): (1) bodega (Etapa 4) y datos limpios (Etapas 3 y 1b(a), F5),
ramas locales apenas empezadas; (2) D1 código de descuento al celular, D3 recordatorio de abono, F6 mermas, G4/G7
comprobantes y adelantos, I6 ZIP de comprobantes; (3) el trabajo contable con la gerencia según L1–L8 (las 14
preguntas para el jefe están en Claude Docs: «Preguntas que faltan, en palabras sencillas»); (4) el aviso **«Se
facturó tu venta S00139 (INV/2026/01117)»** en lugar de «Te asignaron… Borrador de factura» (y, si es sencillo, «Tu
venta S00139 ya está cobrada»); (5) cabos del lote 4: la vendedora todavía ve «Subir» en Facturas (el servidor lo
rechaza, pero conviene esconderlo), y exportar Reponer a Excel solo lo hacen los administradores (Odoo lo trae así);
(6) **Reponer con el tiempo de llegada** (la dueña, 19 oct: todo viene de China y pide con 3 a 4 meses de anticipación;
le hablaron de Profit): en Compras › Reponer, por producto, el **ritmo de venta** (unidades por mes de los últimos N
meses, p. ej. 5, elegible), **en cuánto se agota** con la existencia y lo pedido, el **tiempo de llegada** del
proveedor (el campo de días de entrega del precio de proveedor de Odoo, que llenan ellos; nunca uno inventado) y
**cuánto pedir** para cubrir la llegada más los meses de reserva que ellos elijan; con aviso de lo que hay que pedir
ya; (7) el traslado del dominio, con la puerta `/master` obligatoria ese día ([TRASLADO_DOMINIO.md](TRASLADO_DOMINIO.md)).
Lo de abajo (18 oct) queda como historia: K1, cámara, Reponer y vendedoras ya están hechos.

**Estado al 2026-10-18:** la tanda 2 (Inicio de Gerencia sobre facturas + reglas contables de la gerencia y permisos
de vendedoras + pedidos web sin vendedora) está unida y con la revisión cruzada en la rama `tanda2`; sigue CI, staging y
producción. Antes de abrir: rol Caja al jefe administrativo.

**Estado al 2026-10-18, tarde:** en producción la tanda 2 (Desplegar 19: Ajustes, Inicio sobre facturas, reglas
contables) y el lote 3 (Desplegar 20: `/master` con diagnóstico, Mi cuenta, documentación para replicar, Meta apagada).
Todas las preguntas contables respondidas. Orden de lo que sigue: (1) K1 en el Inicio; (2) bodega (Etapa 4) y datos
limpios (Etapas 3 y 1b(a), F5), ramas locales apenas empezadas; (3) D1 código de descuento al celular, D3 recordatorio
de abono, F6 mermas, G4/G7 comprobantes y adelantos, I6 ZIP de comprobantes; (4) el trabajo contable con la gerencia
según L1–L8; (5) cambiar el aviso automático de Odoo «Te asignaron… Borrador de factura» (le llega a la vendedora
cada vez que Caja o Gerencia factura su pedido y confunde: la factura nace en borrador un instante) por uno claro,
**«Se facturó tu venta S00139 (INV/2026/01117)»** (decisión de la dueña, 19 oct); y, si es sencillo, al cobrarse:
«Tu venta S00139 ya está cobrada»; (6) **cámara del lector de códigos en blanco** (la dueña, 19 oct, en su celular): el diálogo «Lector de
códigos de barras» de Odoo (recuadro de recorte y barra de zoom) se ve todo blanco; sí lee códigos, pero no se ve
la imagen para apuntar. La dueña usa **iPhone con Google Chrome** (en iOS, Chrome usa el motor de Safari: probar en WebKit). Reproducir ahí y en Android; sospechas: un estilo propio que tapa o
esconde el `<video>`, o el video sin reproducirse en línea en iOS (`playsinline`/`muted`/`autoplay`); probarlo con
captura del video vivo (Escáner › Contar, y la cámara de los campos de código); (7) **lista de lo vendido para reponer con el proveedor** (pedido del jefe, 19 oct: «cómo puedo pedir un listado de
los artículos vendidos para hacer reposiciones con el proveedor de manera más acertada»): una pantalla «Reponer» para
Gerencia con, por producto y por proveedor, lo vendido en un periodo (con la misma base del Inicio), lo que hay hoy en
existencia y lo pedido que aún no llega; exportable a Excel y agrupable por proveedor, y que Brian la diga
(«¿qué tengo que reponerle a X?»). Sin cifras inventadas: la sugerencia sale solo de esos datos; (8) el traslado del dominio, con la puerta `/master` obligatoria ese día ([TRASLADO_DOMINIO.md](TRASLADO_DOMINIO.md)).

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
| Inicio de Gerencia sobre las **facturas** (A1/A2 del jefe): interruptor Facturado · Con abonos · Completadas, «N de M salieron de un pedido», notas de crédito que restan, ganancia de facturas sin pedido con el costo de hoy, la semana y lo más vendido con la misma base, notas largas en un ícono ⓘ; Brian igual | Unido en la rama `tanda2` con las reglas de la gerencia (2026-10-18). Falta: CI, staging y producción | — |
| Abonos: el papel dice «Abono» con el saldo; condiciones en dos hojas; el cliente ve lo que le falta | En producción (Desplegar 17): papel «ABONO» y condiciones en dos hojas. Sigue: abono mínimo 50 % y 30 días (reglas del jefe, `DECISIONES_CONTABLES.md`) | — |
| Panel del cliente «Mi cuenta» | En producción (Desplegar 17); falta la ronda de pulido de la auditoría visual | — |
| Permisos: cada vendedora ve solo lo suyo, con interruptor; rol Caja | Unido en la rama `tanda2` (2026-10-18); falta CI, staging y producción. Antes de encender: Caja al jefe administrativo | — |
| Reglas contables de la gerencia: cobro solo en Caja, anular/notas/devoluciones solo Gerencia, abono a 30 días y primer abono del 50 %, Tafi y Crediviva; pedidos web sin vendedora | Unido en la rama `tanda2` (2026-10-18); falta CI, staging y producción | — |
| Correos con Resend (factura/abono al pagar, bienvenida, cotizaciones) y teléfono+correo obligatorios | En producción y apagado (Desplegar 17): falta que la dueña cree la cuenta de Resend y ponga `RESEND_API_KEY` en GitHub | — |
| Meta: catálogo, píxel y Conversions API | Construido, unido y revisado en la rama local `meta-unido` (todo apagado de fábrica; revisión adversarial con 10 arreglos y sus pruebas). Siguen: capturas y decisiones de la dueña, CI a staging, el abogado (sección de privacidad), el arreglo de guardar Ajustes (`ajustes-guardar`) y, al trasladar el dominio, conectar en Meta (`META_CATALOGO.md`, `META_EVENTOS.md`) | — |

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

- **#92** (antes de traspasar el dominio): «Iniciar sesión» de la web ya lleva a Mi cuenta (2026-10-18, rama `master-puerta`). `/master` en producción: espera que la dueña revise la aplicación de Access y `DCASA_ACCESS_AUD` ([PUERTA_MASTER.md](PUERTA_MASTER.md)); `/master` ya dice el motivo. Traslado: [TRASLADO_DOMINIO.md](TRASLADO_DOMINIO.md).
- ~~**#97**: por qué el primer despliegue de una versión deja la base sin actualizar.~~ Resuelto el 2026-10-16
  (Desplegar 9): la imagen decide por la huella de su código, no por la variable `APP_VERSION`.
- Estudio de envíos para La Chorrera: entregado; esperan sus respuestas (ver el documento en Claude Docs).
- Lo que le toca a la dueña: [PENDIENTES_DUENA.md](PENDIENTES_DUENA.md).
