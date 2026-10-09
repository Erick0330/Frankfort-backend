# Arquitectura y flujos

Deriva de los hallazgos en [01-estado-del-arte.md](01-estado-del-arte.md). Las decisiones marcadas **[D]** son las que necesitan tu confirmación antes de escribir código.

---

## 0. El principio que ordena todo

> **Ninguna afirmación sale del sistema sin su procedencia y su nivel de confianza adjuntos. Una métrica que descansa en un punto mal marcado no se reporta con una advertencia: no se reporta.**

Esto es lo que separa el producto de Qoves y de Looksmax, y es la lección literal de tu sesión previa. Todo lo demás en este documento es maquinaria para sostener esa frase.

Corolarios que se implementan como restricciones duras:
1. **Prohibido el milímetro.** Solo ángulos y ratios adimensionales. La fotogrametría 2D no da escala absoluta fiable.
2. **Prohibida la proporción áurea.** Sin base empírica.
3. **Prohibido inferir etnia, ancestría u origen.** Prohibición del EU AI Act, no una preferencia.
4. **Prohibido un score global de atractivo.** No es medible, y es el vector principal de daño psicológico.
5. **El LLM de visión nunca produce números.** Los números salen de geometría determinista. El VLM describe cualidades; el motor mide.

El punto 5 es el más importante y el más fácil de romper por accidente. Un VLM al que le preguntás "¿cuánto mide el ratio de Goode?" **inventa un número plausible**. La separación tiene que ser arquitectónica: el VLM ni ve la pregunta métrica.

---

## 1. Stack

```
┌─ Next.js 15 (App Router) en Vercel Hobby ──────────────────┐
│  · Landing (estático, SSG)                                  │
│  · App: captura guiada, marcado manual, visor de informe    │
│  · MediaPipe FaceLandmarker vía WASM  ← geometría en cliente│
└──────────────────────┬──────────────────────────────────────┘
                       │ REST + SSE (streaming de progreso)
┌──────────────────────┴──────────────────────────────────────┐
│  FastAPI en Hugging Face Spaces (Docker, CPU free)          │
│  · Grafo LangGraph (orquestación de agentes)                │
│  · Motor de métricas determinista (numpy, sin ML)           │
│  · Capa de abstracción de proveedor LLM                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
┌───────┴────────┐          ┌─────────┴──────────┐
│ Supabase free  │          │  Proveedores LLM   │
│ · Auth         │          │  · Groq (texto)    │
│ · Postgres     │          │  · [D] visión      │
│ · SIN fotos    │          └────────────────────┘
└────────────────┘
```

### Por qué MediaPipe en el cliente y no en el servidor
Tres razones y todas pesan:
- **Coste cero de cómputo.** El free tier de HF Spaces es CPU compartida; correr MediaPipe por request lo tumba.
- **Privacidad real.** Las fotos frontales y oblicuas nunca salen del navegador para el landmarking. Solo viajan al servidor las que necesita el VLM, y solo si el usuario lo acepta.
- **Latencia.** Feedback en vivo durante la captura ("acercate", "nivelá la cabeza") es imposible con round-trip.

### El problema del cold start
Render free duerme a los 15 min (~50 s de arranque); HF Spaces a las 48 h. Mitigación:
- Un **GitHub Actions cron** (gratis) que pinguee backend y Supabase cada ~10 min en horario activo. Resuelve también la pausa de Supabase a los 7 días.
- La landing es estática en Vercel, así que el primer contacto es siempre instantáneo. El backend solo se necesita cuando el usuario ya está en el flujo de análisis, momento en que un spinner honesto ("iniciando el motor de análisis, ~40 s") es aceptable.

---

## 2. El protocolo de captura — las 8 fotos

No es un formulario de upload. Es un wizard de 8 pasos, cada uno con: foto de ejemplo, overlay de guía en vivo sobre la cámara, y **validación automática que bloquea el avance**.

