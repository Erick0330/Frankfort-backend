"""Lo que el sistema SABE de cada medida: qué es, qué significa, qué se puede hacer.

── Por qué existe este módulo ───────────────────────────────────
El agente que personaliza las explicaciones (`agents.personalize`) no
puede sacar el conocimiento de su propia memoria. Un LLM preguntado «¿qué
significa un ángulo nasolabial de 118°?» contesta algo plausible, y a
veces es falso; preguntado «¿cómo se corrige?» recomienda con la misma
soltura una crema que una cirugía. En un producto que habla de la cara de
alguien, las dos cosas son inaceptables.

Así que el conocimiento vive AQUÍ, escrito y revisado a mano, y el agente
solo lo PERSONALIZA: lo cruza con las cifras de esa persona y lo redacta.
Es el patrón de «generación anclada»: el modelo no aporta hechos, aporta
redacción sobre hechos que se le dan. Y lo que se le da está en un sitio
donde se puede auditar, testear y corregir sin tocar un prompt.

── Las opciones van por NIVELES, y los niveles no los elige el modelo ───
La escala es la del `recommender` de docs/02 §4:

    0. Gratis / de hábito    → peinado, barba, postura, repetir la foto
    1. Cosmético             → lo que se compra sin receta
    2. Médico sin cirugía    → rellenos, toxina; los pone un médico
    3. Cirugía               → solo con especialista y medición clínica

Qué niveles se enseñan lo decide `allowed_level()` en `insight.py` según
cuánto se sale la medida, no el LLM. Una proporción que se sale un poco
no abre la puerta a la cirugía por mucho que el modelo quiera ser
servicial: es la regla de la escalada proporcional del `safety_reviewer`,
y es la que el caso del tercio inferior demostró necesaria — ortognática
por una proporción un 8 % distinta, y medida mal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Locale = Literal["es", "en"]
Level = Literal[0, 1, 2, 3]
Side = Literal["low", "high"]


@dataclass(frozen=True, slots=True)
class Option:
    level: Level
    es: str
    en: str

    def text(self, locale: Locale) -> str:
        return self.es if locale == "es" else self.en


@dataclass(frozen=True, slots=True)
class MetricKnowledge:
    #: Qué mide, en dos frases y sin jerga.
    what: dict[Locale, str]
    #: Qué quiere decir caer dentro del rango.
    inside: dict[Locale, str]
    #: Qué quiere decir salirse por cada lado, en lo que se VE.
    meaning: dict[Side, dict[Locale, str]]
    #: Lo que se puede hacer, por lado. El orden es de menos a más
    #: invasivo, y así se enseña.
    options: dict[Side, tuple[Option, ...]]
    #: Lo que la fotografía o el marcado distorsionan de esta medida.
    #: Se usa cuando el sello de captura es B o C: la persona tiene que
    #: saber si el número puede ser culpa de la foto antes que de su cara.
    sensitive_to: dict[Locale, str]


#: Coletilla obligatoria de todo nivel 3. Una cirugía sugerida a partir de
#: fotos de móvil y marcas puestas a mano es irresponsable; mencionarla
#: como existente y remitir al especialista es información.
_SURGERY_NOTE = {
    "es": " Es una decisión de especialista, con medición clínica — nunca a partir de fotos.",
    "en": " That is a specialist's decision, on clinical measurement — never from photos.",
}


def _surgery(es: str, en: str) -> Option:
    return Option(3, es + _SURGERY_NOTE["es"], en + _SURGERY_NOTE["en"])


KNOWLEDGE: dict[str, MetricKnowledge] = {
    "goode_ratio": MetricKnowledge(
        what={
            "es": "Compara lo que la punta de la nariz se separa de la cara con lo larga que es la nariz, desde el entrecejo hasta la punta. Es la forma estándar de medir cuánto se proyecta la nariz sin depender del tamaño de la foto.",
            "en": "Compares how far the tip of the nose stands off the face with how long the nose is, from the brow to the tip. It is the standard way to measure nasal projection without depending on the size of the photo.",
        },
        inside={
            "es": "La punta se proyecta en proporción con el largo de la nariz: de perfil, ni adelantada ni hundida.",
            "en": "The tip projects in proportion to the length of the nose: in profile, neither pushed forward nor sunk back.",
        },
        meaning={
            "high": {
                "es": "La punta se adelanta más de lo que corresponde al largo de la nariz. De perfil, la nariz se ve más prominente.",
                "en": "The tip sits further forward than the length of the nose calls for. In profile, the nose reads as more prominent.",
            },
            "low": {
                "es": "La punta se proyecta poco para lo larga que es la nariz. De perfil, se ve más plana o como si cayera.",
                "en": "The tip projects little for how long the nose is. In profile it reads flatter, or as if it drops.",
            },
        },
        options={
            "high": (
                Option(0, "No cambia con hábitos. Lo que sí cambia cómo se percibe es el equilibrio con el mentón: una barba corta en la barbilla lo compensa.",
                          "No habit changes it. What does change how it reads is the balance with the chin: a short beard on the chin offsets it."),
                _surgery("Reducir la proyección de la punta es cirugía de nariz (rinoplastia).",
                         "Reducing tip projection is nose surgery (rhinoplasty)."),
            ),
            "low": (
                Option(0, "No cambia con hábitos, y es de las medidas que más varían con la lente: una selfie a un brazo de distancia agranda la nariz.",
                          "No habit changes it, and it is one of the measures most affected by the lens: a selfie at arm's length enlarges the nose."),
                Option(2, "Un relleno de ácido hialurónico en la punta (rinomodelación) puede proyectarla sin cirugía. Dura meses, no años.",
                          "A hyaluronic acid filler in the tip (non-surgical rhinoplasty) can project it without surgery. It lasts months, not years."),
                _surgery("La proyección permanente se consigue con rinoplastia.",
                         "Permanent projection comes from rhinoplasty."),
            ),
        },
        sensitive_to={
            "es": "la distancia de la cámara: de cerca, la lente agranda la nariz respecto al resto.",
            "en": "camera distance: up close, the lens enlarges the nose relative to the rest.",
        },
    ),
    "nasolabial_angle": MetricKnowledge(
        what={
            "es": "Es el ángulo que forman la parte de abajo de la nariz y el labio superior, visto de perfil. Dice hacia dónde apunta la punta de la nariz.",
            "en": "The angle formed by the underside of the nose and the upper lip, seen in profile. It says which way the tip of the nose points.",
        },
        inside={
            "es": "La punta apunta hacia delante, sin subir ni caer de forma apreciable.",
            "en": "The tip points forward, neither turned up nor drooping noticeably.",
        },
        meaning={
            "high": {
                "es": "La punta mira hacia arriba: de perfil se ve más de lo habitual la base de la nariz. Es lo que se suele llamar una nariz respingona.",
                "en": "The tip turns upwards: in profile, more of the base of the nose shows than usual. It is what people call an upturned nose.",
            },
            "low": {
                "es": "La punta cae hacia el labio. Es muy común, y suele acentuarse al sonreír o con los años.",
                "en": "The tip drops towards the lip. It is very common, and tends to show more when smiling or with age.",
            },
        },
        options={
            "high": (
                Option(0, "No cambia con hábitos. Ojo con la foto: levantar la barbilla abre este ángulo varios grados.",
                          "No habit changes it. Watch the photo: lifting the chin opens this angle by several degrees."),
                _surgery("Bajar una punta muy levantada solo se hace con rinoplastia.",
                         "Lowering a strongly upturned tip is only done with rhinoplasty."),
            ),
            "low": (
                Option(0, "Mídelo con la cara relajada: sonreír tira de la punta hacia abajo y cierra el ángulo.",
                          "Measure it with a relaxed face: smiling pulls the tip down and closes the angle."),
                Option(2, "La toxina botulínica en el músculo que tira de la punta hacia abajo puede subirla unos grados. Temporal: unos meses.",
                          "Botulinum toxin in the muscle that pulls the tip down can lift it a few degrees. Temporary: a few months."),
                _surgery("Subir la punta de forma permanente es rinoplastia.",
                         "Lifting the tip permanently is rhinoplasty."),
            ),
        },
        sensitive_to={
            "es": "la inclinación de la cabeza: con la barbilla levantada el ángulo sale más abierto de lo que es.",
            "en": "head tilt: with the chin up the angle comes out wider than it is.",
        },
    ),
    "nasofrontal_angle": MetricKnowledge(
        what={
            "es": "Es el ángulo del escalón entre la frente y la nariz, en el entrecejo. Dice si la nariz arranca con un hundimiento marcado o casi en línea con la frente.",
            "en": "The angle of the step between forehead and nose, at the bridge. It says whether the nose starts with a marked dip or almost in line with the forehead.",
        },
        inside={
            "es": "El paso de la frente a la nariz tiene una curva visible pero suave.",
            "en": "The transition from forehead to nose has a visible but gentle curve.",
        },
        meaning={
            "high": {
                "es": "El paso de la frente a la nariz es muy suave, casi recto: la nariz parece continuar la frente sin escalón.",
                "en": "The transition from forehead to nose is very gentle, almost straight: the nose seems to continue the forehead with no step.",
            },
            "low": {
                "es": "El entrecejo está hundido y la nariz arranca con un escalón marcado. Suele hacer que el dorso de la nariz parezca más prominente.",
                "en": "The bridge is deep and the nose starts with a marked step. It tends to make the nasal ridge look more prominent.",
            },
        },
        options={
            "high": (
                Option(0, "No cambia con hábitos, y es de las medidas que menos afecta a cómo se ve la cara de frente.",
                          "No habit changes it, and it is one of the measures that least affects how the face looks head-on."),
                _surgery("Profundizar el arranque de la nariz es rinoplastia.",
                         "Deepening the start of the nose is rhinoplasty."),
            ),
            "low": (
                Option(0, "No cambia con hábitos.",
                          "No habit changes it."),
                Option(2, "Un relleno en la raíz de la nariz suaviza el escalón sin cirugía. Temporal.",
                          "A filler at the root of the nose softens the step without surgery. Temporary."),
                _surgery("De forma permanente, con rinoplastia.",
                         "Permanently, with rhinoplasty."),
            ),
        },
        sensitive_to={
            "es": "dónde se marcan la glabela y el nasion: son puntos de hueso bajo piel, y un par de milímetros mueven el ángulo.",
            "en": "where glabella and nasion are marked: they are bone points under skin, and a couple of millimetres move the angle.",
        },
    ),
    "facial_convexity_angle": MetricKnowledge(
        what={
            "es": "Une con dos líneas el entrecejo, la base de la nariz y la barbilla, y mide el ángulo que forman. Dice si el perfil va recto o si hace curva, y hacia dónde.",
            "en": "It joins the brow, the base of the nose and the chin with two lines and measures the angle between them. It says whether the profile runs straight or curves, and which way.",
        },
        inside={
            "es": "El perfil tiene una curva ligera hacia fuera, que es lo más común: la barbilla un poco por detrás de la línea de la frente.",
            "en": "The profile has a slight outward curve, which is the most common: the chin a little behind the line of the forehead.",
        },
        meaning={
            "low": {
                "es": "El perfil hace más curva de lo habitual: la barbilla queda por detrás respecto a la frente y la nariz. Suele leerse como una barbilla poco marcada.",
                "en": "The profile curves more than usual: the chin sits back relative to forehead and nose. It usually reads as a weak chin.",
            },
            "high": {
                "es": "El perfil es muy recto o incluso hacia dentro: la barbilla avanza hasta la línea de la frente o más allá.",
                "en": "The profile is very straight or even inward: the chin comes forward to the line of the forehead or beyond.",
            },
        },
        options={
            "low": (
                Option(0, "La postura cuenta mucho: adelantar la cabeza respecto al cuello exagera este perfil. Una barba en la barbilla lo compensa visualmente.",
                          "Posture matters a lot: pushing the head forward of the neck exaggerates this profile. A beard on the chin offsets it visually."),
                Option(2, "Un relleno de barbilla la adelanta sin cirugía.",
                          "A chin filler brings it forward without surgery."),
                _surgery("De forma permanente, implante de mentón o genioplastia; si el origen es la mandíbula entera, cirugía ortognática.",
                         "Permanently, a chin implant or genioplasty; if the whole jaw is the cause, orthognathic surgery."),
            ),
            "high": (
                Option(0, "Una barba recortada corta en la barbilla reduce su presencia visual.",
                          "A short, trimmed beard on the chin reduces its visual presence."),
                _surgery("Si la mandíbula está adelantada, el tratamiento es ortodoncia y, a veces, cirugía ortognática.",
                         "If the jaw sits forward, the treatment is orthodontics and sometimes orthognathic surgery."),
            ),
        },
        sensitive_to={
            "es": "la postura: la cabeza adelantada o echada atrás cambia la posición aparente de la barbilla.",
            "en": "posture: a head pushed forward or tilted back changes where the chin appears.",
        },
    ),
    "upper_third_pct": MetricKnowledge(
        what={
            "es": "La cara se divide en tres alturas: del pelo a las cejas, de las cejas a la base de la nariz y de ahí a la barbilla. Esta es la primera: cuánto de la altura total ocupa la frente.",
            "en": "The face splits into three heights: hairline to brows, brows to the base of the nose, and from there to the chin. This is the first: how much of the total height the forehead takes.",
        },
        inside={
            "es": "Tu frente ocupa aproximadamente un tercio de la altura de la cara, que es el reparto más habitual.",
            "en": "Your forehead takes roughly a third of the face's height, which is the most common split.",
        },
        meaning={
            "high": {
                "es": "La frente ocupa más de lo habitual: es una frente alta, o una línea del pelo que ha subido.",
                "en": "The forehead takes more than usual: a high forehead, or a hairline that has moved up.",
            },
            "low": {
                "es": "La frente ocupa menos de lo habitual: el pelo nace bajo.",
                "en": "The forehead takes less than usual: the hairline starts low.",
            },
        },
        options={
            "high": (
                Option(0, "Es la medida que más cambia con el peinado: un flequillo o pelo hacia delante acorta visualmente la frente.",
                          "It is the measure the haircut changes most: a fringe or hair brought forward visually shortens the forehead."),
                Option(1, "Si la frente ha crecido por entradas, los tratamientos contra la caída frenan que siga subiendo.",
                          "If the forehead grew through a receding hairline, hair-loss treatments slow it from rising further."),
                _surgery("Bajar la línea del pelo es trasplante capilar o, en frentes muy altas, cirugía de descenso frontal.",
                         "Lowering the hairline is a hair transplant or, for very high foreheads, hairline-lowering surgery."),
            ),
            "low": (
                Option(0, "El peinado hacia atrás y despejado alarga visualmente la frente.",
                          "Hair swept back and clear of the face visually lengthens the forehead."),
            ),
        },
        sensitive_to={
            "es": "dónde se marque el nacimiento del pelo: con entradas, el punto se mueve y la medida con él.",
            "en": "where the hairline is marked: with a receding hairline the point moves, and the measure with it.",
        },
    ),
    "middle_third_pct": MetricKnowledge(
        what={
            "es": "Es la segunda de las tres alturas de la cara: de las cejas a la base de la nariz. Depende sobre todo de lo larga que sea la nariz.",
            "en": "The second of the face's three heights: from the brows to the base of the nose. It depends mostly on how long the nose is.",
        },
        inside={
            "es": "La zona de la nariz ocupa más o menos un tercio de la altura de la cara, lo habitual.",
            "en": "The nose area takes roughly a third of the face's height, which is usual.",
        },
        meaning={
            "high": {
                "es": "La zona entre las cejas y la base de la nariz ocupa más de lo habitual: la nariz es larga respecto al resto de la cara.",
                "en": "The area between brows and base of the nose takes more than usual: the nose is long relative to the rest of the face.",
            },
            "low": {
                "es": "La zona de la nariz ocupa menos de lo habitual: nariz corta respecto al resto.",
                "en": "The nose area takes less than usual: a short nose relative to the rest.",
            },
        },
        options={
            "high": (
                Option(0, "No cambia con hábitos ni con el peinado: es el largo de la nariz.",
                          "Neither habits nor haircut change it: it is the length of the nose."),
                _surgery("Acortar la nariz es rinoplastia.",
                         "Shortening the nose is rhinoplasty."),
            ),
            "low": (
                Option(0, "No cambia con hábitos ni con el peinado.",
                          "Neither habits nor haircut change it."),
            ),
        },
        sensitive_to={
            "es": "que las tres alturas se reparten el 100 %: si otra se marca mal, esta se mueve aunque esté bien.",
            "en": "the three heights sharing 100 %: if another one is marked wrong, this one moves even when it is right.",
        },
    ),
    "lower_third_pct": MetricKnowledge(
        what={
            "es": "Es la tercera altura de la cara: de la base de la nariz a la barbilla. Recoge labios, dientes y mandíbula.",
            "en": "The third height of the face: from the base of the nose to the chin. It takes in lips, teeth and jaw.",
        },
        inside={
            "es": "La parte baja de la cara ocupa lo habitual, en equilibrio con las otras dos.",
            "en": "The lower part of the face takes the usual share, balanced with the other two.",
        },
        meaning={
            "high": {
                "es": "La parte baja de la cara ocupa más de lo habitual: barbilla o mandíbula largas.",
                "en": "The lower part of the face takes more than usual: a long chin or jaw.",
            },
            "low": {
                "es": "La parte baja de la cara ocupa menos de lo habitual: barbilla corta o poco marcada.",
                "en": "The lower part of the face takes less than usual: a short or soft chin.",
            },
        },
        options={
            "high": (
                Option(0, "La boca cuenta: mídelo con los labios cerrados y los dientes en contacto. Una barba recortada por debajo acorta visualmente este tercio.",
                          "The mouth matters: measure it with lips closed and teeth touching. A beard trimmed short underneath visually shortens this third."),
                _surgery("Acortarlo es genioplastia o cirugía ortognática.",
                         "Shortening it is genioplasty or orthognathic surgery."),
            ),
            "low": (
                Option(0, "Mídelo con los dientes en contacto: con la boca cerrada muy apretada se acorta. Una barba en la barbilla lo alarga visualmente.",
                          "Measure it with teeth touching: a tightly clenched mouth shortens it. A beard on the chin visually lengthens it."),
                Option(2, "Un relleno de barbilla la alarga sin cirugía.",
                          "A chin filler lengthens it without surgery."),
                _surgery("De forma permanente, genioplastia o implante de mentón.",
                         "Permanently, genioplasty or a chin implant."),
            ),
        },
        sensitive_to={
            "es": "la posición de la boca: abrirla un poco o apretarla cambia esta medida más que ninguna otra.",
            "en": "the position of the mouth: opening it slightly or clenching it changes this measure more than any other.",
        },
    ),
    "mandibular_plane_angle": MetricKnowledge(
        what={
            "es": "Es la inclinación de la línea de la mandíbula —del ángulo de debajo de la oreja a la barbilla— respecto a la horizontal de la cara. Dice si la mandíbula cae empinada o va casi plana.",
            "en": "The slope of the jawline —from the angle below the ear to the chin— against the horizontal of the face. It says whether the jaw drops steeply or runs almost flat.",
        },
        inside={
            "es": "La mandíbula tiene la inclinación más común: ni muy empinada ni plana.",
            "en": "The jaw has the most common slope: neither steep nor flat.",
        },
        meaning={
            "high": {
                "es": "La mandíbula cae empinada hacia la barbilla. Suele ir con una cara más larga y un ángulo de la mandíbula poco marcado.",
                "en": "The jaw drops steeply towards the chin. It usually comes with a longer face and a soft jaw angle.",
            },
            "low": {
                "es": "La mandíbula va casi horizontal: ángulo marcado y cara más cuadrada.",
                "en": "The jaw runs almost horizontal: a marked angle and a squarer face.",
            },
        },
        options={
            "high": (
                Option(0, "Lo primero es descartar la foto: con la cabeza inclinada hacia abajo esta medida sale más alta de lo real. Repite el perfil mirando al horizonte.",
                          "First rule out the photo: with the head tilted down this measure comes out higher than it is. Retake the profile looking at the horizon."),
                Option(1, "Una barba que siga la línea de la mandíbula la hace ver más marcada.",
                          "A beard following the jawline makes it look more defined."),
                Option(2, "Un relleno en el ángulo de la mandíbula lo marca sin cirugía.",
                          "A filler at the jaw angle defines it without surgery."),
                _surgery("Cambiar la inclinación de verdad es cirugía ortognática, que decide un cirujano maxilofacial con radiografías.",
                         "Actually changing the slope is orthognathic surgery, decided by a maxillofacial surgeon with X-rays."),
            ),
            "low": (
                Option(0, "Con la cabeza echada hacia atrás sale más baja de lo real: repite el perfil mirando al horizonte.",
                          "With the head tilted back it comes out lower than it is: retake the profile looking at the horizon."),
                Option(2, "Si el ángulo marcado viene de músculo —apretar los dientes—, la toxina en el masetero lo suaviza.",
                          "If the marked angle comes from muscle —clenching—, toxin in the masseter softens it."),
            ),
        },
        sensitive_to={
            "es": "la inclinación de la cabeza: es un ángulo contra la horizontal, y cualquier cabeceo en la foto lo mueve igual.",
            "en": "head tilt: it is an angle against the horizontal, and any nod in the photo moves it just as much.",
        },
    ),
}

# ───────────────────────────── frontal ──────────────────────────────

KNOWLEDGE.update({
    "horizontal_fifths": MetricKnowledge(
        what={
            "es": "Compara el hueco entre tus ojos con el ancho de un ojo. El canon clásico divide la cara en cinco partes iguales —ojo, hueco, ojo y los dos lados—, y esta es la parte de ese canon que se puede medir con nitidez en una foto.",
            "en": "Compares the gap between your eyes with the width of one eye. The classical canon splits the face into five equal parts —eye, gap, eye and both sides—, and this is the part of that canon that can be measured cleanly in a photo.",
        },
        inside={
            "es": "El hueco entre tus ojos es del tamaño de un ojo, o algo más, que es lo más común en adultos.",
            "en": "The gap between your eyes is about one eye wide, or a little more, which is most common in adults.",
        },
        meaning={
            "high": {
                "es": "Tus ojos están más separados de lo habitual para su tamaño. De frente se lee como una mirada más abierta.",
                "en": "Your eyes sit further apart than usual for their size. Head-on it reads as a more open look.",
            },
            "low": {
                "es": "Tus ojos están más juntos de lo habitual para su tamaño: el hueco entre ellos es menor que un ojo.",
                "en": "Your eyes sit closer together than usual for their size: the gap between them is less than one eye.",
            },
        },
        options={
            "high": (
                Option(0, "Las cejas cambian mucho cómo se percibe: unas cejas que arrancan más cerca del centro acortan visualmente el hueco.",
                          "Brows change how it reads a lot: brows that start closer to the centre visually shorten the gap."),
                Option(1, "Con maquillaje, oscurecer la esquina interna del ojo acerca visualmente los ojos.",
                          "With make-up, darkening the inner corner of the eye visually brings the eyes closer."),
            ),
            "low": (
                Option(0, "Unas cejas que arrancan un poco más hacia fuera ensanchan visualmente el hueco entre los ojos.",
                          "Brows that start slightly further out visually widen the gap between the eyes."),
                Option(1, "Con maquillaje, aclarar la esquina interna y alargar la externa separa visualmente los ojos.",
                          "With make-up, lightening the inner corner and extending the outer one visually spaces the eyes."),
            ),
        },
        sensitive_to={
            "es": "lo precisas que queden las esquinas de los ojos: en una foto oscura o lejana se pierden entre las pestañas.",
            "en": "how precisely the eye corners are marked: in a dark or distant photo they get lost among the lashes.",
        },
    ),
    "facial_index": MetricKnowledge(
        what={
            "es": "Divide la altura de la cara —del entrecejo a la barbilla— entre su anchura a la altura de los pómulos. Es el índice clásico para decir si una cara es más alargada o más ancha.",
            "en": "Divides the height of the face —from the bridge of the nose to the chin— by its width at the cheekbones. It is the classical index for whether a face is longer or wider.",
        },
        inside={
            "es": "Tu cara tiene una proporción media entre alto y ancho: ni alargada ni ancha.",
            "en": "Your face has an average balance of height and width: neither long nor wide.",
        },
        meaning={
            "high": {
                "es": "Tu cara es más alargada de lo habitual: más alta respecto a lo ancha que es.",
                "en": "Your face is longer than usual: taller relative to how wide it is.",
            },
            "low": {
                "es": "Tu cara es más ancha de lo habitual respecto a su altura: una cara más corta y redondeada.",
                "en": "Your face is wider than usual relative to its height: a shorter, rounder face.",
            },
        },
        options={
            "high": (
                Option(0, "El corte de pelo es lo que más cambia esta proporción a la vista: volumen a los lados ensancha; volumen arriba alarga. Barba corta en los lados del mentón la compensa.",
                          "The haircut changes this proportion the most to the eye: volume at the sides widens; volume on top lengthens. A short beard at the sides of the chin offsets it."),
            ),
            "low": (
                Option(0, "Volumen arriba y lados cortos alargan visualmente la cara; una barba con algo más de largo en la barbilla también.",
                          "Volume on top with short sides visually lengthens the face; so does a beard slightly longer at the chin."),
                Option(2, "Si la anchura viene del músculo de la mandíbula —apretar los dientes—, la toxina en el masetero la estrecha. Temporal.",
                          "If the width comes from the jaw muscle —clenching—, toxin in the masseter slims it. Temporary."),
            ),
        },
        sensitive_to={
            "es": "dónde se marquen los pómulos: su borde es hueso bajo piel y no tiene una esquina nítida.",
            "en": "where the cheekbones are marked: their edge is bone under skin with no sharp corner.",
        },
    ),
    "midline_deviation": MetricKnowledge(
        what={
            "es": "Traza la línea media de tu cara —la vertical justo entre los dos ojos— y mide cuánto se apartan de ella la base de la nariz y la barbilla. Ninguna cara es simétrica del todo: esto dice cuánto.",
            "en": "Draws the midline of your face —the vertical exactly between the eyes— and measures how far the base of the nose and the chin stray from it. No face is fully symmetrical: this says how much.",
        },
        inside={
            "es": "La nariz y la barbilla caen prácticamente sobre la línea media: la asimetría que hay es la normal de cualquier cara.",
            "en": "Nose and chin sit practically on the midline: whatever asymmetry there is, it is the normal kind every face has.",
        },
        meaning={
            "high": {
                "es": "La base de la nariz o la barbilla se desvían de la línea media más de lo habitual. Puede notarse como una nariz o una mandíbula ligeramente torcidas.",
                "en": "The base of the nose or the chin strays from the midline more than usual. It can show as a slightly crooked nose or jaw.",
            },
            "low": {
                "es": "Desviación prácticamente nula.",
                "en": "Practically no deviation.",
            },
        },
        options={
            "high": (
                Option(0, "Antes que nada, descarta la foto: girar la cabeza un poco desplaza la nariz respecto a los ojos. Repite la frontal mirando recto al objetivo.",
                          "First rule out the photo: turning the head slightly shifts the nose against the eyes. Retake the frontal looking straight at the lens."),
                Option(2, "Si la desviación es de la punta de la nariz, un relleno puede disimularla sin cirugía.",
                          "If the deviation is in the tip of the nose, a filler can disguise it without surgery."),
                _surgery("Si es del tabique o de la mandíbula, la corrección es quirúrgica (septorrinoplastia u ortognática).",
                         "If it comes from the septum or the jaw, correction is surgical (septorhinoplasty or orthognathic)."),
            ),
            "low": (
                Option(0, "Nada que hacer: no hay desviación.",
                          "Nothing to do: there is no deviation."),
            ),
        },
        sensitive_to={
            "es": "el giro de la cabeza: unos pocos grados mueven la nariz respecto a los ojos más que cualquier asimetría real.",
            "en": "head turn: a few degrees move the nose against the eyes more than any real asymmetry.",
        },
    ),
    "canthal_tilt": MetricKnowledge(
        what={
            "es": "Es la inclinación de tus ojos: si la esquina de fuera queda más alta, a la misma altura o más baja que la de dentro. Se mide contra la línea que une las esquinas internas, así que no le afecta tener la cabeza un poco ladeada.",
            "en": "The tilt of your eyes: whether the outer corner sits higher, level or lower than the inner one. It is measured against the line joining the inner corners, so a slightly tilted head does not affect it.",
        },
        inside={
            "es": "La esquina externa de tus ojos queda algo más alta que la interna, que es lo más común.",
            "en": "The outer corner of your eyes sits slightly higher than the inner one, which is most common.",
        },
        meaning={
            "high": {
                "es": "La esquina externa sube bastante más que la interna: una mirada rasgada hacia arriba.",
                "en": "The outer corner rises well above the inner one: an upswept, almond look.",
            },
            "low": {
                "es": "La esquina externa queda a la altura o por debajo de la interna: la mirada cae hacia fuera.",
                "en": "The outer corner sits level with or below the inner one: the eye slopes down at the outside.",
            },
        },
        options={
            "high": (
                Option(0, "No hay nada que corregir: es una variante de forma, no un problema.",
                          "Nothing to correct: it is a variant of shape, not a problem."),
            ),
            "low": (
                Option(0, "Dormir bien y la cara descansada cuentan: el párpado cansado acentúa la caída. Las cejas bien definidas en la cola levantan visualmente la mirada.",
                          "Sleep and a rested face matter: a tired eyelid accentuates the droop. Brows defined at the tail visually lift the eyes."),
                Option(1, "Con maquillaje, un trazo que sube en la esquina externa compensa la inclinación.",
                          "With make-up, a line rising at the outer corner offsets the slope."),
                Option(2, "La toxina botulínica en la cola de la ceja eleva ligeramente la esquina externa. Temporal.",
                          "Botulinum toxin at the tail of the brow slightly lifts the outer corner. Temporary."),
                _surgery("Elevar la esquina de forma permanente es cantopexia.",
                         "Lifting the corner permanently is canthopexy."),
            ),
        },
        sensitive_to={
            "es": "la expresión: entrecerrar los ojos o sonreír levanta la esquina externa.",
            "en": "expression: squinting or smiling lifts the outer corner.",
        },
    ),
})

# ────────────────────────────── basal ───────────────────────────────

KNOWLEDGE.update({
    "nasal_axis_deviation": MetricKnowledge(
        what={
            "es": "Mira tu nariz desde abajo y mide si el tabique —la columela, la tira de carne entre los dos agujeros— apunta recto o se tuerce hacia un lado. Es la única vista donde una desviación pequeña no se confunde con la postura.",
            "en": "Looks at your nose from below and measures whether the columella —the strip between the nostrils— points straight or bends to one side. It is the only view where a small deviation cannot be mistaken for posture.",
        },
        inside={
            "es": "Tu nariz apunta recta desde la base: la pequeña desviación que hay es la de cualquier cara.",
            "en": "Your nose points straight from its base: whatever small deviation there is, every face has.",
        },
        meaning={
            "high": {
                "es": "La columela se tuerce hacia un lado más de lo habitual. De frente puede notarse como una punta ligeramente ladeada.",
                "en": "The columella bends to one side more than usual. Head-on it can show as a slightly sideways tip.",
            },
            "low": {"es": "Sin desviación.", "en": "No deviation."},
        },
        options={
            "high": (
                Option(0, "Lo primero, descartar la foto: si la cámara no estaba centrada bajo la barbilla, la nariz sale torcida sin estarlo. Repite la basal con el móvil justo debajo.",
                          "First rule out the photo: if the camera was not centred under the chin, the nose comes out crooked without being so. Retake the basal with the phone right underneath."),
                Option(2, "Si además cuesta respirar por un lado, es una consulta de otorrino, no de estética: un tabique desviado se trata por función.",
                          "If breathing is also harder on one side, that is an ENT visit, not an aesthetic one: a deviated septum is treated for function."),
                _surgery("Enderezar el tabique es septoplastia, o septorrinoplastia si también se corrige la forma.",
                         "Straightening the septum is septoplasty, or septorhinoplasty if the shape is corrected too."),
            ),
            "low": (Option(0, "Nada que hacer.", "Nothing to do."),),
        },
        sensitive_to={
            "es": "lo centrada que esté la cámara bajo la barbilla: un poco de lado y la nariz parece torcida.",
            "en": "how centred the camera is under the chin: slightly off and the nose looks crooked.",
        },
    ),
    "alar_base_symmetry": MetricKnowledge(
        what={
            "es": "Compara las dos mitades de la base de tu nariz vistas desde abajo: cuánto se separa cada aleta del tabique. Dice si los dos agujeros de la nariz son parecidos o uno es claramente más ancho.",
            "en": "Compares the two halves of the base of your nose seen from below: how far each nostril wing sits from the septum. It says whether both nostrils are similar or one is clearly wider.",
        },
        inside={
            "es": "Las dos mitades de la base de tu nariz son parecidas: la diferencia es la normal de cualquier cara.",
            "en": "Both halves of the base of your nose are similar: the difference is the normal one every face has.",
        },
        meaning={
            "high": {
                "es": "Una aleta queda bastante más separada del centro que la otra: un agujero de la nariz más ancho que el otro.",
                "en": "One wing sits well further from the centre than the other: one nostril wider than the other.",
            },
            "low": {"es": "Base nasal simétrica.", "en": "Symmetrical nasal base."},
        },
        options={
            "high": (
                Option(0, "Muy sensible a la foto: un pequeño giro de la cabeza ensancha una mitad. Repite la basal mirando al techo, con la cabeza recta.",
                          "Very sensitive to the photo: a slight head turn widens one half. Retake the basal looking at the ceiling, head straight."),
                Option(2, "Un relleno en la base de la aleta más estrecha puede igualarlas un poco. Temporal.",
                          "A filler at the base of the narrower wing can even them out a little. Temporary."),
                _surgery("Igualar las aletas de forma permanente es una resección alar, una técnica de rinoplastia.",
                         "Permanently matching the wings is an alar resection, a rhinoplasty technique."),
            ),
            "low": (Option(0, "Nada que hacer.", "Nothing to do."),),
        },
        sensitive_to={
            "es": "el giro de la cabeza: en la basal, unos grados ensanchan una mitad y estrechan la otra.",
            "en": "head turn: in the basal view, a few degrees widen one half and narrow the other.",
        },
    ),
})
