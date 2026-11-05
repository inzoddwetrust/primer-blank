# Frontend image: node builds, nginx serves; the last stage is the default.
#
# No instance value enters the build (contract 3 rule 19). /config.json is
# rendered from the container's environment when it starts, by the nginx
# image's own template step; see nginx/default.conf.template.
#
# The instance's packages are applied at run time (primer.yaml packages, apply:
# runtime): nginx/package.js, run by the njs module of the nginx image, serves
# them; validate-skin and validate-texts (nginx/validate.js, the njs CLI of the
# image) check a package before the machine switches to it.

FROM node:22-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914 AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.30.6-alpine@sha256:47928bf67eb62a1863cb08d9ecb52d3e704304ba614eaee17884204677702951 AS runtime
ENV NGINX_ENVSUBST_FILTER="^(API_BASE_URL|LANGUAGES|DEFAULT_LANGUAGE)$"
RUN rm /etc/nginx/conf.d/default.conf \
    && test "$(grep -c load_module /etc/nginx/nginx.conf)" = 0 \
    && sed -i '1i load_module modules/ngx_http_js_module.so;' /etc/nginx/nginx.conf \
    && nginx -t
COPY nginx/package.js nginx/validate.js /usr/local/lib/primer/
# The product's built-in texts: their files are its languages (nginx/package.js).
COPY src/texts/ /usr/local/lib/primer/texts/
RUN chmod 0644 /usr/local/lib/primer/package.js \
    && chmod 0755 /usr/local/lib/primer/validate.js \
    && ln -s /usr/local/lib/primer/validate.js /usr/local/bin/validate-skin \
    && ln -s /usr/local/lib/primer/validate.js /usr/local/bin/validate-texts
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
