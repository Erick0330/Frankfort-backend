# Frankfort — API

Measurement engine and agents for Frankfort: facial measurement that states its
own error margin. The web app lives in
**[Frankfort-frontend](https://github.com/Erick0330/Frankfort-frontend)**.

**Rules decide, the model writes.** Everything an LLM produces goes through a
verifier; if it fails, the deterministic version is published and the response
says which one you got.

- `metrics.py`, `auditor.py`, `reliability.py` — 14 pure-geometry facial
  metrics, each with an error band propagated from double marking, and an
  auditor that cascades suppression to anything that does not hold.
- `narrative.py`, `insight.py`, `knowledge.py`, `agents.py` — the *explainer*:
  grounded generation over a hand-written knowledge base; it cannot cite a
  number that is not in the facts, nor write "clearly" when a measurement sits
  on the edge of its margin.
- `observer.py` — the *visual observer* (skin, smile, volume, nose tip): closed
  tag vocabulary, no figures, no diagnoses, single-photo findings capped at
  "probable". `scripts/eval_observer.py` scores rule compliance on real photos.
- `recommender.py` — the *recommender* and *safety reviewer*: a step plan from
  free to surgery with proportional escalation, "skin first", per-country
  prices, and a visible list of what the reviewer withdrew.
- `docs/` — architecture, design reversals and measured evaluations.

```bash
uv sync --extra api --extra dev
uv run pytest                                   # 210 tests
uv run uvicorn frankfort.api:app --port 8000
GROQ_API_KEY=... GEMINI_API_KEY=...             # optional: without keys,
                                                # everything runs deterministic
```

Code comments and documentation are in Spanish.

---

# frankfort (documentación en español)

El motor de medición: geometría, métricas, fiabilidad del marcado y el
auditor que decide qué se reporta y qué no.

El núcleo no depende de la web. `frankfort.api` importa el motor y nunca
al revés, así que todo el cálculo se testea sin FastAPI instalado.

## Desarrollo

```bash
uv sync --extra api --extra dev
uv run pytest
uv run uvicorn frankfort.api:app --reload --port 8000
```

`GET /health` dice la versión y cuántas métricas sabe calcular este
despliegue — que delata un servidor viejo mejor que el número de versión.

## `POST /audit`

Recibe COORDENADAS, nunca fotografías: el landmarking ocurre en el
navegador y las caras no salen de ahí para medir. Lo que cruza la red son
parejas de números en píxeles de la imagen original, y el sello de
calidad de la captura.

```json
{
  "views": [
    {
      "view": "profile_right",
      "captureGrade": "A",
      "width": 1200,
      "height": 1500,
      "points": {
        "porion": [[216, 630]],
        "orbitale": [[504, 630]],
        "subnasale": [[480, 780], [485, 787]]
      }
    }
  ]
}
```

Uno o dos marcados por punto, nunca tres. Los puntos frágiles
(`landmarks.FRAGILE_POINTS`) exigen dos: de la distancia entre sus dos
marcas sale la banda de error, y con ella la decisión de reportar o
suprimir.

Cada vista necesita su pareja de escala —intercantal en frontal, plano de
Frankfort en perfil— o la respuesta es un 422 que dice cuál falta. Sin
ella no hay contra qué comparar las discrepancias.

La respuesta es la parte del informe que sabe el motor: métricas con su
banda, controles cruzados entre perfiles, puntos no fiables y frágiles
marcados una sola vez. El sello de captura y las vistas que faltan NO
vuelven: los produce el navegador y devolverlos solo crearía una segunda
copia que puede contradecir a la primera.

Reproducible al bit: misma entrada, mismo informe. El muestreo de
`propagate_error` va con semilla fija, porque un informe que no se puede
citar dos veces no se puede citar.

## El resumen, y la capa de agentes

La respuesta trae también `summary`: el informe en lenguaje llano, que es
lo primero que se lee en la pantalla. Lo redacta el servidor y no el
cliente porque resumir exige mirar todas las medidas a la vez y decidir
cuál merece la primera frase — eso es síntesis, no presentación.

Se produce en dos pasos:

1. `narrative.py` arma los **hechos** (`Brief`) y un resumen con
   plantillas. Determinista, sin red, y publicable tal cual.
2. `agents.py` —el nodo `explainer` de docs/02 §4— lo reescribe con un
   LLM para que suene a persona.

El agente **no puede introducir un número que el motor no haya
calculado**. Lo que devuelve se verifica antes de publicarse: las cifras
contra los hechos, nada de vocabulario de diagnóstico ni de estética,
prosa sin listas ni titulares. Si falla la verificación, si el proveedor
tarda o si no hay clave, se publica el texto del motor — y
`summarySource` dice cuál de los dos salió.

```bash
# Opcional. Sin esto el informe funciona igual, con el texto del motor.
export GROQ_API_KEY=...          # o GEMINI_API_KEY
export FRANKFORT_LLM_PROVIDER=auto   # groq | gemini | none
export FRANKFORT_LLM_MODEL=...       # opcional, si no el de por defecto
```

Al agente solo le llegan **números** —medidas, rangos y márgenes—, nunca
fotografías ni coordenadas. Eso deja fuera del problema toda la
discusión de privacidad de docs/03: no hay nada en el prompt que
identifique a nadie.

## Explicaciones personalizadas por medida

Además del resumen, la respuesta trae `insights`: una explicación por
cada medida publicable, que responde a las cuatro preguntas de quien lee.

| Pregunta | Campo | Quién lo escribe |
|---|---|---|
| ¿Qué es? | `what` | `knowledge.py`, a mano |
| ¿Cómo está la mía? | `reading` | el agente, sobre la plantilla de `insight.py` |
| ¿Qué significa? | `meaning` | el agente, sobre `knowledge.py` |
| ¿Se puede cambiar? | `options` | `knowledge.py`, filtrado por proporcionalidad |

Tres piezas, y la separación es el diseño:

- **Generación anclada.** El conocimiento —qué mide cada cosa, qué
  significa cada lado del rango, qué se puede hacer— vive escrito y
  revisado en `knowledge.py`. El agente no lo saca de su memoria: lo
  cruza con las cifras de esa persona y lo redacta.
- **Certeza calculada, no redactada.** `insight.certainty()` cruza la
  banda de error con el rango: si incluso en el peor caso del margen la
  medida sigue del mismo lado, es `firm`; si el margen cruza el borde, es
  `edge`, y ni se recomienda nada ni el agente puede escribir «claramente».
- **El modelo redacta, no decide.** Hasta qué nivel de intervención se
  habla (gratis → cosmético → médico → cirugía) lo decide
  `allowed_level()` según cuánto se sale la medida. El agente no toca
  `what` ni `options` aunque los devuelva.

Una sola llamada para todas las medidas —presupuesto de la cuota gratuita
y, sobre todo, para que el agente pueda relacionar una medida con otra—,
en modo JSON del proveedor, con verificación campo a campo: el campo que
falla vuelve a la plantilla sin tirar el resto.

## `POST /observe` — el observador visual

La única petición con imágenes. Exige `consent: true` explícito, recibe
las fotos en base64 (reducidas a 1024 px por el cliente), las analiza y
las descarta: ni disco, ni log. Devuelve observaciones de piel, sonrisa,
volumen y punta de la nariz, con un vocabulario cerrado de etiquetas
(`observer.TAGS`).

Las reglas se hacen cumplir con código: ninguna cifra, ningún nombre de
enfermedad, y lo que solo se ve en una foto nunca pasa de «probable».
Sin `GEMINI_API_KEY` devuelve observaciones de EJEMPLO con
`source: "example"`, que pasan por el mismo verificador.

Banco de evaluación sobre las ocho fotos de prueba:

```bash
GEMINI_API_KEY=... uv run python scripts/eval_observer.py
```

## `POST /plan` — recomendador y revisor de seguridad

Recibe las medidas de `/audit` y las observaciones de `/observe`, y
devuelve un plan por escalones (gratis → cosmético → médico → cirugía)
con precios orientativos para España, México, Colombia, Argentina o
EEUU. Las reglas —escalada proporcional, «primero la piel», nada sobre
medidas en el borde de su margen— viven en `recommender.py`; el LLM solo
redacta la introducción. Lo que el revisor retira se devuelve en
`vetoed`, con el motivo.
