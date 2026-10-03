// Importa los componentes de enrutamiento.
import { Navigate, Route, Routes } from "react-router-dom";
// Provee sesión a toda la aplicación.
import { AuthProvider } from "./api/AuthContext";
// Protege las rutas privadas.
import ProtectedRoute from "./components/ProtectedRoute";
// Importa las pantallas de E1.
import Inicio from "./pages/Inicio";
import Login from "./pages/Login";

// Declara las rutas públicas y protegidas.
export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<Inicio />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
