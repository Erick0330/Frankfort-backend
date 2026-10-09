# Discrepancias entre lo publicado, lo diseñado y lo construido

Las dos primeras aparecieron al implementar el motor de métricas y eran
de contenido. La tercera apareció al USAR el producto, y es de criterio.

> **Estado: las tres RESUELTAS.** Cada una tiene un test que impide que
> vuelva — en el back, en el front, o en los dos, para que el guardarraíl
> no dependa de recordar esto.

| | Qué era | Resolución |
|---|---|---|
| **D-01** | La landing decía «122° ± 4°», que es el ángulo gonial y nadie lo había calculado | Corregido a **26,6° ± 1,7°**, valor y banda producidos por el motor |
| **D-02** | Vista 08: «cenital» en la landing, «primer plano de piel» en la arquitectura | La landing pasa a **primer plano de piel** |
| **D-03** | La captura bloqueaba con los siete checks: una hora sin poder tomar una foto con la cara relajada | Solo bloquea lo **inmedible**; lo demás pasa y se paga en el sello |

---

## D-01 — El ángulo mandibular de la landing era un número inventado ✅ RESUELTA

**Gravedad: alta.** Es exactamente el pecado contra el que se posiciona el
producto.

### Qué dice la landing

En la sección "Lo que descartamos", como ejemplo de métrica CONSERVADA:

> **Ángulo mandibular** — 122° ± 4°
> Depende de: Gonion, Menton, Porion, Orbitale

### El problema

Con esos cuatro puntos, 122° no sale. Lo que sale es otra cosa:

- `Gonion` y `Menton` definen el plano mandibular.
- `Porion` y `Orbitale` definen el plano de Frankfort.
- El ángulo entre esos dos planos es el **ángulo del plano mandibular**, y
  su rango poblacional es **22–28°**, no 120–130°.

Los 120–130° corresponden al **ángulo gonial**, que es el que forman la
rama y el cuerpo mandibular. Ese necesita un punto en la rama
(`condylion` o similar) que **no está en el set de puntos** del proyecto y
que además no es marcable con fiabilidad sobre una fotografía: la rama
queda cubierta por tejido blando.

Así que el 122° no es un error de cálculo. Es un número que suena bien y
que nadie calculó — puesto por mí al redactar el ejemplo. En una landing
cuyo argumento entero es *"ninguna app te dice cuáles de sus números son
basura"*, es el peor sitio posible para que aparezca uno.

### Cómo está resuelto en el back

`metrics.py` implementa `mandibular_plane_angle` con `reference=(22, 28)`,
que es lo que esos cuatro puntos sostienen. Y hay un test que impide
volver atrás:

```python
def test_reference_is_plane_angle_not_gonial(self):
    lo, hi = BY_NAME["mandibular_plane_angle"].reference
    assert hi < 90, "un rango por encima de 90° sería el ángulo gonial"
```

### Las opciones que había

**Opción A** — corregir la landing a lo que el motor mide. **Elegida.**

**Opción B** — añadir `condylion` al set y medir el ángulo gonial.
Descartada: es un punto que no se ve en una foto, y meterlo obligaría a
declararlo frágil y a suprimirlo casi siempre. Sería añadir una métrica
para no reportarla nunca.

### Lo que se hizo

Se aplicó la opción A. El valor **no se redactó: se calculó.** Corriendo
el motor sobre un marcado de perfil plausible (Gonion una pasada, Menton
dos con 0,4 de discrepancia sobre escala 60, sello de captura A):

```
estado          : reported
valor           : 26.57 deg
banda de error  : 1.69 deg
rango de ref    : (22.0, 28.0)
desviacion      : 0.00
```

De ahí sale el `26,6° ± 1,7°` que aparece ahora en la landing, y es
reproducible con la fixture `mandible_marking` de
`api/tests/conftest.py`.

| Campo | Antes | Ahora |
|---|---|---|
| Nombre ES | Ángulo mandibular | Ángulo del plano mandibular |
| Nombre EN | Mandibular angle | Mandibular plane angle |
| Valor | 122° ± 4° | 26,6° ± 1,7° / 26.6° ± 1.7° |
| Discrepancia citada | 0,9 mm | 0,4 mm (la real de la fixture) |

