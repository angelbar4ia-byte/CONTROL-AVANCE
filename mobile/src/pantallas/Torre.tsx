/**
 * Torre de control en campo — pantalla compartida (§5.3, §11.2 `/torre`).
 *
 * La torre de la web (Fase 10) es un tablero: filtros, columnas, orden por
 * cualquier métrica. Esta **no es esa pantalla en chico**, y no lo intenta.
 *
 * En web la torre sale de `GET /torre`, que agrega del lado del servidor.
 * Aquí se calcula sobre la réplica local, y por dos motivos: en campo puede
 * no haber señal, y el alcance ya está resuelto —lo que está en el
 * dispositivo es exactamente lo que este supervisor puede ver, por las sync
 * rules que espejean RLS (§12.4)—. Sumar sobre eso no puede filtrar de más.
 *
 * La diferencia con la web es qué se muestra: aquí caben tres números por
 * obra y el criterio para elegirlos fue *qué hace que el supervisor cambie de
 * ruta hoy*. Retrasadas, bloqueadas e incidencias abiertas. El avance
 * acumulado va como barra, no como columna: es contexto, no decisión.
 */

import { router } from 'expo-router';
import { FlatList, Pressable, Text, View } from 'react-native';
import { useQuery } from '@powersync/react-native';

import { Barra } from '@/ui/Barra';
import { Encabezado } from '@/ui/Encabezado';
import { Estatus } from '@/ui/Estatus';
import { Cargando, Vacio } from '@/ui/Formulario';

interface FilaObra {
  id: string;
  clave: string;
  estatus: string;
  avance_pct: number;
  actividades: number;
  retrasadas: number;
  bloqueadas: number;
  incidencias: number;
  detienen: number;
}

/**
 * Subconsultas y no un `JOIN` con `GROUP BY`: cada conteo mide una cosa
 * distinta —actividades por un lado, incidencias por otro— y un solo join las
 * multiplicaría entre sí. Es el mismo criterio que ya usa la pantalla de obras
 * del Residente.
 *
 * El orden pone arriba lo que está en problemas: primero las obras con algo
 * que detiene, después por retrasos.
 */
const CONSULTA = `
  SELECT o.id, o.clave, o.estatus, o.avance_pct,
         (SELECT COUNT(*) FROM actividad a WHERE a.obra_id = o.id) AS actividades,
         (SELECT COUNT(*) FROM actividad a
           WHERE a.obra_id = o.id AND a.estatus = 'retrasada') AS retrasadas,
         (SELECT COUNT(*) FROM actividad a
           WHERE a.obra_id = o.id AND a.bloqueada = 1) AS bloqueadas,
         (SELECT COUNT(*) FROM incidencia i
           WHERE i.obra_id = o.id
             AND i.estatus NOT IN ('cerrada', 'rechazada')) AS incidencias,
         (SELECT COUNT(*) FROM incidencia i
           WHERE i.obra_id = o.id AND i.impacto = 'detiene'
             AND i.estatus NOT IN ('cerrada', 'rechazada')) AS detienen
    FROM obra o
   ORDER BY detienen DESC, retrasadas DESC, o.clave
`;

export function Torre() {
  const { data: obras, isLoading } = useQuery<FilaObra>(CONSULTA);

  const detenidas = (obras ?? []).filter((o) => o.detienen > 0).length;
  const conRetraso = (obras ?? []).filter((o) => o.retrasadas > 0).length;

  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow="Supervisor"
        titulo="Torre"
        descripcion="Tus obras, calculado sobre lo que hay en el dispositivo (§12.5)."
      />

      <View className="mb-3 flex-row gap-3">
        <Resumen etiqueta="Obras" valor={obras?.length ?? 0} tono="neutro" />
        <Resumen etiqueta="Detenidas" valor={detenidas} tono="danger" />
        <Resumen etiqueta="Con retraso" valor={conRetraso} tono="warn" />
      </View>

      {isLoading ? (
        <Cargando />
      ) : (
        <FlatList
          data={obras}
          keyExtractor={(item) => item.id}
          ListEmptyComponent={
            <Vacio texto="Todavía no hay obras en el dispositivo. Se descargan solas al haber señal." />
          }
          renderItem={({ item }) => (
            <Pressable
              onPress={() => router.push('/(supervisor)/incidencias')}
              className="mb-3 rounded-lg border border-line bg-surface p-4 active:opacity-70"
            >
              <View className="flex-row items-center justify-between">
                <Text className="font-mono text-lg text-text">{item.clave}</Text>
                <Estatus valor={item.estatus} />
              </View>

              <View className="mt-3">
                <Barra pct={item.avance_pct} />
              </View>

              <View className="mt-2 flex-row items-center justify-between">
                <Text className="text-sm text-text-mute">{item.actividades} actividades</Text>
                <Text className="font-mono text-sm text-text">{item.avance_pct}%</Text>
              </View>

              <View className="mt-3 flex-row flex-wrap gap-2">
                {item.detienen > 0 ? (
                  <Marca texto={`${item.detienen} detiene${item.detienen === 1 ? '' : 'n'}`} tono="danger" />
                ) : null}
                {item.retrasadas > 0 ? (
                  <Marca texto={`${item.retrasadas} retrasadas`} tono="warn" />
                ) : null}
                {item.bloqueadas > 0 ? (
                  <Marca texto={`${item.bloqueadas} bloqueadas`} tono="warn" />
                ) : null}
                {item.incidencias > 0 ? (
                  <Marca texto={`${item.incidencias} incidencias abiertas`} tono="info" />
                ) : null}
                {item.detienen === 0 && item.retrasadas === 0 && item.incidencias === 0 ? (
                  <Marca texto="Sin pendientes" tono="ok" />
                ) : null}
              </View>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

function Resumen({
  etiqueta,
  valor,
  tono,
}: {
  readonly etiqueta: string;
  readonly valor: number;
  readonly tono: 'danger' | 'warn' | 'neutro';
}) {
  const color = tono === 'danger' ? 'text-danger' : tono === 'warn' ? 'text-warn' : 'text-text';

  return (
    <View className="flex-1 rounded-lg border border-line bg-surface p-3">
      <Text className={`font-mono text-2xl ${color}`}>{valor}</Text>
      <Text className="text-xs text-text-mute">{etiqueta}</Text>
    </View>
  );
}

function Marca({
  texto,
  tono,
}: {
  readonly texto: string;
  readonly tono: 'danger' | 'warn' | 'info' | 'ok';
}) {
  const clases: Readonly<Record<string, string>> = {
    danger: 'bg-danger-soft text-danger',
    warn: 'bg-warn-soft text-warn',
    info: 'bg-info-soft text-info',
    ok: 'bg-ok-soft text-ok',
  };
  const [fondo, color] = (clases[tono] ?? '').split(' ');

  return (
    <View className={`rounded-full px-2 py-1 ${fondo}`}>
      <Text className={`text-xs ${color}`}>{texto}</Text>
    </View>
  );
}
