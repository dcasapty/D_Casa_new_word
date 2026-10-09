"""Búsqueda por palabras en la base de conocimiento y agrupación de preguntas parecidas: funciones PURAS.

Sin vectores ni extensiones de la base: se normaliza el texto (minúsculas, sin acentos, sin plural), se quitan las
palabras vacías («cuál», «tienen», «de», «la»…) y se cuentan coincidencias. Así «¿Cuál es el horario?» encuentra
la entrada «Horario y WhatsApp» y «¿Tienen garantía en los colchones?» se agrupa con «garantía de colchones».
"""
import re

from .publico import normalizar, raiz

# Palabras que no distinguen una pregunta de otra (ya sin acentos, como las deja ``normalizar``).
PALABRAS_VACIAS = frozenset("""
a al algo ahi alla aqui asi aun cada como con contra cual cuales cuando cuanto cuantos cuantas de del desde
dos el ella ellos en entre era eres es esa ese eso esta estan estar este esto estos fue ha han hasta hay la las le
les lo los mas me mi mis mucho muy ni no nos nosotros o otra otro para pero poco por porque pues que quien quienes
se segun ser si sin sobre son su sus tambien tan te tengo tiene tienen tienes todo todos tu tus un una uno unas
unos usted ustedes va vamos van vas voy y ya yo
hola buenas buenos dias tardes noches favor gracias quiero quisiera saber puedo puede pueden podria podrian necesito
informacion pregunta duda ayuda
""".split())

PESO_TITULO = 6
PESO_ETIQUETA = 6
PESO_CONTENIDO = 2
UMBRAL_PARECIDAS = 0.7


def tokens(texto):
    """Palabras significativas del texto: normalizadas, en singular y sin palabras vacías, sin repetir."""
    vistas, resultado = set(), []
    for palabra in re.findall(r'[a-z0-9]+', normalizar(texto)):
        if palabra in PALABRAS_VACIAS or (len(palabra) < 3 and not palabra.isdigit()):
            continue
        singular = raiz(palabra)
        if singular not in vistas:
            vistas.add(singular)
            resultado.append(singular)
    return resultado


def puntuar(consulta, titulo, etiquetas, contenido):
    """0 si no responde la pregunta; mayor es mejor.

    Cada palabra de la consulta suma si aparece en el título, las etiquetas o el contenido (más en el título y
    las etiquetas). Hace falta que coincida al menos la mitad de las palabras de la consulta.
    """
    buscadas = tokens(consulta)
    if not buscadas:
        return 0
    n_titulo, n_etiquetas, n_contenido = normalizar(titulo), normalizar(etiquetas), normalizar(contenido)
    puntos, coincidencias = 0, 0
    for palabra in buscadas:
        aporte = 0
        if palabra in n_titulo:
            aporte += PESO_TITULO
        if palabra in n_etiquetas:
            aporte += PESO_ETIQUETA
        if palabra in n_contenido:
            aporte += PESO_CONTENIDO
        if aporte:
            coincidencias += 1
            puntos += aporte
    return puntos if coincidencias * 2 >= len(buscadas) else 0


def clave(texto):
    """Forma canónica de una pregunta: sus palabras significativas, ordenadas."""
    return ' '.join(sorted(tokens(texto)))


def similitud(a, b):
    """0 a 1: qué tanto se parecen dos preguntas (palabras significativas en común sobre las totales)."""
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta and not tb:
        return 1.0 if normalizar(a).strip() == normalizar(b).strip() else 0.0
    return len(ta & tb) / len(ta | tb)


def son_parecidas(a, b):
    return similitud(a, b) >= UMBRAL_PARECIDAS
