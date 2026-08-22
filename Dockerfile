# syntax=docker/dockerfile:1
# Slim, multi-arch (amd64 + arm64) Alpine image for PowerliftingDash.
# Build for a Raspberry Pi with:
#   docker buildx build --platform linux/arm64 -t powerliftingdash:latest --load .
# or for both architectures at once (needs a registry to push multi-arch manifests to):
#   docker buildx build --platform linux/amd64,linux/arm64 -t <you>/powerliftingdash:latest --push .

FROM python:3.12-alpine AS builder

WORKDIR /build

# gcc/musl-dev/etc. are only needed to build wheels for packages without
# musl-linux wheels on PyPI; they are not carried into the final image.
RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-alpine AS runtime

# tzdata is needed for correct America/Toronto-style timezone handling.
RUN apk add --no-cache tzdata \
    && addgroup -S app && adduser -S app -G app

COPY --from=builder /install /usr/local

WORKDIR /app
COPY app ./app
COPY schema ./schema

RUN mkdir -p /data && chown -R app:app /data /app

VOLUME ["/data"]
EXPOSE 8080

ENV PLD_DATA_DIR=/data \
    PLD_HOST=0.0.0.0 \
    PLD_PORT=8080 \
    PYTHONUNBUFFERED=1

USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O- http://127.0.0.1:8080/healthz || exit 1

CMD ["python3", "-m", "app"]
