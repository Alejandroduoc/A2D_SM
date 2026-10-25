// Tarjetas que llevan a cada módulo.
import { Link } from "react-router-dom";
// Importa el estado del usuario autenticado.
import { useAuth } from "../api/AuthContext";
// Opciones del menú (con su descripción) y nombres legibles de los roles.
import { NOMBRE_ROL, opcionesPara } from "../components/menu";

// Panel principal: saludo y un acceso por módulo, según los roles.
export default function Inicio() {
  const { usuario } = useAuth();
  // Todos los módulos permitidos menos el propio Inicio.
  const modulos = opcionesPara(usuario.roles).filter((opcion) => opcion.ruta !== "/");

  return (
    <div className="space-y-8">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">Panel principal</p>
        <h1 className="break-words text-2xl font-bold text-frigorifico-900">Bienvenido, {usuario.nombre_completo}</h1>
        <p className="mt-2 text-sm text-slate-500">
          {usuario.roles.map((rol) => NOMBRE_ROL[rol] ?? rol).join(" · ")}. Elige un módulo para continuar.
        </p>
      </div>

      {modulos.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {modulos.map((modulo) => (
            <Link
              key={modulo.ruta}
              to={modulo.ruta}
              className="block rounded-lg border border-slate-200 bg-white p-6 shadow-sm transition hover:border-ambar hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ambar"
            >
              <h2 className="font-bold text-frigorifico-900">{modulo.etiqueta}</h2>
              <p className="mt-1 text-sm text-slate-500">{modulo.descripcion}</p>
            </Link>
          ))}
        </div>
      ) : (
        // Operadores y gerencia aún no tienen módulos: llegan con E3 y E4.
        <p className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-sm">
          Los módulos de recepción y procesamiento de tarjas estarán disponibles en las próximas etapas.
        </p>
      )}
    </div>
  );
}
