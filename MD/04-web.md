# Agente: Web

## Rol
App web **React/Vite (SPA)**. Implementa features por módulo consumiendo los **hooks de Orval** (TanStack Query) para la lógica de dominio y **supabase-js + RLS** para leer catálogos directo de la base (§10.7). Aplica el **sistema de diseño** (§12.10): tokens semánticos, motor de densidad, layout de 3 columnas, tablas virtualizadas. **Sin** lógica de negocio (solo presentación + validación de UI).

## Alcance
`apps/web/` (una carpeta por módulo del §5).

## Domina del spec
Navegación §5, **sistema de diseño** (`design/obractrl-design.css` + `design/DESIGN_SYSTEM.md`, §12.10), DOM/render + virtualización §12.9, roles §4, glosario §2.

## Reglas que DEBE respetar
- **Cero reglas de negocio** en componentes.
- Colores **solo por tokens**; números con `tabular-nums`.
- **Sin localStorage/sessionStorage**; estado en memoria/TanStack/Zustand.
- Programa **contra el contrato**, no la implementación.

## Entradas / Salidas
In: hooks generados + tokens de diseño. Out: UI por módulo (sidebar por rol, filtros, tabla/Gantt, cajón de detalle).

## Definition of Done
Usa hooks generados ✓ · respeta tokens/densidad ✓ · sin lógica de negocio ✓ · accesible ✓.
