#!/usr/bin/env bash
# build-and-deploy.sh
# Compiles the Obsidian plugin and deploys it to the Research Lab static directory.
# Run from the repository root:
#   bash obsidian-plugin/build-and-deploy.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLUGIN_DIR="${SCRIPT_DIR}"
TARGET_DIR="${REPO_ROOT}/investigacion/static/plugin"
VERSION_FILE="${TARGET_DIR}/plugin_version.json"
MANIFEST="${PLUGIN_DIR}/manifest.json"

echo "==> Building Obsidian plugin..."
cd "${PLUGIN_DIR}"
npm run build

echo "==> Deploying to ${TARGET_DIR}"
mkdir -p "${TARGET_DIR}"
cp "${PLUGIN_DIR}/main.js" "${TARGET_DIR}/main.js"

# Read version from manifest.json
PLUGIN_VERSION=$(node -e "const m=require('./manifest.json');process.stdout.write(m.version)")
RELEASED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
FILENAME="sspa-research-lab-${PLUGIN_VERSION}.js"

cat > "${VERSION_FILE}" <<EOF
{
  "version": "${PLUGIN_VERSION}",
  "filename": "${FILENAME}",
  "released_at": "${RELEASED_AT}",
  "build_available": true
}
EOF

echo "==> Plugin v${PLUGIN_VERSION} deployed — ${RELEASED_AT}"
echo "    File : ${TARGET_DIR}/main.js"
echo "    Meta : ${VERSION_FILE}"
