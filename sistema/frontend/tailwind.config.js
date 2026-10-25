/** @type {import('tailwindcss').Config} */
export default {
  // Limita el CSS generado a los archivos que contienen clases de Tailwind.
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  // Identidad visual alineada con el proyecto de referencia: azul marino y dorado.
  theme: {
    extend: {
      colors: {
        // Azul marino institucional (se mantiene el nombre para no tocar cada pantalla).
        frigorifico: {
          950: "#0b1f33", // Fondo del encabezado y textos más oscuros.
          900: "#0f2a43", // Botón principal y títulos.
          800: "#173a59", // Hover del botón principal.
          700: "#254766", // Bordes y textos secundarios oscuros.
          100: "#e3e9ef", // Fondos suaves.
          50: "#f8fafb", // Encabezados de tabla y filas resaltadas.
        },
        acero: "#78909c",
        // Dorado: acentos, foco de campos y subrayado del menú activo.
        ambar: {
          DEFAULT: "#b1883a",
          claro: "#d7b76a",
        },
        // Fondo general claro.
        hielo: "#f4f7fa",
      },
      // Títulos con serifa y texto con sans-serif, como en la referencia.
      fontFamily: {
        serif: ['"Merriweather"', "Georgia", "serif"],
        sans: ['"Source Sans 3"', '"Segoe UI"', "Tahoma", "sans-serif"],
      },
      boxShadow: {
        panel: "0 20px 45px -25px rgba(15, 42, 67, 0.35)",
      },
    },
  },
  plugins: [],
};
