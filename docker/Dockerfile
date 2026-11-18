FROM registry.access.redhat.com/ubi9/python-39:latest

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

ENV UV_PROJECT_ENVIRONMENT=/opt/app-root/

WORKDIR /opt/app-root/
COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock
RUN uv sync --python=/opt/app-root/bin/python --locked --no-install-project --no-dev --no-cache

# remove uv binary copied in earlier to hopefully save some space
USER root
RUN rm /bin/uv pyproject.toml uv.lock
USER default

COPY ./8Knot/ /opt/app-root/src/

ENV PATH="/opt/app-root/bin:$PATH"

WORKDIR /opt/app-root/src

# Description of how to choose the number of workers and threads.
# common wisdom is (2*CPU)+1 workers:
# https://medium.com/building-the-system/gunicorn-3-means-of-concurrency-efbb547674b7
# this is a microservice - above may not apply
CMD [ "gunicorn", "--bind", ":8080", "app:server", "--workers", "1", "--threads", "2" ]
