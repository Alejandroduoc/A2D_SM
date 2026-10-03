// Importa los componentes de redirección y rutas hijas.
import { Navigate, Outlet } from "react-router-dom";
// Lee la sesión centralizada.
import { useAuth } from "../api/AuthContext";

// Protege una ruta con sesión y, opcionalmente, con roles.
export default function ProtectedRoute({ rolesPermitidos }) {
  const { usuario, cargando } = useAuth();

  // Evita redirigir antes de validar un token al recargar.
  if (cargando) {
    return <div className="flex min-h-screen items-center justify-center text-frigorifico-800">Validando sesión...</div>;
  }

  // Envía al login a quien no tiene una sesión válida.
  if (!usuario) return <Navigate to="/login" replace />;

  // La API sigue siendo la autoridad; esta validación solo mejora la UX.
  if (rolesPermitidos && !rolesPermitidos.some((rol) => usuario.roles.includes(rol))) {
    return <Navigate to="/" replace />;
  }

  // Renderiza la ruta protegida correspondiente.
  return <Outlet />;
}
