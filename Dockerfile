# Reproducible environment for the full pipeline: `docker build -t mmm-geo . && docker run --rm mmm-geo`
# (or `make docker`, which also mounts outputs/ and reports/ so results land in the working copy).
FROM python:3.12-slim

# make: pipeline driver; g++: pytensor compiles fast C code for prediction (pure-Python fallback is very slow);
# curl: data download
RUN apt-get update \
 && apt-get install -y --no-install-recommends make g++ curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

WORKDIR /app
COPY requirements.lock .
RUN uv venv --python /usr/local/bin/python3.12 .venv \
 && uv pip install --python .venv/bin/python -r requirements.lock

COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["make", "all"]
