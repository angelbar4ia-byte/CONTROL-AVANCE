/**
 * "Más" — pantalla compartida (§5.2, §5.3).
 *
 * El §5.2 le cuelga a este tab una lista larga: Frentes, Extra-catálogo,
 * Control de materiales, Autoevaluación, Guía de estimación y Expediente para
 * el Residente; Obras supervisadas para el Supervisor. En web esas pantallas
 * existen desde la Fase 9; en móvil, no todas tienen sentido.
 *
 * **La regla que se aplicó aquí:** en el teléfono va lo que se consulta o se
 * captura *parado frente a la obra*. Lo que se hace sentado —configurar
 * catálogos, revisar una estimación renglón por renglón, comparar un
 * presupuesto— se queda en la web, y se dice con todas sus letras en vez de
 * ofrecer una pantalla que va a decepcionar. Un "solo web" honesto ahorra el
 * viaje al teléfono equivocado; un enlace que abre una tabla ilegible, no.
 *
 * Aquí vive también lo que no es del §5.2 pero solo tiene lugar aquí: el
 * estado detallado de las tres colas de salida, el aviso de versión nueva
 * (§12.12) y cerrar sesión.
 */

import type { ReactNode } from 'react';
import { router } from 'expo-router';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { useQuery } from '@powersync/react-native';

import { cerrarSesion } from '@/lib/auth';
import { useDiagnosticoDeVersion } from '@/lib/guardiaVersion';
import { useSesion } from '@/lib/sesion';
import { VERSION_APP } from '@/lib/version';
import { useEstadoSync } from '@/sync/estado';
import { Encabezado } from '@/ui/Encabezado';

interface FilaFrente {
  id: string;
  clave: string;
  nombre: string;
}

/**
 * Control de obra no tiene tab "Más" (§5.2: *Obras · Revisión · Fotos ·
 * Calidad*), y por eso no está en este tipo: su configuración es toda web y
 * no queda nada que colgar de un menú.
 */
type Papel = 'residente' | 'supervisor';

/**
 * Qué del §5.2 vive en el teléfono y qué no. El texto de `motivo` es lo que
 * se le muestra al usuario: no es documentación interna.
 */
const SOLO_WEB: Readonly<Record<Papel, readonly { titulo: string; motivo: string }[]>> = {
  residente: [
    {
      titulo: 'Extra-catálogo',
      motivo: 'Alta de actividad fuera de catálogo: exige elegir concepto y precio (§11.3 G).',
    },
    {
      titulo: 'Control de materiales',
      motivo: 'Consulta de almacén y salidas; se revisa por renglón (§7.7).',
    },
    {
      titulo: 'Autoevaluación',
      motivo: 'Cuestionario por criterios ponderados (§7.8).',
    },
    {
      titulo: 'Guía de estimación',
      motivo: 'El corte semanal se arma y valida en web (§11.3 E).',
    },
    {
      titulo: 'Expediente técnico',
      motivo: 'Planos y contratos: documentos para leer en pantalla grande (§7.9).',
    },
  ],
  supervisor: [
    {
      titulo: 'Asignaciones',
      motivo: 'Es solo web por spec (§5.2).',
    },
    {
      titulo: 'Evaluaciones',
      motivo: 'Nivel control y final, por criterios ponderados (§7.8).',
    },
  ],
};

