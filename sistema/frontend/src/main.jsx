// Activa advertencias adicionales durante el desarrollo.
import { StrictMode } from "react";
// Conecta React con el elemento root del HTML.
import { createRoot } from "react-dom/client";
// Habilita las rutas de la aplicación.
import { BrowserRouter } from "react-router-dom";
// Importa las rutas y el proveedor de sesión.
import App from "./App.jsx";
// Carga los estilos globales.
import "./index.css";

// Monta la aplicación en el navegador.
createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
