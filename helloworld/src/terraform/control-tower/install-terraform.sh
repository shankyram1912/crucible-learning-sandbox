#!/usr/bin/env bash
# Learning Sandbox Day-0: optional standalone Terraform installer (no sudo needed).
#
#   ./install-terraform.sh [--version=<x.y.z|latest>] [--dir=<install dir>] [--no-profile]
#
# Defaults: version 1.17.1, installs to ~/.local/bin (persists in Cloud Shell's home),
# and adds that directory to PATH in ~/.bashrc if it is not there yet.
# The download is verified against HashiCorp's published SHA256 checksums.
# Safe to re-run: skips the download if the requested version is already installed there.

set -Eeuo pipefail

TF_VERSION="${TF_VERSION:-1.17.1}"
INSTALL_DIR="${HOME}/.local/bin"
UPDATE_PROFILE=1

for arg in "$@"; do
  case "$arg" in
    --version=*)  TF_VERSION="${arg#*=}" ;;
    --dir=*)      INSTALL_DIR="${arg#*=}" ;;
    --no-profile) UPDATE_PROFILE=0 ;;
    -h|--help)    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)            echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [[ -t 1 && -z "${NO_COLOR-}" ]]; then
  G=$'\e[32m'; R=$'\e[31m'; B=$'\e[34m'; N=$'\e[0m'
else
  G=""; R=""; B=""; N=""
fi
info() { printf '%s\n' "  ${B}›${N} $*"; }
ok()   { printf '%s\n' "  ${G}✔${N} $*"; }
die()  { printf '%s\n' "  ${R}✖${N} $*" >&2; exit 1; }

for tool in curl sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || die "required tool not found: $tool"
done

# Resolve "latest" from HashiCorp's checkpoint API.
if [[ "$TF_VERSION" == "latest" ]]; then
  TF_VERSION="$(curl -fsS -m 20 https://checkpoint-api.hashicorp.com/v1/check/terraform \
    | sed -nE 's/.*"current_version":"([0-9.]+)".*/\1/p')"
  [[ -n "$TF_VERSION" ]] || die "could not determine the latest Terraform version"
fi
[[ "$TF_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid version: $TF_VERSION"

case "$(uname -m)" in
  x86_64|amd64)  ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) die "unsupported CPU architecture: $(uname -m)" ;;
esac
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
[[ "$OS" == "linux" ]] || die "this installer supports Linux only (found: $OS)"

TARGET="${INSTALL_DIR}/terraform"
if [[ -x "$TARGET" ]] && "$TARGET" version 2>/dev/null | head -n1 | grep -q "v${TF_VERSION}$"; then
  ok "Terraform ${TF_VERSION} already installed at ${TARGET}"
else
  ZIP="terraform_${TF_VERSION}_linux_${ARCH}.zip"
  BASE="https://releases.hashicorp.com/terraform/${TF_VERSION}"
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT

  info "Downloading ${BASE}/${ZIP}"
  curl -fsS -m 300 -o "$TMP/$ZIP" "$BASE/$ZIP" || die "download failed: $BASE/$ZIP"
  curl -fsS -m 60 -o "$TMP/SHA256SUMS" "$BASE/terraform_${TF_VERSION}_SHA256SUMS" || die "checksum download failed"

  info "Verifying SHA256 checksum"
  ( cd "$TMP" && grep " ${ZIP}\$" SHA256SUMS | sha256sum -c - >/dev/null ) || die "checksum mismatch for $ZIP"
  ok "checksum OK"

  info "Extracting"
  if command -v unzip >/dev/null 2>&1; then
    unzip -q -o "$TMP/$ZIP" terraform -d "$TMP"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extract('terraform', sys.argv[2])" "$TMP/$ZIP" "$TMP"
  else
    die "need unzip or python3 to extract the archive"
  fi

  mkdir -p "$INSTALL_DIR"
  install -m 0755 "$TMP/terraform" "$TARGET"
  ok "installed ${TARGET}"
fi

# Make sure the install dir is on PATH (now and in future shells).
case ":${PATH}:" in
  *":${INSTALL_DIR}:"*) ;;
  *)
    if (( UPDATE_PROFILE )); then
      LINE="export PATH=\"${INSTALL_DIR}:\$PATH\"  # added by learning-sandbox install-terraform.sh"
      if ! grep -qF "$LINE" "${HOME}/.bashrc" 2>/dev/null; then
        printf '\n%s\n' "$LINE" >> "${HOME}/.bashrc"
        ok "added ${INSTALL_DIR} to PATH in ~/.bashrc"
      fi
    fi
    info "For this shell, run:  export PATH=\"${INSTALL_DIR}:\$PATH\"   (new shells pick it up automatically)"
    ;;
esac

"$TARGET" version | head -n1
