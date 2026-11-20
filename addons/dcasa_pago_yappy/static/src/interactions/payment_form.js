import { patch } from '@web/core/utils/patch';
import { rpc } from '@web/core/network/rpc';
import { PaymentForm } from '@payment/interactions/payment_form';

/**
 * El Botón de Pago de Yappy dentro del formulario de pago de Odoo (flujo «direct»).
 *
 * EL NAVEGADOR NUNCA MARCA UN PAGO. `eventSuccess` solo cambia lo que se ve en pantalla: lo único que paga un pedido es el
 * aviso firmado que Yappy manda a nuestro servidor (`/payment/yappy/ipn`).
 *
 * Cómo se encaja (docs/YAPPY.md §3.2):
 *  1. Al elegir la fila «Yappy», se pide el script de Yappy (UNA vez, con espera máxima) y se pone `<btn-yappy>`. Antes no
 *     se pide nada: son ~545 KB de un tercero que además carga reCAPTCHA, Firebase y fuentes de Google.
 *  2. Cuando la clienta pulsa el botón de Yappy (`eventClick`) se crea la transacción con la maquinaria de Odoo
 *     (`submitForm`), se llama a NUESTRA ruta `/payment/yappy/iniciar` (que hace los dos POST con la clave secreta, en el
 *     servidor) y con lo que devuelve se llama a `boton.eventPayment({transactionId, token, documentName})`.
 *  3. Si algo falla, el botón se TIRA y se pone uno nuevo: al pulsar, el componente se apaga solo (`disable-btn`,
 *     opacity .4) y solo él se quita esa clase al terminar un pago; bajar `isButtonLoading` no basta.
 *  4. Un `eventError` ANTES del primer `eventPayment` no es un pago fallido: es la comprobación de disponibilidad de
 *     Yappy. Se trata como «Yappy no está disponible» y NO se rehace el botón (eso creaba un bucle contra la API de Yappy).
 */

// El único host que responde en producción es el de la TABLA de Yappy; el del ejemplo de su frontend no responde.
const SCRIPTS_PERMITIDOS = new Map([
    ['bt-cdn.yappy.cloud', '/v1/cdn/web-component-btn-yappy.js'],
    ['bt-cdn-uat.yappycloud.com', '/v1/cdn/web-component-btn-yappy.js'],
]);
const ELEMENTO = 'btn-yappy';
// De los seis temas de Yappy solo `dark` cumple contraste AA con margen (blanco sobre #444c5e = 8.60:1; medido en el
// paquete real, docs/YAPPY.md §3.2). Los otros: 2.40, 2.16, 4.28, 4.50 y 4.50.
const TEMA = 'dark';
// No es una cifra del negocio: es una espera. Un <script> que no llega nunca no dispara `error`.
const ESPERA_MAXIMA_MS = 12000;

const MENSAJES = {
    celular: 'Escribe el celular de tu app de Yappy: 8 números, sin el +507 (por ejemplo 6123 4567).',
    generico: 'No pudimos abrir el pago con Yappy ahora. Intenta de nuevo en un momento o elige otra forma de pago; ' +
              'si quieres, escríbenos por WhatsApp.',
    esperando: 'Abre tu app de Yappy y confirma el pago: tienes 5 minutos. No cierres esta página.',
    termino: 'Yappy dice que el pago salió bien. Estamos confirmándolo con ellos; no cierres esta página.',
    sinLinea: 'En este momento, Yappy no está disponible. Intenta de nuevo en un rato o elige otra forma de pago.',
    EXPIRED: 'La solicitud de Yappy venció (dura 5 minutos). Pulsa el botón de Yappy para generar una nueva.',
    FAILED: 'Yappy no pudo completar el pago. Puedes intentarlo otra vez.',
    DENIED: 'Yappy no aprobó el pago. Puedes intentarlo otra vez o elegir otra forma de pago.',
    DUPLICATED_TRANSACTION: 'Yappy dice que ese cobro ya estaba registrado. Pulsa el botón de Yappy otra vez para ' +
                            'generar uno nuevo; no te cobramos dos veces.',
    CANCELLED: 'Cancelaste el pago en la app de Yappy. Tu pedido sigue guardado: puedes intentarlo otra vez.',
};

/** El celular de Panamá sin prefijo (8 números), o null. La misma regla que `celular_de_yappy` del servidor. */
export function celularDeYappy(texto) {
    if (typeof texto !== 'string' || texto.length > 40) {
        return null;
    }
    let digitos = texto.replace(/[\s\-().]/g, '');
    for (const prefijo of ['+507', '00507', '507']) {
        if (digitos.startsWith(prefijo) && digitos.length === prefijo.length + 8) {
            digitos = digitos.slice(prefijo.length);
            break;
        }
    }
    return /^[2-9][0-9]{7}$/.test(digitos) ? digitos : null;
}

