/**
 * Cómo acomoda la pantalla «Conversaciones» sus columnas según el tamaño de la ventana, y las preferencias de cada
 * persona (ficha del cliente abierta o cerrada, lista ancha o angosta).
 *
 * La conversación (el hilo) es lo que más espacio tiene. La ficha del cliente NACE CERRADA y un botón «Cliente» la abre;
 * solo en pantallas amplias nace abierta. Los números de aquí son LOS MISMOS de los @media de panel.scss (si cambias
 * uno, cambia el otro):
 *  - celular: hasta 767 px de ancho (una pantalla a la vez; la ficha es otra pantalla);
 *  - tablet: de 768 a 1023 px (la ficha se abre ENCIMA del hilo y se cierra sola al cambiar de conversación);
 *  - escritorio: desde 1024 px (la ficha, al abrirla, queda AL LADO del hilo);
 *  - pantalla amplia: 1500 px de ancho y 800 de alto o más (la ficha nace abierta);
 *  - ancho para todo: desde 1250 px caben lista y ficha a la vez; con menos, la lista se reduce a las fotos mientras
 *    la ficha está abierta;
 *  - pantalla estrecha: hasta 1100 px (la lista nace reducida a las fotos).
 *
 * Las preferencias se guardan en este navegador (localStorage), una por persona. Si el almacenamiento falta o falla
 * (ventana privada, datos bloqueados), la pantalla funciona igual con sus valores de siempre.
 */
const PREFIJO = "dcasa.conversaciones.";

export const CONSULTA_CELULAR = "(max-width: 767.98px)";
export const CONSULTA_AL_LADO = "(min-width: 1024px)";
export const CONSULTA_AMPLIA = "(min-width: 1500px) and (min-height: 800px)";
export const CONSULTA_ANCHO_PARA_TODO = "(min-width: 1250px)";
export const CONSULTA_ESTRECHA = "(max-width: 1100px)";

function coincide(consulta) {
    try {
        return !!window.matchMedia?.(consulta)?.matches;
    } catch {
        return false;
    }
}

export const esCelular = () => coincide(CONSULTA_CELULAR);
/** Desde 1024 px la ficha, al abrirla, queda al lado del hilo (en tablet se abre encima). */
export const fichaVaAlLado = () => coincide(CONSULTA_AL_LADO);
export const esPantallaAmplia = () => coincide(CONSULTA_AMPLIA);
export const esAnchoParaTodo = () => coincide(CONSULTA_ANCHO_PARA_TODO);
export const esPantallaEstrecha = () => coincide(CONSULTA_ESTRECHA);

/** Avisa cuando la ventana cruza alguno de los límites de arriba (p. ej. al cambiar el zoom del navegador). */
export function escucharCambioDeTamano(alCambiar) {
    const escuchas = [];
    for (const texto of [CONSULTA_CELULAR, CONSULTA_AL_LADO, CONSULTA_AMPLIA, CONSULTA_ANCHO_PARA_TODO]) {
        try {
            const consulta = window.matchMedia?.(texto);
            if (consulta?.addEventListener) {
                consulta.addEventListener("change", alCambiar);
                escuchas.push(() => consulta.removeEventListener("change", alCambiar));
            }
        } catch {
            /* sin matchMedia: la pantalla se acomoda al abrirse y listo */
        }
    }
    return () => escuchas.forEach((quitar) => quitar());
}

function clave(nombre, usuarioId) {
    return `${PREFIJO}${nombre}.${usuarioId || 0}`;
}

export function leerPreferencia(nombre, usuarioId) {
    try {
        return window.localStorage.getItem(clave(nombre, usuarioId));
    } catch {
        return null;
    }
}

export function guardarPreferencia(nombre, valor, usuarioId) {
    try {
        window.localStorage.setItem(clave(nombre, usuarioId), valor);
    } catch {
        /* sin almacenamiento: la preferencia dura hasta que se cierre la pantalla */
    }
}
