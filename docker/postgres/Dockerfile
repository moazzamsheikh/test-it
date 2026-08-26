# PostgreSQL 16 with BOTH PostGIS and pgvector.
# No official image ships both, so we extend the PostGIS image (Debian + PGDG apt
# repo already configured) and add pgvector from PGDG.
FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*

# Extensions are created on first boot against the default database.
COPY init/00-extensions.sql /docker-entrypoint-initdb.d/00-extensions.sql