/** ¿Es el script de Yappy (de producción o de pruebas) y por https? Nadie nos hace cargar otro. */
export function scriptPermitido(url) {
    try {
        const u = new URL(url);
        return u.protocol === 'https:' && SCRIPTS_PERMITIDOS.get(u.hostname) === u.pathname;
    } catch {
        return false;
    }
}

let cargaEnVuelo = null;

/**
 * Carga el script una sola vez y dice si el elemento quedó definido. Se resuelve con `false` en vez de reventar: una
 * pantalla de pago que lanza una excepción deja a la clienta sin nada, y lo que hace falta es poder decirle que use el
 * otro camino. Un `false` no se guarda (pudo ser un túnel); un `true` sí (el elemento ya no se desdefine).
 */
export function cargarScriptDeYappy(url) {
    if (window.customElements.get(ELEMENTO) !== undefined) {
        return Promise.resolve(true);
    }
    if (!scriptPermitido(url)) {
        return Promise.resolve(false);
    }
    cargaEnVuelo ??= new Promise((resolver) => {
        // El `load` del <script> NO garantiza que el elemento esté definido: es un módulo y se define al ejecutarse.
        window.customElements.whenDefined(ELEMENTO).then(() => resolver(true));
        const etiqueta = document.createElement('script');
        etiqueta.type = 'module';
        etiqueta.src = url;
        etiqueta.addEventListener('error', () => resolver(false));
        document.head.appendChild(etiqueta);
        window.setTimeout(() => resolver(false), ESPERA_MAXIMA_MS);
    }).then((salio) => {
        if (!salio) {
            cargaEnVuelo = null;
        }
        return salio;
    });
    return cargaEnVuelo;
}

