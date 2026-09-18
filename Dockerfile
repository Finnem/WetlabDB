# syntax=docker/dockerfile:1

FROM node:20-bookworm AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM mambaorg/micromamba:2.0.5
USER root
RUN micromamba install -y -n base -c conda-forge \
        python=3.11 rdkit pandas pillow \
        fastapi uvicorn python-multipart argon2-cffi itsdangerous pymongo \
    && micromamba clean -a -y
WORKDIR /app
COPY wetlabdb ./wetlabdb
COPY pyproject.toml ./
COPY --from=frontend /src/dist ./frontend/dist
ENV PYTHONPATH=/app \
    WETLABDB_MODE=remote \
    WETLABDB_DATA_DIR=/data \
    PYTHONUNBUFFERED=1 \
    MAMBA_DOCKERFILE_ACTIVATE=1
EXPOSE 8000
CMD ["micromamba", "run", "-n", "base", "python", "-m", "uvicorn", "wetlabdb.api.app:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
