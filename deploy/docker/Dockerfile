# Base images are pinned to an immutable digest (in addition to a human-readable
# tag) so every build resolves the exact same layers — reproducible builds and
# safe rollbacks (#563).

# Stage 1: Build frontend SPA
FROM node:22.23.3-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS frontend
# Public Supabase anon key for the savings leaderboard; empty by default so
# the image's leaderboard stays disabled (#589). Pass --build-arg to enable.
ARG OPENJARVIS_LEADERBOARD_PUBLIC_ANON=

WORKDIR /frontend
# Éden: npm do projeto (11) e .npmrc antes de instalar; só "npm ci" com o
# lockfile e sem scripts de instalação (sem cair num "npm install" solto).
RUN npm install --global npm@11.19.0
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci --ignore-scripts
COPY frontend/ .
RUN VITE_SUPABASE_ANON_KEY="${OPENJARVIS_LEADERBOARD_PUBLIC_ANON}" npm run build

# Stage 2: Build Python package
FROM python:3.12.13-slim-bookworm@sha256:76d4b7b6305788c6b4c6a19d6a22a3921bf802e9af4d5e1e5bd771208dba74bf AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:${PATH}"

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
        sh -s -- -y --profile minimal --default-toolchain none && \
    rustup toolchain install 1.89 --profile minimal && \
    rustup default 1.89
# Éden: 1.89 é a versão mínima pedida em rust/rust-toolchain.toml
# (uuid 1.27). Com 1.88 a montagem da imagem falhava.

WORKDIR /app

# Install dependencies from the committed lockfile (#567). `uv export --frozen`
# reads uv.lock as-is (no re-resolution) and emits a fully pinned, hash-verified
# requirements set; `--no-deps` then installs exactly that set. This is a
# separate layer from the source copy so dependency installs stay cached when
# only application code changes.
COPY pyproject.toml uv.lock README.md ./
RUN pip install --no-cache-dir uv && \
    uv export --frozen --no-dev --extra server --extra inference-cloud --extra security-signing --no-emit-project > requirements.txt && \
    uv pip install --system --no-deps -r requirements.txt && \
    uv pip install --system --no-deps "maturin>=1.12.6,<2"

# Copy the source and the non-src force-include paths (see pyproject
# [tool.hatch.build.targets.wheel.force-include]) before building the project.
COPY src/ src/
COPY rust/ rust/
COPY scripts/install scripts/install
COPY deploy/windows deploy/windows

# Copy built frontend into the server static directory
COPY --from=frontend /src/openjarvis/server/static src/openjarvis/server/static/

# Install the project itself without re-resolving dependencies.
RUN uv pip install --system --no-deps . && \
    maturin build --release \
        --manifest-path rust/crates/openjarvis-python/Cargo.toml \
        --interpreter python3 \
        --out /tmp/openjarvis-rust-wheel && \
    uv pip install --system --no-deps /tmp/openjarvis-rust-wheel/*.whl && \
    python3 -c "import openjarvis_rust; print('openjarvis_rust ok')" && \
    python3 -m pip uninstall -y maturin && \
    rm -rf /tmp/openjarvis-rust-wheel rust

# Stage 3: Runtime
FROM python:3.12.13-slim-bookworm@sha256:76d4b7b6305788c6b4c6a19d6a22a3921bf802e9af4d5e1e5bd771208dba74bf

COPY --from=builder /usr/local /usr/local
COPY --from=builder /app /app
WORKDIR /app

# Run as an unprivileged user — the server needs no root privileges, so dropping
# them limits the blast radius of a compromise (#565). The app writes only to
# $HOME (config/cache/state), which is owned by this user.
RUN groupadd --system --gid 10001 openjarvis && \
    useradd --system --uid 10001 --gid openjarvis \
        --create-home --home-dir /home/openjarvis openjarvis

# Éden: correções de segurança do Debian na hora de montar (a imagem base é
# fixa e fica desatualizada; o verificador Trivy apontava pacotes com correção).
RUN apt-get update && \
    apt-get -y upgrade && \
    rm -rf /var/lib/apt/lists/*

# Éden: configuração, personalidade e script de início dentro da imagem, e a
# pasta de dados (/dados) do usuário sem privilégios. Os SDKs da OpenAI e da
# Anthropic entram acima (extra inference-cloud), para o servidor ligar com a
# chave de qualquer uma das duas.
COPY eden/ /app/eden/
COPY deploy/eden/iniciar-no-conteiner.sh /app/deploy/eden/iniciar-no-conteiner.sh
RUN mkdir -p /dados && chown openjarvis:openjarvis /dados
# Marca a imagem como Éden: sem a seção [eden] na configuração, o servidor se
# recusa a ligar (em vez de subir o OpenJarvis completo).
ENV EDEN_IMAGEM=1
ENV HOME=/home/openjarvis
USER openjarvis

EXPOSE 8000

# Keep `jarvis` as the image entrypoint so Docker and Compose command overrides
# remain subcommands (for example, `docker run IMAGE serve ...`). Platforms
# such as Render replace CMD while preserving this entrypoint.
ENTRYPOINT ["jarvis"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
