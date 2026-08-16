import { View } from 'react-native';

import { Encabezado } from '@/ui/Encabezado';

export default function Pantalla() {
  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow="Residente"
        titulo="Mis incidencias"
        descripcion="Reporte de incidencias con evidencias (§6)."
      />
    </View>
  );
}
