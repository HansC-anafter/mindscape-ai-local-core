ARG POSTGRES_BASE_IMAGE=pgvector/pgvector:pg16
FROM ${POSTGRES_BASE_IMAGE}

ARG PG_MAJOR=16

COPY docker/postgres/archive-wal.sh /usr/local/bin/mindscape-archive-wal

RUN set -eux; \
    chmod 0755 /usr/local/bin/mindscape-archive-wal; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc; \
    . /etc/os-release; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends pgbouncer postgresql-${PG_MAJOR}-repack; \
    test "${PG_MAJOR}" = "16"; \
    test -x "/usr/lib/postgresql/${PG_MAJOR}/bin/pg_ctl"; \
    rm -rf /var/lib/apt/lists/*
