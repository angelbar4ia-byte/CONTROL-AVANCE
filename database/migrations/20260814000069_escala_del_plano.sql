-- ============================================================
-- ObraCtrl · 0069 · La escala del plano
--
-- QUÉ FALTABA
--
-- El cuantificador mide sobre las coordenadas del plano (SRID 0): un polígono de
-- 10 × 12 «unidades» da 120 «unidades²». Pero esas unidades son las del visor
-- —píxeles de la imagen del PDF, o lo que el CAD traiga—, no metros. Sin saber
-- cuántos metros vale cada unidad, la cantidad que se compara contra la
-- `cant_base` del presupuesto (m², ml) no es una cantidad: es un número en
-- otra unidad, y la desviación que levanta no significa nada.
--
-- Todo cuantificador lo resuelve igual: se marcan dos puntos de una distancia
-- conocida del plano (una cota, un eje) y se dice cuántos metros son. De ahí sale
-- la escala.
--
-- QUÉ SE GUARDA
--
--   escala_m_por_unidad   metros por cada unidad de plano. NULL = sin calibrar:
--                         se asume 1 unidad = 1 m, que es lo que se hacía hasta
--                         aquí, y la pantalla lo avisa.
--   escala_referencia     los dos puntos y la distancia real con que se calibró
--                         ({"punto_a": [x,y], "punto_b": [x,y], "distancia_m": n}),
--                         para poder ver y repetir la calibración en vez de
--                         creerle a un número suelto.
--   escala_calibrada_por/en   quién y cuándo.
--
-- La escala **no se aplica a la geometría guardada**: sigue siendo la del plano.
-- Se aplica al **leer** la medida (área × k², perímetro y longitud × k). Así una
-- recalibración corrige de golpe todos los trazos del plano sin reescribir
-- ninguno, igual que la medida ya se calculaba al leer (0057).
-- ============================================================

alter table plano
  add column escala_m_por_unidad numeric(18,9)
    constraint ck_plano_escala_positiva check (escala_m_por_unidad > 0),
  add column escala_referencia   jsonb,
  add column escala_calibrada_por uuid references usuario(id),
  add column escala_calibrada_en  timestamptz,
  add constraint ck_plano_escala_completa check (
    (escala_m_por_unidad is null) = (escala_referencia is null)
  );

comment on column plano.escala_m_por_unidad is
  'Metros por unidad de plano (0069). NULL = sin calibrar: se asume 1 unidad = 1 m. Se aplica al leer la medida (area × k², perimetro y longitud × k), no a la geometria guardada.';
comment on column plano.escala_referencia is
  'Los dos puntos y la distancia real con que se calibro: {"punto_a": [x, y], "punto_b": [x, y], "distancia_m": n}.';
