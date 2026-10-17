/**
 * «Escáner»: se escanea (o se escribe) un código y sale el producto con su foto, precio «+ ITBMS» y existencias.
 *
 * El lector (Bluetooth, 2.4G, USB o el Android con lector integrado) escribe el código como un teclado y termina con
 * Enter: el cuadro de arriba siempre tiene el foco. En «Contar» (Gerencia) se escribe lo contado, se muestra la
 * diferencia con lo que dice el sistema y solo se guarda al confirmar. En «Asignar» (Gerencia) se escanea una etiqueta
 * numerada del rollo, se elige el producto y ese número queda como su código de barras. Todo lo que se lee o se guarda
 * lo comprueba el servidor (dcasa.barras); aquí no hay reglas de negocio, solo la pantalla.
 *
 * Si lo que se lee es el código QR de un documento (factura, cotización, compra o entrega: …/dcasa/doc/FAC/INV/2026/00001),
 * el servidor dice si quien escanea puede verlo y, si puede, esta pantalla abre el documento.
 */
import { Component, onMounted, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { scanBarcode } from "@web/core/barcode/barcode_dialog";
import { isBarcodeScannerSupported } from "@web/core/barcode/barcode_video_scanner";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

const ETIQUETAS = { disponible: "Disponible", pocas: "Pocas", agotado: "Agotado" };
const ESTADOS_ETIQUETA = { libre: "Sin producto", asignada: "Ya asignada", retirada: "Retirada" };

export class DcasaEscaner extends Component {
    static template = "dcasa_barras.Escaner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.entrada = useRef("entrada");
        this.state = useState({
            texto: "",
            modo: "consultar", // consultar | contar | asignar
            cargando: false,
            ficha: null, // la tarjeta del producto
            opciones: [], // varios productos con ese código, o los que salieron de buscar por nombre
            mensaje: null, // { tipo: "ok" | "aviso" | "error", texto }
            ubicacion: null,
            cantidad: "",
            confirmando: null, // { antes, cantidad, diferencia } mientras se espera el visto bueno
            precio: "", // el precio nuevo que se escribe en «Contar» (sin ITBMS)
            confirmandoPrecio: null, // { antes, nuevo } mientras se espera el visto bueno del precio
            parecido: false, // el producto salió de un código «parecido», no igual: hay que confirmarlo
            // Asignar: la etiqueta escaneada y lo que se va decidiendo. paso: dueno | producto | confirmar.
            asig: null,
            historial: [],
        });
        this.confirmar = useRef("confirmar");
        this.confirmarPrecio = useRef("confirmarPrecio");
        // La cámara del celular como lector (pedido de la dueña, 2026-10-16): solo si el navegador deja usar la cámara.
        this.camaraDisponible = isBarcodeScannerSupported();
        this.busquedaProducto = useRef("busquedaProducto");
        // Asignar etiquetas es de Gerencia: a quien no lo es no se le muestra la pestaña (el servidor lo exige igual).
        this.puedeAsignar = false;
        onWillStart(async () => {
            this.puedeAsignar =
                (await user.hasGroup("stock.group_stock_manager")) && (await user.hasGroup("product.group_product_manager"));
        });
        // Cada búsqueda lleva un número: si llega la respuesta de una vieja cuando ya salió una más nueva, se ignora.
        this.peticion = 0;
        onMounted(() => this.enfocar());
        // Al cambiar de paso en «Asignar» el foco se va a donde se escribe después (la búsqueda o el cuadro del lector).
        useEffect(
            () => this.enfocar(),
            () => [this.state.modo, this.state.asig && this.state.asig.paso, this.state.asig && !!this.state.asig.pregunta]
        );
        // Al terminar una petición el foco vuelve a donde se escribe, ya con la pantalla dibujada (un botón que estaba
        // desactivado mientras tanto no recibe el foco hasta entonces).
        useEffect(
            () => {
                if (!this.state.cargando) {
                    this.enfocar();
                }
            },
            () => [this.state.cargando]
        );
        // Al pedir el visto bueno de un conteo el foco pasa al botón de confirmar: Enter confirma y un escaneo no cae en
        // el cuadro de cantidad. Se hace cuando el botón ya está dibujado (no con un temporizador, que a veces llega antes).
        useEffect(
            () => {
                if (this.state.confirmando && this.confirmar.el) {
                    this.confirmar.el.focus();
                }
            },
            () => [!!this.state.confirmando]
        );
        useEffect(
            () => {
                if (this.state.confirmandoPrecio && this.confirmarPrecio.el) {
                    this.confirmarPrecio.el.focus();
                }
            },
            () => [!!this.state.confirmandoPrecio]
        );
    }

    // --- Entrada ----------------------------------------------------------------------------------------------
    destinoDelFoco() {
        const a = this.state.asig;
        if (this.state.modo === "asignar" && a) {
            if (a.paso === "producto" && this.busquedaProducto.el) {
                return this.busquedaProducto.el;
            }
        }
        return this.entrada.el;
    }

    enfocar() {
        const campo = this.destinoDelFoco();
        if (campo) {
            campo.focus();
            if (campo.select) {
                campo.select();
            }
        }
    }

    alPerderFoco() {
        // Si el foco se fue al fondo de la página (un toque en blanco), el lector escribiría en el vacío: se recupera.
        setTimeout(() => {
            if (document.activeElement === document.body && !this.state.confirmando && !this.state.confirmandoPrecio) {
                this.enfocar();
            }
        }, 60);
    }

    alTeclear(ev) {
        // Casi todos los lectores terminan con Enter; algunos con Tab.
        if ((ev.key === "Enter" || ev.key === "Tab") && this.state.texto.trim()) {
            ev.preventDefault();
            this.escanear();
        } else if (ev.key === "Enter" && this.state.modo === "asignar" && this.state.asig?.paso === "confirmar") {
            // Con el cuadro vacío, Enter confirma. Un escaneo escribe el código antes del Enter: eso es otra etiqueta
            // y no confirma nada.
            ev.preventDefault();
            this.confirmarAsignacion();
        }
    }

    get textoDeAyuda() {
        return this.state.modo === "asignar" ? "Escanea la etiqueta que vas a pegar" : "Escanea el código o escríbelo";
    }

    get textoDeEjemplo() {
        if (this.state.modo !== "asignar") {
            return "Código, referencia o nombre";
        }
        return this.state.asig?.paso === "confirmar"
            ? "Enter para asignar, o escanea otra etiqueta"
            : "Etiqueta (por ejemplo DC0001)";
    }

    async escanear() {
        const codigo = this.state.texto.trim();
        if (!codigo) {
            return;
        }
        // El lector ya escribió: el cuadro queda libre para el siguiente código, aunque este siga en camino. Se limpia
        // también el cuadro mismo: un lector escribe el código y el Enter dentro del mismo cuadro de pantalla, y si
        // el estado cambia dos veces antes de dibujar, el cuadro se quedaría con el código viejo.
        this.state.texto = "";
        if (this.entrada.el) {
            this.entrada.el.value = "";
        }
        await this.procesarCodigo(codigo);
    }

    /** Lee el código con la cámara del celular y sigue igual que si lo hubiera escrito la pistola. */
    async escanearConCamara() {
        let codigo;
        try {
            codigo = await scanBarcode(this.env, "environment");
        } catch {
            this.avisar("error", "No se pudo usar la cámara. Revisa que el navegador tenga permiso para usarla.");
            return;
        }
        codigo = String(codigo || "").trim();
        if (codigo) {
            await this.procesarCodigo(codigo);
        }
    }

    async procesarCodigo(codigo) {
        const mia = ++this.peticion;
        this.state.cargando = true;
        this.state.mensaje = null;
        try {
            if (this.state.modo === "asignar") {
                await this.escanearEtiqueta(codigo, mia);
                return;
            }
            const r = await this.orm.call("dcasa.barras", "buscar", [codigo]);
            if (mia !== this.peticion) {
                return; // llegó la respuesta de un escaneo viejo: manda el más nuevo
            }
            if (r.resultado === "documento") {
                this.limpiarProducto();
                this.sonar(true);
                await this.action.doAction(r.documento.accion);
            } else if (r.resultado === "documento_sin_permiso" || r.resultado === "documento_no_existe") {
                this.limpiarProducto();
                this.avisar("error", r.documento.mensaje);
                this.sonar(false);
            } else if (r.resultado === "ok") {
                this.mostrarFicha(r.productos[0], codigo, r.forma === "parecido");
            } else if (r.resultado === "varios") {
                this.limpiarProducto();
                this.state.opciones = r.productos;
                this.avisar("aviso", `Hay ${r.productos.length} productos con «${r.codigo}». Elige el correcto.`);
                this.sonar(false);
            } else {
                await this.noEncontrado(codigo, mia, r.retirada, r.archivado);
            }
        } catch (e) {
            if (mia === this.peticion) {
                this.fallo(e);
            }
        } finally {
            if (mia === this.peticion) {
                this.state.cargando = false;
            }
            this.enfocar();
        }
    }

    async noEncontrado(codigo, mia, retirada, archivado) {
        this.limpiarProducto();
        this.sonar(false);
        if (archivado) {
            this.avisar("aviso", `El código «${codigo}» es del producto «${archivado.producto}», que está archivado.`);
            return;
        }
        if (retirada) {
            const motivo = retirada.motivo ? ` (${retirada.motivo})` : "";
            this.avisar(
                "aviso",
                `La etiqueta «${codigo}» está retirada: era de «${retirada.producto}»${motivo} y ya no es de ningún producto.`
            );
            return;
        }
        const parecidos = await this.orm.call("dcasa.barras", "buscar_por_nombre", [codigo]);
        if (mia !== this.peticion) {
            return;
        }
        this.state.opciones = parecidos;
        this.avisar(
            "aviso",
            parecidos.length
                ? `No hay ningún producto con el código «${codigo}». Quizá sea alguno de estos:`
                : `No hay ningún producto con el código «${codigo}». Revisa que esté bien escrito.`
        );
    }

    async elegir(opcion) {
        const mia = ++this.peticion;
        this.state.cargando = true;
        try {
            const ficha = await this.orm.call("dcasa.barras", "ficha", [opcion.id]);
            if (mia === this.peticion) {
                this.mostrarFicha(ficha, ficha.codigo_de_barras || ficha.referencia, false);
            }
        } catch (e) {
            if (mia === this.peticion) {
                this.fallo(e);
            }
        } finally {
            if (mia === this.peticion) {
                this.state.cargando = false;
            }
            this.enfocar();
        }
    }

    // --- Tarjeta ------------------------------------------------------------------------------------------------
    mostrarFicha(ficha, codigo, parecido) {
        this.state.ficha = ficha;
        this.state.opciones = [];
        this.state.mensaje = null;
        this.state.parecido = !!parecido;
        this.state.confirmando = null;
        this.state.ubicacion = ficha.ubicacion_habitual;
        this.state.cantidad = "";
        this.state.precio = "";
        this.state.confirmandoPrecio = null;
        this.sonar(!parecido);
        this.anotar("consulta", ficha, `Escaneado ${codigo}`);
    }

    esEste() {
        this.state.parecido = false;
        this.enfocar();
    }

    limpiarProducto() {
        this.state.ficha = null;
        this.state.parecido = false;
        this.state.opciones = [];
        this.state.confirmando = null;
        this.state.confirmandoPrecio = null;
    }

    cambiarModo(modo) {
        this.peticion++; // lo que estaba en camino ya no corresponde a esta pestaña
        this.state.cargando = false;
        this.state.modo = modo;
        this.state.confirmando = null;
        this.state.confirmandoPrecio = null;
        this.state.mensaje = null;
        this.state.asig = null;
        this.enfocar();
    }

    get etiqueta() {
        return ETIQUETAS[this.state.ficha?.etiqueta] || "";
    }

    cifra(numero) {
        if (numero === null || numero === undefined) {
            return "—";
        }
        return Number.isInteger(numero) ? String(numero) : numero.toFixed(2);
    }

    get existenciaAqui() {
        const aqui = (this.state.ficha?.ubicaciones || []).find((u) => u.id === this.state.ubicacion);
        return aqui ? aqui.cantidad : 0;
    }

    // --- Contar -------------------------------------------------------------------------------------------------
    get lugarContado() {
        const lugar = (this.state.ficha?.lugares_para_contar || []).find((u) => u.id === this.state.ubicacion);
        return lugar ? lugar.nombre : "";
    }

    alTeclearCantidad(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.pedirConfirmacion();
        }
    }

    pedirConfirmacion() {
        const texto = String(this.state.cantidad).trim();
        // Solo dígitos y, si la unidad lo admite, un punto decimal: «1,200» se leería como 1.2 y dejaría el stock mal.
        if (!/^\d+(\.\d+)?$/.test(texto)) {
            this.avisar("error", "Escribe solo el número contado, sin comas ni letras (los decimales van con punto).");
            return;
        }
        const cantidad = Number(texto);
        if (!this.state.ficha.admite_decimales && !Number.isInteger(cantidad)) {
            this.avisar("error", `Este producto se cuenta en ${this.state.ficha.unidad} enteras: sin decimales.`);
            return;
        }
        const antes = this.existenciaAqui;
        this.state.confirmando = { antes, cantidad, diferencia: cantidad - antes };
        this.state.mensaje = null;
    }

    cancelarConteo() {
        this.state.confirmando = null;
        this.enfocar();
    }

    async confirmarConteo() {
        const c = this.state.confirmando;
        if (!c || this.state.cargando) {
            return;
        }
        this.state.cargando = true;
        try {
            const r = await this.orm.call("dcasa.barras", "contar", [
                this.state.ficha.id,
                this.state.ubicacion,
                c.cantidad,
                c.antes, // lo que vio quien contó: si el sistema cambió mientras tanto, el servidor no guarda
            ]);
            this.state.ficha = r.ficha;
            this.state.confirmando = null;
            this.state.cantidad = "";
            if (r.cambio) {
                const signo = r.diferencia > 0 ? "+" : "";
                this.avisar("ok", `Conteo guardado: había ${this.cifra(r.antes)}, ahora ${this.cifra(r.despues)} (${signo}${this.cifra(r.diferencia)}).`);
                this.anotar("conteo", r.ficha, `Contado: ${this.cifra(r.antes)} → ${this.cifra(r.despues)}`);
            } else {
                this.avisar("aviso", "Coincide con lo que ya decía el sistema: no hubo nada que ajustar.");
            }
            this.sonar(true);
        } catch (e) {
            this.fallo(e);
        } finally {
            this.state.cargando = false;
            this.enfocar();
        }
    }

    // --- Precio (en «Contar», Gerencia) -----------------------------------------------------------------------
    alTeclearPrecio(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.revisarPrecio();
        }
    }

    revisarPrecio() {
        const texto = String(this.state.precio).trim().replace(/^\$/, "");
        // Solo dígitos y, si hace falta, un punto y dos decimales: «1,299» se leería como 1.299.
        if (!/^\d+(\.\d{1,2})?$/.test(texto)) {
            this.avisar("error", "Escribe el precio sin ITBMS, solo con números y punto para los centavos (por ejemplo 399.99).");
            return;
        }
        this.state.confirmandoPrecio = { antes: this.state.ficha.precio, nuevo: Number(texto) };
        this.state.mensaje = null;
    }

    cancelarPrecio() {
        this.state.confirmandoPrecio = null;
        this.enfocar();
    }

    async guardarPrecio() {
        const p = this.state.confirmandoPrecio;
        if (!p || this.state.cargando) {
            return;
        }
        this.state.cargando = true;
        try {
            const r = await this.orm.call("dcasa.barras", "cambiar_precio", [this.state.ficha.id, p.nuevo, p.antes]);
            this.state.ficha = r.ficha;
            this.state.confirmandoPrecio = null;
            this.state.precio = "";
            if (r.cambio) {
                this.avisar("ok", `Precio guardado: antes ${this.dinero(r.antes)}, ahora ${this.dinero(r.despues)} + ITBMS.`);
                this.anotar("precio", r.ficha, `Precio: ${this.dinero(r.antes)} → ${this.dinero(r.despues)}`);
            } else {
                this.avisar("aviso", "Es el mismo precio que ya tenía: no hubo nada que cambiar.");
            }
            this.sonar(true);
        } catch (e) {
            this.fallo(e);
        } finally {
            this.state.cargando = false;
            this.enfocar();
        }
    }

    dinero(valor) {
        return "$" + new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(valor || 0);
    }

    // --- Asignar etiqueta ---------------------------------------------------------------------------------------
    async escanearEtiqueta(codigo, mia) {
        const r = await this.orm.call("dcasa.barras", "etiqueta", [codigo]);
        if (mia !== this.peticion) {
            return; // llegó la respuesta de un escaneo viejo: manda el más nuevo
        }
        this.state.asig = {
            codigo: r.codigo,
            estado: r.estado, // libre | asignada | retirada
            dueno: r.producto, // la tarjeta del producto que ya tiene la etiqueta
            antes: r.antes, // de quién fue, si está retirada
            paso: r.estado === "asignada" ? "dueno" : "producto",
            busqueda: "",
            opciones: [],
            elegido: null,
            pregunta: null, // lo que el servidor pidió confirmar si la etiqueta cambió de dueño mientras tanto
            // Lo que se le mostró a la persona: el servidor solo toma una etiqueta ajena o retirada si sigue igual.
            visto: { estado: r.estado, dueno_id: r.producto ? r.producto.id : false },
        };
        this.sonar(r.estado !== "retirada");
    }

    get estadoDeLaEtiqueta() {
        return ESTADOS_ETIQUETA[this.state.asig?.estado] || "";
    }

    get botonAsignar() {
        return this.state.asig?.pregunta ? "Sí, asignarla" : "Asignar etiqueta";
    }

    cancelarAsignacion() {
        this.state.asig = null;
        this.state.mensaje = null;
        this.enfocar();
    }

    pasarAOtro() {
        const a = this.state.asig;
        a.paso = "producto";
        a.busqueda = "";
        a.opciones = [];
    }

    volverABuscar() {
        const a = this.state.asig;
        a.paso = "producto";
        a.elegido = null;
        a.pregunta = null;
    }

    alTeclearBusqueda(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        ev.preventDefault();
        const texto = this.state.asig ? this.state.asig.busqueda.trim() : "";
        if (this.parecidaALaEtiqueta(texto)) {
            // El lector escribió otra etiqueta del rollo (misma forma: letras y el mismo largo de número) en el cuadro de
            // buscar: es un escaneo, no el nombre de un producto.
            this.state.asig.busqueda = "";
            if (this.busquedaProducto.el) {
                this.busquedaProducto.el.value = "";
            }
            this.procesarCodigo(texto);
        } else {
            this.buscarProducto();
        }
    }

    parecidaALaEtiqueta(texto) {
        const forma = (codigo) => /^([A-Za-z]+)(\d+)$/.exec(codigo);
        const actual = this.state.asig && forma(this.state.asig.codigo);
        const escrita = forma(texto);
        return !!(
            actual &&
            escrita &&
            actual[1].toUpperCase() === escrita[1].toUpperCase() &&
            actual[2].length === escrita[2].length
        );
    }

    async buscarProducto() {
        const a = this.state.asig;
        const texto = a ? a.busqueda.trim() : "";
        if (!a || this.state.cargando) {
            return;
        }
        if (texto.length < 2) {
            this.avisar("aviso", "Escribe al menos dos letras del nombre o de la referencia.");
            return;
        }
        const mia = ++this.peticion;
        this.state.cargando = true;
        this.state.mensaje = null;
        try {
            const opciones = await this.orm.call("dcasa.barras", "buscar_por_nombre", [texto]);
            if (mia !== this.peticion || !this.state.asig) {
                return;
            }
            this.state.asig.opciones = opciones;
            if (!opciones.length) {
                this.avisar("aviso", `No encontré productos con «${texto}». Prueba con otra palabra o con la referencia.`);
            }
        } catch (e) {
            if (mia === this.peticion) {
                this.fallo(e);
            }
        } finally {
            if (mia === this.peticion) {
                this.state.cargando = false;
            }
        }
    }

    async elegirParaEtiqueta(opcion) {
        const mia = ++this.peticion;
        this.state.cargando = true;
        try {
            const ficha = await this.orm.call("dcasa.barras", "ficha", [opcion.id]);
            if (mia === this.peticion && this.state.asig) {
                this.state.mensaje = null;
                this.state.asig.elegido = ficha;
                this.state.asig.pregunta = null;
                this.state.asig.paso = "confirmar";
            }
        } catch (e) {
            if (mia === this.peticion) {
                this.fallo(e);
            }
        } finally {
            if (mia === this.peticion) {
                this.state.cargando = false;
            }
        }
    }

    async confirmarAsignacion() {
        const a = this.state.asig;
        if (!a || !a.elegido || this.state.cargando) {
            return;
        }
        this.state.cargando = true;
        try {
            const r = await this.orm.call("dcasa.barras", "asignar_etiqueta", [a.codigo, a.elegido.id, a.visto]);
            if (r.resultado === "confirmar") {
                // La etiqueta no está como se le mostró a la persona (otra persona la pasó mientras tanto): se le
                // muestra cómo está ahora y se espera otro clic, que ya vale para lo nuevo.
                a.pregunta = r;
                a.visto = {
                    estado: r.motivo === "dueno" ? "asignada" : "retirada",
                    dueno_id: r.dueno ? r.dueno.id : false,
                };
                return;
            }
            const nombre = a.elegido.nombre;
            if (r.resultado === "igual") {
                this.avisar("aviso", `«${nombre}» ya tenía la etiqueta ${a.codigo}: no hubo nada que cambiar.`);
            } else {
                const antes = r.etiqueta_anterior ? ` (la ${r.etiqueta_anterior} quedó retirada)` : "";
                const dueno = r.dueno_anterior ? ` «${r.dueno_anterior}» se quedó sin etiqueta.` : "";
                this.avisar("ok", `Listo: ${a.codigo} es ahora de «${nombre}»${antes}.${dueno}`);
                this.anotar("etiqueta", r.ficha, `Etiqueta ${a.codigo}`);
            }
            this.cerrarAsignacion(a.codigo);
            this.sonar(true);
        } catch (e) {
            this.fallo(e);
        } finally {
            this.state.cargando = false;
            this.enfocar();
        }
    }

    cerrarAsignacion(codigo) {
        // Si mientras tanto se escaneó otra etiqueta, esa sigue en pantalla.
        if (this.state.asig && this.state.asig.codigo === codigo) {
            this.state.asig = null;
        }
    }

    quitarEtiqueta() {
        const a = this.state.asig;
        if (!a || !a.dueno) {
            return;
        }
        const { id, nombre } = a.dueno;
        this.dialog.add(ConfirmationDialog, {
            title: "Quitar la etiqueta",
            body: `¿Quitar la etiqueta ${a.codigo} de «${nombre}»? El producto se queda sin código de barras y el número queda retirado.`,
            confirmLabel: "Sí, quitarla",
            cancelLabel: "No",
            confirm: () => this.confirmarQuitar(id, a.codigo),
            cancel: () => this.enfocar(),
        });
    }

    async confirmarQuitar(productoId, codigo) {
        this.state.cargando = true;
        try {
            const r = await this.orm.call("dcasa.barras", "quitar_etiqueta", [productoId, codigo]);
            this.avisar("ok", `Listo: «${r.ficha.nombre}» ya no tiene etiqueta; la ${codigo} quedó retirada.`);
            this.anotar("etiqueta", r.ficha, `Quitada ${codigo}`);
            this.cerrarAsignacion(codigo);
            this.sonar(true);
        } catch (e) {
            this.fallo(e);
        } finally {
            this.state.cargando = false;
            this.enfocar();
        }
    }

    // --- Avisos y sonido -----------------------------------------------------------------------------------------
    avisar(tipo, texto) {
        this.state.mensaje = { tipo, texto };
    }

    fallo(e) {
        const texto = e?.data?.message || e?.message || "No se pudo completar. Inténtalo otra vez.";
        this.avisar("error", texto);
        this.sonar(false);
    }

    anotar(tipo, ficha, detalle) {
        this.state.historial.unshift({ id: Date.now() + Math.random(), tipo, nombre: ficha.nombre, detalle });
        this.state.historial.splice(15);
    }

    sonar(bien) {
        // Un pitido corto: agudo si salió bien, grave si no. Si el aparato no lo permite, no pasa nada.
        try {
            const Audio = window.AudioContext || window.webkitAudioContext;
            if (!Audio) {
                return;
            }
            this.audio = this.audio || new Audio();
            const oscilador = this.audio.createOscillator();
            const volumen = this.audio.createGain();
            oscilador.frequency.value = bien ? 1100 : 300;
            volumen.gain.value = 0.08;
            oscilador.connect(volumen);
            volumen.connect(this.audio.destination);
            oscilador.start();
            oscilador.stop(this.audio.currentTime + (bien ? 0.09 : 0.25));
            if (!bien && navigator.vibrate) {
                navigator.vibrate(120);
            }
        } catch {
            // sin sonido
        }
    }
}

registry.category("actions").add("dcasa_barras_escaner", DcasaEscaner);
