# Deliberately does NOT install PaddleOCR — that pulls paddlepaddle plus model
# weights and turns a ~200 MB image into a multi-gigabyte one. When Phase 2
# self-hosts PP-StructureV3, give it its own image and service so the API stays
# small and deploys fast.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# WeasyPrint renders through pango rather than in pure Python, so these have to
# be present or `import weasyprint` fails at startup — the kind of thing that
# passes locally and breaks on first deploy.
#
# This list is the set of shared objects WeasyPrint actually dlopens, read off a
# working process rather than recalled: libpango-1.0, libpangoft2-1.0,
# libharfbuzz, libharfbuzz-subset (font subsetting when embedding), libfontconfig.
# glib/gobject and freetype arrive as pango's own dependencies, and libjpeg comes
# bundled inside the Pillow wheel, so none of those are listed.
#
# fonts-dejavu-core is not optional: with no font installed, PDFs render with no
# text at all — a silent failure that still produces a valid-looking file.
#
# VERIFIED 2026-09-26: this image builds and `import weasyprint` succeeds
# (70.0) inside it, so the list below is complete. If it ever regresses you will
# see `OSError: cannot load library 'libgobject-2.0-0'` at import time — that is
# a missing name here, not a Python problem.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libharfbuzz-subset0 \
        libfontconfig1 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
