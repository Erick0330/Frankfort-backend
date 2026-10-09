# Manejo de imágenes — decisión

**Pregunta:** ¿usar Cloudinary para gestionar las imágenes?
**Decisión:** No. **Supabase Storage con TTL corto y borrado duro.**
**Fecha:** 2026-08-06

---

## Primero: una corrección a mi propio cálculo

En [01-estado-del-arte.md](01-estado-del-arte.md) escribí que 1 GB de Supabase Storage da para "~60 usuarios y se acabó". **Eso solo es cierto si las imágenes son permanentes.**

Si viven ~15 minutos —lo que tarda el nivel 1 más la sesión de marcado—, 1 GB deja de ser un límite de capacidad y pasa a ser un límite de **concurrencia**: ~60 sesiones *simultáneas*, no 60 usuarios totales. Para un portfolio eso es abundante, y el problema que motivaba tu pregunta desaparece.

---

## Por qué Cloudinary no aporta aquí

Cloudinary resuelve tres problemas reales. Ninguno de los tres existe en este proyecto:

**1. Servir una URL al VLM en vez de base64.** Este era el argumento fuerte: base64 infla el payload ~33% y cuenta contra los límites de tamaño de request. Pero **Cloudflare Workers AI no acepta URLs** — solo base64 o bytes crudos (`llama-3.2-11b-vision-instruct` toma base64; LLaVA toma bytes). El backend tiene que tener los bytes en la mano de todas formas. El argumento se cae solo.

**2. Transformaciones on-the-fly (resize, compress, crop).** Se hacen en el navegador con canvas, gratis:
- *Redimensionar antes de subir* → reduce tiempo de subida **y** tokens del VLM (el coste escala con la resolución). Conviene hacerlo en cliente igual, aunque hubiera CDN.
- *Zoom y pan del marcado manual* → el navegador ya tiene la imagen completa en memoria. Pedir crops al servidor sería más lento y peor UX que un canvas local.

**3. CDN para entrega rápida.** Irrelevante: cada imagen la ve una sola persona, una sola vez, en una sesión. Un CDN optimiza lecturas repetidas de contenido compartido. Aquí no hay ninguna.

Y añade tres problemas:

- **Un tercero persistente más en la cadena de custodia de fotos de caras.** Es literalmente lo que el diseño dice no hacer, y obliga a declararlo en el consentimiento.
- **El free tier no tiene auto-expiry** (las políticas de expiración automática son solo de planes pagos). Tendrías que implementar el borrado por API igual que con Supabase — cero ahorro de trabajo. Y en una CDN, borrar el original no garantiza que no queden copias cacheadas en los edge nodes.
- **25 credits/mes son un pool compartido**: 1 credit = 1 GB de storage **o** 1 GB de ancho de banda **o** 1K transformaciones, todo del mismo bote.

---

## El diseño que sí

```
navegador                        backend                    Cloudflare
─────────                        ───────                    ──────────
1. captura foto
2. valida calidad (MediaPipe WASM)
3. redimensiona a ~1280px, JPEG q85   ← canvas, gratis
4. sube a bucket privado ─────────►
   Supabase Storage
   (RLS por session_id)
                              5. lee bytes
                              6. base64 ──────────────────► visual_observer
                              7. BORRADO DURO inmediato
                                 tras el nodo de visión
8. landmarks (marcado
   local, imagen ya en
   memoria del navegador)
   envía solo coordenadas ───►  9. métricas + resto del grafo
                                  (ya sin imágenes)
```

Implementación:
- **Bucket privado** con RLS: solo el dueño de la sesión puede leer. Nunca público.
- **URLs firmadas con TTL de minutos**, no horas.
- **Borrado duro en cuanto `visual_observer` termina.** No al final del grafo — el resto del pipeline trabaja sobre landmarks y métricas, no sobre píxeles.
- **Cron de purga** (GitHub Actions, gratis) que borra huérfanos con más de 1 hora. Cubre las sesiones abandonadas a mitad, que son muchas. Se aprovecha el mismo workflow que ya hace keep-alive de Supabase.
- Las fotos **nunca** entran en Postgres. En `photo_meta` solo van hash SHA-256, checks de calidad y EXIF.

---

## Una imprecisión que hay que arreglar en el texto del consentimiento

"No almacenamos tus fotos" es cierto. **"Tus fotos nunca salen de tu dispositivo" es falso**, y no se puede escribir en ninguna parte de la app.

En el nivel 1 las imágenes viajan al backend y de ahí al proveedor de visión. Lo que es cierto y hay que decir exactamente así:

> El análisis visual requiere enviar tus fotos a nuestro servidor y de ahí a un proveedor de inferencia (Cloudflare Workers AI), cuyos términos establecen que los datos enviados no se usan para entrenar modelos. Se borran de nuestro servidor en cuanto termina el análisis, en cuestión de segundos. No se guardan.
>
> El análisis geométrico (nivel 2) es distinto: se procesa **enteramente en tu navegador**. De ahí solo salen coordenadas numéricas, nunca la imagen.

Esa asimetría entre nivel 1 y nivel 2 es una ventaja real y conviene decirla, no esconderla. Además da una opción honesta al usuario que no quiera enviar nada: **el nivel 2 funciona sin subir una sola imagen.**

---

## Cuándo esta decisión se revierte

Hay un caso en que Cloudinary (o cualquier storage real) pasa a ser correcto: **seguimiento de progreso en el tiempo**. Fotos de "antes/después" a lo largo de meses para ver si la rutina de piel funcionó es una feature genuinamente buena, y exige almacenamiento persistente.

Si eso entra en el roadmap, cambia todo el planteamiento — pero entonces debe ser:
- **Opt-in explícito y separado**, no incluido en el consentimiento del análisis
- Con borrado a petición, que funcione de verdad
- Y ahí sí, 1 GB de Supabase vuelve a ser un límite de capacidad real y toca comparar con Cloudinary en serio

Por ahora queda fuera del alcance.
