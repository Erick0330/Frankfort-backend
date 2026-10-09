# Proveedores LLM gratis — informe y estrategia de resiliencia

Fecha: 2026-08-06. **Todas las cuotas cambian rápido; hay que verificarlas en runtime, no confiar en este documento a los 3 meses.**

---

## 1. Tu estrategia de rotación de keys: una funciona, la otra no

### Groq: rotar 3 API keys **no sirve de nada**

Los rate limits de Groq son **a nivel de organización, no por API key**. Cita directa de la documentación y de los análisis: crear cinco keys no te da 150 RPM — sigue siendo 30 RPM compartido en toda la cuenta. Todas las keys de una misma organización comparten el mismo cubo.

Para multiplicar de verdad harían falta **3 cuentas separadas**, y eso es evasión de límites: es la clase de cosa que hace que te baneen la cuenta principal justo cuando el proyecto tiene usuarios. Para un portfolio público no vale la pena el riesgo. La vía legítima es `console.groq.com/settings/limits`, donde se pueden pedir límites mayores para cargas específicas.

Lo que **sí** tiene sentido con varias keys de Groq: **aislamiento**, no multiplicación. Una key para desarrollo y otra para producción, para que tus pruebas no se coman la cuota de los usuarios.

### Gemini: aquí sí escala, y es legítimo

Las cuotas de Gemini son **por proyecto de Google Cloud**, no por API key. Crear más keys en el mismo proyecto no multiplica nada, pero **crear proyectos separados sí da cuotas independientes**. Es un mecanismo documentado, no un truco.

Reset: **medianoche hora del Pacífico (00:00 PT)**, todos los proyectos a la vez.

> **Trampa crítica:** activar billing en un proyecto **elimina su free tier**. No toques la facturación de los proyectos que uses para esto.

---

## 2. Gemini free tier: cuánto da realmente

| Modelo | RPM | RPD | Visión | Nota |
|---|---|---|---|---|
| **Gemini 2.5 Flash-Lite** | 15 | **1.000** | Sí | El caballo de batalla: 4× la cuota de Flash |
| Gemini 2.5 Flash | 10 | 250 | Sí | Mejor calidad |
| Gemini 2.5 Pro | 5 | 100 | Sí | Para razonamiento duro |

Free tier: sin tarjeta, sin expiración, no caduca, se recarga cada día a las 00:00 PT. Incluye multimodal (imagen, audio, vídeo, PDF), function calling, JSON mode, embeddings y 1M de contexto.

Con 3 proyectos: **3.000 RPD de Flash-Lite + 750 de Flash**. Es un orden de magnitud más que Groq, y todo con visión.

### El problema de privacidad — y su excepción regional

Términos de Gemini API, textualmente sobre los servicios **no pagados** (AI Studio y la cuota gratuita de la API):

> Google usa el contenido que envías y las respuestas generadas para proveer, mejorar y desarrollar los productos y servicios de Google.

Y peor:

> **Revisores humanos pueden leer, anotar y procesar tus inputs y outputs de la API.**

Google desconecta esos datos de tu cuenta y tu key antes de que un revisor los vea, pero eso no cambia el hecho de fondo. Los propios términos avisan: *"No envíes información sensible, confidencial o personal a los Servicios No Pagados."*

**Revisores humanos mirando las fotos de la cara de tus usuarios.** Para este producto es inaceptable, y punto.

**Pero existe una excepción que lo resuelve por completo**, cita textual de los términos:

> Si estás en el Espacio Económico Europeo, Suiza o el Reino Unido, los términos de "How Google uses Your Data" de los *Paid Services* aplican a **todos** los Servicios, incluido Google AI Studio y la cuota no pagada de la Gemini API, aunque se ofrezcan de forma gratuita.

O sea:

| Dónde está el titular de la cuenta | Gemini free tier |
|---|---|
| **UE / EEE / Suiza / Reino Unido** | **Limpio.** No entrenan, no hay revisión humana. Es la mejor opción disponible, con diferencia |
| Canadá, LatAm, EEUU, resto | **Inutilizable para caras.** Entrenan y hay revisión humana |

Esto es lo que decide [D3], y depende de un dato que solo tenés vos: **dónde está (o estará) la cuenta de Google que use la app**.

---

## 3. Groq: la cuota real es peor de lo que parece

El límite que muerde no es RPM ni RPD, es **TPD (tokens por día)**, y varía brutalmente por modelo:

