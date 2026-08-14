import type { Config } from 'tailwindcss';

/**
 * Tailwind tematizado con los tokens de ObraCtrl (§12.10, DESIGN_SYSTEM.md §5).
 *
 * Regla: **cero colores crudos**. Todo pasa por un token `--c-*` definido en
 * `src/estilos/obractrl-design.css`, que es la fuente de verdad del diseño.
 * Aquí solo se exponen a Tailwind; los valores viven allá, una sola vez.
 *
 * Por eso la paleta por defecto de Tailwind se **reemplaza** en vez de
 * extenderse: si `bg-red-500` siguiera existiendo, acabaría usándose.
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    // Reemplazo, no extensión: no debe haber un segundo lenguaje visual.
    colors: {
      transparent: 'transparent',
      current: 'currentColor',

      bg: 'var(--c-bg)',
      surface: 'var(--c-surface)',
      panel: 'var(--c-panel)',
      elev: 'var(--c-elev)',

      line: {
        DEFAULT: 'var(--c-line)',
        strong: 'var(--c-line-strong)',
        soft: 'var(--c-line-soft)',
      },

      text: {
        DEFAULT: 'var(--c-text)',
        soft: 'var(--c-text-soft)',
        mute: 'var(--c-text-mute)',
        faint: 'var(--c-text-faint)',
      },

      accent: {
        DEFAULT: 'var(--c-accent)',
        soft: 'var(--c-accent-soft)',
        strong: 'var(--c-accent-strong)',
        fg: 'var(--c-accent-fg)',
      },

      ok: { DEFAULT: 'var(--c-ok)', soft: 'var(--c-ok-soft)' },
      warn: { DEFAULT: 'var(--c-warn)', soft: 'var(--c-warn-soft)' },
      danger: { DEFAULT: 'var(--c-danger)', soft: 'var(--c-danger-soft)' },
      info: { DEFAULT: 'var(--c-info)', soft: 'var(--c-info-soft)' },
    },

    fontFamily: {
      sans: 'var(--f-sans)',
      mono: 'var(--f-mono)',
    },

    fontSize: {
      xs: 'var(--fs-xs)',
      sm: 'var(--fs-sm)',
      md: 'var(--fs-md)',
      base: 'var(--fs-base)',
      lg: 'var(--fs-lg)',
      xl: 'var(--fs-xl)',
      '2xl': 'var(--fs-2xl)',
      '3xl': 'var(--fs-3xl)',
    },

    borderRadius: {
      none: '0',
      sm: 'var(--r-sm)',
      md: 'var(--r-md)',
      lg: 'var(--r-lg)',
      xl: 'var(--r-xl)',
      full: '9999px',
    },

    boxShadow: {
      sm: 'var(--shadow-sm)',
      md: 'var(--shadow-md)',
      lg: 'var(--shadow-lg)',
      none: 'none',
    },

    extend: {
      spacing: {
        // Motor de densidad (§12.10): los componentes leen la variable, nunca
        // hardcodean la altura de fila.
        fila: 'var(--row-h)',
        'celda-y': 'var(--pad-cell-y)',
        'celda-x': 'var(--pad-cell-x)',
        sidebar: 'var(--sidebar-w)',
        topbar: 'var(--topbar-h)',
        subbar: 'var(--subbar-h)',
      },
    },
  },
  plugins: [],
} satisfies Config;
