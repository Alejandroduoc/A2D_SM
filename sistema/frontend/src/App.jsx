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
// Vista previa de los selectores de recepción (HU11).
import RecepcionVistaPrevia from "./pages/RecepcionVistaPrevia";

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
            {/* Recepción y administrador, los mismos roles que exige /opciones en la API. */}
            <Route element={<ProtectedRoute rolesPermitidos={["operador_recepcion", "administrador"]} />}>
              <Route path="recepcion" element={<RecepcionVistaPrevia />} />
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
