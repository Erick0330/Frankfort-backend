# Estado del arte — Análisis facial asistido por LLM

Fecha de investigación: 2026-08-06

---

## 1. Qué existe ya (competencia directa)

| Producto | Modelo de negocio | Qué hace | Debilidad explotable |
|---|---|---|---|
| **Qoves Studio** | $150/año, revisión humana, 28 días | 521 landmarks, 160+ métricas, protocolo de 4 meses | Lento, caro, y reporta métricas sin declarar el error de medición. Clasifica por "morfología étnica" → problema legal en la UE (ver §5) |
| **Facet** (thefacetapp.com) | $39 pago único, 60 s | Scoring determinista con citas peer-reviewed por umbral | Determinista = no adapta la explicación al usuario, no conversa, no corrige sus propios hallazgos |
| **Looksmax AI** | Freemium, app móvil | Score de atractivo + sugerencias | Gamificado, orientado a engagement. Cero rigor. Riesgo alto de daño psicológico |
| **The Face Report** | Gratis, sin registro | Herramientas de navegador: forma de cara, simetría, canthal tilt | Métricas sueltas sin síntesis ni plan |
| **Skinive** | CE-marked, dispositivo médico | Solo piel (acné, rosácea, pigmentación) | No hace morfología. Complementario, no competidor |
| **Face++ / DeepFace / OpenFace** | API / OSS | Landmarks y atributos crudos | Son primitivas, no producto |

### Repos open source relevantes
- **`TadasBaltrusaitis/OpenFace`** — SOTA en landmarks + head pose + gaze. Da *head pose*, que es justo lo que se necesita para validar que una foto de perfil está realmente a 90°.
- **`sujims22/Facial-Landmark-Analysis`** — ratios y ángulos orientados a planificación de cirugía cosmética. El más cercano al caso de uso.
- **`zementalist/Facial-Features-Measurement-and-Analysis`** — tercios faciales.
- Varios repos de "golden ratio / beauty score" con MediaPipe. **Todos son pseudociencia**: aplican φ sin base empírica. Sirven como ejemplo de lo que no hay que hacer.

### El hueco de mercado real
Nadie hace **auditoría de su propia medición**. Todos reportan `ratio = 0.63` como si fuera un hecho. Ninguno dice *"este número descansa en un punto mal marcado, no lo uses"*.

Eso es exactamente el fallo que aparece en tu propia sesión previa: el hallazgo del tercio inferior venía de un punto `Sn` mal marcado en ambos perfiles, y aun así llegó al informe como "8% largo" antes de ser corregido. **Esa corrección, automatizada, es el producto.**

---

## 2. El problema científico de fondo (define la arquitectura)

La literatura de fotogrametría facial 2D es contundente y hay que diseñar en torno a ella:

