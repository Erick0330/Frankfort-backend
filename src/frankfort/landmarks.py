"""Puntos antropométricos canónicos y las vistas de las que salen.

Los nombres siguen la nomenclatura antropométrica estándar (Farkas), no
inventada, para que un cirujano que lea el informe reconozca de qué se
está hablando.

Nota sobre la vista 08: es un primer plano frontal para piel, según
docs/02-arquitectura.md §2. Hubo un periodo en que la landing decía
"cenital con inclinación", que era incompatible; se resolvió a favor de
esta, porque el primer plano habilita toda la sección dermatológica del
informe —y con ella los peldaños 0 y 1 de la escala de
recomendaciones, los gratuitos— mientras que la cenital solo aportaba
contorno del dorso, que ya dan los dos perfiles.
Ver docs/05-discrepancias.md, D-02.
"""

from __future__ import annotations

from enum import StrEnum


class View(StrEnum):
    FRONTAL_REST = "frontal_rest"
    FRONTAL_SMILE = "frontal_smile"
    PROFILE_RIGHT = "profile_right"
    PROFILE_LEFT = "profile_left"
    OBLIQUE_RIGHT = "oblique_right"
    OBLIQUE_LEFT = "oblique_left"
    BASAL = "basal"
    SKIN_CLOSEUP = "skin_closeup"


class Point(StrEnum):
    """Puntos en la línea media (sagitales) y bilaterales."""

    # ── Línea media, visibles en frontal y en perfil ──
    TRICHION = "trichion"          # nacimiento del pelo
    GLABELLA = "glabella"          # punto más prominente de la frente
    NASION = "nasion"              # raíz nasal, sutura nasofrontal
    PRONASALE = "pronasale"        # punta de la nariz
    SUBNASALE = "subnasale"        # unión de columela y labio superior
    LABRALE_SUPERIUS = "labrale_superius"
    STOMION = "stomion"            # cierre labial
    LABRALE_INFERIUS = "labrale_inferius"
    SUBLABIALE = "sublabiale"      # surco labiomentoniano
    POGONION = "pogonion"          # punto más anterior del mentón
    GNATHION = "gnathion"          # más inferior y anterior
    MENTON = "menton"              # punto más inferior del mentón

    # ── Solo perfil ──
    PORION = "porion"              # conducto auditivo — define Frankfort
    ORBITALE = "orbitale"          # borde infraorbitario — define Frankfort
    COLUMELLA_APEX = "columella_apex"
    ALAR_CREASE = "alar_crease"    # surco alar, origen de la proyección
    CERVICAL_POINT = "cervical_point"

    # ── Bilaterales ──
    ENDOCANTHION_L = "endocanthion_l"
    ENDOCANTHION_R = "endocanthion_r"
    EXOCANTHION_L = "exocanthion_l"
    EXOCANTHION_R = "exocanthion_r"
    ZYGION_L = "zygion_l"
    ZYGION_R = "zygion_r"
    GONION_L = "gonion_l"
    GONION_R = "gonion_r"
    ALARE_L = "alare_l"
    ALARE_R = "alare_r"
    CHEILION_L = "cheilion_l"
    CHEILION_R = "cheilion_r"


#: Puntos que exigen doble marcado.
#:
#: No es una lista arbitraria: son los que carecen de un borde visual
#: nítido, así que dos personas —o la misma dos veces— los sitúan en
#: sitios distintos. Es la razón de ser del doble marcado.
#:
#: Subnasale encabeza la lista por un motivo concreto: es de quien
#: dependen los tres tercios verticales, y fue el que arruinó la
#: medición en la sesión que originó este proyecto.
FRAGILE_POINTS: frozenset[Point] = frozenset(
    {
        Point.SUBNASALE,
        Point.PRONASALE,
        Point.GLABELLA,
        Point.TRICHION,
        Point.POGONION,
        Point.GNATHION,
        Point.NASION,
        Point.MENTON,
        Point.ALAR_CREASE,
        Point.CERVICAL_POINT,
    }
)

#: Puntos que MediaPipe puede dar automáticamente, y en qué vistas.
#: En perfil a 90° MediaPipe no devuelve nada, así que ahí todo es
#: marcado manual. Ver docs/01-estado-del-arte.md.
AUTO_POINTS: frozenset[Point] = frozenset(
    {
        Point.ENDOCANTHION_L,
        Point.ENDOCANTHION_R,
        Point.EXOCANTHION_L,
        Point.EXOCANTHION_R,
        Point.ALARE_L,
        Point.ALARE_R,
        Point.CHEILION_L,
        Point.CHEILION_R,
        Point.STOMION,
    }
)

#: Vistas en las que MediaPipe funciona. En las demás, marcado manual.
AUTO_VIEWS: frozenset[View] = frozenset(
    {View.FRONTAL_REST, View.FRONTAL_SMILE, View.SKIN_CLOSEUP}
)


def requires_double_marking(point: Point) -> bool:
    return point in FRAGILE_POINTS


def is_profile(view: View) -> bool:
    return view in (View.PROFILE_RIGHT, View.PROFILE_LEFT)


def mirror_view(view: View) -> View | None:
    """La vista del lado opuesto, para el control cruzado."""
    pairs = {
        View.PROFILE_RIGHT: View.PROFILE_LEFT,
        View.PROFILE_LEFT: View.PROFILE_RIGHT,
        View.OBLIQUE_RIGHT: View.OBLIQUE_LEFT,
        View.OBLIQUE_LEFT: View.OBLIQUE_RIGHT,
    }
    return pairs.get(view)
