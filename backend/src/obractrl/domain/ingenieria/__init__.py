"""Ingeniería del lote: identificación de prototipo, reversión por destajo
y hallazgos de desviación candidatos (cerebro `CONOCIMIENTO.md` §11.4-§11.9).

Dominio puro, de análisis multi-archivo — a diferencia de
`domain.cargadores.ingenieria_lote` (el parseo de UN archivo, fila por
fila), este paquete consolida varios archivos del mismo lote, los compara
contra el árbol/matriz de un prototipo ya cargado (`domain.cargadores.
presupuesto`/`domain.catalogos.apu`) y devuelve `domain.desviacion.
Desviacion` candidatas **sin persistir**: §12.11, ningún módulo de dominio
toca la base.
"""
