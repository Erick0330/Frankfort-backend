# Evaluaciones medidas

Números sacados de ejecutar el sistema, no de opinar sobre él. Cada
entrada dice qué se midió, con qué datos y qué significa — y qué NO
significa, que suele ser lo más importante.

---

## E-01 — Sugerencias de MediaPipe en el marcado frontal

**Fecha:** 2026-10-06 · **Datos:** foto frontal de prueba
(`web/public/frames/tests/1.jpg`, selfie a un brazo, 959×1280).

**Qué se midió.** Para cada punto del módulo «Cara de frente», la
distancia entre la sugerencia de la malla de MediaPipe
(`lib/marking/suggest.ts`) y una marca puesta a mano, en porcentaje de
la distancia intercantal — la misma unidad en la que el motor juzga el
doble marcado (tolerancia: 6 %).

| Punto | Índice de malla | Distancia |
|---|---|---|
| Endocanthion R / L | 133 / 362 | 4 % / 6 % |
| Nasion | 168 | 6 % |
| Exocanthion R / L | 33 / 263 | 8 % / 6 % |
| Zygion R / L | 234 / 454 | 9 % / 10 % |
| Subnasale | 2 | 12 % |
| Gnathion / Menton | 175 / 152 | 11 % / 11 % |

**Qué significa.** En las esquinas de los ojos y el entrecejo, el modelo
cae a la distancia de la tolerancia del doble marcado: del orden de lo
que discrepa una persona consigo misma. En los bordes blandos —pómulos,
base de la nariz, mentón— se va al doble. Por eso es una SUGERENCIA que
se acepta o se corrige, y no un marcado automático.

**Qué NO significa.** No es precisión contra una verdad de referencia:
las marcas a mano también son una estimación, y es una sola cara. Es
acuerdo entre dos estimaciones. Para medir precisión hace falta un
conjunto con marcado de especialista, que no hay.

**Lo que se comprobó además.** Con la sugerencia activa, la segunda
pasada del doble marcado no la enseñó en ningún punto (también lo fija
un test): las dos marcas siguen siendo dos opiniones del usuario, y la
banda de error no se maquilla.

---

## E-02 — Sugerencias de MediaPipe en la basal

**Fecha:** 2026-10-06 · **Datos:** foto basal de prueba
(`web/public/frames/tests/7.jpg`, cabeza echada atrás, ~43° de pitch).

Misma medida que E-01, pero en porcentaje de la anchura alar —la escala
de esta vista—, que es bastante más corta que la intercantal: el mismo
error en píxeles pesa más aquí.

| Punto | Índice de malla | Distancia |
|---|---|---|
| Alare R / L | 129 / 358 | 19 % / 17 % |
| Pronasale | 1 | 17 % |
| Subnasale | 2 | 7 % |

**Qué significa.** Con la cara vista desde abajo la malla trabaja fuera de
lo que mejor conoce —la entrenaron sobre todo con caras de frente— y sus
aletas caen en el pliegue de la mejilla, no en el borde de la aleta. La
sugerencia sirve para encontrar la ZONA; el punto lo pone quien marca.
Es lo que el anillo discontinuo y el texto de la pantalla dicen.

**Lo que se comprobó además.** La segunda pasada no enseñó sugerencia en
ningún punto.

---

## E-03 — Una subida temprana se validaba sin modelo

No es una métrica, pero salió midiendo E-02: subir la foto en los
primeros segundos tras cargar la página la validaba antes de que el
modelo de visión estuviera listo, y salía bloqueada por «no hay cara».
El veredicto dependía de lo rápido que se eligiera el archivo. Ahora la
subida espera al modelo (`UploadStage`), y la misma foto, subida medio
segundo después de cargar, se acepta.

---

## E-04 — Banco del observador visual, sin modelo

**Fecha:** 2026-10-06 · `api/scripts/eval_observer.py` sobre las ocho
fotos de prueba, SIN clave de visión.

| Métrica | Resultado |
|---|---|
| Cumplimiento de reglas | 8/8 (100 %) |
| Rebajas de «claro» a «probable» | 0 |
| Cobertura de zonas | 4/4 |

**Qué significa.** Nada sobre ningún modelo: sin clave, el banco evalúa
las observaciones de EJEMPLO, y lo dice en su primera línea. Lo que
demuestra es que el banco funciona y que los ejemplos que enseña la
pantalla cumplen las mismas reglas que tendría que cumplir un modelo.
La evaluación de verdad es correrlo con `GEMINI_API_KEY`.