patch(PaymentForm.prototype, {

    // #=== LA FILA «YAPPY» ===#

    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== 'yappy') {
            await super._prepareInlineForm(...arguments);
            return;
        }
        this._setPaymentFlow('direct');
        // El botón «Pagar» de Odoo no se usa con Yappy: paga el botón de Yappy.
        this._hideInputs();
        await this._yappyMontar();
    },

    _yappyEstado() {
        this._yappy ??= {caja: null, boton: null, celular: null, enMarcha: false, enviado: false, enLinea: null};
        return this._yappy;
    },

    _yappyCaja() {
        const radio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        return radio ? this._getInlineForm(radio)?.querySelector('.o_dcasa_yappy') : null;
    },

    async _yappyMontar() {
        const caja = this._yappyCaja();
        if (!caja) {
            return;
        }
        const estado = this._yappyEstado();
        estado.caja = caja;
        this._yappyMensaje('');
        caja.querySelector('.o_dcasa_yappy_sin_script').hidden = true;
        const definido = await this.waitFor(cargarScriptDeYappy(caja.dataset.yappyScript));
        if (!definido) {
            caja.querySelector('.o_dcasa_yappy_sin_script p').hidden = false;
            caja.querySelector('.o_dcasa_yappy_sin_script').hidden = false;
            const reintentar = caja.querySelector('.o_dcasa_yappy_reintentar');
            reintentar.onclick = () => this._yappyMontar();
            return;
        }
        this._yappyCrearBoton();
    },

    /** Pone un botón NUEVO de Yappy (si había uno, se tira entero: se van con él sus escuchas y su suscripción). */
    _yappyCrearBoton() {
        const estado = this._yappyEstado();
        const contenedor = estado.caja?.querySelector('.o_dcasa_yappy_boton');
        if (!contenedor) {
            return;
        }
        estado.vigia?.disconnect();
        this._yappyGuardarLaSalida(false);      // un botón nuevo es un intento nuevo: el anterior ya terminó
        contenedor.replaceChildren();
        const boton = document.createElement(ELEMENTO);
        boton.setAttribute('theme', TEMA);
        estado.boton = boton;
        estado.enviado = false;
        estado.enLinea = null;
        boton.addEventListener('eventClick', () => this._yappyAlPulsar(boton));
        boton.addEventListener('eventSuccess', () => this._yappyAlTerminar(boton));
        boton.addEventListener('eventError', (ev) => this._yappyAlFallar(boton, ev.detail));
        boton.addEventListener('isYappyOnline', (ev) => this._yappyEnLinea(boton, ev.detail === true));
        contenedor.appendChild(boton);
        // El teclado: el botón de Yappy es un <div> con un clic, sin rol ni tabindex. La caja que lo contiene sí es un
        // botón para quien navega con teclado o lector de pantalla, y reenvía Enter y espacio al botón de Yappy.
        contenedor.setAttribute('role', 'button');
        contenedor.setAttribute('tabindex', '0');
        contenedor.setAttribute('aria-label', 'Pagar con Yappy');
        contenedor.onkeydown = (ev) => {
            // Una tecla mantenida repite el evento: un solo clic por pulsación (los repetidos no abren más cobros).
            if ((ev.key !== 'Enter' && ev.key !== ' ') || ev.repeat) {
                return;
            }
            const dentro = contenedor.querySelector('.yappy-button');
            if (dentro && estado.enLinea !== false) {
                ev.preventDefault();
                dentro.click();
            }
        };
    },

    _yappyRehacer() {
        const estado = this._yappyEstado();
        if (estado.boton) {
            estado.boton.isButtonLoading = false;
        }
        this._yappyCrearBoton();
    },

    _yappyMensaje(texto, tipo = 'error') {
        const caja = this._yappyEstado().caja;
        const parrafo = caja?.querySelector('.o_dcasa_yappy_mensaje');
        if (!parrafo) {
            return;
        }
        parrafo.replaceChildren();
        parrafo.hidden = !texto;
        parrafo.dataset.tipo = tipo;
        if (texto) {
            const icono = document.createElement('i');
            icono.className = tipo === 'error' ? 'fa fa-exclamation-circle' : 'fa fa-clock-o';
            icono.setAttribute('aria-hidden', 'true');
            parrafo.append(icono, texto);
        }
    },

    // #=== LO QUE PASA AL PULSAR EL BOTÓN DE YAPPY ===#

    async _yappyAlPulsar(boton) {
        const estado = this._yappyEstado();
        // Con un intento ya en marcha no se empieza otro: el teclado salta el «pointer-events: none» con que el botón se
        // apaga solo (Enter dos veces pulsa dos veces), y cerrar «la ventana vieja» aquí cerraría la del intento vivo.
        if (boton !== estado.boton || estado.enMarcha || estado.enviado || estado.pulsado) {
            return;
        }
        estado.pulsado = true;
        try {
            this._yappyMensaje('');
            this._yappyCerrarVentanaVieja();
            const campo = estado.caja.querySelector('input[name="o_dcasa_yappy_celular"]');
            const celular = celularDeYappy(campo.value);
            if (!celular) {
                this._yappyMensaje(MENSAJES.celular);
                campo.focus();
                this._yappyRehacer();
                return;
            }
            estado.celular = celular;
            estado.enMarcha = false;
            try {
                // La maquinaria de Odoo crea la transacción (con el monto del pedido, en el servidor) y llama a
                // `_processDirectFlow`; allí se abre el cobro en Yappy.
                await this.submitForm({stopPropagation() {}, preventDefault() {}});
            } catch {
                // Odoo ya enseñó su diálogo de error.
            }
            if (!estado.enMarcha) {
                this._yappyRehacer();       // la transacción no llegó a abrirse: otro intento con un botón limpio
            }
        } finally {
            estado.pulsado = false;
        }
    },

    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== 'yappy') {
            await super._processDirectFlow(...arguments);
            return;
        }
        const estado = this._yappyEstado();
        estado.enMarcha = true;
        const boton = estado.boton;
        this._enableButton();       // quita el bloqueo de pantalla que puso `submitForm`
        try {
            const datos = await this.waitFor(rpc('/payment/yappy/iniciar', {
                reference: processingValues.reference,
                celular: estado.celular,
            }));
            if (!datos || !datos.ok) {
                this._yappyFallo(datos?.mensaje || MENSAJES.generico);
                return;
            }
            if (boton !== estado.boton || typeof boton.eventPayment !== 'function') {
                this._yappyFallo(MENSAJES.generico);
                return;
            }
            estado.enviado = true;
            this._yappyGuardarLaSalida(true);
            boton.eventPayment({
                transactionId: datos.transactionId,
                documentName: datos.documentName,
                token: datos.token,
            });
            this._yappyMensaje(MENSAJES.esperando, 'info');
            this._yappyVigilarVentana(boton);
        } catch {
            this._yappyFallo(MENSAJES.generico);
        } finally {
            estado.enMarcha = false;
        }
    },

    /**
     * Si queda abierta la ventana de un intento anterior (su «Transacción cancelada», con su X), se cierra con SU botón de
     * cerrar antes de empezar otro: mientras siga abierta el componente no abre la ventana del intento nuevo y la clienta
     * veía «cancelada» encima de «confirma el pago» (medido con el componente real).
     */
    _yappyCerrarVentanaVieja() {
        const cerrar = this._yappyEstado().caja?.querySelector('dialog[open] .close-icon');
        cerrar?.dispatchEvent(new MouseEvent('click', {bubbles: true}));
    },

    /**
     * La ventana de Yappy se puede cerrar SIN que el componente avise con ningún evento: pasa cuando su contador de 5
     * minutos llega a cero (dice «Transacción expirada», la clienta la cierra y no hay `eventError`). Sin esto el botón se
     * quedaba apagado para siempre y el mensaje seguía diciendo «tienes 5 minutos». Al cerrarse la ventana sin que haya
     * llegado ningún evento, se pone un botón nuevo y se dice por qué.
     */
    _yappyVigilarVentana(boton) {
        const estado = this._yappyEstado();
        estado.vigia?.disconnect();
        const contenedor = estado.caja?.querySelector('.o_dcasa_yappy_boton');
        if (!contenedor || typeof MutationObserver === 'undefined') {
            return;
        }
        let estuvoAbierta = !!contenedor.querySelector('dialog')?.open;
        const vigia = new MutationObserver(() => {
            if (contenedor.querySelector('dialog')?.open) {
                estuvoAbierta = true;
            } else if (estuvoAbierta && boton === estado.boton && estado.enviado) {
                vigia.disconnect();
                this._yappyFallo(MENSAJES.EXPIRED);
            }
        });
        vigia.observe(contenedor, {subtree: true, attributes: true, attributeFilter: ['open']});
        estado.vigia = vigia;
    },

    /**
     * Con un cobro en marcha (la solicitud ya salió hacia la app de Yappy), cerrar o refrescar la pestaña deja a la clienta
     * sin saber qué pasó con su pedido: el navegador pregunta antes («¿Salir del sitio?»). Solo mientras el intento está
     * vivo: sin intento, o con el intento terminado, no molesta. El texto del aviso es del navegador (no se puede cambiar).
     */
    _yappyGuardarLaSalida(vivo) {
        const estado = this._yappyEstado();
        if (vivo && !estado.quitarGuardaDeSalida) {
            estado.quitarGuardaDeSalida = this.addListener(window, 'beforeunload', (ev) => {
                ev.preventDefault();
                ev.returnValue = '';
            });
        } else if (!vivo && estado.quitarGuardaDeSalida) {
            estado.quitarGuardaDeSalida();
            estado.quitarGuardaDeSalida = null;
        }
    },

    _yappyFallo(mensaje) {
        this._yappyMensaje(mensaje);
        this._yappyRehacer();
    },

    /** Yappy dice que terminó. NO ES UN PAGO: solo se pasa a «Estamos confirmando» (el aviso firmado lo decide). */
    _yappyAlTerminar(boton) {
        if (boton !== this._yappyEstado().boton) {
            return;
        }
        this._yappyMensaje(MENSAJES.termino, 'info');
        this._yappyGuardarLaSalida(false);      // vamos nosotros a la página de estado: sin aviso del navegador
        // `replace`, no `assign`: la página de pago no queda en el historial. Con «atrás» la clienta volvía a un botón de
        // Yappy listo para pagar OTRA VEZ un pedido que ya tiene un cobro en espera.
        window.location.replace('/payment/status');
    },

    _yappyAlFallar(boton, detalle) {
        const estado = this._yappyEstado();
        if (boton !== estado.boton) {
            return;
        }
        if (!estado.enviado) {
            // Antes del primer cobro, `eventError` es la comprobación de disponibilidad de Yappy, no un pago fallido.
            this._yappyEnLinea(boton, false);
            return;
        }
        this._yappyMensaje(MENSAJES[detalle] || MENSAJES.generico);
        this._yappyRehacer();
    },

    _yappyEnLinea(boton, enLinea) {
        const estado = this._yappyEstado();
        if (boton !== estado.boton) {
            return;
        }
        estado.enLinea = enLinea;
        const sinScript = estado.caja?.querySelector('.o_dcasa_yappy_sin_script');
        if (!enLinea) {
            estado.mensajeSinLinea = true;
            this._yappyMensaje(MENSAJES.sinLinea);
            if (sinScript) {
                // Con Yappy fuera de línea: el camino alterno (WhatsApp) a la vista, sin esconder el motivo.
                sinScript.querySelector('p').hidden = true;
                sinScript.hidden = false;
                sinScript.querySelector('.o_dcasa_yappy_reintentar').onclick = () => this._yappyMontar();
            }
        } else if (sinScript) {
            sinScript.hidden = true;
            // El botón nuevo que se pone tras un fallo avisa «en línea» a los pocos milisegundos (el componente real hace
            // su comprobación al nacer): eso solo borra el aviso de «Yappy no está disponible», nunca el motivo de un
            // fallo que la clienta aún no leyó.
            if (estado.mensajeSinLinea) {
                estado.mensajeSinLinea = false;
                this._yappyMensaje('');
            }
        }
    },
});