| Modelo | RPM | RPD | TPD | Visión |
|---|---|---|---|---|
| `openai/gpt-oss-120b` | 30 | 1.000 | **200K** | No |
| `llama-3.1-8b-instant` | 30 | **14.400** | alto | No |
| `qwen/qwen3-32b` | 30 | 14.400 | 30K TPM | No |
| `qwen/qwen3.6-27b` | ? | ? | ? | **Por verificar** |

**Corrección a mi estimación anterior:** con `gpt-oss-120b` y 200K TPD, no son 1.000 llamadas al día — son **~100 llamadas/día** con prompts realistas. Eso son **3 o 4 análisis completos diarios**, no 35.

La consecuencia de diseño es clara: **hay que repartir por dificultad**, no mandar todo al modelo grande.
- `red_team`, `intake_validator`, formateo → `llama-3.1-8b-instant` (14.400 RPD, cuota enorme)
- `metrology_auditor`, `synthesis`, `safety_reviewer` → `gpt-oss-120b`, y solo estos (son 3 llamadas por análisis, no 25)
- `explainer`, `recommender` → `qwen3-32b`

Así el modelo caro se usa ~3 veces por análisis y los 200K TPD dan para ~20-25 análisis diarios.

---

## 4. Los otros proveedores gratis con visión

Investigados todos los que existen. Con visión gratis quedan pocos:

| Proveedor | Cuota gratis | Visión | Política de datos | Veredicto para este proyecto |
|---|---|---|---|---|
| **Cloudflare Workers AI** | 10.000 neurons/día, reset 00:00 UTC | Sí (~80 modelos, incl. Llama Vision) | **Explícita y buena**: "los datos enviados para inferencia no se usan para entrenar modelos", y no se comparten con otros clientes. Cloudflare no crea ni entrena los modelos | **La opción limpia.** Sin dilema de privacidad, sin importar la región. Ojo: los neurons son un pool compartido y los modelos grandes lo funden rápido |
| **GitHub Models** | 10 RPM / **50 RPD**, 8K tokens in / 4K out | Sí (GPT-4o) | Azure, mejor que Gemini free | Fallback de emergencia. 50 RPD ÷ 8 fotos = **6 análisis/día**. Testimonial |
| **OpenRouter** (`:free`) | **50 req/día** (sube a 1.000 solo si compras $10 de crédito) | Sí: `google/gemma-4-31b-it:free`, `google/gemma-4-26b-a4b-it:free`, `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | Variable: enruta a terceros con políticas distintas | Útil como capa de fallback por su variedad, pero 50 RPD y política opaca. No para caras |
| **Zhipu AI** (`GLM-4.6V-Flash`) | Sin documentar | Sí | Proveedor chino | **Descartado.** Datos biométricos faciales a un proveedor chino es un problema de compliance y de percepción que no vale la pena discutir con un usuario |
| **Mistral** (Experiment) | ~1B tokens/mes — la cuota más generosa de todas | **No** | **Obliga a opt-in de entrenamiento con tus datos** | Sin visión y con entrenamiento obligatorio. Solo serviría para texto, y ni eso |
| **Cerebras** | ~1M tokens/día, 30 RPM | No | — | Buen refuerzo de **texto**. Rapidísimo |
| **NVIDIA NIM** | 1.000 créditos (no recurrente) | No | Requiere verificación telefónica | Descartado: se agota y no se recarga |
| **Cohere** | 20 RPM / ~1.000 req/mes | No | — | Texto, cuota mensual pobre |
| **Hugging Face Serverless** | $0,10 de crédito/mes | No | — | Testimonial |

---

## 5. La estrategia correcta: cascada, no rotación

Rotar keys es el patrón equivocado (en Groq no funciona, en Gemini funciona pero por proyectos). El patrón correcto es **cascada de proveedores con circuit breaker**, y se implementa una sola vez en la capa de abstracción del backend.

**Resuelto:** la cuenta está fuera de UE/EEE/Suiza/UK, así que **no aplica la excepción regional de Gemini**. Gemini queda excluido de todo lo que lleve imágenes; se usa solo para texto, donde no hay caras en juego.

```python
# Pseudocódigo de la capa de proveedor
VISION_CASCADE = [
    # Cloudflare no entrena con datos de inferencia -> unico apto para caras
    ("cloudflare",    "@cf/meta/llama-3.2-11b-vision-instruct", {"quota": "neurons"}),
    ("github_models", "gpt-4o",                                 {"rpd": 50}),
    (None, None, {"degrade": "skip_level_1"}),   # degradacion explicita
]
# Gemini NO aparece aqui a proposito: su free tier entrena y admite
# revision humana fuera de UE/UK/CH. No se le mandan caras.

