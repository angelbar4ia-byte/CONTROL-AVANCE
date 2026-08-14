# ObraCtrl — Sistema de diseño

> **Fuente de verdad del diseño.** El lenguaje visual de ObraCtrl es el del **prototipo aprobado** (Claude Design). Los tokens y componentes reales viven en **`obractrl-design.css`** (en esta carpeta). Este documento explica cómo está hecho y cómo **continuar con el mismo diseño**. Vinculado al spec §12.10.

## 1. Filosofía
Interfaz **densa, calmada y orientada a datos** (estilo Linear/back-office moderno): mucha información legible sin ruido. Tres decisiones la definen:
- **Color OKLCH** con **neutrales fríos sutiles** (tinte azul, hue 255) y un **azul operacional desaturado** como acento. Nada de colores saturados salvo señales semánticas.
- **Tipografía Geist** (sans) + **Geist Mono** para todo lo numérico/código (con `tabular-nums`).
- **Densidad ajustable** (comfy/compact) para vistas con muchas filas.

## 2. Tokens (resumen — ver `obractrl-design.css` para valores exactos)
**Color (OKLCH):**
- Neutrales: `--c-bg`, `--c-surface`, `--c-panel`, `--c-elev`, `--c-line` / `--c-line-strong` / `--c-line-soft`.
- Texto: `--c-text` → `--c-text-soft` → `--c-text-mute` → `--c-text-faint` (jerarquía por luminosidad).
- Acento (azul desaturado): `--c-accent`, `--c-accent-soft`, `--c-accent-strong`, `--c-accent-fg`.
- Semánticos: `--c-ok` (verde), `--c-warn` (ámbar), `--c-danger` (rojo), `--c-info` (azul), cada uno con variante `-soft` para fondos.

**Tipografía:** `--f-sans` (Geist) · `--f-mono` (Geist Mono). Escala `--fs-xs 11` → `sm 12` → `md 13` → `base 14` → `lg 16` → `xl 19` → `2xl 24` → `3xl 32`. Helpers `.mono` (`ss01`,`tnum`) y `.tnum`.

**Densidad (`body[data-density]`):** comfy (default) `--row-h 36`, padding celda `8/12`, base `14`; compact `--row-h 30`, padding `5/10`, base `13`.

**Geometría:** radios `--r-sm 5` · `md 7` · `lg 10` · `xl 14`. Sombras `--shadow-sm/md/lg` (muy sutiles, OKLCH con alpha baja).

**Layout:** `--sidebar-w 232`, `--topbar-h 48`, `--subbar-h 44`.

## 3. Layout (shell)
- **`.app`** = CSS grid `[sidebar | contenido]` × `[topbar | main]`, `100vh`. Variante **topnav** (`.app.nav-top`): topbar + subbar + main.
- **Topbar:** marca (mono, peso 700) · breadcrumbs (`.crumbs`) · `role-chip` (perfil con dot de avatar) · acciones.
- **Sidebar:** secciones en mayúsculas (`letter-spacing .06em`), ítems con ícono + contador mono; el **ítem activo** lleva fondo `surface`, sombra sutil y **barra de acento a la izquierda**.
- **Página (`.page`):** `eyebrow` (mono, mayúsculas) + `title` (`2xl`, `letter-spacing -.02em`) + acciones; ancho máx `1600px`.
- **Móvil:** `.mobile-tabbar` aparece **< 881px**; el resto se adapta.

## 4. Componentes (inventario)
Todos en `obractrl-design.css` + `components.jsx`:
- **Button** — variantes `default · primary` (texto sobre tinta) `· accent` (azul) `· ghost · danger`; tamaños `sm/lg/icon`. Altura base 30px, radio `md`.
- **Badge** — tonos `ok/warn/danger/info/accent/outline`, mono, radio 4px; **StatusBadge** lo deriva del estado.
- **Bar** (progreso, color por % : ≥90 ok, <25 danger) · **Donut** (conic-gradient) · **Spark** (mini-barras).
- **Card** — `header` (título + sub) / `body` (`--flush` sin padding).
- **Inputs** (`input/select/textarea`) — foco con **anillo `accent-soft`**; `kbd` para atajos.
- **Sheet** (cajón derecho, ancho 480, cierra con `Esc`) · **Modal** (centrado) · **scrim**.
- **EditableNumber** (edición en línea con estados `is-over`/`is-near` y % calculado) · **InlineEdit** (texto) · **Empty** · **Toast**.
- **Tabla** — `table-wrap` con borde y radio `lg`; filas a `--row-h`; números mono.

**Íconos:** set lucide-style propio, `strokeWidth 1.6`, viewBox 24, 16px por defecto.
**Formato:** `fmtMXN` (`$` + es-MX), `fmtNum` (2 dec es-MX), `fmtPct`, `fmtDate` (`dd mmm aa`).

## 5. Cómo continuar con este diseño
- **Web:** importar `obractrl-design.css` y **tematizar shadcn/ui con estos tokens** (mapear las CSS vars de shadcn a `--c-*`); **no** usar el tema Zinc por defecto. Reusar las clases (`.btn`, `.badge`, `.card`, `.sheet`, `.table-wrap`…) o reconstruir los equivalentes con los mismos tokens.
- **Móvil (RN/Expo):** portar **los mismos tokens** a `tailwind.config` de **NativeWind** (mismos valores OKLCH y escala) y replicar los componentes de forma nativa; el tab bar sustituye al sidebar.
- **Reglas para los agentes Web/Mobile:**
  1. **Cero colores crudos** — todo por token `--c-*`.
  2. Números **siempre** `--f-mono` + `tabular-nums`.
  3. Respetar el **motor de densidad** (`body[data-density]`); no hardcodear alturas/paddings de fila.
  4. Mantener el **shell** (sidebar/topbar/página) y los patrones (Sheet para drill-down, edición en línea en tablas).
  5. Cualquier componente nuevo **se construye con estos tokens**; no se introduce un segundo lenguaje visual.
