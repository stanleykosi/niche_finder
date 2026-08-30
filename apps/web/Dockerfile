FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build
RUN cp -r .next/static .next/standalone/.next/static
CMD ["node", ".next/standalone/server.js"]
