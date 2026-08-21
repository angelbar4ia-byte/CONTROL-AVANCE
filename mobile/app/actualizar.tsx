/**
 * Actualización sugerida — el lado suave del §12.12.
 *
 * El force-update no pasa por aquí: `GuardiaDeVersion` sustituye la app
 * entera antes de que haya navegación, porque una pantalla que se puede
 * cerrar no es un bloqueo. Esta ruta es la otra mitad: se llega desde "Más"
 * cuando hay versión nueva y el usuario decide cuándo.
 */

import { router } from 'expo-router';

import { useDiagnosticoDeVersion } from '@/lib/guardiaVersion';
import { AvisoActualizar } from '@/ui/AvisoActualizar';

export default function Pantalla() {
  const diagnostico = useDiagnosticoDeVersion();

  return <AvisoActualizar diagnostico={diagnostico} onPosponer={() => router.back()} />;
}
