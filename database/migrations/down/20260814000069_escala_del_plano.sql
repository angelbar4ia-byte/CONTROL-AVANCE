-- Revierte 0069: quita la escala del plano. Las medidas vuelven a leerse en
-- unidades de plano.

alter table plano
  drop constraint ck_plano_escala_completa,
  drop column escala_calibrada_en,
  drop column escala_calibrada_por,
  drop column escala_referencia,
  drop column escala_m_por_unidad;
