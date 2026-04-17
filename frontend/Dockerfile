FROM node:24-alpine

WORKDIR /app

COPY package.json /app/package.json
COPY tsconfig.json /app/tsconfig.json
COPY next.config.ts /app/next.config.ts
COPY next-env.d.ts /app/next-env.d.ts
COPY app /app/app
COPY components /app/components
COPY lib /app/lib

RUN npm install

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0"]

