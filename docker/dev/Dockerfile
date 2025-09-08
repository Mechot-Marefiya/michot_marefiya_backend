#syntax=docker/dockerfile:1.4
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1
ENV MAIN_DIR=/usr/src/app

# Build args we expect from the compose. 1000 is just default vals
ARG USER_ID=1000
ARG GROUP_ID=1000

# Create non-root user with matching UID/GID
RUN addgroup --system --gid $GROUP_ID app && \
    adduser --system --uid $USER_ID --gid $GROUP_ID app

WORKDIR $MAIN_DIR

# Install uv with pip cache
RUN --mount=type=cache,target=/home/app/.cache/pip,id=pip \
    python -m pip install uv

# Install dependencies (requirements first for better caching)
COPY ./requirements/ ./requirements/

RUN --mount=type=cache,target=/home/app/.cache/pip,id=pip \
    uv pip install --system -r ./requirements/dev.txt

# Copy the rest of the code (ownership doesn’t matter — will be bind-mounted in dev)
COPY . .

EXPOSE 8000
