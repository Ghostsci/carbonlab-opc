FROM alpine:3.20

RUN apk add --no-cache \
      postgresql16 \
      postgresql16-client \
      postgresql16-contrib \
      postgresql-pgvector \
      su-exec \
      tzdata \
    && mkdir -p /var/lib/postgresql/data /run/postgresql \
    && chown -R postgres:postgres /var/lib/postgresql /run/postgresql \
    && chmod 2775 /run/postgresql

ENV PGDATA=/var/lib/postgresql/data

COPY deploy/offline/postgres/docker-entrypoint.sh /usr/local/bin/carbonlab-postgres-entrypoint
RUN chmod 0755 /usr/local/bin/carbonlab-postgres-entrypoint

VOLUME ["/var/lib/postgresql/data"]
EXPOSE 5432

ENTRYPOINT ["carbonlab-postgres-entrypoint"]
CMD ["postgres"]
