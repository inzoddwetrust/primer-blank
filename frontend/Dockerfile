# Frontend image: node builds, nginx serves; the last stage is the default.
#
# No instance value enters the build (contract 3 rule 19). /config.json is
# rendered from the container's environment when it starts, by the nginx
# image's own template step; see nginx/default.conf.template.

FROM node:22-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914 AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.30.6-alpine@sha256:47928bf67eb62a1863cb08d9ecb52d3e704304ba614eaee17884204677702951 AS runtime
ENV NGINX_ENVSUBST_FILTER="^API_BASE_URL$"
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
