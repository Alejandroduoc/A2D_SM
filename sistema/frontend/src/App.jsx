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
// Presenta los catálogos relacionados de especies y variedades.
import EspeciesVariedades from "./pages/EspeciesVariedades";
import CalidadesSistemasProductivos from "./pages/CalidadesSistemasProductivos";
// Administración de cuentas (solo administrador) y cambio de la propia contraseña (todos).
import Usuarios from "./pages/Usuarios";
import CambiarContrasena from "./pages/CambiarContrasena";

// Declara las rutas públicas y protegidas.
export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* Login permanece fuera del layout privado. */}
        <Route path="/login" element={<Login />} />
        {/* La protección exterior valida sesión para cualquier perfil autenticado. */}
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            {/* Inicio conserva el acceso de todos los perfiles. */}
            <Route index element={<Inicio />} />
            {/* Cualquier perfil autenticado puede cambiar su contraseña. */}
            <Route path="cambiar-contrasena" element={<CambiarContrasena />} />
            {/* La URL de Productores se protege además de ocultar su opción de menú. */}
            <Route element={<ProtectedRoute rolesPermitidos={["administrador"]} />}>
              <Route path="productores" element={<Productores />} />
              <Route path="especies-variedades" element={<EspeciesVariedades />} />
              <Route path="calidades-sistemas-productivos" element={<CalidadesSistemasProductivos />} />
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
