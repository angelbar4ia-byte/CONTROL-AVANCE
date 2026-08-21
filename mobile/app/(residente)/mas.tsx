/**
 * Más — Residente (§5.2).
 *
 * La pantalla vive en `src/pantallas/Mas.tsx`: es compartida entre roles
 * (§5.3) y esta ruta solo la monta para el Residente.
 */

import { Mas } from '@/pantallas/Mas';

export default function Pantalla() {
  return <Mas papel="residente" />;
}
