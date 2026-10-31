// La pestaña elegida se guarda en la URL (?pestana=...) para poder recargar o compartir el enlace.
import { useSearchParams } from "react-router-dom";
// Pantallas de cada grupo de catálogos.
import CalidadesSistemasProductivos from "./CalidadesSistemasProductivos";
import BandejasEmbalajes from "./BandejasEmbalajes";
import EspeciesVariedades from "./EspeciesVariedades";

// Pestañas disponibles, en el orden en que se muestran.
const PESTANAS = [
  { clave: "especies-variedades", etiqueta: "Especies y variedades", Componente: EspeciesVariedades },
  { clave: "calidades-sistemas", etiqueta: "Calidades y sistemas productivos", Componente: CalidadesSistemasProductivos },
  { clave: "bandejas-embalajes", etiqueta: "Bandejas y embalajes", Componente: BandejasEmbalajes },
];

// Agrupa los catálogos de E2 en pestañas, como el mantenedor del proyecto de referencia.
export default function Mantenedores() {
  const [parametros, setParametros] = useSearchParams();
  // Una clave desconocida o ausente abre la primera pestaña.
  const activa = PESTANAS.find((pestana) => pestana.clave === parametros.get("pestana")) ?? PESTANAS[0];

  // Mueve el foco entre pestañas con las flechas, como pide el patrón de pestañas accesibles.
  function moverConTeclado(event, indice) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const siguiente = (indice + (event.key === "ArrowRight" ? 1 : -1) + PESTANAS.length) % PESTANAS.length;
    setParametros({ pestana: PESTANAS[siguiente].clave });
    document.getElementById(`pestana-${PESTANAS[siguiente].clave}`)?.focus();
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-ambar">E2 · Catálogos</p>
        <h1 className="text-2xl font-bold text-frigorifico-900">Mantenedores</h1>
        <p className="mt-2 text-sm text-slate-500">Catálogos de soporte para la recepción y el proceso, uno por pestaña.</p>
      </div>

      {/* Pestañas: la activa lleva el subrayado dorado. */}
      <div role="tablist" aria-label="Catálogos" className="flex flex-wrap gap-1 border-b border-slate-200">
        {PESTANAS.map((pestana, indice) => {
          const seleccionada = pestana.clave === activa.clave;
          return (
            <button
              key={pestana.clave}
              id={`pestana-${pestana.clave}`}
              type="button"
              role="tab"
              aria-selected={seleccionada}
              aria-controls={`panel-${pestana.clave}`}
              tabIndex={seleccionada ? 0 : -1}
              onClick={() => setParametros({ pestana: pestana.clave })}
              onKeyDown={(event) => moverConTeclado(event, indice)}
              className={`-mb-px rounded-t px-4 py-2 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-ambar ${
                seleccionada ? "border-b-2 border-ambar text-frigorifico-900" : "text-slate-500 hover:text-frigorifico-900"
              }`}
            >
              {pestana.etiqueta}
            </button>
          );
        })}
      </div>

      {/* Solo se monta la pestaña activa: cada una carga sus datos al abrirse. */}
      <div id={`panel-${activa.clave}`} role="tabpanel" aria-labelledby={`pestana-${activa.clave}`} className="pt-2">
        <activa.Componente />
      </div>
    </div>
  );
}
