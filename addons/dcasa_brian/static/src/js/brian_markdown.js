/**
 * Markdown simple y SEGURO para las respuestas de Brian.
 *
 * No produce HTML: convierte el texto en una estructura de bloques que la plantilla
 * `dcasa_brian.Markdown` pinta con t-esc/t-att (OWL escapa todo). Así, aunque el modelo o
 * un dato de un registro traiga `<script>` o `<img onerror>`, se muestra como texto.
 *
 * Soporta: párrafos (con saltos de línea), **negritas**, *cursivas*, `código`,
 * títulos (#), listas con viñetas y numeradas, tablas simples con encabezado,
 * bloques ``` de código y enlaces [texto](https://… o /odoo/…).
 */

const INLINE =
    /(\*\*[^*\n]+?\*\*|__[^_\n]+?__|`[^`\n]+`|\[[^\]\n]+\]\((?:https?:\/\/|\/(?!\/))[^\s)]*\)|\*[^*\s][^*\n]*?\*)/g;

/** Texto → [{t: 'texto'|'negrita'|'cursiva'|'codigo'|'enlace', v, href?}] */
export function parsearInline(texto) {
    const partes = [];
    let ultimo = 0;
    const src = String(texto ?? "");
    for (const m of src.matchAll(INLINE)) {
        if (m.index > ultimo) {
            partes.push({ t: "texto", v: src.slice(ultimo, m.index) });
        }
        const s = m[0];
        if (s.startsWith("**") || s.startsWith("__")) {
            partes.push({ t: "negrita", v: s.slice(2, -2) });
        } else if (s.startsWith("`")) {
            partes.push({ t: "codigo", v: s.slice(1, -1) });
        } else if (s.startsWith("[")) {
            const cierre = s.indexOf("](");
            partes.push({ t: "enlace", v: s.slice(1, cierre), href: s.slice(cierre + 2, -1) });
        } else {
            partes.push({ t: "cursiva", v: s.slice(1, -1) });
        }
        ultimo = m.index + s.length;
    }
    if (ultimo < src.length) {
        partes.push({ t: "texto", v: src.slice(ultimo) });
    }
    return partes;
}

const RE_UL = /^\s*[-*•]\s+(.*)$/;
const RE_OL = /^\s*\d+[.)]\s+(.*)$/;
const RE_H = /^(#{1,4})\s+(.*)$/;
const RE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function celdas(linea) {
    let s = linea.trim();
    if (s.startsWith("|")) {
        s = s.slice(1);
    }
    if (s.endsWith("|")) {
        s = s.slice(0, -1);
    }
    return s.split("|").map((c) => parsearInline(c.trim()));
}

/** Texto → [{tipo: 'p'|'h'|'ul'|'ol'|'tabla'|'codigo', ...}] */
export function parsearMarkdown(texto) {
    const lineas = String(texto ?? "").replace(/\r\n?/g, "\n").split("\n");
    const bloques = [];
    let parrafo = null;
    const cerrarParrafo = () => {
        parrafo = null;
    };
    for (let i = 0; i < lineas.length; i++) {
        const linea = lineas[i];
        if (!linea.trim()) {
            cerrarParrafo();
            continue;
        }
        if (linea.trim().startsWith("```")) {
            cerrarParrafo();
            const codigo = [];
            i++;
            while (i < lineas.length && !lineas[i].trim().startsWith("```")) {
                codigo.push(lineas[i]);
                i++;
            }
            bloques.push({ tipo: "codigo", texto: codigo.join("\n") });
            continue;
        }
        const h = linea.match(RE_H);
        if (h) {
            cerrarParrafo();
            bloques.push({ tipo: "h", inline: parsearInline(h[2]) });
            continue;
        }
        if (linea.includes("|") && i + 1 < lineas.length && RE_SEP.test(lineas[i + 1]) && lineas[i + 1].includes("-")) {
            cerrarParrafo();
            const tabla = { tipo: "tabla", encabezado: celdas(linea), filas: [] };
            i += 2;
            while (i < lineas.length && lineas[i].includes("|") && lineas[i].trim()) {
                tabla.filas.push(celdas(lineas[i]));
                i++;
            }
            i--;
            bloques.push(tabla);
            continue;
        }
        const ul = linea.match(RE_UL);
        const ol = !ul && linea.match(RE_OL);
        if (ul || ol) {
            cerrarParrafo();
            const tipo = ul ? "ul" : "ol";
            const previo = bloques[bloques.length - 1];
            const item = parsearInline((ul || ol)[1]);
            if (previo && previo.tipo === tipo && previo.abierta) {
                previo.items.push(item);
            } else {
                bloques.push({ tipo, items: [item], abierta: true });
            }
            continue;
        }
        const previo = bloques[bloques.length - 1];
        if (previo && (previo.tipo === "ul" || previo.tipo === "ol")) {
            previo.abierta = false;
        }
        if (!parrafo) {
            parrafo = { tipo: "p", lineas: [] };
            bloques.push(parrafo);
        }
        parrafo.lineas.push(parsearInline(linea));
    }
    return bloques;
}
