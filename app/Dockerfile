# Build stage
FROM node:18-alpine as build

WORKDIR /app

# Optional: override API base URL at build time (defaults to /api/v1 for nginx proxy)
ARG REACT_APP_API_URL
ENV REACT_APP_API_URL=${REACT_APP_API_URL}

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built assets from build stage
COPY --from=build /app/build /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Railway sets PORT dynamically; substitute it into nginx.conf at startup
EXPOSE ${PORT:-80}

CMD ["/bin/sh", "-c", "envsubst '${PORT}' < /etc/nginx/conf.d/default.conf > /tmp/nginx.conf && cp /tmp/nginx.conf /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]