-- Revierte 0083: Costos deja de subir ingeniería.

drop policy carga_datos_costos on carga_datos;
drop policy carga_snapshot_costos on carga_snapshot;
drop policy pendiente_costos on pendiente;
drop policy prototipo_costos_alta on prototipo;
drop policy prototipo_costos_cambio on prototipo;
drop policy prototipo_nodo_costos on prototipo_nodo;