**Guardarraíles**, uno en cada lado:

- `api/tests/test_metrics.py::test_reference_is_plane_angle_not_gonial` —
  exige que el rango de referencia quede por debajo de 90°.
- `web/src/lib/i18n/i18n.test.ts` — parsea el valor del diccionario en
  los dos idiomas y exige que esté en 22–28°. Con el viejo «122°» el
  parse da 122 y el test falla.

---

## D-02 — La vista 08 era una cosa distinta en cada documento ✅ RESUELTA

**Gravedad: media.** No es un número falso, pero son dos productos
distintos.

| Fuente | Vista 08 | Para qué |
|---|---|---|
| `docs/02-arquitectura.md` §2 | Frontal cerca, luz difusa, sin flash | Piel: acné, textura, poros, eritema, ojeras, pigmentación |
| Landing publicada | Cenital con inclinación | Contorno del dorso nasal, proyección relativa de frente y pómulos |

### Análisis

La vista de piel es claramente más útil:

- Habilita una sección entera del informe (dermatológica) que hoy no
  tendría datos de entrada.
- La escala de recomendaciones del §5 arranca en rutina de piel, que es el
  nivel 0–1. Sin la foto de piel, los dos primeros peldaños de la escala
  no tienen de dónde salir — y son los que se recorren primero.
- El contexto que originó el proyecto tenía el acné como prioridad
  explícita, y la rutina de piel como requisito previo a cualquier cosa
  quirúrgica.

Lo que aporta la cenital ya se obtiene, casi todo, de los dos perfiles.

### Estado en el back

`landmarks.py` ya implementaba `View.SKIN_CLOSEUP` siguiendo la
arquitectura. Era la landing la que había que mover, no el motor.

### Las opciones que había

**Opción A** — cambiar la landing a la vista de piel. **Elegida.**

**Opción B** — nueve fotos, las dos vistas. Descartada: añade fricción a
un flujo que ya tiene ocho pasos, y §2 de la arquitectura dice que
ninguna foto es decorativa. Si entrara la novena habría que justificar
qué métrica habilita ella sola, y la cenital no habilita ninguna que no
den ya los perfiles.

### Lo que se hizo

Se aplicó la opción A. La vista 08 de la landing es ahora:

| | ES | EN |
|---|---|---|
| Nombre | Primer plano, luz difusa | Close-up, diffuse light |
| Ángulo | 0°, de cerca | 0°, up close |
| Habilita | Acné y textura, eritema, ojeras, pigmentación | Acne and texture, erythema, dark circles, pigmentation |

Cambios de código:

- `ViewKind`: `"vertex"` → `"closeup"` en `web/src/lib/i18n/types.ts`.
- `FrameDiagram.tsx`: `kind` nuevo `closeup`. Es geometría de planta con
  cámara a 0° igual que la frontal, pero con `R_CAM_CLOSE` en vez de
  `R_CAM` y dos marcas de proximidad. El diagrama tiene que decir «de
  cerca», no «desde otro ángulo» — por eso lo que cambia es la
  distancia, no el ángulo.
- `public/frames/PROMPTS.md`: el prompt 08 pasa a pedir un primer plano
  con luz difusa y textura de piel visible, en vez de una cenital.

**Guardarraíl**: `web/src/lib/i18n/i18n.test.ts` exige que el frame 08
tenga `kind === "closeup"` en los dos idiomas y que declare al menos una
métrica habilitada.

---

## D-03 — La captura era un portón que no se podía cruzar ✅ RESUELTA

**Gravedad: alta.** No producía un número falso, que es lo que vigilan
D-01 y D-02; producía algo peor de otra manera: ningún número. Un
producto de medición que no deja medir no tiene un fallo de usabilidad,
no tiene producto.

### Qué pasaba

Los siete checks de `validateCapture` estaban marcados como `blocking`.
El que más bloqueaba era el de expresión neutra: con la cara relajada,
una hora de intentos sin conseguir que aceptara una sola fotografía.

Dos causas, una encima de la otra.

