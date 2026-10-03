/** @type {import('tailwindcss').Config} */
export default {
  // Limita el CSS generado a los archivos que contienen clases de Tailwind.
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  // Define la identidad visual institucional del sistema.
  theme: {
    extend: {
      colors: {
        frigorifico: {
          950: "#102a43",
          900: "#163b5c",
          800: "#1d5278",
          700: "#28688f",
          100: "#dbeef7",
          50: "#eff8fc",
        },
        acero: "#78909c",
        ambar: "#c18b2c",
        hielo: "#f4f8fa",
      },
      boxShadow: {
        panel: "0 24px 70px -32px rgba(16, 42, 67, 0.45)",
      },
    },
  },
  // No se necesitan plugins adicionales para E1.
  plugins: [],
};
