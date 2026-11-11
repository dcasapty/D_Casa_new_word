/** @odoo-module **/
// «Más datos» de la cotización (2026-11-11): en el celular había que bajar dos pantallas para llegar a los productos.
//
// Los datos de la cabecera que casi nunca se tocan al cotizar llevan en la vista la clase «o_dcasa_mas_dato»
// (direcciones de factura y de entrega, vencimiento, lista de precios, términos de pago y teléfono fijo). Este botón,
// que va justo antes de las pestañas, los pliega y los despliega. Ningún campo cambia de sitio ni se vuelve a pintar:
// siguen donde están en la vista (otros módulos los buscan ahí) y la hoja de estilos esconde su renglón mientras el
// botón dice `aria-expanded="false"` (scss/mas_datos.scss, con `:has()`; sin `:has()` el botón no sale y todo queda
// como antes).
//
// * Cerrado al abrir. La persona lo abre o lo cierra y ese aparato lo recuerda (localStorage; si no se puede guardar,
//   funciona igual).
// * Se abre solo cuando ahí dentro hay algo que la persona debe ver: la dirección de entrega o la de factura no es la
//   del cliente, o hay un dato obligatorio sin llenar o con error. Mientras falte un dato obligatorio no se puede
//   cerrar: nunca queda escondido un campo que impide guardar.
// * El botón dice por qué se abrió («La entrega va a otra dirección.», «Falta llenar un dato de aquí.»): en el celular
//   el nombre de la dirección sale cortado y las dos direcciones parecen la misma; y si la persona lo cierra, el aviso
//   de la otra dirección sigue a la vista.
import { Component, onWillUpdateProps, useEffect, useRef, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export const CLAVE_MAS_DATOS = "dcasa.cotizacion.mas_datos";
export const MARCA_MAS_DATO = "o_dcasa_mas_dato";
const DIRECCIONES = ["partner_invoice_id", "partner_shipping_id"];
// Cómo nombra el botón lo que guarda, en este orden. Un dato marcado que no esté aquí sale con su propio rótulo.
const NOMBRES = [
    [DIRECCIONES, "direcciones"],
    [["validity_date"], "vencimiento"],
    [["pricelist_id"], "lista de precios"],
    [["payment_term_id"], "pago"],
    [["dcasa_cliente_fijo"], "teléfono fijo"],
];
const CONOCIDOS = NOMBRES.flatMap(([campos]) => campos);

function leerPreferencia() {
    try {
        return browser.localStorage.getItem(CLAVE_MAS_DATOS) === "1";
    } catch {
        return false; // sin almacenamiento (ventana privada, bloqueado): cerrado, como la primera vez
    }
}

/** El id de un «muchos a uno» (según la versión llega como objeto o como par [id, nombre]). */
function idDe(valor) {
    return Array.isArray(valor) ? valor[0] : (valor && valor.id) || false;
}

/** «a, b y c». */
function enumerar(partes) {
    return partes.length > 1 ? `${partes.slice(0, -1).join(", ")} y ${partes.at(-1)}` : partes[0] || "";
}

export class DcasaMasDatos extends Component {
    static template = "dcasa_interfaz.MasDatos";
    static props = { ...standardWidgetProps };

    setup() {
        this.raiz = useRef("raiz");
        const registro = this.props.record;
        this.estado = useState({
            // Los datos marcados que hay en el formulario (lo que esa persona vería al abrir). Antes de mirar la
            // pantalla, los conocidos que el formulario trae a la vista; después manda lo que de verdad está pintado.
            presentes: CONOCIDOS.filter((campo) => campo in registro.activeFields && !registro._isInvisible(campo)),
            controla: "",
            preferida: leerPreferencia(),
            // Lo que la persona eligió en este documento (null: no ha tocado el botón) y si ya se abrió solo.
            manual: null,
            seAbrioSolo: false,
        });
        this.motivoAnterior = null;
        onWillUpdateProps((siguientes) => {
            if (siguientes.record.id !== this.props.record.id) {
                // Otro documento: vuelve a lo recordado en el aparato.
                Object.assign(this.estado, { manual: null, seAbrioSolo: false });
                this.motivoAnterior = null;
            }
        });
        // Qué datos marcados están pintados: se mira la hoja del formulario cada vez que cambia (un dato puede salir o
        // esconderse según el estado del pedido o los permisos de la persona).
        useEffect(
            () => {
                const hoja = this.raiz.el.closest(".o_form_sheet") || this.raiz.el.closest(".o_form_renderer");
                if (!hoja) {
                    return;
                }
                let pendiente = 0;
                const mirar = () => {
                    pendiente = 0;
                    const campos = [...hoja.querySelectorAll(`.o_field_widget.${MARCA_MAS_DATO}[name]`)];
                    const presentes = [...new Set(campos.map((campo) => campo.getAttribute("name")))];
                    const controla = campos
                        .map((campo) => campo.querySelector("[id]")?.id)
                        .filter(Boolean)
                        .join(" ");
                    if (presentes.join() !== this.estado.presentes.join()) {
                        this.estado.presentes = presentes;
                    }
                    if (controla !== this.estado.controla) {
                        this.estado.controla = controla;
                    }
                };
                const observador = new MutationObserver(() => {
                    pendiente ||= browser.requestAnimationFrame(mirar);
                });
                observador.observe(hoja, { childList: true, subtree: true });
                mirar();
                return () => {
                    observador.disconnect();
                    browser.cancelAnimationFrame(pendiente);
                };
            },
            () => []
        );
        // Cuando aparece un motivo para abrirlo, se abre solo (aunque la persona lo hubiera cerrado antes) y así se
        // queda en este documento hasta que ella lo cierre: no se pliega bajo sus dedos mientras corrige el dato.
        useEffect(
            (motivo) => {
                if (motivo && !this.motivoAnterior) {
                    Object.assign(this.estado, { manual: null, seAbrioSolo: true });
                }
                this.motivoAnterior = motivo;
            },
            () => [this.motivo]
        );
        // Al cerrarlo, lo de arriba se encoge y el botón sube con lo demás: si quedó fuera de la vista, la pantalla
        // lo acompaña lo justo para que siga a la vista, con los productos debajo (de un salto, sin animación).
        this.recienCerrado = false;
        useEffect(
            (abierto) => {
                if (this.recienCerrado && !abierto) {
                    this.raiz.el.scrollIntoView({ block: "nearest" });
                }
                this.recienCerrado = false;
            },
            () => [this.abierto]
        );
    }

    /** Los datos marcados que este formulario tiene y la persona vería al abrir. */
    get campos() {
        const registro = this.props.record;
        return this.estado.presentes.filter((campo) => campo in registro.activeFields);
    }

    /**
     * Por qué tiene que estar abierto: "falta" (un dato obligatorio sin llenar o con error: no se puede cerrar),
     * "distinta" (la dirección de entrega o la de factura no es la del cliente) o null.
     */
    get motivo() {
        const registro = this.props.record;
        const cliente = idDe(registro.data.partner_id);
        const campos = this.campos;
        for (const campo of campos) {
            if (registro.isFieldInvalid(campo)) {
                return "falta";
            }
            // Sin cliente, las direcciones están vacías porque salen de él: lo que falta es el cliente, que está a
            // la vista. Si se intenta guardar así, Odoo las marca con error y entonces sí se abre.
            const esperaAlCliente = DIRECCIONES.includes(campo) && !cliente;
            if (!registro.data[campo] && !esperaAlCliente && registro._isRequired(campo)) {
                return "falta";
            }
        }
        return this.distintas.length ? "distinta" : null;
    }

    /** Las direcciones (de las que esa persona ve) que no son la del cliente. */
    get distintas() {
        const registro = this.props.record;
        const cliente = idDe(registro.data.partner_id);
        const campos = this.campos;
        return DIRECCIONES.filter((campo) => {
            const direccion = campos.includes(campo) && idDe(registro.data[campo]);
            return direccion && cliente && direccion !== cliente;
        });
    }

    /** Por qué está abierto, en palabras: lo dice el botón. */
    get aviso() {
        if (this.obligado) {
            return "Falta llenar un dato de aquí.";
        }
        const entrega = this.distintas.includes("partner_shipping_id");
        const factura = this.distintas.includes("partner_invoice_id");
        if (entrega && factura) {
            return "La entrega y la factura van a otra dirección.";
        }
        if (entrega) {
            return "La entrega va a otra dirección.";
        }
        return factura ? "La factura va a otra dirección." : "";
    }

    get obligado() {
        return this.motivo === "falta";
    }

    get abierto() {
        if (this.obligado) {
            return true;
        }
        if (this.estado.manual !== null) {
            return this.estado.manual;
        }
        return this.estado.seAbrioSolo || Boolean(this.motivo) || this.estado.preferida;
    }

    /** «direcciones, vencimiento, lista de precios, pago y teléfono fijo»: lo que de verdad hay ahí dentro. */
    get detalle() {
        const campos = this.campos;
        const partes = NOMBRES.filter(([propios]) => propios.some((campo) => campos.includes(campo))).map(
            ([, nombre]) => nombre
        );
        for (const campo of campos) {
            if (!CONOCIDOS.includes(campo)) {
                partes.push((this.props.record.fields[campo].string || campo).toLowerCase());
            }
        }
        return enumerar(partes);
    }

    alternar() {
        if (this.obligado) {
            return; // falta un dato obligatorio de aquí dentro: no se esconde
        }
        const abierto = !this.abierto;
        this.recienCerrado = !abierto;
        this.estado.manual = abierto;
        this.estado.preferida = abierto;
        try {
            browser.localStorage.setItem(CLAVE_MAS_DATOS, abierto ? "1" : "0");
        } catch {
            // no se pudo recordar: vale para esta vez
        }
    }
}

registry.category("view_widgets").add("dcasa_mas_datos", { component: DcasaMasDatos });