TEXT_CASCADE = {
    "hard":  [("groq", "openai/gpt-oss-120b"),
              ("cerebras", "llama-3.3-70b"),
              ("gemini", "gemini-2.5-flash")],        # texto: sin caras, OK
    "cheap": [("groq", "llama-3.1-8b-instant"),
              ("gemini", "gemini-2.5-flash-lite"),    # 1000 RPD por proyecto
              ("cloudflare", "@cf/qwen")],
}
```

**Nota sobre el formato de imagen:** Cloudflare Workers AI acepta **base64 o bytes crudos, no URLs**. El backend tiene que sostener los bytes; no hay forma de que el proveedor los busque por su cuenta. Esto es lo que descarta usar un CDN de imágenes — ver [04-manejo-de-imagenes.md](04-manejo-de-imagenes.md).

Reglas de la implementación:
1. **Contador de cuota persistido en Supabase**, no en memoria — el backend se reinicia en cada cold start y perdería la cuenta. Una tabla `provider_usage(provider, date, requests, tokens)`.
2. **Circuit breaker por proveedor**: tras N fallos o un 429, se marca caído con TTL y la cascada lo salta sin intentarlo.
3. **Reset consciente del huso horario**: Gemini a 00:00 PT, Cloudflare a 00:00 UTC, Groq según su propio ciclo. El contador tiene que saberlo o desperdiciás cuota.
4. **Degradación explícita, nunca silenciosa.** Si se agotó todo, el informe dice *"el análisis cualitativo no está disponible ahora mismo"* y ofrece reintentar. No se inventa contenido para rellenar.
5. **Registrar en `reports.model_versions` qué proveedor y modelo produjo cada sección.** Sin esto, dos informes del mismo usuario en días distintos son incomparables y no se puede depurar nada.

### Reducir la demanda de visión 3× (más efectivo que cualquier rotación)
Mi diseño inicial gastaba 8 llamadas de visión por análisis, una por foto. Innecesario: los VLM aceptan **varias imágenes en un solo request**. Agrupando:

- 1 llamada: las 4 vistas de morfología (frontal reposo + 2 perfiles + basal)
- 1 llamada: las 3 de contexto (sonrisa + 2 oblicuas)
- 1 llamada: la foto de piel, sola y a máxima resolución

**8 → 3 llamadas.** Combinado con el reparto de modelos por dificultad del §3, un análisis completo baja de ~28 llamadas a **~12**, y las caras solo salen del navegador en 3 requests.

---

## 6. Qué hay que verificar en runtime antes de construir

1. `qwen/qwen3.6-27b` en Groq: ¿acepta `image_url` en free tier? → [scripts/verify_groq_vision.py](../scripts/verify_groq_vision.py)
2. Cuotas reales de Gemini Flash-Lite hoy (las fuentes discrepan entre 250 y 1.000 RPD).
3. Cuántos neurons consume una llamada de visión en Cloudflare — determina si 10.000/día son 5 análisis o 200.
4. Que `qwen3.6-27b` y `gpt-oss-120b` sigan existiendo. Groq deprecó dos modelos en cinco meses; asumir estabilidad es un error.

---

## Fuentes

- [Groq — Rate Limits](https://console.groq.com/docs/rate-limits) · [Spend Limits](https://console.groq.com/docs/spend-limits) · [Deprecations](https://console.groq.com/docs/deprecations)
- [Groq free tier limits 2026 (TokenMix)](https://tokenmix.ai/blog/groq-free-tier-limits-2026)
- [Groq API free tier — qué obtenés realmente (Grizzly Peak)](https://www.grizzlypeaksoftware.com/articles/p/groq-api-free-tier-limits-in-2026-what-you-actually-get-uwysd6mb)
- [Gemini API — Additional Terms of Service](https://ai.google.dev/gemini-api/terms)
- [Gemini API — Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Enabling Billing Deletes Your Gemini API Free Tier](https://usagebox.com/articles/gemini-api-billing-free-tier-confusion)
- [Cloudflare — Your Data and Workers AI](https://developers.cloudflare.com/workers-ai/platform/data-usage/) · [Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
- [OpenRouter — Vision models collection](https://openrouter.ai/collections/vision-models) · [Free LLM APIs compared](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/)
- [awesome-free-llm-apis (amardeeplakshkar)](https://github.com/amardeeplakshkar/awesome-free-llm-apis)
- [GitHub Models — rate limits (community discussion)](https://github.com/orgs/community/discussions/137298)
- [15 Free LLM APIs (Analytics Vidhya)](https://www.analyticsvidhya.com/blog/2026/01/top-free-llm-apis/)
