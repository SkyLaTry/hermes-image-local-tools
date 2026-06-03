#!/usr/bin/env bash
# SkyLaTry Hermes plugin installer (generated per repo by stage-release-repos.sh)
#
# Usage (same pattern as Hermes Agent itself):
#   curl -fsSL https://raw.githubusercontent.com/SkyLaTry/REPO/main/install.sh | bash
#
# Requires Hermes Agent 0.15.1+, git, and the hermes CLI.
set -euo pipefail

PLUGIN_ID="image_gen/local-tools"
GITHUB_REPO="SkyLaTry/hermes-image-local-tools"
INSTALL_MODE="nested"          # flat | nested
NESTED_FOLDER="local-tools"
REQUIRES_ESSENTIALS="false"  # true | false

HERMES_INSTALL='curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash'
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
PLUGINS_DIR="${HERMES_HOME}/plugins"
ORG="${GITHUB_REPO%%/*}"
REPO="${GITHUB_REPO##*/}"

die() {
  echo "install.sh: $*" >&2
  exit 1
}

resolve_hermes() {
  if command -v hermes >/dev/null 2>&1; then
    return 0
  fi
  for c in /usr/local/bin/hermes /usr/bin/hermes /opt/hermes-agent/venv/bin/hermes; do
    if [[ -x "$c" ]]; then
      export PATH="$(dirname "$c"):$PATH"
      return 0
    fi
  done
  return 1
}

resolve_git() {
  command -v git >/dev/null 2>&1 && return 0
  for c in /usr/bin/git /usr/local/bin/git /bin/git; do
    if [[ -x "$c" ]]; then
      export PATH="$(dirname "$c"):$PATH"
      return 0
    fi
  done
  die "git is not installed. Install Hermes first (it bundles git guidance): ${HERMES_INSTALL}"
}

plugin_installed() {
  local id="$1"
  if [[ "$id" == */* ]]; then
    [[ -d "${PLUGINS_DIR}/${id}" ]]
  else
    [[ -d "${PLUGINS_DIR}/${id}" ]]
  fi
}

ensure_hermes() {
  if resolve_hermes; then
    return 0
  fi
  cat >&2 <<EOF
Hermes CLI not found.

Install Hermes Agent first (one command, same as upstream):

  ${HERMES_INSTALL}

Then open a new shell and run this script again:

  curl -fsSL https://raw.githubusercontent.com/${GITHUB_REPO}/main/install.sh | bash
EOF
  exit 1
}

ensure_essentials() {
  [[ "${REQUIRES_ESSENTIALS}" == "true" ]] || return 0
  if plugin_installed "hermes-essentials"; then
    return 0
  fi
  echo "==> Installing dependency: hermes-essentials"
  hermes plugins install "${ORG}/hermes-essentials" --enable
}

install_flat() {
  echo "==> Installing ${PLUGIN_ID} (${GITHUB_REPO})"
  hermes plugins install "${GITHUB_REPO}" --enable
}

install_nested() {
  local dest="${PLUGINS_DIR}/image_gen/${NESTED_FOLDER}"
  mkdir -p "${PLUGINS_DIR}/image_gen"
  if [[ -d "${dest}/.git" ]]; then
    echo "==> Updating ${PLUGIN_ID}"
    git -C "${dest}" pull --ff-only
  else
    echo "==> Cloning ${PLUGIN_ID} (${GITHUB_REPO})"
    git clone --depth 1 "https://github.com/${GITHUB_REPO}.git" "${dest}"
  fi
  hermes plugins enable "${PLUGIN_ID}"
}

main() {
  resolve_git
  ensure_hermes
  mkdir -p "${PLUGINS_DIR}"
  ensure_essentials

  case "${INSTALL_MODE}" in
    flat) install_flat ;;
    nested) install_nested ;;
    *) die "unknown INSTALL_MODE: ${INSTALL_MODE}" ;;
  esac

  echo ""
  echo "Installed and enabled: ${PLUGIN_ID}"
  echo "Restart the gateway: hermes gateway restart"
}

main "$@"
