/**
 * «Bodega»: las entregas pendientes para despachar o retirar, pensado primero para una tablet.
 *
 * Lista: tarjetas grandes, separadas en «Para despachar (envío)» y «Para retirar en tienda» (y «Sin definir» cuando el
 * pedido no lo dice), con filtros «Listas para salir» / «Esperando producto». Arriba, un cuadro donde escribe el lector
 * (tipo teclado) o se busca por cliente, número o pedido; el botón «Cámara» lee con la cámara (scanBarcode de Odoo).
 * Escanear el QR de la nota de entrega (o el de la factura o el pedido) abre esa entrega. Se actualiza sola.
 *
 * Entrega abierta: cliente, teléfono, dirección, pedido y la lista de productos con foto. Se marca lo que sale con los
 * botones o escaneando cada producto. «Validar entrega»: si está todo, valida; si falta algo, pregunta en sencillo si se
 * entrega solo lo marcado (lo demás queda pendiente) o se vuelve. Todo lo comprueba el servidor (dcasa.bodega).
 *
 * En una tablet sin lector, el cuadro con el foco no debe sacar el teclado de la pantalla a cada rato: tiene
 * inputmode="none" hasta que la persona lo toca para escribir.
 */
import { Component, onMounted, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { scanBarcode } from "@web/core/barcode/barcode_dialog";
import { isBarcodeScannerSupported } from "@web/core/barcode/barcode_video_scanner";
import { useService } from "@web/core/utils/hooks";

const REFRESCO_MS = 60000; // la lista se vuelve a pedir cada minuto mientras está a la vista
// «corto»: lo que dice la pestaña en el celular, para que quepan sin ocupar media pantalla.
const COMOS = [
    { clave: "todas", texto: "Todas", corto: "Todas" },
    { clave: "envio", texto: "Para despachar (envío)", corto: "Envío" },
    { clave: "retiro", texto: "Para retirar en tienda", corto: "Retiro" },
    { clave: "sin_definir", texto: "Sin definir", corto: "Sin definir" },
];
const ICONOS_COMO = { envio: "fa-truck", retiro: "fa-shopping-bag", sin_definir: "fa-question-circle" };

/** Sin tildes ni mayúsculas: «Peña» se encuentra escribiendo «pena». */
export function normalizar(texto) {
    return String(texto || "")
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase();
}

/** ¿Lo que llegó parece la dirección de un QR de documento (…/dcasa/doc/…)? Va directo al servidor. */
export function pareceQr(texto) {
    return /dcasa[^0-9a-z]{1,2}doc[^0-9a-z]/i.test(texto || "");
}

export function cifra(numero) {
    const n = Number(numero) || 0;
    return Number.isInteger(n) ? String(n) : String(Math.round(n * 1000) / 1000);
}

export class DcasaBodega extends Component {
    static template = "dcasa_barras.Bodega";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.entrada = useRef("entrada");
        this.lector = useRef("lector");
        this.confirmarBoton = useRef("confirmarBoton");
        this.comos = COMOS;
        this.iconosComo = ICONOS_COMO;
        this.cifra = cifra;
        this.camaraDisponible = isBarcodeScannerSupported();
        // Pantalla táctil (tablet o celular): el cuadro del lector no saca el teclado hasta que se toca.
        this.tactil = !!window.matchMedia?.("(pointer: coarse)").matches;
        this.state = useState({
            vista: "lista", // lista | entrega
            cargando: false,
            lista: [],
            cuantas: 0,
            recortada: false,
            hora: "",
            como: "todas",
            filtroEstado: "todas", // todas | listas | esperando
            texto: "",
            conProducto: null, // { ids, nombre }: se escaneó un producto en la lista
            soloIds: null, // { ids, mensaje }: varias entregas del mismo pedido o factura
            mensaje: null, // { tipo: ok | aviso | error, texto }
            exito: null, // { mensaje, imprimir, pendiente, pendienteId }
            entrega: null,
            marcas: {},
            lectorTexto: "",
            confirmar: null, // { faltan, deja_pendiente }
            validando: false,
            teclado: false,
        });
        this.peticion = 0;
        onWillStart(async () => {
            await this.cargarLista();
            const inicial = this.props.resId || this.props.action?.params?.entrega_id;
            if (inicial) {
                await this.abrir(Number(inicial));
            }
        });
        onMounted(() => {
            this.enfocar();
            this.reloj = setInterval(() => this.refrescar(), REFRESCO_MS);
            this.alVolverALaVista = () => {
                if (document.visibilityState === "visible") {
                    this.refrescar();
                }
            };
            document.addEventListener("visibilitychange", this.alVolverALaVista);
        });
        onWillUnmount(() => {
            clearInterval(this.reloj);
            document.removeEventListener("visibilitychange", this.alVolverALaVista);
        });
        useEffect(
            () => {
                if (!this.state.cargando && !this.state.validando && !this.state.confirmar) {
                    this.enfocar();
                }
            },
            () => [this.state.vista, this.state.cargando, this.state.validando, !!this.state.confirmar]
        );
        useEffect(
            () => {
                if (this.state.confirmar && this.confirmarBoton.el) {
                    this.confirmarBoton.el.focus();
                }
            },
            () => [!!this.state.confirmar]
        );
    }

    // --- Foco y teclado de la pantalla ---------------------------------------------------------------------------
    get campoActivo() {
        return this.state.vista === "entrega" ? this.lector.el : this.entrada.el;
    }

    get modoDeEntrada() {
        return this.tactil && !this.state.teclado ? "none" : "search";
    }

    enfocar() {
        const campo = this.campoActivo;
        if (campo && document.activeElement !== campo) {
            campo.focus({ preventScroll: true });
        }
    }

    /** Al tocar el cuadro en una tablet: ahora sí sale el teclado para escribir. */
    alTocarCampo(ev) {
        if (this.tactil && !this.state.teclado) {
            this.tocando = true;
            this.state.teclado = true;
            ev.currentTarget.setAttribute("inputmode", "search");
            ev.currentTarget.blur(); // al terminar el toque se vuelve a enfocar y ahora sí sale el teclado
            setTimeout(() => {
                this.tocando = false;
                if (document.activeElement === document.body && !this.state.confirmar) {
                    this.enfocar();
                }
            }, 600);
        }
    }

    alPerderFoco() {
        if (this.tocando) {
            return;
        }
        this.state.teclado = false;
        // Si el foco se fue al fondo (un toque en blanco), el lector escribiría en el vacío: se recupera.
        setTimeout(() => {
            if (document.activeElement === document.body && !this.state.confirmar && !this.tocando) {
                this.enfocar();
            }
        }, 80);
    }

    // --- Lista ---------------------------------------------------------------------------------------------------
    async cargarLista({ silencioso = false } = {}) {
        if (!silencioso) {
            this.state.cargando = true;
        }
        try {
            const r = await this.orm.call("dcasa.bodega", "pendientes", []);
            this.state.lista = r.entregas;
            this.state.cuantas = r.cuantas;
            this.state.recortada = r.recortada;
            this.state.hora = r.hora;
        } catch (e) {
            if (!silencioso) {
                this.fallo(e);
            }
        } finally {
            this.state.cargando = false;
        }
    }

    refrescar() {
        if (this.state.vista === "lista" && !this.state.cargando && document.visibilityState !== "hidden") {
            this.cargarLista({ silencioso: true });
        }
    }

    async actualizar() {
        this.state.mensaje = null;
        await this.cargarLista();
        this.enfocar();
    }

    cuantasPorComo(clave) {
        return clave === "todas" ? this.state.lista.length : this.state.lista.filter((e) => e.como === clave).length;
    }

    get comosVisibles() {
        // «Sin definir» solo sale si hay alguna (o si es la pestaña elegida).
        return this.comos.filter(
            (c) => c.clave !== "sin_definir" || this.cuantasPorComo("sin_definir") || this.state.como === "sin_definir"
        );
    }

    get delComo() {
        const como = this.state.como;
        return como === "todas" ? this.state.lista : this.state.lista.filter((e) => e.como === como);
    }

    cuantasPorEstado(clave) {
        const lista = this.delComo;
        if (clave === "listas") {
            return lista.filter((e) => e.estado === "lista").length;
        }
        if (clave === "esperando") {
            return lista.filter((e) => e.estado !== "lista").length;
        }
        return lista.length;
    }

    get tarjetas() {
        let lista = this.delComo;
        if (this.state.filtroEstado === "listas") {
            lista = lista.filter((e) => e.estado === "lista");
        } else if (this.state.filtroEstado === "esperando") {
            lista = lista.filter((e) => e.estado !== "lista");
        }
        if (this.state.soloIds) {
            const ids = new Set(this.state.soloIds.ids);
            lista = lista.filter((e) => ids.has(e.id));
        }
        if (this.state.conProducto) {
            const ids = new Set(this.state.conProducto.ids);
            lista = lista.filter((e) => e.producto_ids.some((id) => ids.has(id)));
        }
        const palabras = normalizar(this.state.texto).split(/\s+/).filter(Boolean);
        if (palabras.length && !pareceQr(this.state.texto)) {
            lista = lista.filter((e) => {
                const donde = normalizar(e.buscar);
                return palabras.every((p) => donde.includes(p));
            });
        }
        return lista;
    }

    elegirComo(clave) {
        this.state.como = clave;
        this.enfocar();
    }

    elegirEstado(clave) {
        this.state.filtroEstado = clave;
        this.enfocar();
    }

    quitarFiltros() {
        this.state.texto = "";
        this.state.conProducto = null;
        this.state.soloIds = null;
        this.state.mensaje = null;
        if (this.entrada.el) {
            this.entrada.el.value = "";
        }
        this.enfocar();
    }

    verTodas() {
        this.state.como = "todas";
        this.state.filtroEstado = "todas";
        this.quitarFiltros();
    }

    alTeclearEnLista(ev) {
        if ((ev.key === "Enter" || ev.key === "Tab") && this.state.texto.trim()) {
            ev.preventDefault();
            this.buscarEnLista();
        } else if (ev.key === "Escape") {
            this.quitarFiltros();
        }
    }

    async buscarEnLista() {
        const texto = this.state.texto.trim();
        if (!texto) {
            return;
        }
        // Escribiendo: si una sola entrega coincide, Enter la abre.
        if (!pareceQr(texto)) {
            const coinciden = this.tarjetas;
            if (coinciden.length === 1) {
                await this.abrir(coinciden[0].id);
                return;
            }
        }
        await this.procesarCodigo(texto);
    }

    // --- Lo que leyó el lector o la cámara ---------------------------------------------------------------------------
    async escanearConCamara() {
        let codigo;
        try {
            codigo = await scanBarcode(this.env, "environment");
        } catch {
            this.avisar("error", "No se pudo usar la cámara. Revisa que el navegador tenga permiso para usarla.");
            this.sonar(false);
            return;
        }
        codigo = String(codigo || "").trim();
        if (codigo) {
            await this.procesarCodigo(codigo);
        } else {
            this.enfocar();
        }
    }

    async procesarCodigo(codigo) {
        const enEntrega = this.state.vista === "entrega" && this.state.entrega;
        const mia = ++this.peticion;
        this.state.cargando = true;
        this.state.mensaje = null;
        try {
            const r = await this.orm.call("dcasa.bodega", "leer", [codigo, enEntrega ? this.state.entrega.id : false]);
            if (mia !== this.peticion) {
                return; // llegó la respuesta de una lectura vieja: manda la más nueva
            }
            if (enEntrega) {
                await this.leidoEnEntrega(r, codigo);
            } else {
                await this.leidoEnLista(r, codigo);
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

    limpiarCuadro() {
        this.state.texto = "";
        if (this.entrada.el) {
            this.entrada.el.value = "";
        }
    }

    async leidoEnLista(r, codigo) {
        if (r.resultado === "entrega") {
            this.limpiarCuadro();
            this.sonar(true);
            this.mostrarEntrega(r.entrega);
        } else if (r.resultado === "entregas") {
            this.limpiarCuadro();
            this.state.conProducto = null;
            this.state.soloIds = { ids: r.ids, mensaje: r.mensaje };
            this.state.como = "todas";
            this.state.filtroEstado = "todas";
            this.sonar(true);
        } else if (r.resultado === "producto") {
            this.limpiarCuadro();
            this.state.soloIds = null;
            this.state.conProducto = { ids: r.producto_ids, nombre: r.nombre };
            this.sonar(true);
        } else if (r.resultado === "aviso") {
            this.limpiarCuadro();
            this.avisar(r.sin_pago ? "error" : "aviso", r.mensaje);
            this.sonar(false);
        } else if (!this.tarjetas.length) {
            this.avisar("aviso", `No hay entregas pendientes con «${codigo}».`);
            this.sonar(false);
        }
    }

    async leidoEnEntrega(r, codigo) {
        this.state.lectorTexto = "";
        if (this.lector.el) {
            this.lector.el.value = "";
        }
        if (r.resultado === "producto") {
            this.marcarPorProducto(r.producto_ids, r.nombre);
        } else if (r.resultado === "entrega") {
            await this.cambiarA(r.entrega);
        } else if (r.resultado === "misma") {
            this.avisar("aviso", r.mensaje);
            this.sonar(true);
        } else if (r.resultado === "entregas" || r.resultado === "aviso") {
            this.avisar(r.sin_pago ? "error" : "aviso", r.mensaje);
            this.sonar(false);
        } else {
            this.avisar("error", `«${codigo}» no es un producto de esta entrega ni el QR de una nota de entrega.`);
            this.sonar(false);
        }
    }

    // --- Abrir una entrega -----------------------------------------------------------------------------------------
    async abrir(id) {
        const mia = ++this.peticion;
        this.state.cargando = true;
        this.state.mensaje = null;
        try {
            const entrega = await this.orm.call("dcasa.bodega", "abrir", [id]);
            if (mia === this.peticion) {
                this.mostrarEntrega(entrega);
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

    mostrarEntrega(entrega) {
        this.state.entrega = entrega;
        this.state.marcas = Object.fromEntries(entrega.lineas.map((l) => [l.id, 0]));
        this.state.confirmar = null;
        this.state.exito = null;
        this.state.lectorTexto = "";
        this.state.vista = "entrega";
        this.props.updateActionState?.({ resId: entrega.id });
        window.scrollTo?.(0, 0);
        const raiz = document.querySelector(".o_dcasa_bodega");
        if (raiz) {
            raiz.scrollTop = 0;
        }
    }

    get hayMarcas() {
        return Object.values(this.state.marcas).some((n) => n > 0);
    }

    async cambiarA(entrega) {
        if (!this.hayMarcas) {
            this.sonar(true);
            this.mostrarEntrega(entrega);
            return;
        }
        this.sonar(true);
        this.dialog.add(ConfirmationDialog, {
            title: "¿Cambiar de entrega?",
            body: `Escaneaste la nota de ${entrega.nombre}. Lo que marcaste en ${this.state.entrega.nombre} se pierde.`,
            confirmLabel: `Abrir ${entrega.nombre}`,
            cancelLabel: "Seguir aquí",
            confirm: () => this.mostrarEntrega(entrega),
            cancel: () => {},
        });
    }

    volver() {
        const salir = () => {
            this.state.vista = "lista";
            this.state.entrega = null;
            this.state.marcas = {};
            this.state.confirmar = null;
            this.state.mensaje = null;
            this.props.updateActionState?.({ resId: false });
            this.cargarLista({ silencioso: true });
        };
        if (!this.hayMarcas || this.esSoloLectura) {
            salir();
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: "¿Salir sin validar?",
            body: "Lo que marcaste en esta entrega se pierde. La entrega sigue pendiente.",
            confirmLabel: "Sí, salir",
            cancelLabel: "Seguir aquí",
            confirm: salir,
            cancel: () => {},
        });
    }

    get esSoloLectura() {
        return ["hecha", "cancelada"].includes(this.state.entrega?.estado);
    }

    // --- Marcar ----------------------------------------------------------------------------------------------------
    marcada(linea) {
        return this.state.marcas[linea.id] || 0;
    }

    completa(linea) {
        return this.marcada(linea) >= linea.pedida;
    }

    poner(linea, cantidad) {
        if (this.esSoloLectura) {
            return;
        }
        const tope = linea.pedida;
        this.state.marcas[linea.id] = Math.max(0, Math.min(tope, Math.round(cantidad * 1000) / 1000));
        this.state.mensaje = null;
        this.enfocar();
    }

    sumar(linea, paso) {
        const actual = this.marcada(linea);
        if (paso > 0 && actual + paso > linea.pedida) {
            // Una cantidad con decimales (metros) se completa con «Todo».
            this.poner(linea, linea.pedida);
            return;
        }
        this.poner(linea, actual + paso);
    }

    alternar(linea) {
        this.poner(linea, this.completa(linea) ? 0 : linea.pedida);
    }

    marcarTodo() {
        for (const linea of this.state.entrega.lineas) {
            this.state.marcas[linea.id] = linea.pedida;
        }
        this.state.mensaje = null;
        this.enfocar();
    }

    marcarPorProducto(ids, nombre) {
        const lineas = this.state.entrega.lineas.filter((l) => ids.includes(l.producto_id));
        if (!lineas.length) {
            this.avisar("error", `«${nombre}» no es de esta entrega. Revisa que sea el producto correcto.`);
            this.sonar(false);
            return;
        }
        const linea = lineas.find((l) => !this.completa(l));
        if (!linea) {
            this.avisar("aviso", `Ya marcaste todas las piezas de «${lineas[0].nombre}».`);
            this.sonar(false);
            return;
        }
        this.sumar(linea, 1);
        this.avisar("ok", `Marcado: ${linea.nombre} (${cifra(this.marcada(linea))} de ${linea.pedida_texto}).`);
        this.sonar(true);
        const fila = document.querySelector(`.o_dcasa_bodega_linea[data-linea="${linea.id}"]`);
        fila?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    }

    get progreso() {
        const lineas = this.state.entrega?.lineas || [];
        const pedidas = lineas.reduce((s, l) => s + l.pedida, 0);
        const marcadas = lineas.reduce((s, l) => s + this.marcada(l), 0);
        return {
            pedidas: cifra(pedidas),
            marcadas: cifra(marcadas),
            completas: lineas.filter((l) => this.completa(l)).length,
            total: lineas.length,
            porcentaje: pedidas ? Math.round((marcadas / pedidas) * 100) : 0,
        };
    }

    alTeclearEnEntrega(ev) {
        if ((ev.key === "Enter" || ev.key === "Tab") && this.state.lectorTexto.trim()) {
            ev.preventDefault();
            const codigo = this.state.lectorTexto.trim();
            this.state.lectorTexto = "";
            ev.currentTarget.value = "";
            this.procesarCodigo(codigo);
        }
    }

    // --- Validar ---------------------------------------------------------------------------------------------------
    get faltantes() {
        return this.state.entrega.lineas
            .filter((l) => !this.completa(l))
            .map((l) => ({ nombre: l.nombre, marcada: cifra(this.marcada(l)), pedida: l.pedida_texto }));
    }

    async validar() {
        if (!this.hayMarcas) {
            this.avisar("error", "Marca lo que sale antes de validar: toca cada producto o escanéalo.");
            this.sonar(false);
            return;
        }
        const faltan = this.faltantes;
        if (faltan.length) {
            this.state.confirmar = { faltan, deja_pendiente: this.state.entrega.deja_pendiente };
            return;
        }
        await this.enviar(false);
    }

    async entregarSoloLoMarcado() {
        await this.enviar(true);
    }

    cancelarParcial() {
        this.state.confirmar = null;
    }

    async enviar(parcial) {
        const entrega = this.state.entrega;
        const marcas = entrega.lineas.map((l) => ({ id: l.id, cantidad: this.marcada(l) }));
        this.state.validando = true;
        this.state.mensaje = null;
        try {
            const r = await this.orm.call("dcasa.bodega", "validar", [entrega.id, marcas, parcial]);
            if (r.resultado === "confirmar_parcial") {
                this.state.confirmar = { faltan: r.faltan, deja_pendiente: r.deja_pendiente };
                return;
            }
            this.state.confirmar = null;
            this.sonar(true);
            this.state.exito = {
                mensaje: r.mensaje,
                imprimir: r.imprimir,
                pendiente: r.pendiente,
                pendienteId: r.pendiente_id,
            };
            this.state.vista = "lista";
            this.state.entrega = null;
            this.state.marcas = {};
            this.props.updateActionState?.({ resId: false });
            this.quitarFiltros();
            await this.cargarLista({ silencioso: true });
        } catch (e) {
            this.state.confirmar = null;
            this.fallo(e);
        } finally {
            this.state.validando = false;
        }
    }

    imprimir(accion) {
        if (accion) {
            this.action.doAction(accion);
        }
    }

    cerrarExito() {
        this.state.exito = null;
        this.enfocar();
    }

    async abrirPendiente() {
        const id = this.state.exito?.pendienteId;
        if (id) {
            await this.abrir(id);
        }
    }

    // --- Avisos y sonido -------------------------------------------------------------------------------------------
    avisar(tipo, texto) {
        this.state.mensaje = { tipo, texto };
    }

    fallo(e) {
        const texto = e?.data?.message || e?.message || "No se pudo completar. Inténtalo otra vez.";
        this.avisar("error", texto);
        this.sonar(false);
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

registry.category("actions").add("dcasa_barras_bodega", DcasaBodega);