**La de criterio.** El §2 de la arquitectura pide que la validación
bloquee el avance en vez de avisar, y el argumento es correcto: un aviso
que se puede ignorar produce el informe que este producto existe para no
producir. Pero la conclusión —bloquear con TODO— no se sigue de la
premisa. El proyecto ya tenía el otro mecanismo, y es su tesis entera:
aceptar la medición, declarar lo que vale y suprimir lo que no se
sostiene. Tanto es así que el tipo `Severity` distinguía `blocking` de
`degrading` desde el primer día… y `degrading` no se usaba en ningún
sitio.

**La de calibración.** El check de expresión cogía el máximo de seis
blendshapes de MediaPipe —sonrisa, ceño y entrecerrar de ojos— y lo
comparaba con un único 0,25. `eyeSquint` y `browDown` NO valen cero con
la cara en reposo: el primero refleja la posición del párpado inferior y
el segundo depende de lo bajas que uno tenga las cejas de fábrica. En
muchas caras se quedan entre 0,3 y 0,6 sin que nadie esté gesticulando.
Con esos dos en el mismo saco que la sonrisa, el check era imposible de
pasar para media población.

### Lo que se hizo

La regla nueva cabe en una línea: **bloquea lo que hace la fotografía
imposible de medir; degrada lo que la hace menos precisa.**

| Check | Antes | Ahora |
|---|---|---|
| `face_present` | bloquea | bloquea — no hay nada que medir |
| `occlusion` | bloquea | bloquea — el punto a marcar no está en la imagen |
| `head_pose` | bloquea siempre | bloquea solo pasado el **portón** (3× la tolerancia); entre medias, sello C |
| `sharpness` | bloquea siempre | bloquea solo bajo el **suelo** (40 % del mínimo); entre medias, sello B |
| `exposure` | bloquea | baja el sello |
| `neutral_expression` | bloquea | baja el sello, y con límite por gesto |
| `framing` | bloquea | baja el sello |

La frontera es la diferencia entre un número **equivocado** y un número
**impreciso**: lo impreciso se declara con una banda de error, lo
equivocado no. Una foto a 40° de lo pedido no es una frontal imprecisa,
es una oblicua, y medirla como frontal daría una cifra falsa. Una foto
algo movida sí se puede marcar, con más duda — y esa duda la mide el
doble marcado por su cuenta, sin que nadie tenga que estimarla.

Los límites de expresión pasan a ser uno por gesto, calibrados sobre lo
que marca cada blendshape EN REPOSO: la sonrisa en 0,4, el ceño en 0,75
y el entrecerrar en 0,8. El gesto que de verdad contamina el informe
—la sonrisa, que mueve el tercio inferior— es el más estricto.

### Lo que NO cambió

El informe sigue sin poder reportar basura. Lo que antes se impedía en la
puerta ahora se paga por dentro: el sello ensancha la banda de error de
todas las métricas de esa foto (`GRADE_FACTOR`) y suprime las que su
calidad no sostiene. Una foto con la pose pasada de tolerancia entra con
sello C y pierde las métricas de proyección de esa vista — exactamente el
mismo castigo que ya tenía el gran angular, por el mismo motivo.

### Guardarraíles

En `web/src/lib/capture/capture.test.ts`:

- el caso exacto que lo destapó: una cara en reposo con `eyeSquint` a
  0,52 y `browDown` a 0,44 tiene que pasar el check y salir con sello A;
- una sonrisa no impide tomar la foto, pero cae a B;
- la pose a 20° se acepta con C, la de 40° bloquea;
- algo movida se acepta, papilla no;
- y uno que fija el criterio entero: ningún check fuera de los cuatro
  inmedibles puede volver a ser `blocking`.

### Nota

Esta no la encontró una revisión ni un test: la encontró usar el
producto. Los dos primeros fallos se vieron implementando el motor; este
se vio delante de la cámara. Es un argumento para probar el recorrido
completo a mano antes de dar por buena cualquier decisión de flujo.

---

## D-04 — Los dos ejes de la pose estaban cambiados ✅ RESUELTA

**Dónde:** `web/src/lib/capture/pose.ts::poseFromMatrix`, y de rebote el
protocolo entero de las ocho vistas.

### Qué pasaba

