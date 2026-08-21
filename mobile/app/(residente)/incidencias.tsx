/**
 * Incidencias — Residente: levanta lo que detiene la obra (§11.3 F.1).
 *
 * La pantalla vive en `src/pantallas/Incidencias.tsx`: es compartida entre roles
 * (§5.3) y esta ruta solo la monta para el Residente.
 */

import { Incidencias } from '@/pantallas/Incidencias';

export default function Pantalla() {
  return <Incidencias papel="residente" />;
}
