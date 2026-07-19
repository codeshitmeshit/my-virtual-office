#!/usr/bin/env bash
# Human Resources environment defaults shared by startup and tests.

_hr_ensure_env_default() {
    local env_file="$1"
    local name="$2"
    local value="$3"
    if ! grep -q "^${name}=" "$env_file"; then
        printf '%s=%s\n' "$name" "$value" >> "$env_file"
    fi
}

ensure_hr_env_defaults() {
    local env_file="$1"
    local needs_defaults="false"
    local name
    for name in \
        VO_HR_ENABLED \
        VO_HR_SCHEDULER_ENABLED \
        VO_HR_TIMEZONE \
        VO_HR_DAILY_TIME \
        VO_HR_SUBMISSION_WINDOW_MINUTES \
        VO_HR_MAX_WORKERS \
        VO_HR_AGENT_TIMEOUT_SECONDS \
        VO_HR_RETRY_LIMIT
    do
        if ! grep -q "^${name}=" "$env_file"; then
            needs_defaults="true"
            break
        fi
    done
    if [ "$needs_defaults" = "true" ] && ! grep -q '^# Human Resources' "$env_file"; then
        printf '\n%s\n' '# Human Resources (safe rollout defaults)' >> "$env_file"
    fi
    _hr_ensure_env_default "$env_file" "VO_HR_ENABLED" "true"
    _hr_ensure_env_default "$env_file" "VO_HR_SCHEDULER_ENABLED" "false"
    _hr_ensure_env_default "$env_file" "VO_HR_TIMEZONE" ""
    _hr_ensure_env_default "$env_file" "VO_HR_DAILY_TIME" "18:00"
    _hr_ensure_env_default "$env_file" "VO_HR_SUBMISSION_WINDOW_MINUTES" "120"
    _hr_ensure_env_default "$env_file" "VO_HR_MAX_WORKERS" "2"
    _hr_ensure_env_default "$env_file" "VO_HR_AGENT_TIMEOUT_SECONDS" "30"
    _hr_ensure_env_default "$env_file" "VO_HR_RETRY_LIMIT" "3"
}
