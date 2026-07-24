#!/usr/bin/env bash
# Codex permission defaults shared by local startup and tests.

_codex_ensure_env_default() {
    local env_file="$1"
    local name="$2"
    local value="$3"
    if ! grep -q "^${name}=" "$env_file"; then
        printf '%s=%s\n' "$name" "$value" >> "$env_file"
    fi
}

ensure_codex_env_defaults() {
    local env_file="$1"
    local needs_defaults="false"
    local name
    for name in \
        VO_CODEX_SANDBOX \
        VO_CODEX_APPROVAL_POLICY \
        VO_CODEX_ROUTE_APPROVALS_THROUGH_VO
    do
        if ! grep -q "^${name}=" "$env_file"; then
            needs_defaults="true"
            break
        fi
    done
    if [ "$needs_defaults" = "true" ] && ! grep -q '^# Codex local permission defaults' "$env_file"; then
        printf '\n%s\n' '# Codex local permission defaults (trusted machine only)' >> "$env_file"
    fi
    _codex_ensure_env_default "$env_file" "VO_CODEX_SANDBOX" "danger-full-access"
    _codex_ensure_env_default "$env_file" "VO_CODEX_APPROVAL_POLICY" "never"
    _codex_ensure_env_default "$env_file" "VO_CODEX_ROUTE_APPROVALS_THROUGH_VO" "false"
}

apply_codex_runtime_defaults() {
    export VO_CODEX_SANDBOX="${VO_CODEX_SANDBOX:-danger-full-access}"
    export VO_CODEX_APPROVAL_POLICY="${VO_CODEX_APPROVAL_POLICY:-never}"
    export VO_CODEX_ROUTE_APPROVALS_THROUGH_VO="${VO_CODEX_ROUTE_APPROVALS_THROUGH_VO:-false}"
}
