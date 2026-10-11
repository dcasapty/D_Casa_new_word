/**
 * «Escáner»: se escanea (o se escribe) un código y sale el producto con su foto, precio «+ ITBMS» y existencias.
 *
 * El lector (Bluetooth, 2.4G, USB o el Android con lector integrado) escribe el código como un teclado y termina con
 * Enter: el cuadro de arriba siempre tiene el foco. En «Contar» (Gerencia) se escribe lo contado, se muestra la
 * diferencia con lo que dice el sistema y solo se guarda al confirmar. Todo lo que se lee o se guarda lo comprueba
 * el servidor (dcasa.barras); aquí no hay reglas de negocio, solo la pantalla.
 */
import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ETIQUETAS = { disponible: "Disponible", pocas: "Pocas", agotado: "Agotado" };

export class DcasaEscaner extends Component {
    static template = "dcasa_barras.Escaner";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.entrada = useRef("entrada");
        this.state = useState({
            texto: "",
            modo: "consultar", // consultar | contar
            cargando: false,
            ficha: null, // la tarjeta del producto
            opciones: [], // varios productos con ese código, o los que salieron de buscar por nombre
            mensaje: null, // { tipo: "ok" | "aviso" | "error", texto }
            ubicacion: null,
            cantidad: "",
            confirmando: null, // { antes, cantidad, diferencia } mientras se espera el visto bueno
            parecido: false, // el producto salió de un código «parecido», no igual: hay que confirmarlo
            historial: [],
        });
        this.confirmar = useRef("confirmar");
        // Cada búsqueda lleva un número: si llega la respuesta de una vieja cuando ya salió una más nueva, se ignora.
        this.peticion = 0;
        onMounted(() => this.enfocar());
    }

    // --- Entrada ----------------------------------------------------------------------------------------------
    enfocar() {
        const campo = this.entrada.el;
        if (campo) {
            campo.focus();
            campo.select();
        }
    }

    alPerderFoco() {
        // Si el foco se fue al fondo de la página (un toque en blanco), el lector escribiría en el vacío: se recupera.
        setTimeout(() => {
            if (document.activeElement === document.body && !this.state.confirmando) {
                this.enfocar();
            }
        }, 60);
    }

    alTeclear(ev) {
        // Casi todos los lectores terminan con Enter; algunos con Tab.
        if ((ev.key === "Enter" || ev.key === "Tab") && this.state.texto.trim()) {
            ev.preventDefault();
            this.escanear();
        }
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
        const mia = ++this.peticion;
        this.state.cargando = true;
        this.state.mensaje = null;
        try {
            const r = await this.orm.call("dcasa.barras", "buscar", [codigo]);
            if (mia !== this.peticion) {
                return; // llegó la respuesta de un escaneo viejo: manda el más nuevo
            }
            if (r.resultado === "ok") {
                this.mostrarFicha(r.productos[0], codigo, r.forma === "parecido");
            } else if (r.resultado === "varios") {
                this.limpiarProducto();
                this.state.opciones = r.productos;
                this.avisar("aviso", `Hay ${r.productos.length} productos con «${r.codigo}». Elige el correcto.`);
                this.sonar(false);
            } else {
                await this.noEncontrado(codigo, mia);
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

    async noEncontrado(codigo, mia) {
        this.limpiarProducto();
        this.sonar(false);
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
    }

    cambiarModo(modo) {
        this.state.modo = modo;
        this.state.confirmando = null;
        this.state.mensaje = null;
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
        // El foco pasa al botón de confirmar: Enter confirma y un escaneo no cae en el cuadro de cantidad.
        setTimeout(() => this.confirmar.el?.focus(), 0);
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
