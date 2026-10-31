# CPU-only image for the tool check of Vol.4: Pyserini's BM25 baseline on BEIR SciFact, run with the command and the
# prebuilt index that Pyserini's own reproduction page gives. No GPU is used and none is requested.
# The base image is pinned by digest (Debian 13, Python 3.12.13); Pyserini 2.4.0 needs Java 21.
FROM python:3.12-slim@sha256:401f6e1a67dad31a1bd78e9ad22d0ee0a3b52154e6bd30e90be696bb6a3d7461
RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
 && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir pyserini==2.4.0
WORKDIR /work
