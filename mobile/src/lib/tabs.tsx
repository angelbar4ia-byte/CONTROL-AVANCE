/**
 * Opciones compartidas del tab bar (§5.2, §12.10).
 *
 * El móvil no usa el layout de 3 columnas: sigue el tab bar y patrones
 * táctiles, pero **comparte los mismos tokens** que la web (§12.10).
 */

import type { BottomTabNavigationOptions } from '@react-navigation/bottom-tabs';

/** Tokens portados (ver tailwind.config.js). */
export const TOKENS = {
  accent: 'oklch(55% 0.14 255)',
  textMute: 'oklch(58% 0.012 255)',
  surface: 'oklch(100% 0 0)',
  line: 'oklch(92% 0.006 250)',
} as const;

export const opcionesTabs: BottomTabNavigationOptions = {
  headerShown: false,
  tabBarActiveTintColor: TOKENS.accent,
  tabBarInactiveTintColor: TOKENS.textMute,
  tabBarStyle: {
    backgroundColor: TOKENS.surface,
    borderTopColor: TOKENS.line,
    height: 56,
  },
  tabBarLabelStyle: { fontSize: 11 },
};
