# --- Etapa 1: compilar la app Angular ---
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# --- Etapa 2: servir con Nginx ---
FROM nginx:1.27-alpine AS runtime

# Configuración que sirve la SPA y hace proxy de /api al backend.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/consultor/browser /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
