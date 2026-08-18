"""Modelo de los reportes (§11.2 Reportes, §7.9 expediente).

Aquí vive **qué dice** un reporte —qué renglones lo componen y cómo suman—,
nunca **cómo se dibuja**: el XLSX y el PDF se generan en `adapters/export/`
(§12.11, §MD/06-reportes.md "vive en `adapters/`; consume el dominio por
puertos"). Así el mismo agregado alimenta la respuesta JSON y el PDF sin
duplicar una sola suma.
"""
