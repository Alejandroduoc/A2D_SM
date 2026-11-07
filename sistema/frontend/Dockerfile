# Usa Node 26, LTS vigente y compatible con Vite, React Router y sus dependencias.
FROM node:26-alpine

# Define la carpeta de trabajo del contenedor.
WORKDIR /app

# Copia primero las dependencias para aprovechar la caché de Docker.
COPY package*.json ./

# Instala las dependencias dentro del contenedor.
RUN npm install

# Copia el código del frontend.
COPY . .

# Documenta el puerto del servidor de desarrollo.
EXPOSE 5173

# Expone Vite fuera del contenedor y habilita el modo desarrollo.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