| # | Vista | Para qué es indispensable |
|---|---|---|
| 1 | **Frontal, reposo** | Tercios y quintos verticales, anchuras, canthal tilt, simetría, desviación nasal, posición de cejas |
| 2 | **Frontal, sonrisa completa** | Exposición gingival, corredores bucales, simetría dinámica, curva de la sonrisa |
| 3 | **Perfil derecho 90°** | Ángulo nasofrontal, nasolabial, dorso, ratio de Goode, proyección de mentón, ángulo mentocervical |
| 4 | **Perfil izquierdo 90°** | Lo mismo — **y es el control cruzado**: si los dos perfiles no coinciden, la medición es sospechosa (§4) |
| 5 | **Oblicua derecha 45°** | Proyección malar, transición dorso-punta, definición mandibular |
| 6 | **Oblicua izquierda 45°** | Control cruzado de la anterior |
| 7 | **Basal / submental** (cabeza hacia atrás, cámara desde abajo) | Base nasal, forma de la punta, simetría de las alas, desviación del tabique |
| 8 | **Frontal cerca, luz difusa, sin flash** | Piel: acné, textura, poros, eritema, ojeras, pigmentación |

Las 6 primeras en **plano horizontal de Frankfurt** (borde infraorbitario alineado con el trago), expresión neutra, pelo retirado de la frente y orejas visibles, fondo liso, luz frontal difusa.

### Validación por foto (gate duro, no advertencia)
Corre en el navegador antes de aceptar cada imagen:

| Check | Método | Falla si |
|---|---|---|
| Ángulo de cabeza correcto para la vista | Head pose (matriz de transformación de MediaPipe en frontales/oblicuas; estimación por ratio de anchuras en perfiles) | Desvío > 7° del objetivo |
| Nitidez | Varianza del Laplaciano en canvas | Bajo umbral |
| Exposición | Histograma: clipping en sombras/luces | > 5% píxeles quemados en la zona facial |
| Expresión neutra (1, 3–7) | Blendshapes de MediaPipe (`mouthSmile`, `browDown`, `eyeSquint`) | Cualquiera sobre umbral |
| Oclusión | Pelo/gafas/mano sobre landmarks clave | Landmarks clave ocultos |
| **Distancia y focal** | EXIF si existe; si no, **selfie a distancia de brazo queda rechazada** | Ver abajo |

**Sobre la distorsión de perspectiva** — es el hallazgo más incómodo de la literatura y no hay solución mágica. La mitigación honesta:
- Instrucción explícita: **cámara trasera, no la frontal**, a ~1,5–2 m, con alguien sujetándola o un trípode/temporizador. La cámara frontal de un móvil es gran angular y a distancia de brazo deforma la nariz varios puntos porcentuales — exactamente la métrica que más te importaba.
- Leer focal y modelo del EXIF cuando esté disponible, y **anotar el informe con la banda de error correspondiente**.
- Si el usuario solo puede hacer selfies: la app funciona, pero **degrada explícitamente** los hallazgos de proyección (Goode, proyección de mentón) a "no medible con esta captura".

**[D1]** Esto es fricción real. Un usuario con el móvil en la mano y sin ayuda no va a poder completar el set correctamente. ¿Aceptamos el modo degradado con hallazgos suprimidos (honesto, pero más pobre), o hacemos la captura asistida obligatoria (riguroso, pero mucha gente abandona)? Mi recomendación: permitir ambos, con un **sello de calidad de captura** visible en el informe (A/B/C) y la lista de métricas suprimidas en el nivel C.

---

## 3. Los dos niveles de análisis (tu flujo, con la corrección técnica)

### Nivel 1 — Observación cualitativa (automática, sin marcado)
El VLM mira las 8 fotos y produce **solo descripciones verificables visualmente**, con prohibición explícita de números. Salida estructurada:

```python
class Observation(BaseModel):
    region: Literal["nose","chin","jaw","eyes","brows","midface","skin","lips","forehead"]
    view: PhotoView                    # de qué foto sale
    claim: str                         # "el dorso presenta convexidad en el tercio medio"
    visual_evidence: str               # qué se ve exactamente que lo sustenta
    confidence: Literal["clear","probable","uncertain"]
    corroborating_views: list[PhotoView]   # ¿se ve en más de una foto?
```

Regla: una observación vista en **una sola foto** nunca sube de `probable`. Es la generalización directa del fallo del tercio inferior.

Después, el nodo `explainer` traduce el bloque técnico a lenguaje llano. **Dos registros, mismo contenido** — no un resumen, una traducción. El usuario puede alternar entre ambos en el visor.

### Nivel 2 — Medición guiada (opcional, con humano en el loop)
Aquí es donde entra tu idea del marcado paso a paso, y la literatura la justifica: MediaPipe **no devuelve nada** en perfil a 90°, así que no hay alternativa automática.