La descomposición de la matriz de MediaPipe daba tres ángulos y dos
estaban mal etiquetados: lo que el código llamaba `yaw` era el giro sobre
el eje X —asentir— y lo que llamaba `pitch` era el giro sobre Y —girar la
cabeza—. En el espacio de cámara de MediaPipe (+X derecha, +Y arriba, +Z
hacia el observador) es justo al revés.

Consecuencias, todas vistas delante de la cámara:

- **Las oblicuas eran imposibles.** Girar la cabeza 45° no movía el
  número: se quedaba en 0 contra un objetivo de 45 y bloqueaba.
- **El perfil derecho pedía "el ángulo desde arriba de la cabeza"**, que
  es exactamente lo que se siente cuando el número solo responde al
  cabeceo.
- **La basal pedía la vista contraria.** Su objetivo era `-60`, y con el
  signo corregido (pitch positivo = mentón arriba) ese `-60` significaba
  agachar la cabeza en vez de echarla atrás.

Y una segunda mitad, independiente: `estimatePose` infiere "perfil a 90°"
cuando el detector ve una cara y el mesh no la resuelve, y esa inferencia
saltaba el check de pose **en todas las vistas**. El mesh también se
rinde con la cabeza agachada. Resultado medido: en la oblicua derecha,
con la coronilla llenando la pantalla, los siete checks decían "bien" y
la fotografía se aceptaba. La web aprobaba una fotografía de una nuca —
mientras bloqueaba la de una cara.

### Por qué no lo cazó ningún test

Había un solo fixture de rotación, y se comparaba siempre contra
objetivos frontales (0,0). `poseDeviation` toma el máximo de los dos
ejes, así que daba exactamente lo mismo cuál de los dos se moviera. Un
test verde midiendo lo que no dice medir es peor que no tenerlo: da
permiso para no mirar.

### Qué cambió

| | Antes | Ahora |
|---|---|---|
| Ejes | yaw = giro sobre X | yaw = giro sobre Y, pitch = giro sobre X |
| Signo del pitch | sin definir en la práctica | positivo = mentón arriba |
| Basal | `targetPitch: -60` | `targetPitch: 60` |
| Perfil inferido | salta el check en cualquier vista | solo donde la vista PIDE un perfil |
| Checks sin medir | salían como "correcto" | salen como "aquí no se puede medir" |
| Oblicuas | ±7° | ±12° |
| Primer plano | los siete checks | cuatro: cara, nitidez, exposición, encuadre |

Las dos últimas salen de medir, no de opinar. Con ocho fotografías reales
tomadas a pulso, las oblicuas dieron 20,6° y −25,6° contra un objetivo de
45: la vista de tres cuartos es una BANDA (la frontal a 0° y el perfil a
90° sí son ángulos geométricos), y pedir 45±7 a ojo es pedir puntería. Y
el primer plano fue la única de las ocho sin malla —la cara llena el
encuadre y se recorta por los bordes—, que con `head_pose` en su lista
bloqueaba la vista entera. Esa vista mide PIEL: ni el ángulo ni la
oclusión de puntos que quedan fuera a propósito le dicen nada.

### Efecto sobre las ocho fotografías de prueba

Antes: dos rechazadas sin decir por qué. Ahora: las ocho entran, con
sellos B/C y cada rebaja explicada en su fila. Y una tercera cosa que
aparecía en silencio — una subida bloqueada se descartaba sin mensaje, ni
foto ni motivo: ahora el informe se publica siempre, se acepte o no.

### Guardarraíles

En `web/src/lib/capture/capture.test.ts`, un fixture por eje —`yawMatrix`
y `nodMatrix`— y con ellos: girar mueve el yaw y deja el pitch quieto;
asentir mueve el pitch y agachar es negativo; una oblicua se satisface
girando y NO cabeceando; la basal pide la cabeza atrás; un mesh perdido
bloquea en la oblicua y se acepta en el perfil; y en el primer plano no
bloquea nada.

### Nota

Igual que la D-03, esta la encontró usar el producto — y la prueba que la
cerró fue pasar ocho fotografías reales por el recorrido entero. Los
tests sintéticos comprobaban que el código hacía lo que el código decía;
hacía falta una cara de verdad para ver que decía lo que no era.

---

## D-05 — La tolerancia de los perfiles medía la exigencia, no el instrumento ✅ RESUELTA

