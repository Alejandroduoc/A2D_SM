// Importa los componentes de enrutamiento.
import { Navigate, Route, Routes } from "react-router-dom";
// Provee sesión a toda la aplicación.
import { AuthProvider } from "./api/AuthContext";
// Protege las rutas privadas.
import ProtectedRoute from "./components/ProtectedRoute";
// Comparte encabezado, menú y contenido entre las rutas privadas.
import Layout from "./components/Layout";
// Importa las pantallas de E1.
import Inicio from "./pages/Inicio";
import Login from "./pages/Login";
// Importa la página mínima del mantenimiento administrativo.
import Productores from "./pages/Productores";
// Agrupa en pestañas los catálogos de especies, variedades, calidades y sistemas productivos.
import Mantenedores from "./pages/Mantenedores";
// Administración de cuentas (solo administrador) y cambio de la propia contraseña (todos).
import Usuarios from "./pages/Usuarios";
import CambiarContrasena from "./pages/CambiarContrasena";
// Formulario real de recepción de tarjas (HU12-HU14).
import Recepcion from "./pages/Recepcion";
// Consulta de tarjas (HU17).
import Tarjas from "./pages/Tarjas";
// Saldo de bandejas por productor (HU15).
import Bandejas from "./pages/Bandejas";
// Hoja de impresión de la tarja (HU16).
import ImprimirTarja from "./pages/ImprimirTarja";
// Registro de procesos de tarjas (HU18).
import Procesamiento from "./pages/Procesamiento";
// Comprobante del proceso.
import ImprimirProceso from "./pages/ImprimirProceso";
// Rendimiento y merma por folios (HU19).
import Rendimiento from "./pages/Rendimiento";
// Recorrido completo de una tarja (HU23).
import Trazabilidad from "./pages/Trazabilidad";

// Declara las rutas públicas y protegidas.
export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Login permanece fuera del layout privado. */}
        <Route path="/login" element={<Login />} />
        {/* La protección exterior valida sesión para cualquier perfil autenticado. */}
        <Route element={<ProtectedRoute />}>
          {/* Sin Layout: la hoja de impresión no muestra el menú; mismos roles que /tarjas en la API. */}
          <Route element={<ProtectedRoute rolesPermitidos={["operador_recepcion", "administrador"]} />}>
            <Route path="tarjas/:id/imprimir" element={<ImprimirTarja />} />
          </Route>
          {/* Sin Layout: el comprobante no muestra el menú; mismos roles que /procesos en la API. */}
          <Route element={<ProtectedRoute rolesPermitidos={["operador_proceso", "administrador"]} />}>
            <Route path="procesamiento/:id/imprimir" element={<ImprimirProceso />} />
          </Route>
          <Route element={<Layout />}>
            {/* Inicio conserva el acceso de todos los perfiles. */}
            <Route index element={<Inicio />} />
            {/* Cualquier perfil autenticado puede cambiar su contraseña. */}
            <Route path="cambiar-contrasena" element={<CambiarContrasena />} />
            {/* Recepción y administrador, los mismos roles que exige /opciones en la API. */}
            <Route element={<ProtectedRoute rolesPermitidos={["operador_recepcion", "administrador"]} />}>
              <Route path="recepcion" element={<Recepcion />} />
              <Route path="tarjas" element={<Tarjas />} />
              <Route path="bandejas" element={<Bandejas />} />
            </Route>
            {/* Proceso y administrador, los mismos roles que exige /procesos en la API. */}
            <Route element={<ProtectedRoute rolesPermitidos={["operador_proceso", "administrador"]} />}>
              <Route path="procesamiento" element={<Procesamiento />} />
              <Route path="rendimiento" element={<Rendimiento />} />
            </Route>
            {/* Gerencia y administrador, los mismos roles que exige /trazabilidad en la API. */}
            <Route element={<ProtectedRoute rolesPermitidos={["gerencia", "administrador"]} />}>
              <Route path="trazabilidad" element={<Trazabilidad />} />
            </Route>
            {/* La URL de Productores se protege además de ocultar su opción de menú. */}
            <Route element={<ProtectedRoute rolesPermitidos={["administrador"]} />}>
              <Route path="productores" element={<Productores />} />
              <Route path="mantenedores" element={<Mantenedores />} />
              {/* Las direcciones anteriores siguen funcionando y abren su pestaña. */}
              <Route path="especies-variedades" element={<Navigate to="/mantenedores?pestana=especies-variedades" replace />} />
              <Route path="calidades-sistemas-productivos" element={<Navigate to="/mantenedores?pestana=calidades-sistemas" replace />} />
              <Route path="usuarios" element={<Usuarios />} />
            </Route>
          </Route>
        </Route>
        {/* Las rutas desconocidas vuelven al inicio con la protección de sesión vigente. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