Flujo por punto:
1. Se muestra la foto ampliada con zoom y lupa en el cursor.
2. Al lado, **foto de ejemplo anotada** del mismo punto en otra cara, más definición anatómica en una frase. Ej. para *subnasale*: "el punto más profundo donde el labio superior se une a la columela — no la punta de la nariz, no el borde del labio".
3. El usuario marca. Feedback inmediato si el punto cae fuera de la región plausible (validación por región respecto a los puntos ya marcados).
4. **Los puntos críticos se marcan dos veces**, en pasadas separadas y en orden distinto.

**El doble marcado es el corazón del sistema.** Da el error intra-observador, y de ahí sale la decisión de reportar o suprimir cada métrica. Es la solución mecánica al problema que tuviste: si `Sn` se marca dos veces y las dos marcas discrepan más de la tolerancia, todas las métricas que dependen de `Sn` —los tercios verticales— quedan suprimidas automáticamente. Nunca llegan al informe con un número.

Puntos que requieren doble marcado (los frágiles): `subnasale`, `pronasale`, `glabella`, `trichion`, `pogonion`, `gnathion`, `nasion`, `menton`.

**[D2]** El set completo son ~14 puntos en frontal (automáticos con MediaPipe) + ~12 por perfil × 2 perfiles, con doble marcado en 8 de ellos ≈ **40+ interacciones de marcado**. Eso son 10–15 minutos de trabajo del usuario. ¿Lo partimos en módulos que se pueden completar por separado (*"medí solo el perfil nasal: 6 puntos, 3 minutos"*) y así el usuario elige qué le interesa? Mi recomendación: sí, módulos por región, con el nivel 1 siempre como entrada gratuita.

---

## 4. El grafo LangGraph

```
                      ┌──────────────┐
   8 fotos  ────────► │   intake     │  validación por foto, calidad A/B/C
                      │  validator   │  (mayormente cliente; servidor confirma)
                      └──────┬───────┘
                             │
                   ┌─────────┴─────────┐   paralelo
                   ▼                   ▼
          ┌────────────────┐   ┌────────────────┐
          │ visual_observer│   │ landmark_engine│
          │  (VLM × vista) │   │ (MediaPipe +   │
          │  SIN números   │   │  manual)       │
          └────────┬───────┘   └────────┬───────┘
                   │                    ▼
                   │           ┌────────────────┐
                   │           │  metrics_calc  │  numpy puro, 0 LLM
                   │           │  ángulos+ratios│
                   │           └────────┬───────┘
                   │                    ▼
                   │           ┌────────────────┐
                   │           │   metrology    │  ◄── EL NODO CLAVE
                   │           │    auditor     │
                   │           └────────┬───────┘
                   └─────────┬──────────┘
                             ▼
                    ┌────────────────┐
                    │   synthesis    │  resuelve contradicciones
                    └────────┬───────┘         VLM ↔ métricas
                             ▼
                    ┌────────────────┐
                    │  red_team      │  ◄── veto, refuta cada hallazgo
                    └────────┬───────┘
                        ┌────┴────┐
              refutado  │         │ sobrevive
                        ▼         ▼
                 (descartar) ┌────────────────┐
                             │  recommender   │  intervenciones por nivel
                             └────────┬───────┘   + geo del usuario
                                      ▼
                             ┌────────────────┐
                             │ safety_reviewer│  ◄── veto final
                             └────────┬───────┘
                                      ▼
                             ┌────────────────┐
                             │   explainer    │  técnico → llano
                             └────────────────┘
```

Los nodos que hacen el trabajo real:

**`metrology_auditor`** — mitad determinista, mitad LLM. Es lo que nadie más tiene:
- **Simetría izquierda/derecha**: compara la misma métrica medida en perfil D y perfil I. Si el nasolabial da 95° y 108°, o hay asimetría real o hay error de marcado, y hay que decir cuál. (En tu caso el Goode dio 0.63 y 0.67 en dos mediciones independientes → coincidencia razonable → el hallazgo de sobreproyección era **sólido**, y así hay que reportarlo.)
- **Error intra-observador**: de las marcas duplicadas. Métrica cuya banda de error supera su desviación respecto a la norma → **suprimida**.
- **Grafo de dependencias punto→métrica**: cada métrica declara de qué puntos depende. Un punto marcado como poco fiable invalida en cascada todas sus métricas. Determinista, sin LLM, sin posibilidad de que se le olvide.
- **Penalización por calidad de captura**: la banda de error se ensancha según el sello A/B/C y el EXIF.

