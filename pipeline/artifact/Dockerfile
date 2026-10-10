# Artifact image: Ubuntu 22.04, HMMER 3.4, pinned Python packages.
# Build from the repository root:
#   docker build -f pipeline/artifact/Dockerfile -t acts-artifact .
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HMMER_SHA256=ca70d94fd0cf271bd7063423aabb116d42de533117343a9b27a65c17ff06fbf3 \
    PATH=/opt/hmmer/bin:${PATH} \
    PYTHONPATH=/src/pipeline

# Python 3.11: the unit suite imports tomllib (3.11 stdlib). Ubuntu 22.04's
# default interpreter is 3.10. git is required by provenance checks.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        python3 \
        python3.11 \
        python3.11-venv \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/hmmer-3.4.tar.gz http://eddylab.org/software/hmmer/hmmer-3.4.tar.gz \
    && echo "${HMMER_SHA256}  /tmp/hmmer-3.4.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/hmmer-3.4.tar.gz -C /tmp \
    && cd /tmp/hmmer-3.4 \
    && ./configure --prefix=/opt/hmmer \
    && make -j"$(nproc)" \
    && make install \
    && rm -rf /tmp/hmmer-3.4 /tmp/hmmer-3.4.tar.gz

COPY pipeline/artifact/requirements.txt /tmp/artifact-requirements.txt
RUN python3.11 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/artifact-requirements.txt

ENV PATH=/opt/venv/bin:/opt/hmmer/bin:${PATH}

COPY . /src
# The checkout's .git is a worktree pointer. Replace it with a repo that
# lives inside the image so `git rev-parse HEAD` succeeds for the unit suite.
RUN rm -rf /src/.git \
    && git init /src \
    && git -C /src add -A \
    && git -C /src -c user.email=artifact@localhost -c user.name=artifact commit -m "artifact image" \
    && chmod +x /src/pipeline/artifact/kick_the_tires.sh /src/pipeline/artifact/run_in_image.sh \
    && hmmscan -h > /tmp/hmmscan-h.txt \
    && grep -q "HMMER 3.4" /tmp/hmmscan-h.txt \
    && python3 -c "import tomllib, numpy, matplotlib" \
    && make -C /src/pipeline/fixtures/fat_copy clean all

WORKDIR /src/pipeline

# Unit suite, then the laptop reproductions and the paper-number check.
CMD ["/src/pipeline/artifact/run_in_image.sh"]