export function Mas({ papel }: { readonly papel: Papel }) {
  const { sesion } = useSesion();
  const { estado, detalle, pendientes, ultimaSync } = useEstadoSync();
  const diagnostico = useDiagnosticoDeVersion();
  const { data: frentes } = useQuery<FilaFrente>('SELECT id, clave, nombre FROM frente ORDER BY orden');

  return (
    <ScrollView className="flex-1 bg-bg px-5 pt-14">
      <Encabezado eyebrow={sesion?.nombre ?? ''} titulo="Más" />

      {diagnostico.estado === 'sugerida' ? (
        <Pressable
          onPress={() => router.push('/actualizar')}
          className="mb-4 rounded-lg border border-accent bg-accent-soft p-4 active:opacity-70"
        >
          <Text className="text-base text-accent">Hay una versión nueva de la app</Text>
          <Text className="mt-1 text-sm text-text-mute">
            Tienes la {VERSION_APP}; disponible la {diagnostico.recomendada}.
          </Text>
        </Pressable>
      ) : null}

      <Seccion titulo="Sincronización">
        <Linea etiqueta="Estado" valor={etiquetaEstado(estado)} />
        <Linea etiqueta="Cambios por subir" valor={String(detalle.cambios)} />
        <Linea etiqueta="Fotos por subir" valor={String(detalle.fotos)} />
        <Linea etiqueta="Operaciones por enviar" valor={String(detalle.operaciones)} />
        <Linea
          etiqueta="Última sincronización"
          valor={ultimaSync ? ultimaSync.toLocaleString() : 'nunca en este dispositivo'}
        />
        {pendientes > 0 ? (
          <Text className="mt-2 text-xs text-text-mute">
            Nada se pierde sin señal: sube solo al reconectar (§12.5).
          </Text>
        ) : null}
      </Seccion>

      {papel === 'residente' ? (
        <Seccion titulo="Frentes (§8.3)">
          {(frentes ?? []).length === 0 ? (
            <Text className="text-sm text-text-mute">Aún no se descargan al dispositivo.</Text>
          ) : (
            (frentes ?? []).map((frente) => (
              <Linea key={frente.id} etiqueta={frente.clave} valor={frente.nombre} />
            ))
          )}
        </Seccion>
      ) : null}

      <Seccion titulo="Se hace en la web">
        {SOLO_WEB[papel].map((item) => (
          <View key={item.titulo} className="mb-3">
            <Text className="text-base text-text">{item.titulo}</Text>
            <Text className="text-sm text-text-mute">{item.motivo}</Text>
          </View>
        ))}
      </Seccion>

      <Seccion titulo="Sesión">
        <Linea etiqueta="Usuario" valor={sesion?.nombre ?? '—'} />
        <Linea etiqueta="Rol" valor={sesion?.rol ?? '—'} />
        <Linea etiqueta="Versión" valor={VERSION_APP} />

        <Pressable
          onPress={() => void cerrarSesion()}
          className="mt-4 h-fila items-center justify-center rounded-md border border-danger active:opacity-70"
        >
          <Text className="text-base text-danger">Cerrar sesión</Text>
        </Pressable>
        <Text className="mt-2 text-xs text-text-mute">
          Lo capturado sin subir se queda en el dispositivo y sale al volver a entrar: cerrar sesión no
          borra la base local (§12.5).
        </Text>
      </Seccion>

      <View className="h-12" />
    </ScrollView>
  );
}

function etiquetaEstado(estado: string): string {
  switch (estado) {
    case 'sincronizado':
      return 'Todo sincronizado';
    case 'sincronizando':
      return 'Sincronizando';
    case 'pendiente':
      return 'Con cambios por subir';
    case 'sin-red':
      return 'Sin red';
    default:
      return 'Solo local (sync sin configurar)';
  }
}

function Seccion({ titulo, children }: { readonly titulo: string; readonly children: ReactNode }) {
  return (
    <View className="mb-4 rounded-lg border border-line bg-surface p-4">
      <Text className="mb-3 font-mono text-xs uppercase text-text-faint">{titulo}</Text>
      {children}
    </View>
  );
}

function Linea({ etiqueta, valor }: { readonly etiqueta: string; readonly valor: string }) {
  return (
    <View className="mb-1.5 flex-row items-center justify-between gap-3">
      <Text className="text-sm text-text-mute">{etiqueta}</Text>
      <Text className="flex-1 text-right font-mono text-sm text-text">{valor}</Text>
    </View>
  );
}