**`red_team`** — un agente cuyo único trabajo es **refutar**. Recibe cada hallazgo y su procedencia, e intenta tumbarlo: ¿se apoya en una sola foto? ¿en un punto de marcado frágil? ¿es un artefacto de pose o de iluminación? ¿la magnitud es perceptible o es ruido? Por defecto refuta ante la duda. Un hallazgo que no sobrevive no aparece en el informe — o aparece en una sección **"Descartado y por qué"**, que es contenido genuinamente valioso y que ningún competidor ofrece.

**`recommender`** — políticas duras, no criterio del modelo. Escala obligatoria de menos a más invasivo:
```
0. Gratis / conductual  → sueño, corte de pelo, barba, postura, hidratación
1. Cosmético / tópico   → rutina de piel, retinoides OTC, protector solar, cejas
2. Médico no quirúrgico → dermatólogo, tópicos con receta, láser, filler
3. Quirúrgico           → solo con las 4 condiciones del §5
```
Cada recomendación viene con producto/servicio real, disponible **en el país del usuario** (`user_locale`), con rango de precio y qué esperar. Nunca se salta niveles: si hay acné activo, se resuelve antes de hablar de cirugía nasal — que además es requisito preoperatorio real de la mayoría de cirujanos.

**`safety_reviewer`** — veto final. Verifica: nada de diagnóstico médico, nada de score global, nada de inferencia étnica, nada de números sin banda de error, y **escalada proporcional**: si la magnitud del hallazgo es leve y la intervención propuesta es mayor, se bloquea. Eso es exactamente el juicio correcto del tercio inferior: *"la magnitud de la cirugía no tiene ninguna relación con el tamaño del problema"* — ortognática por una proporción 8% distinta (medida mal, además) es desproporcionado y el sistema debe negarse solo.

### Human-in-the-loop
El marcado manual se implementa con `interrupt()` de LangGraph: el grafo se pausa en `landmark_engine`, persiste el estado en el checkpointer (Postgres de Supabase), el frontend recoge los puntos del usuario y reanuda. Esto permite además que el usuario **abandone y vuelva días después** sin perder el progreso — que con 40 marcados es imprescindible.

### Presupuesto de llamadas LLM (revisado — ver [03-proveedores-llm-gratis.md](03-proveedores-llm-gratis.md))

El límite que muerde en Groq no es RPM ni RPD sino **TPD**: `gpt-oss-120b` tiene 200K tokens/día ≈ **~100 llamadas**, no 1.000. Así que hay que repartir por dificultad y agrupar imágenes.

| Nodo | Llamadas | Nivel de modelo |
|---|---|---|
| `intake_validator` | 0–1 | barato (`llama-3.1-8b-instant`) |
| `visual_observer` | **3** (imágenes agrupadas, no 8) | visión |
| `metrology_auditor` | 1 | **duro** (`gpt-oss-120b`) |
| `synthesis` | 1 | **duro** |
| `red_team` | 2 (hallazgos batcheados) | barato |
| `recommender` | 1–2 | medio (`qwen3-32b`) |
| `safety_reviewer` | 1 | **duro** |
| `explainer` | 2 (técnico + llano) | medio |
| **Total** | **~12 llamadas**, de las cuales solo **3 al modelo duro** | |

Con 200K TPD en el modelo duro y 3 llamadas por análisis: **~20-25 análisis completos al día**. El resto de nodos van a modelos con 14.400 RPD, que no son el cuello de botella.

**Agrupación de imágenes** (8 → 3 llamadas de visión): los VLM aceptan varias imágenes por request.
1. Morfología: frontal reposo + perfil D + perfil I + basal
2. Contexto: sonrisa + oblicua D + oblicua I
3. Piel: sola, a máxima resolución

Beneficio secundario y nada menor: las caras salen del navegador en 3 requests, no en 8.

---

## 5. La política de cirugía (codificada, no improvisada)

Destilada de la postura que ya funcionó en tu sesión. El `recommender` solo menciona la opción quirúrgica si se cumplen **las cuatro**:

1. **El usuario ha declarado incomodidad sostenida con esa región.** Se pregunta, no se asume. Ninguna métrica por sí sola desbloquea una recomendación quirúrgica — *"no operes porque una métrica te lo diga"*.
2. **El hallazgo sobrevivió al `red_team`** y descansa en ≥2 mediciones o vistas concordantes.
3. **La magnitud de la intervención es proporcional** al hallazgo.
4. **Los niveles 0–2 están agotados o son inaplicables.**

