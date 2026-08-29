FROM python:3.12-slim AS builder

WORKDIR /source
COPY . .
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.12-slim

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels agentic-discipline-kit \
    && rm -rf /wheels

WORKDIR /workspace
ENTRYPOINT ["agentic-discipline"]
CMD ["doctor"]
