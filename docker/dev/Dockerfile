# syntax=docker/dockerfile:1.4
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1

RUN addgroup --system app && adduser --system --group app

WORKDIR /code

# Install uv 
RUN --mount=type=cache,target=/home/dagi/.cache/pip,id=pip \
    python -m pip install uv 

# Install dependencies
COPY ./requirements/ ./requirements/

# Run uv pip install with caching! 
RUN --mount=type=cache,target=/home/dagi/.cache/pip,id=pip \
    uv pip install --system -r /code/requirements/dev.txt


# Copy the rest of the application code
COPY . .

# change the ownership all the files to the app user
RUN chown -R app:app /code

EXPOSE 8000