Y cuando se menciona, viene completo o no viene: tasa de revisión, tiempo hasta resultado final, riesgo funcional, irreversibilidad, cómo elegir cirujano (credencial concreta del país del usuario), rango de coste local, cobertura pública si hay componente funcional, y timing. Ese fue el contenido más útil de tu informe y es replicable como plantilla.

**Screening de dismorfia**: un cuestionario breve y opcional al inicio. No diagnostica. Si el patrón de respuestas es de riesgo, el sistema **no se bloquea** —eso es paternalista y el usuario se va a otra app peor— pero cambia el tono, prioriza los niveles 0–1, y menciona que hablarlo con un profesional antes de decidir es parte del proceso normal, no un castigo.

---

## 6. Modelo de datos (sin fotos)

```sql
users            -- Supabase Auth
sessions         -- id, user_id, locale, capture_grade, status, created_at
photo_meta       -- session_id, view, quality_checks jsonb, exif jsonb, sha256
                 --   ↑ metadatos y hash. NUNCA la imagen.
landmarks        -- session_id, view, point_name, x, y, pass_number, source(auto|manual)
metrics          -- session_id, name, value, unit, error_band, depends_on[], status(reported|suppressed), suppression_reason
findings         -- session_id, region, claim, provenance jsonb, confidence, red_team_verdict, rationale
recommendations  -- session_id, finding_id, tier, action, product_or_service, price_range, locale, caveats
reports          -- session_id, technical_md, plain_md, pdf_path, model_versions jsonb
consents         -- user_id, scope, granted_at, provider_disclosed, revoked_at
```

Coordenadas de landmarks **normalizadas** por una distancia de referencia intra-imagen (distancia intercantal, la más estable), no en píxeles. Así el dato sobrevive a cambios de resolución.

`model_versions` en `reports` es para reproducibilidad: dentro de seis meses el modelo de visión habrá cambiado (Groq deprecó dos en cinco meses) y hay que saber qué produjo cada informe.

---

## 7. Decisiones

- **[D1] RESUELTA** — Ambos modos de captura + **sello de calidad A/B/C** visible en el informe, con lista explícita de métricas suprimidas en el nivel C.
- **[D2] RESUELTA** — **Módulos por región** (nariz / perfil / tercios / ojos / mandíbula). Nivel 1 siempre gratis como entrada. Progreso guardable vía `interrupt()` + checkpointer.
- **[D3] RESUELTA** — Cuenta fuera de UE/EEE/Suiza/UK, así que **no aplica la excepción regional de Gemini**: su free tier entrena con los datos y admite revisión humana. **Gemini queda descartado para imágenes.** Ver [03-proveedores-llm-gratis.md](03-proveedores-llm-gratis.md).
  - **Visión → Cloudflare Workers AI** (`llama-3.2-11b-vision-instruct`). No entrena con datos de inferencia ni los comparte, sin importar la región. 10.000 neurons/día.
  - **Texto → Groq**, una sola cuenta, repartiendo por dificultad (los límites son por organización, así que rotar keys no multiplica nada).
  - **Fallback de visión → GitHub Models** (GPT-4o, 50 RPD) y luego degradación explícita a "nivel 1 no disponible".
  - Gemini queda disponible **solo para texto**, donde no hay caras en juego y su cuota es generosa.
- **[D4] RESUELTA** — Proyecto **personal / portfolio**. Vercel Hobby + HF Spaces + Supabase free, sin conflicto de términos.
- **[D5] RESUELTA** — Imágenes: **Supabase Storage con TTL corto y borrado duro**, no Cloudinary. Ver [04-manejo-de-imagenes.md](04-manejo-de-imagenes.md).

---

## 8. Orden de construcción propuesto

1. **Espina dorsal del riesgo primero**: verificar `qwen/qwen3.6-27b` con visión en el free tier de Groq. Un script de 20 líneas. Si falla, [D3] cambia y con él parte del stack — hay que saberlo antes de escribir nada más.
2. Motor de métricas determinista + grafo de dependencias punto→métrica + `metrology_auditor`. **Sin LLM, con tests unitarios sobre caras sintéticas de geometría conocida.** Es el núcleo defendible; si esto no es correcto, nada más importa.
3. Wizard de captura + validación en cliente con MediaPipe.
4. Marcado manual guiado con doble pasada.
5. Grafo LangGraph completo, empezando por `visual_observer` + `synthesis`.
6. `red_team` + `safety_reviewer` + `recommender`.
7. Landing y visor de informe.
8. PDF (reciclando el generador de reportlab que ya tenés).
