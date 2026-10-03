// Importa el helper de configuración de Vite.
import { defineConfig } from "vite";
// Activa el soporte oficial para JSX y React.
import react from "@vitejs/plugin-react";

// Exporta la configuración usada por el servidor y el compilador.
export default defineConfig({
  // Registra el plugin de React.
  plugins: [react()],
  // Configura el servidor de desarrollo para Docker y Windows.
  server: {
    // Mantiene el puerto acordado con CORS y la documentación del proyecto.
    port: 5173,
    // Usa polling para detectar cambios a través del volumen compartido.
    watch: { usePolling: true, interval: 300 },
  },
});
