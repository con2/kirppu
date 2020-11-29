FROM node:14
WORKDIR /usr/src/app/kirppu
COPY kirppu /usr/src/app/kirppu
RUN cd /usr/src/app/kirppu && \
    npm install && \
    npm run gulp && \
    rm -rf node_modules

FROM python:3.9
WORKDIR /usr/src/app

RUN apt-get update && apt-get -y install gettext && rm -rf /var/lib/apt/lists

COPY requirements.txt requirements-oauth.txt requirements-production.txt /usr/src/app/
RUN pip install --no-cache-dir -r requirements.txt -r requirements-oauth.txt -r requirements-production.txt

COPY . /usr/src/app
COPY --from=0 /usr/src/app/kirppu/static /usr/src/app/kirppu/static

RUN groupadd -r kirppu && useradd -r -g kirppu kirppu && \
    env DEBUG=1 python manage.py collectstatic --noinput && \
    env DEBUG=1 python manage.py compilemessages && \
    python -m compileall -q .

USER kirppu
EXPOSE 8000
ENTRYPOINT ["/usr/src/app/scripts/docker-entrypoint.sh"]
CMD ["python", "manage.py", "docker_start"]
