# Vol.4 · the timing client as a container, so that it can sit on the same Docker network as a NIM and reach it without
# the host's port forwarding. CPU only. The scripts are mounted at run time (read-only); nothing of this repository is
# copied into the image.
FROM python:3.12-slim@sha256:401f6e1a67dad31a1bd78e9ad22d0ee0a3b52154e6bd30e90be696bb6a3d7461
RUN pip install --no-cache-dir numpy==2.4.6 requests==2.34.2 pyarrow==25.0.1
WORKDIR /work
