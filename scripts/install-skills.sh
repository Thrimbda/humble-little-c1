#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/install-skills.sh [--quiet]

Install every skill in this repository to user-level agent directories.
Targets all agents that support global skills. By default, the skills.sh CLI
lets you choose the installation method and confirm before installing.

  -q, --quiet, --silent  Install to all supported global agents without prompts.
                        Print nothing on success; report errors on stderr.
  -y, --yes             Alias for --quiet.
  -h, --help            Show this help.

Requires Node.js >= 22.20.0 and npm (npx).
EOF
}

quiet=false
for argument in "$@"; do
  case "$argument" in
    -q|--quiet|--silent|-y|--yes) quiet=true ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$argument" >&2; usage >&2; exit 2 ;;
  esac
done

if ! command -v npx >/dev/null 2>&1; then
  printf 'npx is required. Install Node.js >= 22.20.0 and npm first.\n' >&2
  exit 127
fi

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
skills_cli=skills@1.5.23

# Global-capable agent IDs from the skills@1.5.23 README. Update this list when
# changing skills_cli. The CLI owns directory mappings, copying, and symlinks.
# Upstream --all / auto-detection can include agents that reject --global.
global_agents=(
  aider-desk amp replit universal antigravity antigravity-cli
  astrbot autohand-code augment bob claude-code openclaw
  cline dexto kimi-code-cli loaf warp zed
  codearts-agent codebuddy codemaker codestudio codex command-code
  continue cortex crush cursor deepagents devin
  droid firebender forgecode gemini-cli github-copilot goose
  grok hermes-agent inference-sh jazz junie iflow-cli
  kilo kimchi kiro-cli kode lingma mcpjam
  minimax-code mistral-vibe moxby mux opencode openhands
  ona pi posit-assistant qoder qoder-cn qwen-code
  reasonix rovodev roo tabnine-cli terramind tinycloud
  trae trae-cn windsurf zcode zencoder zenflow
  neovate pochi adal
)

install_command=(npx --yes "$skills_cli" add "$repo_root" --global --skill '*'
  --agent "${global_agents[@]}")

if [[ "$quiet" == false ]]; then
  if [[ ! -t 0 || ! -t 1 ]]; then
    printf 'Interactive installation needs a terminal. Use --quiet for unattended installation.\n' >&2
    exit 2
  fi
  exec "${install_command[@]}"
fi

install_log=$(mktemp)
trap 'rm -f "$install_log"' EXIT

install_status=0
NO_COLOR=1 "${install_command[@]}" --yes >"$install_log" 2>&1 || install_status=$?

# This CLI version can report per-agent failures while still exiting with 0.
if grep -Eq 'Failed to install [0-9]+' "$install_log"; then
  install_status=1
fi

if [[ "$install_status" -ne 0 ]]; then
  cat "$install_log" >&2
fi
exit "$install_status"
