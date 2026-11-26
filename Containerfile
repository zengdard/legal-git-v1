# Legal Git API image: multi-stage build.
# Stage 1 compiles the C++20 document core (pybind11 module).
# Stage 2 ships a slim Python 3.12 image with the app, migrations and the
# demo corpus. The module_name scheme uses the tag's interpreter (3.12).

FROM docker.io/library/python:3.12-slim AS core-build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        g++ cmake ninja-build git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY core/ core/
RUN mkdir -p app \
    && cmake -S core -B core/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    && cmake --build core/build \
    && ./core/build/core_tests

FROM docker.io/library/python:3.12-slim

# libpq is not needed: the runtime uses the pure-Python pg8000 driver.
WORKDIR /srv

COPY pyproject.toml README.md ./
COPY app/ app/
COPY --from=core-build /src/app/ app/
COPY migrations/ migrations/
COPY alembic.ini ./
COPY fixtures/ fixtures/
COPY docs/ docs/

RUN pip install --no-cache-dir -e . \
    && useradd --create-home --uid 10001 legalgit \
    && mkdir -p /data/storage \
    && chown -R legalgit:legalgit /data /srv

USER legalgit
ENV LEGALGIT_STORAGE_DIR=/data/storage \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
