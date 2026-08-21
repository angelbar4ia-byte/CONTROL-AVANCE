/**
 * Mis obras — Residente (§4, §5.2).
 *
 * La pantalla vive en `src/pantallas/Obras.tsx`: es compartida entre roles
 * (§5.3) y esta ruta solo la monta para el Residente.
 */

import { Obras } from '@/pantallas/Obras';

export default function Pantalla() {
  return <Obras papel="residente" />;
}
