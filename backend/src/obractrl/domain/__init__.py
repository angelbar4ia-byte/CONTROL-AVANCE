"""Núcleo de dominio — puro y determinista.

Ningún archivo de este paquete importa de `adapters/`, `infrastructure/` ni de
las apps. Los puertos (repos, parsers, exportadores) se declaran en
dominio/aplicación y se implementan en el borde (§12.11).

Las carpetas son 1:1 con los dominios del §7 (Screaming Architecture).
"""
