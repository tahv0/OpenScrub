# syntax=docker/dockerfile:1

# OpenScrub server image (CPU). Built and pushed to GitHub Container
# Registry and Docker Hub automatically on every release
# (.github/workflows/docker-image.yml):
#
#     docker run -d -p 8384:8384 \
#       -v openscrub_data:/root/.local/share/OpenScrub \
#       ghcr.io/austinmabry/openscrub:latest        # or pharmhero/openscrub
#
# then open https://<host>:8384/ (self-signed cert; add --token via the
# command below for access control):
#     docker run ... ghcr.io/austinmabry/openscrub:latest \
#       openscrub-web --host 0.0.0.0 --token mysecret
#
# Data (jobs, certs, zones, models, vault) lives in the mounted volume —
# the container itself is disposable. To update: pull the new tag and
# recreate the container (the in-app updater is disabled in Docker).
# Notes: CPU OCR/encode only (no CUDA/NVENC). spaCy NER is included.
#
# LAYER ORDER MATTERS: heavy dependencies install BEFORE the app code is
# copied, so a release that only changes code rebuilds (and users only
# re-download) the small app layers at the bottom. Combined with the
# workflow's registry build cache, unchanged dependency layers keep the
# same digest across releases.

FROM python:3.12-slim

# Debian OS packages are installed and updated here (cached across normal
# code changes). A later security refresh is deliberately placed after
# expensive dependencies/models but BEFORE application source COPY.
RUN --mount=type=cache,id=openscrub-pip-cpu,target=/root/.cache/pip,sharing=locked \
 apt-get update \
 && apt-get dist-upgrade -y \
 && apt-get install -y --no-install-recommends tesseract-ocr ffmpeg \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --upgrade pip setuptools wheel

WORKDIR /src

# Persistent pip cache mount keeps downloaded wheels across rebuilds without
# putting pip's cache inside the image. It is safe if a requirements file
# changes or BuildKit has to re-execute the install step.
# ---- heavy dependency layer: rebuilds ONLY when requirements.txt changes
COPY requirements.txt ./
RUN --mount=type=cache,id=openscrub-pip-cpu,target=/root/.cache/pip,sharing=locked \
 pip install -r requirements.txt \
 # faster-whisper: local speech transcription for spoken-PII
 # suggestions (fully offline)
 && pip install faster-whisper \
 # spaCy NER for name detection, baked in with its model
 && python -m spacy download en_core_web_sm

# ---- model layer: pre-fetched detection models so first run works
# offline. In its OWN cached layer ABOVE the app code (standalone script,
# no openscrub import — retries the flaky LFS media host and verifies
# every pinned sha256): a release that only changes code no longer
# re-downloads ~60MB of unchanged models. Rebuilds only when
# docker/prefetch_models.py itself changes; a sync test pins its table
# to the engine's constants.
COPY docker/prefetch_models.py ./
RUN python prefetch_models.py yunet sface vittrack ppdet pprec pprec_yml plate_t640

# ---- weekly security refresh: after large deps/models, BEFORE app code
# CI varies SECURITY_REFRESH to install OS updates. Only this step and the
# small source/app layers below rebuild; CUDA, Python wheels and downloaded
# models remain cached. Ordinary code edits keep the default value (0) and
# never need to re-run apt-get update or dist-upgrade.
ARG SECURITY_REFRESH=0
RUN --mount=type=cache,id=openscrub-pip-cpu,target=/root/.cache/pip,sharing=locked \
 echo "security refresh ${SECURITY_REFRESH}" \
 && apt-get update \
 && apt-get dist-upgrade -y \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --upgrade pip setuptools wheel

# ---- app layers: tiny, change every release
COPY pyproject.toml README.md LICENSE NOTICE THIRD_PARTY_NOTICES.md plate_models.json face_models.json person_models.json ./
COPY openscrub.py openscrub_web.py stop_review.py openscrub_logging.py learning_session.py video_learning.py learned_models.py learning_candidates.py plate_verifier.py confirmed_findings.py finding_previews.py review_preview_index.py review_journal.py findings_training.py findings_web.py findings_ui.py plate_text_hints.py plate_text_web.py video_sections.py section_workflow.py openscrub_setup.py openscrub_update.py \
     openscrub_vault.py zones_ui.py install.py test_openscrub.py ./
COPY plate_text_subprocess.py ./
COPY assets/openscrub.ico assets/
COPY scripts/ scripts/
RUN --mount=type=cache,id=openscrub-pip-cpu,target=/root/.cache/pip,sharing=locked \
 pip install --no-deps .

# tells the web UI it runs in a container: the update notice becomes
# inform-only ("pull the new image") instead of offering the in-place
# updater, whose writes would vanish on the next container recreate
ENV OPENSCRUB_IN_DOCKER=1
# Unbuffered stdout: without this, Python block-buffers prints in a non-TTY
# container and `docker logs` stays EMPTY for minutes — a real Mac user
# debugged a perfectly healthy server because the startup banner (and any
# crash traceback stuck behind it) never appeared.
ENV PYTHONUNBUFFERED=1
ENV PYTHONFAULTHANDLER=1

EXPOSE 8384
# Lets `docker ps`/Docker Desktop show whether the server actually answers
# (the reported failure looked identical whether the server was up or not).
# Scheme-agnostic: tries the default self-signed HTTPS, then --http.
HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3 \
  CMD python -c "import urllib.request,ssl;\
ctx=ssl._create_unverified_context();\
exec('try:\n urllib.request.urlopen(\"https://127.0.0.1:8384/\",context=ctx,timeout=8)\nexcept Exception:\n urllib.request.urlopen(\"http://127.0.0.1:8384/\",timeout=8)')"

VOLUME ["/root/.local/share/OpenScrub"]
CMD ["openscrub-web", "--host", "0.0.0.0"]
