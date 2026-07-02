FROM node:22 AS frontend

WORKDIR /build

COPY package.json webpack.config.js ./
RUN npm install --omit=dev

COPY js ./js
COPY css ./css
RUN npm run build


FROM python:3-slim

WORKDIR /usr/src/app

COPY . .
COPY --from=frontend /build/static ./static

RUN pip3 install --no-cache-dir -r py/requirements.txt

EXPOSE 8058

CMD ["python3", "py/micboard.py"]
