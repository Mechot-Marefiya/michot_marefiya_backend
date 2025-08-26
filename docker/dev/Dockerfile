# Pull base image
FROM python:3.13-slim


# Install build dependencies b/c the base image lacks
# RUN apt-get update && apt-get install -y \
#     curl\
#     build-essential \
#     libpq-dev \
#     python3-dev \
#     && apt-get clean \
#     && rm -rf /var/lib/apt/lists/*

# Set global environment variables
# ENV PIP_DISABLE_PIP_VERSION_CHECK=1
# ENV PYTHONDONTWRITEBYTECODE=1
# ENV PYTHONUNBUFFERED=1
# ENV APP_HOME=/usr/src/app
# Create a user to run the application
RUN addgroup --system app && adduser --system --group app

RUN mkdir /code

WORKDIR /code

# Install uv 
RUN --mount=type=cache,target=/home/dag/.cache,id=pip \
    python -m pip install uv 

# Install dependencies
COPY ./requirements/ ./requirements/
# RUN pip install pip --upgrade
# RUN pip install -r ./requirements/dev.txt



# Run uv pip install with caching! 
RUN --mount=type=cache,target=/home/dag/.cache,id=pip \
    uv pip install --system -r /code/requirements/dev.txt



# Copy the rest of the application code
COPY . .

# change the ownership all the files to the app user
RUN chown -R app:app /code

EXPOSE 8000
