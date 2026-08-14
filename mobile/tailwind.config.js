/**
 * NativeWind v4 — tokens de ObraCtrl portados a móvil.
 *
 * Spec §12.10 · DESIGN_SYSTEM.md §5.
 *
 * El móvil **comparte los mismos tokens** que la web, pero no puede
 * compartir el CSS: React Native no usa DOM ni variables CSS (§12.9). Por eso
 * los valores OKLCH del prototipo se escriben aquí como literales.
 *
 * IMPORTANTE: si cambia un token en `frontend/src/estilos/obractrl-design.css`,
 * hay que reflejarlo aquí. Son dos copias del mismo lenguaje visual y la
 * divergencia se nota de inmediato entre plataformas.
 *
 * El tab bar sustituye al sidebar; el layout de 3 columnas no aplica (§5.2).
 */

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{ts,tsx}', './src/**/*.{ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    colors: {
      transparent: 'transparent',

      // Neutrales — escala fría sutil (hue 250/255)
      bg: 'oklch(99.2% 0.003 250)',
      surface: 'oklch(100% 0 0)',
      panel: 'oklch(98.5% 0.004 250)',
      elev: 'oklch(96.5% 0.005 250)',

      line: {
        DEFAULT: 'oklch(92% 0.006 250)',
        strong: 'oklch(88% 0.008 250)',
        soft: 'oklch(95% 0.005 250)',
      },

      text: {
        DEFAULT: 'oklch(20% 0.012 255)',
        soft: 'oklch(40% 0.012 255)',
        mute: 'oklch(58% 0.012 255)',
        faint: 'oklch(72% 0.010 255)',
      },

      // Azul operacional desaturado
      accent: {
        DEFAULT: 'oklch(55% 0.14 255)',
        soft: 'oklch(94% 0.045 255)',
        strong: 'oklch(47% 0.16 255)',
        fg: 'oklch(98% 0.005 255)',
      },

      ok: { DEFAULT: 'oklch(58% 0.12 155)', soft: 'oklch(94% 0.045 155)' },
      warn: { DEFAULT: 'oklch(72% 0.13 75)', soft: 'oklch(95% 0.05 75)' },
      danger: { DEFAULT: 'oklch(58% 0.18 25)', soft: 'oklch(94% 0.045 25)' },
      info: { DEFAULT: 'oklch(62% 0.10 230)', soft: 'oklch(94% 0.035 230)' },
    },

    fontSize: {
      xs: '11px',
      sm: '12px',
      md: '13px',
      base: '14px',
      lg: '16px',
      xl: '19px',
      '2xl': '24px',
      '3xl': '32px',
    },

    borderRadius: {
      none: '0px',
      sm: '5px',
      md: '7px',
      lg: '10px',
      xl: '14px',
      full: '9999px',
    },

    extend: {
      fontFamily: {
        sans: ['Geist', 'System'],
        // Todo lo numérico va en mono (DESIGN_SYSTEM.md §5, regla 2)
        mono: ['GeistMono', 'Menlo', 'monospace'],
      },
      spacing: {
        // Altura de fila por densidad. En móvil el objetivo táctil manda:
        // 44px es el mínimo recomendado, por encima de los 36/30 de la web.
        fila: '44px',
        'fila-compacta': '38px',
        tabbar: '56px',
      },
    },
  },
  plugins: [],
};
