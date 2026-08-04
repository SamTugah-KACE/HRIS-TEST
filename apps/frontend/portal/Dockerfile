FROM node:20-alpine AS build

WORKDIR /app

ARG VITE_HRIS_CORE_API_BASE_URL=http://localhost:8000
ARG VITE_AUTH_MODE=dev

COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts || npm install

COPY tsconfig.json vite.config.ts tailwind.config.js postcss.config.js index.html ./
COPY src ./src

RUN echo "VITE_HRIS_CORE_API_BASE_URL=$VITE_HRIS_CORE_API_BASE_URL" > .env.production \
 && echo "VITE_AUTH_MODE=$VITE_AUTH_MODE" >> .env.production

RUN npm run build

FROM nginx:1.27-alpine

RUN rm /etc/nginx/conf.d/default.conf 2>/dev/null; true

RUN printf 'server {\n\
  listen 80;\n\
  root /usr/share/nginx/html;\n\
  index index.html;\n\
  location / {\n\
    try_files $uri $uri/ /index.html;\n\
  }\n\
}\n' > /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