- **La evidencia de exactitud de la fotogrametría 2D es escasa y contradictoria.** En el estudio de referencia (Frontiers in Public Health, 2021, [PMC8826070](https://pmc.ncbi.nlm.nih.gov/articles/PMC8826070/)), solo **7 de 10** dimensiones faciales resultaron exactas frente a medición directa.
- **Los ratios NO salvan del problema.** Cita clave: los errores por distancia sujeto-cámara y focal *no se resuelven usando ratios*; los atributos faciales cambian drásticamente con la distancia. Esto mata la excusa habitual de "medimos proporciones, no milímetros".
- Condiciones mínimas para foto-antropometría fiable: resolución y foco suficientes, compresión mínima, distorsión mínima, **mismo punto de vista**, misma iluminación, sin oclusión, **focal conocida**, **distorsión de lente conocida**, **distancia al sujeto conocida**, **inclinación de cabeza conocida**.

**Implicación de diseño:** la app no puede aceptar 8 fotos cualesquiera. El protocolo de captura y su validación automática son un componente de primera clase, no un formulario de upload. Y las métricas absolutas (mm) están prohibidas; solo ángulos y ratios, con banda de error declarada.

### MediaPipe: sirve de frente, falla de perfil
- `FaceLandmarker` (paquete `@mediapipe/tasks-vision`) da **478 landmarks 3D** + blendshapes, corre en el navegador vía WASM. Gratis, sin servidor.
- **Pero**: con vistas de perfil no devuelve landmarks en absoluto. Y en cuanto un ojo desaparece de la vista, la malla se deforma alrededor de frente y nariz. El modelo tiene sesgo frontal por diseño.
- La frente es la región con menor densidad de landmarks — relevante si se quiere medir tercio superior o altura de línea de pelo.

**Implicación de diseño:** híbrido obligatorio. Landmarks automáticos para frontal y oblicuas; **marcado manual guiado para los perfiles**. Tu intuición de "marcar los puntos paso a paso con fotos de ejemplo" no es un extra, es la única forma correcta de medir el perfil. Y como el marcado manual introduce error humano, hace falta cuantificarlo (ver arquitectura, nodo `metrology_auditor`).

---

## 3. Infraestructura gratis: lo que realmente se puede (agosto 2026)

### LLM — aquí hay un problema con Groq
Groq **deprecó sus dos modelos de visión**:
- `meta-llama/llama-4-maverick-17b-128e-instruct` → deprecado 9 marzo 2026
- `meta-llama/llama-4-scout-17b-16e-instruct` → deprecado 17 junio 2026

Las migraciones que Groq recomienda (`openai/gpt-oss-120b`, `qwen/qwen3.6-27b`) son mayormente texto, **excepto** `qwen/qwen3.6-27b`, que la documentación describe como multimodal (visión + texto), con modos thinking y non-thinking. `Qwen3-VL-32B` existe en GroqCloud pero **solo para clientes Enterprise**.

> **Acción pendiente**: verificar en runtime con tu API key que `qwen/qwen3.6-27b` acepta `image_url` en el free tier. Es el único candidato de visión gratis en Groq y no está confirmado documentalmente para free tier.

Free tier Groq: ~30 RPM / 6.000 TPM / 1.000 RPD en modelos de cuota alta. Suficiente para prototipo, **muy justo** para un flujo de 8 imágenes + 8 agentes por usuario (una sola sesión de análisis puede consumir 15-25 llamadas).

### La alternativa de visión: Gemini free tier
Google AI Studio: free tier sin tarjeta, sin expiración, multimodal (imágenes, audio, vídeo, PDF), ~1.500 req/día y 1M TPM en Gemini 2.5 Flash según fuentes de abril 2026 (otras fuentes dan 250 RPD — hay que verificar en runtime).

**Pero hay un problema serio:** los términos de Google permiten **usar los prompts del free tier para entrenar el modelo** (el tier pago y Vertex AI no). Enviar fotos de la cara de un usuario a un endpoint que entrena con ellas es inaceptable sin consentimiento explícito y destacado. Ver §5.

### Backend, front y datos
| Pieza | Opción gratis | Trampa |
|---|---|---|
| Front (Next.js) | **Vercel Hobby** | Prohibido uso comercial. Timeout de función limitado |
| Backend (FastAPI) | **Hugging Face Spaces (Docker)** o **Render free** | Render: spin-down a los 15 min → cold start ~50 s. HF Spaces: duerme a las 48 h. Ambos necesitan keep-alive |
| BD + Storage + Auth | **Supabase free** | 500 MB BD, 1 GB storage, 5 GB egress, **el proyecto se pausa a los 7 días de inactividad**, máx. 2 proyectos activos |

**Implicación crítica de storage:** 1 GB / (8 fotos × ~2 MB) ≈ 60 usuarios **si las fotos fueran permanentes**. La salida —y además la correcta en privacidad— es **no almacenarlas**: procesar, guardar landmarks + métricas + informe, borrar la imagen. Un set de landmarks son unos pocos KB.

> Con imágenes efímeras (~15 min de vida), 1 GB deja de ser un límite de capacidad y pasa a ser uno de **concurrencia**: ~60 sesiones *simultáneas*, no 60 usuarios totales. Ver [04-manejo-de-imagenes.md](04-manejo-de-imagenes.md).

**Keep-alive:** hace falta un cron externo (GitHub Actions con un workflow programado es gratis) que pinguee Supabase y el backend para evitar la pausa por inactividad.

---

## 4. Riesgo de producto: daño psicológico

No es un apartado de compliance, es diseño. La prevalencia de trastorno dismórfico corporal en pacientes que buscan cirugía estética es sustancialmente mayor que en población general. Una app que devuelve "tu tercio inferior está 8% largo" a alguien vulnerable hace daño real, y encima —como quedó demostrado— el dato podía ser falso.

Lo que **sí** funciona, y está en tu propia transcripción, es la postura: *"que te incomode a vos, de forma sostenida, es una razón válida y suficiente. Es de hecho la única indicación real en cirugía estética. No necesitás que un número te autorice."* Eso hay que codificarlo como política del sistema, no dejarlo al criterio del LLM en cada corrida.

---

## 5. Marco legal (UE + Canadá)

### EU AI Act — qué está **prohibido** (Art. 5, en vigor desde 2 feb 2025)
- **Categorización biométrica por características protegidas** (raza, etnia, religión, orientación sexual, opiniones políticas). Esto aplica *independientemente de que haya consentimiento*.
  → **Consecuencia directa: prohibido hacer lo que hace Qoves** ("tu morfología es de tipo étnico X"). Nada de inferir etnia, ancestría ni origen a partir de la cara.
- Reconocimiento de emociones en trabajo y educación. No aplica a este caso de uso, pero conviene no inferir estados emocionales.
- Scraping no dirigido de imágenes faciales para construir bases de datos.

Análisis morfológico estético con consentimiento **no** está en la lista de prohibiciones.

### GDPR
Una imagen facial es dato biométrico *de categoría especial* (Art. 9) **cuando se usa para identificar unívocamente** a la persona. El análisis estético no identifica, así que probablemente no cae en Art. 9 — pero sigue siendo dato personal sensible y el criterio conservador es tratarlo como si lo fuera: consentimiento explícito, procesamiento efímero, y **prohibido entrenar con datos del usuario** (lo que choca de frente con el free tier de Gemini).

### Contenido médico
El informe no puede ser un diagnóstico. Tu PDF ya cerraba con esa nota — hay que convertirla en una restricción estructural del sistema (nodo de safety con capacidad de veto), no en un disclaimer al pie.

---

## Fuentes

- [Reliability and Accuracy of 2D Photogrammetry: A Comparison With Direct Measurement (PMC8826070)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8826070/)
- [Accuracy between 2D Photography and Dual-Structured Light 3D Facial Scanner (MDPI)](https://www.mdpi.com/2077-0383/12/9/3090)
- [Estimation of 2D to 3D dimensions and proportionality indices for facial examination (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0379073818301348)
- [MediaPipe Face Landmarker — guía web](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/web_js)
- [MediaPipe Face Mesh: los 478 puntos](https://www.sanderdesnaijer.com/blog/mediapipe-face-mesh-landmarks)
- [MediaPipe issue #3510 — landmarks en vista lateral](https://github.com/google-ai-edge/mediapipe/issues/3510)
- [Groq — Model Deprecations](https://console.groq.com/docs/deprecations)
- [Groq — Images and Vision](https://console.groq.com/docs/vision)
- [Groq — Qwen 3.6 27B](https://console.groq.com/docs/model/qwen/qwen3.6-27b)
- [Groq free tier limits 2026](https://tokenmix.ai/blog/groq-free-tier-limits-2026)
- [Gemini API free tier 2026](https://tokenmix.ai/blog/gemini-api-free-tier-limits)
- [Supabase free tier limits 2026](https://www.itpathsolutions.com/supabase-free-tier-limits)
- [Red Lines under the EU AI Act — prohibición de categorización biométrica (FPF)](https://fpf.org/blog/red-lines-under-the-eu-ai-act-understanding-the-prohibition-of-biometric-categorization-for-certain-sensitive-characteristics/)
- [Biometrics in the EU: Navigating the GDPR, AI Act (IAPP)](https://iapp.org/news/a/biometrics-in-the-eu-navigating-the-gdpr-ai-act)
- [OpenFace](https://github.com/TadasBaltrusaitis/OpenFace)
- [sujims22/Facial-Landmark-Analysis](https://github.com/sujims22/Facial-Landmark-Analysis)
- [Qoves Studio](https://www.qoves.com/)
- [Facet](https://www.thefacetapp.com/alternatives/qoves)
