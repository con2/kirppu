# Stage 0
FROM node:20-alpine
WORKDIR /usr/src/app/kirppu

COPY kirppu/package.json kirppu/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY kirppu ./
# build will contain the directories {audio,css,fonts,img,js,jst}
# expected to be found in /kirppu/static/kirppu before collectstatic.
RUN mkdir /usr/src/build && npm run gulp -- --dest /usr/src/build --type production


# Stage 1
FROM python:3.13
WORKDIR /usr/src/app

RUN apt-get update && \
    apt-get -y install gettext && \
    mkdir -p /usr/src/app/kirppu && \
    groupadd -r kirppu && \
    useradd -r -g kirppu kirppu && \
    rm -rf /var/lib/apt/lists

COPY requirements-production.txt constraints.txt /usr/src/app/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-production.txt

COPY . ./
COPY --from=0 /usr/src/build ./kirppu/static/kirppu

RUN env DEBUG=1 python manage.py collectstatic --noinput && \
    env DEBUG=1 python manage.py compilemessages && \
    python -m compileall -q .

USER kirppu
EXPOSE 8000
ENTRYPOINT ["/usr/src/app/scripts/docker-entrypoint.sh"]
# overridden in deployment
CMD ["gunicorn",\
     "--bind=0.0.0.0:8000",\
     "--workers=4",\
     "--capture-output",\
     "--access-logfile=-",\
     "kirppu_project.wsgi:application"]
