# API Exorcist: the REST API and dashboard as one container.
#
#   docker build -t api-exorcist .
#   apix token ops --role approver          # on any machine; prints an entry
#   docker run -d --name apix -p 127.0.0.1:8600:8600 \
#     -e APIX_API_TOKENS='ops:approver:<sha256>' \
#     -v apix-data:/data --read-only --tmpfs /tmp api-exorcist
#
# The image serves the simulated estate; nothing real is touched.
#
# Decisions:
# - Base image pinned by digest, so a rebuild cannot silently pick up a
#   different Python. Bump it deliberately (`docker pull`, read the digest).
# - Two stages: wheels are built in the first, and only they reach the
#   runtime image. No compiler, no source tree, no pip cache.
# - Runs as an unprivileged user with a fixed uid, and works with a read-only
#   root filesystem: the only writable path it needs is /data (the audit log).
# - Binds 0.0.0.0 inside the container, which `apix serve` only allows with
#   --allow-remote and configured tokens; it will not mint a one-time token
#   into the container's logs. Publish the port on 127.0.0.1, or behind a
#   TLS-terminating proxy: tokens over plain HTTP travel in cleartext.
# - JSON logs and no Swagger pages (they load scripts from a CDN).
# - No pip in the final image (see below).
# - One replica. Pending approvals live in the process; the audit log is safe
#   to share between writers, the approval queue is not yet.

ARG PYTHON_IMAGE=python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

FROM ${PYTHON_IMAGE} AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[api]"

FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APIX_DATA_DIR=/data \
    APIX_LOG_FORMAT=json
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin apix \
    && mkdir /data && chown apix /data
COPY --from=build /wheels /wheels
# pip is removed once it has installed the wheels: the server never uses it,
# and the only known vulnerabilities pip-audit found in this image were in the
# base image's own pip.
RUN pip install --no-cache-dir --no-index /wheels/*.whl && rm -rf /wheels \
    && pip uninstall --yes pip

USER 10001
WORKDIR /data
VOLUME /data
EXPOSE 8600
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8600/v1/health', timeout=2)"]
ENTRYPOINT ["apix"]
CMD ["serve", "--host", "0.0.0.0", "--allow-remote", "--no-docs"]
