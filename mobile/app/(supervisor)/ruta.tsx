/**
 * Ruta crítica — Supervisor (§7.5, §11.3 A).
 *
 * La pantalla vive en `src/pantallas/Ruta.tsx`: es compartida entre roles
 * (§5.3) y esta ruta solo la monta para el Supervisor.
 */

import { Ruta } from '@/pantallas/Ruta';

export default function Pantalla() {
  return <Ruta papel="supervisor" />;
}
