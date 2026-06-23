# syntax=docker/dockerfile:1.4
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONPYCACHEPREFIX=/tmp/pycache \
    MAIN_DIR=/usr/src/app \
    DJANGO_SETTINGS_MODULE=config.settings.dev \
    PORT=10000

WORKDIR $MAIN_DIR

RUN python -m pip install --no-cache-dir uv

COPY ./requirements/ ./requirements/
RUN --mount=type=cache,target=/root/.cache/pip,id=pip \
    uv pip install --system -r ./requirements/prod.txt

COPY . .

RUN chmod +x docker/render/start.sh

EXPOSE 10000

CMD ["sh", "docker/render/start.sh"]
