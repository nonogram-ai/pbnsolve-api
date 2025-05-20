FROM ubuntu:22.04 AS builder

# Instalacja niezbędnych narzędzi do kompilacji z pełnym wsparciem dla libxml2
RUN apt-get update && apt-get install -y \
    build-essential \
    libxml2-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Kopiowanie kodu źródłowego
WORKDIR /src
COPY pbnsolve-1.10/ ./pbnsolve-1.10/

# Upewniamy się, że wsparcie dla XML nie jest wyłączone
WORKDIR /src/pbnsolve-1.10
RUN grep -q "\/\* #define NOXML \/\*\*\/ " config.h || echo "XML support enabled"

# Modyfikacja Makefile aby użyć pkg-config do znalezienia libxml2
RUN sed -i 's/^LIB=.*$/LIB=$(shell pkg-config --libs libxml-2.0) -lm/' Makefile && \
    sed -i 's/^CFLAGS=.*$/CFLAGS= -O2 $(shell pkg-config --cflags libxml-2.0)/' Makefile

# Kompilacja pbnsolve
RUN make pbnsolve

# Drugi etap budowy - dla obrazu API
FROM python:3.11-slim

# Instalacja zależności dla API i runtime libxml2
RUN apt-get update && apt-get install -y \
    libxml2 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir fastapi uvicorn python-multipart pydantic

# Kopiowanie skompilowanego pliku binarnego z poprzedniego etapu
COPY --from=builder /src/pbnsolve-1.10/pbnsolve /usr/local/bin/

# Stworzenie katalogu na pliki tymczasowe
RUN mkdir -p /tmp/pbnsolve

# Kopiowanie kodu API
WORKDIR /app
COPY api/ ./

# Ekspozycja portu dla API
EXPOSE 8000

# Uruchomienie API
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]