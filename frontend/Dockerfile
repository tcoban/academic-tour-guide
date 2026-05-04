FROM node:24-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json next.config.ts next-env.d.ts ./
COPY app ./app
COPY components ./components
COPY lib ./lib

ARG NEXT_PUBLIC_API_BASE_URL=/api/roadshow
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
ENV NODE_ENV=production
RUN npm run build

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "npm run start -- --hostname 0.0.0.0 --port ${PORT}"]
