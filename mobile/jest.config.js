/**
 * Jest del móvil (§11.7).
 *
 * `jest-expo` y no `ts-jest`: los módulos de Expo y de React Native se
 * publican como ESM sin transpilar, así que hace falta el transformador de
 * Babel del preset y su `transformIgnorePatterns`. Con `ts-jest` cada import
 * de `expo-*` rompería en `SyntaxError: Cannot use import statement outside a
 * module`.
 *
 * `moduleNameMapper` repite el alias `@/*` de `tsconfig.json`. Es una segunda
 * copia inevitable —Jest no lee `paths`— y si divergen, los tests fallan al
 * resolver imports que TypeScript sí acepta.
 */

module.exports = {
  preset: 'jest-expo',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  setupFilesAfterEnv: ['<rootDir>/tests/setup.ts'],
  testMatch: ['<rootDir>/tests/**/*.test.ts', '<rootDir>/tests/**/*.test.tsx'],
  collectCoverageFrom: ['src/**/*.{ts,tsx}'],
};
