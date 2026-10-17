/**
 * Mi cuenta: «Copiar enlace» (el de invitar) y la confirmación de «Cancelar» un premio, sin JavaScript dentro del HTML.
 * Sin JavaScript todo sigue sirviendo: el enlace se puede seleccionar a mano y el premio se cancela igual.
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";

export class CopiarEnlace extends Interaction {
    static selector = "[data-dcasa-copiar]";
    dynamicContent = {
        _root: { "t-on-click": this.copiar },
    };

    async copiar() {
        const texto = this.el.dataset.dcasaCopiar || "";
        const original = this.el.textContent;
        try {
            await this.waitFor(navigator.clipboard.writeText(texto));
            this.el.textContent = "¡Copiado!";
        } catch {
            // Sin permiso para el portapapeles: se deja seleccionado para copiarlo a mano.
            const campo = this.el.parentElement && this.el.parentElement.querySelector("input");
            if (campo) {
                campo.focus();
                campo.select();
            }
            this.el.textContent = "Selecciónalo y cópialo";
        }
        this.waitForTimeout(() => {
            this.el.textContent = original;
        }, 2500);
    }
}

export class ConfirmarAntes extends Interaction {
    static selector = "form.o_dcasa_mc_confirmar[data-confirmar]";
    dynamicContent = {
        _root: { "t-on-submit": this.confirmar },
    };

    confirmar(ev) {
        if (!window.confirm(this.el.dataset.confirmar)) {
            ev.preventDefault();
        }
    }
}

registry.category("public.interactions").add("dcasa_mi_cuenta.copiar_enlace", CopiarEnlace);
registry.category("public.interactions").add("dcasa_mi_cuenta.confirmar_antes", ConfirmarAntes);
