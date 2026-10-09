"""El observador visual: las reglas que lo hacen defendible.

Ninguno de estos tests llama a un modelo. Prueban lo que rodea al
modelo —el vocabulario controlado, el veto a las cifras y a los
diagnósticos, el tope de confianza con una sola foto— con un proveedor
falso. Es lo que tiene que funcionar IGUAL con cualquier modelo que se
enchufe mañana.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from frankfort.api.app import app
from frankfort.observer import (
    TAGS,
    Observation,
    examples,
    observe,
    verify_all,
    verify_observation,
)

ALL = {"frontal_rest", "frontal_smile", "oblique_right", "oblique_left", "basal", "skin_closeup"}


def obs(**kw) -> Observation:
    base = dict(
        tag="dark_circles",
        area="skin",
        view="skin_closeup",
        claim="Debajo de los ojos hay un tono más oscuro que en el resto.",
        evidence="Una sombra azulada bajo el párpado inferior.",
        confidence="probable",
        corroborating_views=(),
    )
    base.update(kw)
    return Observation(**base)  # type: ignore[arg-type]


# ─────────────────── las reglas ───────────────────


def test_una_cifra_tumba_la_observacion():
    """Regla 1 de docs/02 §3: el observador describe, el motor mide."""
    out = verify_observation(obs(claim="Tienes unas 12 marcas en las mejillas, más bien pequeñas."), ALL)
    assert isinstance(out, str) and "cifra" in out


def test_un_diagnostico_con_nombre_tumba_la_observacion():
    out = verify_observation(obs(tag="redness", claim="Las rojeces de las mejillas parecen rosácea leve."), ALL)
    assert isinstance(out, str)


def test_un_juicio_estetico_tumba_la_observacion():
    out = verify_observation(obs(tag="malar_prominent", area="volume", view="oblique_right",
                                 claim="Tus pómulos tienen una belleza muy marcada en ángulo."), ALL)
    assert isinstance(out, str)


def test_una_sola_foto_nunca_es_claro():
    """Regla 2: lo que sale en una foto puede ser la foto."""
    out = verify_observation(obs(confidence="clear"), ALL)
    assert isinstance(out, Observation)
    assert out.confidence == "probable"


def test_corroborada_en_otra_foto_si_puede_ser_clara():
    out = verify_observation(obs(confidence="clear", corroborating_views=("frontal_rest",)), ALL)
    assert isinstance(out, Observation) and out.confidence == "clear"


def test_la_corroboracion_tiene_que_ser_una_foto_valida_para_esa_etiqueta():
    """Ver «ojeras» en la foto basal no corrobora nada: desde abajo no se
    ven los párpados. La corroboración inválida se quita, y con ella el
    «claro»."""
    out = verify_observation(obs(confidence="clear", corroborating_views=("basal",)), ALL)
    assert isinstance(out, Observation)
    assert out.corroborating_views == ()
    assert out.confidence == "probable"


def test_una_etiqueta_fuera_de_su_foto_se_descarta():
    """La sonrisa solo se ve en la foto de la sonrisa."""
    out = verify_observation(obs(tag="gum_display_high", area="smile", view="basal"), ALL)
    assert isinstance(out, str)


def test_no_se_puede_hablar_de_una_foto_que_no_se_mando():
    out = verify_observation(obs(), {"frontal_rest"})
    assert isinstance(out, str)


def test_una_etiqueta_inventada_se_descarta():
    assert isinstance(verify_observation(obs(tag="skin_glow"), ALL), str)


def test_las_repetidas_se_quedan_en_una():
    ok, rejected = verify_all([obs(), obs()], ALL)
    assert len(ok) == 1 and rejected


# ─────────────────── los ejemplos ───────────────────


@pytest.mark.parametrize("locale", ["es", "en"])
def test_los_ejemplos_cumplen_las_mismas_reglas(locale):
    """Los ejemplos se enseñan cuando no hay modelo. Si rompieran una
    regla, la pantalla de ejemplo enseñaría algo que el sistema real
    nunca dejaría pasar."""
    items = examples(locale)
    ok, rejected = verify_all(items, ALL)
    assert rejected == []
    assert len(ok) == len(items)


def test_los_ejemplos_cubren_las_cuatro_zonas():
    areas = {o.area for o in examples("es")}
    assert areas == {"skin", "smile", "volume", "nose_tip"}


def test_sin_foto_de_la_sonrisa_no_hay_ejemplo_de_la_sonrisa():
    items = examples("es", {"skin_closeup"})
    assert items and all(o.view == "skin_closeup" for o in items)


def test_todas_las_etiquetas_tienen_al_menos_una_foto():
    for name, tag in TAGS.items():
        assert tag.views, name


# ─────────────────── el flujo ───────────────────


def test_sin_proveedor_se_enseñan_los_ejemplos_y_se_dice():
    r = observe({"skin_closeup": b"x"}, "es", None)
    assert r.source == "example"
    assert r.observations


class FakeVision:
    name = "fake"
    model = "fake-vision"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.seen: dict[str, bytes] = {}

    def observe(self, system, photos, prompt):
        self.seen = photos
        return json.dumps(self.payload, ensure_ascii=False)


def test_con_proveedor_pasa_lo_bueno_y_se_tira_lo_malo():
    fake = FakeVision({"observations": [
        {"tag": "dark_circles", "view": "skin_closeup",
         "claim": "Debajo de los ojos hay un tono más oscuro.",
         "evidence": "Sombra bajo el párpado inferior en los dos ojos.",
         "confidence": "clear", "corroborating_views": []},
        {"tag": "redness", "view": "skin_closeup",
         "claim": "Tienes 3 zonas rojas en la cara, más o menos.",
         "evidence": "Rojez en mejillas y barbilla.",
         "confidence": "probable"},
    ]})
    r = observe({"skin_closeup": b"x"}, "es", fake)
    assert r.source == "agent"
    assert [o.tag for o in r.observations] == ["dark_circles"]
    assert r.observations[0].confidence == "probable"  # una sola foto
    assert r.rejected


def test_al_modelo_solo_le_llegan_las_fotos_enviadas():
    fake = FakeVision({"observations": []})
    observe({"skin_closeup": b"x", "frontal_smile": b"y"}, "es", fake)
    assert set(fake.seen) == {"skin_closeup", "frontal_smile"}


def test_si_el_modelo_falla_se_vuelve_a_los_ejemplos_y_se_dice():
    class Caido:
        name = "x"
        model = "x"

        def observe(self, system, photos, prompt):
            raise OSError("reset")

    r = observe({"skin_closeup": b"x"}, "es", Caido())
    assert r.source == "example"


# ─────────────────── la API ───────────────────

client = TestClient(app)
JPEG = base64.b64encode(b"\xff\xd8\xff\xe0fake").decode()


def test_sin_consentimiento_no_se_analiza_nada():
    r = client.post("/observe", json={"consent": False, "photos": {"skin_closeup": JPEG}})
    assert r.status_code == 422


def test_el_endpoint_dice_de_donde_salen_las_observaciones(monkeypatch):
    monkeypatch.setenv("FRANKFORT_LLM_PROVIDER", "none")
    r = client.post("/observe", json={"consent": True, "locale": "es",
                                      "photos": {"skin_closeup": JPEG, "oblique_right": JPEG,
                                                 "oblique_left": JPEG}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "example"
    assert body["observations"]
    assert {"tag", "area", "view", "claim", "evidence", "confidence", "corroboratingViews"} <= set(body["observations"][0])


def test_base64_roto_es_un_422():
    r = client.post("/observe", json={"consent": True, "photos": {"skin_closeup": "@@@"}})
    assert r.status_code == 422
