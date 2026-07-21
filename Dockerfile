# Runtime image for the admin app on Fly.io. Base image already carries
# Python + Playwright's Chromium OS dependencies matching the pinned
# playwright==1.48.0 in admin/requirements.txt, so no hand-rolled apt list
# for headless-browser support is needed.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Only requirements.txt is needed from the build context — the actual app
# code is pulled from git onto the persistent volume at container start (see
# docker-entrypoint.sh), so a `fly deploy` rebuilding this image never has to
# re-bake repo content and never risks losing volume-resident state.
COPY admin/requirements.txt ./admin/requirements.txt
RUN pip install --no-cache-dir -r admin/requirements.txt

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8787

ENTRYPOINT ["docker-entrypoint.sh"]