**Dónde:** `web/src/lib/capture/protocol.ts`, y `UploadStage` con
`mediapipe.ts`.

### Qué pasaba

El §2 de la arquitectura fija una tolerancia de 7° para todas las vistas.
Con los ejes de la pose ya arreglados (D-04) salió a la luz lo que ese
número tapaba: **MediaPipe comprime el yaw en los extremos**. Sobre un
perfil de manual —nariz recortada contra el fondo, un solo ojo visible,
imposible estar más de perfil— la matriz devuelve **68,1°**, no 90.

Con ±7, esa fotografía bloqueaba. Y la incoherencia era doble: cuando la
malla se rinde del todo, la pose se INFIERE como perfil y la fotografía
se acepta con sello B. O sea que el sistema castigaba a quien se coloca
lo bastante bien como para que el modelo todavía lea algo, y premiaba a
quien se sale del rango del modelo.

La tolerancia tiene que ponerse donde el instrumento MIDE, no donde nos
gustaría que midiera. Perfiles a ±25, con el portón declarado aparte en
45° — por debajo de eso la fotografía es una oblicua, y eso sí es otra
vista.

De ahí sale también `hardToleranceDeg`: el portón dejó de ser
`tolerancia × 3` para todas. Ese múltiplo funciona en la frontal y es
absurdo en un perfil, donde la tolerancia es grande por culpa del
estimador y no porque la vista admita cualquier cosa.

### Y la segunda mitad: una fotografía no es un fotograma

La vía de subida pasaba la imagen por `detectForVideo`, que es el modo
con SEGUIMIENTO: el grafo usa lo que vio antes para estabilizar lo
siguiente. Sobre un vídeo es lo correcto; sobre una fotografía suelta es
contaminación.

Se vio, no se dedujo: el mismo archivo de perfil, subido dos veces en la
misma sesión, salió una vez con malla —yaw 68,1°— y otra sin ella,
aceptado como «perfil inferido». Dos veredictos para el mismo archivo.
Eso, de cara a quien lo usa, es una máquina que cambia de opinión sola, y
de cara a quien lo arregla es un diagnóstico imposible.

Ahora las subidas van por `analyzeStill`, que cambia los dos grafos a
modo IMAGE, mide y los devuelve a VIDEO. Cuesta una reconstrucción
interna por fotografía y pasa una vez, no diez veces por segundo.

### Efecto sobre las ocho fotografías de prueba

| | Antes | Ahora |
|---|---|---|
| 03 perfil derecho | bloqueada (21,9° de desvío) | sello B |
| 08 primer plano | sin malla, según la ronda | malla estable, sello B |
| El resto | igual | igual |

### Guardarraíles

En `capture.test.ts`: el techo de 15° sigue vigente para todas las vistas
menos los perfiles, que lo rompen con la medición escrita al lado; el
portón siempre queda por FUERA de la tolerancia —si cayera dentro, el
sello C no se usaría nunca en esa vista— y nunca por encima de 45°, que
es la distancia entre dos vistas del protocolo.

---

## D-06 — El informe estaba escrito desde el mecanismo ✅ RESUELTA

**Dónde:** `web/src/components/report/`, y de rebote una capa nueva en el
back (`api/src/frankfort/narrative.py` y `agents.py`).

### Qué decía la arquitectura

El §4 presenta la sección **«Descartado y por qué»** como una de las
piezas de valor del producto: *«contenido genuinamente valioso y que
ningún competidor ofrece»*. El informe la implementaba al pie de la
letra, y con ella una sección por cada estado del motor: hallazgos,
reportadas, suprimidas por el auditor, no calculables, suprimidas por el
sello, control cruzado, puntos no fiables y su cascada.

### Qué pasó al usarlo

Ocho secciones, la mayoría sobre cosas que **no se pudieron medir**, y
escritas en el vocabulario del motor: «suprimida por dependencia no
fiable», «reportada fuera de rango por más de su banda». Todo cierto y
casi nada legible. Y sobre todo: **nada accionable**. Quien lee su
informe no puede hacer nada con la lista de lo que no salió, ni aprende
nada de ella.

El error de razonamiento está en confundir dos cosas distintas:

- **el mecanismo** —que una medida que no se sostiene no se publique— es
  la tesis del producto y no se toca;
