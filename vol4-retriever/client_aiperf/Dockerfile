# Vol.4 · the load tool (AIPerf) as a container, so that it sits on the same Docker network as a NIM and reaches it
# without the host's port forwarding. CPU only. Nothing of this repository is copied into the image.
FROM python:3.12-slim@sha256:401f6e1a67dad31a1bd78e9ad22d0ee0a3b52154e6bd30e90be696bb6a3d7461
RUN pip install --no-cache-dir aiperf==0.11.0
WORKDIR /work