- **la lista de lo suprimido** era una forma de *demostrar* ese
  mecanismo, y esa demostración pertenece a la portada, no al informe de
  alguien que quiere saber cómo tiene la nariz.

### Cómo queda

Tres cosas: **el resumen**, **lo que se midió** y **una línea** diciendo
cuántas medidas se quedaron fuera. Sin lista y sin motivo técnico.

Cada medida trae ahora nombre llano y una frase de qué es —«el ángulo
entre la nariz y el labio: el que forman la base de la nariz y el labio
de arriba»— y la banda de error se escribe en palabras: «puede variar
1,1 % arriba o abajo según cómo marcaste», que además dice de DÓNDE
viene la incertidumbre, que es lo que hace que alguien decida volver a
marcar. El nombre anatómico no desaparece del sistema: sigue en la
captura y en el marcado, donde el término técnico es el correcto.

El control cruzado deja de ser una sección con su tabla y pasa a ser una
línea dentro de la tarjeta: «medido en los dos lados de la cara, y
coinciden». Es lo que significaba.

### La capa de agentes, que era lo que faltaba

El resumen lo redacta el SERVIDOR, no la pantalla. No es un capricho de
arquitectura: resumir exige mirar todas las medidas a la vez y decidir
cuál merece la primera frase, y eso es síntesis, no presentación.

- `narrative.py` arma los **hechos** y un resumen con plantillas,
  determinista y sin red.
- `agents.py` es el nodo `explainer` del §4, con correa corta: reescribe
  ese texto y **no puede introducir un número que el motor no haya
  calculado**. La salida se verifica —cifras contra los hechos, nada de
  vocabulario de diagnóstico ni de estética, prosa sin listas— y un
  fallo de verificación no se reintenta: se publica el determinista.
- La respuesta dice cuál de los dos se usó (`summarySource`). Un informe
  que no puede decir de dónde sale su propio texto es exactamente el
  producto que esta web dice no ser.

Sin `GROQ_API_KEY` ni `GEMINI_API_KEY` el módulo es un no-op y el
producto funciona igual: la capa de agentes MEJORA el informe, no lo
habilita. Y el agente solo ve NÚMEROS —nunca fotografías—, lo que deja
fuera del problema toda la discusión de privacidad de docs/03.

### Guardarraíles

En `api/tests/test_narrative.py`: el resumen nunca menciona cuántas
medidas se cayeron; un número inventado tumba el texto del agente; un
juicio estético o un diagnóstico también; si el proveedor revienta, hay
informe igual. En `web/src/lib/report/report.test.tsx`: la pantalla
empieza por el resumen, enseña el nombre llano y no el anatómico, no
repite una medida por salir en los dos perfiles, y no contiene las
palabras «Suprimida» ni «No calculable».

---

## D-07 — El perfil nasal prometía una medida que no podía dar ✅ RESUELTA

El módulo «Perfil nasal» anunciaba el ángulo nasofrontal y no pedía
marcar la glabela, que es uno de sus tres puntos. El motor la devolvía
siempre «no calculable» y el informe salía con dos medidas donde el
módulo había prometido tres. Lo destapó una prueba de punta a punta con
fotos reales, no un test.

Ahora los dos módulos nasales piden la glabela, y `marking.test.tsx`
cruza lo que cada módulo promete con lo que cada métrica necesita
—incluida la pareja de Frankfort de las que se alinean a ella—: una
promesa que el motor no puede cumplir ya no compila en verde.

---

## Nota de método

Las dos aparecieron por el mismo motivo: la landing se escribió antes que
el motor, y redactar un ejemplo convincente es más fácil que calcularlo.
Es el fallo que el propio producto describe, cometido en su propia
portada.

Lo que lo detectó no fue una revisión: fue implementar el cálculo y que no
cuadrara. Es un argumento para construir el motor antes que el copy en lo
que quede de proyecto, y no al revés.

Y de ahí sale la forma de los guardarraíles: no basta con arreglar el
texto, porque el texto se vuelve a escribir. Lo que hay es un test por
lado que ata el copy publicado a lo que el motor puede sostener. Si
alguien vuelve a poner un número bonito, falla el build.
