#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${ROOT_DIR}/.lan-logs"
PID_DIR="${LOG_DIR}/pids"
LAN_INTERFACE="${LAN_INTERFACE:-en0}"
ACTION="${1:-start}"
ENV_NAME="${2:-}"
# Valid environments
VALID_ENVS=("dev" "stg" "prd")

mkdir -p "${PID_DIR}"

# ── Load environment-specific .env file ─────────────────────
load_env() {
  local env="$1"
  local env_file="${ROOT_DIR}/.env.${env}"
  if [[ ! -f "${env_file}" ]]; then
    echo "ERROR: Environment file not found: ${env_file}" >&2
    exit 1
  fi
  # Unset previous env vars to avoid cross-contamination
  unset NODE_ENV PORT AUTH_PORT DB_HOST DB_PORT DB_NAME DB_USER DB_PASS PORTAL_BASE_URL PORTAL_PUBLIC_BASE_URL USER_ADMIN_PUBLIC_BASE_URL USER_ADMIN_BASE_URL USER_ADMIN_INTERNAL_BASE_URL
  set -a
  source "${env_file}"
  set +a
  export TACAI_DB_ENABLED="${TACAI_DB_ENABLED:-true}"
  # Export env-specific URL variables using PORT and AUTH_PORT
  export PORTAL_PUBLIC_BASE_URL="http://${LAN_IP}:${PORT}"
  export PORTAL_BASE_URL="${PORTAL_PUBLIC_BASE_URL}"
  export USER_ADMIN_PUBLIC_BASE_URL="http://${LAN_IP}:${AUTH_PORT}"
  export USER_ADMIN_BASE_URL="${USER_ADMIN_PUBLIC_BASE_URL}"
  export USER_ADMIN_INTERNAL_BASE_URL="http://127.0.0.1:${AUTH_PORT}"
}

# Load default env (dev) for shared vars if no specific env needed
if [[ -f "${ROOT_DIR}/.env.dev" ]]; then
  set -a
  source "${ROOT_DIR}/.env.dev"
  set +a
fi
export TACAI_DB_ENABLED="${TACAI_DB_ENABLED:-true}"
# ────────────────────────────────────────────────────────────

find_lan_ip() {
  local ip=""
  ip="$(ipconfig getifaddr "${LAN_INTERFACE}" 2>/dev/null || true)"
  if [[ -z "${ip}" ]]; then
    local wifi_device=""
    wifi_device="$(networksetup -listallhardwareports 2>/dev/null | awk '/Hardware Port: Wi-Fi/{getline; print $2; exit}' || true)"
    if [[ -n "${wifi_device}" ]]; then
      ip="$(ipconfig getifaddr "${wifi_device}" 2>/dev/null || true)"
    fi
  fi
  if [[ -z "${ip}" ]]; then
    echo "ERROR: Could not detect Wi-Fi LAN IP. Set LAN_INTERFACE=en0 or connect to Wi-Fi." >&2
    exit 1
  fi
  echo "${ip}"
}

LAN_IP="$(find_lan_ip)"
if [[ -n "${TACAI_PUBLIC_HOST:-}" && "${TACAI_PUBLIC_HOST}" != "127.0.0.1" && "${TACAI_PUBLIC_HOST}" != "localhost" ]]; then
  LAN_IP="${TACAI_PUBLIC_HOST}"
fi

export TACAI_PUBLIC_HOST="${LAN_IP}"
export TACAI_INTERNAL_HOST="127.0.0.1"
# ── Shared service URLs (non-env-specific, ports 8000-8018) ──
export TIMESHEET_PUBLIC_BASE_URL="http://${LAN_IP}:8002"
export EXPENSE_PUBLIC_BASE_URL="http://${LAN_IP}:8003"
export EMPLOYEEADMIN_PUBLIC_BASE_URL="http://${LAN_IP}:8004"
export MASTERDATA_PUBLIC_BASE_URL="http://${LAN_IP}:8007"
export MASTERDATA_INTERNAL_BASE_URL="http://127.0.0.1:8007"
export PAYROLL_PUBLIC_BASE_URL="http://${LAN_IP}:8001"

export TACAIPAYSG_PUBLIC_BASE_URL="http://${LAN_IP}:8016"
export TACAIPAYSG_BASE_URL="${TACAIPAYSG_PUBLIC_BASE_URL}"
export INTERVIEW_READY_PUBLIC_BASE_URL="http://${LAN_IP}:8000"
export TACAIMSG_PUBLIC_BASE_URL="http://${LAN_IP}:8012"
export SELFSERVICE_PUBLIC_BASE_URL="http://${LAN_IP}:8018"
# ── Env-specific URL exports (Portal + User_admin) set by load_env() ──
# PORTAL_PUBLIC_BASE_URL, USER_ADMIN_PUBLIC_BASE_URL, USER_ADMIN_INTERNAL_BASE_URL
export TACAI_ALLOWED_PUBLIC_HOSTS="${LAN_IP},127.0.0.1,localhost${TACAI_ALLOWED_PUBLIC_HOSTS:+,${TACAI_ALLOWED_PUBLIC_HOSTS}}"
export PYTHONUNBUFFERED="1"
export TACAI_GATEWAY_PORT="${TACAI_GATEWAY_PORT:-8010}"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-${HOME}/.local/bin/cloudflared}"

# ── Shared services (same ports across all envs) ─────────────
SHARED_SERVICES=(
  "interview_ready|8000|InterviewReady|python3 -m app.cli web --host 0.0.0.0 --port 8000"
  "payroll|8001|backup/TACAI-PRJ|python3 backend/app.py --host 0.0.0.0 --port 8001"
  "timesheet|8002|TAC-timesheet|python3 backend/app.py --host 0.0.0.0 --port 8002"
  "expense|8003|TAC-reimbursement|python3 backend/app.py --host 0.0.0.0 --port 8003"
  "employee_admin|8004|TAC-employeeadmin|python3 backend/app.py --host 0.0.0.0 --port 8004"
  "masterdata|8007|TACAI-Core/masterdata|python3 backend/app.py --host 0.0.0.0 --port 8007"
  "tacaimsg|8012|TACAI-Core/tacaimsg|python3 backend/app.py --host 0.0.0.0 --port 8012"
  "tacaipay_sg|8016|TACAIPAY/tacaipaysg|python3 backend/app.py --host 0.0.0.0 --port 8016"
  "selfservice|8018|TacSelfService/TacSelfVacation|python3 backend/app.py --host 0.0.0.0 --port 8018"
)

# Build SERVICES array for a specific environment
build_services() {
  local env="$1"
  local portal_port="$2"
  local auth_port="$3"
  SERVICES=(
    "user_admin_${env}|${auth_port}|TACAI-Core/User_admin|python3 backend/app.py --host 0.0.0.0 --port ${auth_port}"
    "portal_${env}|${portal_port}|TACAI-Core/tacai-portal|python3 backend/app.py --host 0.0.0.0 --port ${portal_port}"
    "${SHARED_SERVICES[@]}"
  )
}

# Default SERVICES (dev)
build_services "dev" "${PORT:-3000}" "${AUTH_PORT:-3001}"

upper() {
  echo "$1" | tr '[:lower:]' '[:upper:]'
}

is_pid_running() {
  local pid="$1"
  [[ -n "${pid}" ]] && ps -p "${pid}" >/dev/null 2>&1
}

is_port_listening() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

print_listener() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1 " pid=" $2 " " $9}' || true
}

listener_pid() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $2}' || true
}

stop_service() {
  local name="$1"
  local port="$2"
  local pid_file="${PID_DIR}/${name}.pid"
  local pid=""
  if [[ -f "${pid_file}" ]]; then
    pid="$(tr -d '[:space:]' < "${pid_file}")"
  else
    pid="$(listener_pid "${port}")"
  fi
  if [[ -z "${pid}" ]]; then
    echo "SKIP ${name}: no PID file and no listener on port ${port}"
    return 0
  fi
  if is_pid_running "${pid}"; then
    echo "Stopping ${name} pid=${pid}"
    kill "${pid}" 2>/dev/null || true
    sleep 1
    if is_pid_running "${pid}"; then
      echo "Force stopping ${name} pid=${pid}"
      kill -9 "${pid}" 2>/dev/null || true
    fi
  else
    echo "SKIP ${name}: pid ${pid:-unknown} is not running"
  fi
  if is_port_listening "${port}"; then
    local listening_pid=""
    listening_pid="$(listener_pid "${port}")"
    if [[ -n "${listening_pid}" && "${listening_pid}" != "${pid}" ]]; then
      echo "Stopping ${name} listener pid=${listening_pid} on port ${port}"
      kill "${listening_pid}" 2>/dev/null || true
      sleep 1
      if is_pid_running "${listening_pid}"; then
        echo "Force stopping ${name} listener pid=${listening_pid}"
        kill -9 "${listening_pid}" 2>/dev/null || true
      fi
    fi
  fi
  rm -f "${pid_file}"
}

start_service() {
  local name="$1"
  local port="$2"
  local relative_dir="$3"
  local command="$4"
  local dir="${ROOT_DIR}/${relative_dir}"
  local log_file="${LOG_DIR}/${name}.log"
  local pid_file="${PID_DIR}/${name}.pid"

  if [[ ! -d "${dir}" ]]; then
    echo "SKIP ${name}: missing directory ${relative_dir}"
    return 0
  fi
  if [[ -f "${pid_file}" ]]; then
    local existing_pid=""
    existing_pid="$(tr -d '[:space:]' < "${pid_file}")"
    if is_pid_running "${existing_pid}"; then
      echo "SKIP ${name}: already started by this script pid=${existing_pid}"
      return 0
    fi
    rm -f "${pid_file}"
  fi
  if is_port_listening "${port}"; then
    echo "SKIP ${name}: port ${port} is already listening ($(print_listener "${port}"))"
    echo "      Stop the existing service first if it is bound only to 127.0.0.1."
    return 0
  fi

  echo "Starting ${name} on 0.0.0.0:${port}"
  nohup bash -lc "cd '${dir}' && exec ${command}" >> "${log_file}" 2>&1 &
  local background_pid="$!"
  disown "${background_pid}" 2>/dev/null || true
  sleep 0.5
  local pid=""
  pid="$(listener_pid "${port}")"
  if [[ -z "${pid}" ]]; then
    pid="${background_pid}"
  fi
  echo "${pid}" > "${pid_file}"
  echo "  pid=${pid} log=${log_file}"
}

health_check() {
  local name="$1"
  local port="$2"
  local url="http://${LAN_IP}:${port}/health"
  if curl -fsS --max-time 2 "${url}" >/dev/null 2>&1; then
    echo "OK   ${name}: ${url}"
  else
    echo "WARN ${name}: ${url} did not return HTTP 2xx yet"
  fi
}

status_services() {
  echo "LAN IP: ${LAN_IP}"
  echo ""
  # Check all three environments' Portal + User_admin
  for env in dev stg prd; do
    local env_file="${ROOT_DIR}/.env.${env}"
    if [[ -f "${env_file}" ]]; then
      local p="" a=""
      p="$(grep -E '^PORT=' "${env_file}" | head -1 | cut -d= -f2)"
      a="$(grep -E '^AUTH_PORT=' "${env_file}" | head -1 | cut -d= -f2)"
      echo "--- [$(upper "${env}")] ---"
      if is_port_listening "${p}"; then
        echo "LISTEN portal_${env} ${p}: $(print_listener "${p}")"
      else
        echo "DOWN   portal_${env} ${p}"
      fi
      if is_port_listening "${a}"; then
        echo "LISTEN user_admin_${env} ${a}: $(print_listener "${a}")"
      else
        echo "DOWN   user_admin_${env} ${a}"
      fi
    fi
  done
  echo ""
  echo "--- [Shared Services] ---"
  for service in "${SHARED_SERVICES[@]}"; do
    IFS='|' read -r name port relative_dir command <<< "${service}"
    if is_port_listening "${port}"; then
      echo "LISTEN ${name} ${port}: $(print_listener "${port}")"
    else
      echo "DOWN   ${name} ${port}"
    fi
  done
  if is_port_listening "${TACAI_GATEWAY_PORT}"; then
    echo "LISTEN gateway ${TACAI_GATEWAY_PORT}: $(print_listener "${TACAI_GATEWAY_PORT}")"
  else
    echo "DOWN   gateway ${TACAI_GATEWAY_PORT}"
  fi
}

install_tools() {
  mkdir -p "${HOME}/.local/bin"
  if [[ ! -x "${CLOUDFLARED_BIN}" ]]; then
    local arch=""
    arch="$(uname -m)"
    local asset="cloudflared-darwin-amd64.tgz"
    if [[ "${arch}" == "arm64" ]]; then
      asset="cloudflared-darwin-arm64.tgz"
    fi
    echo "Installing cloudflared (${asset}) to ${CLOUDFLARED_BIN}"
    curl -fsSL --http1.1 -o /tmp/cloudflared.tgz "https://github.com/cloudflare/cloudflared/releases/latest/download/${asset}"
    tar -xzf /tmp/cloudflared.tgz -C "${HOME}/.local/bin" cloudflared
    chmod +x "${CLOUDFLARED_BIN}"
  else
    echo "cloudflared already installed: ${CLOUDFLARED_BIN}"
  fi
  "${CLOUDFLARED_BIN}" version
}

start_gateway() {
  local log_file="${LOG_DIR}/gateway.log"
  local pid_file="${PID_DIR}/gateway.pid"
  if is_port_listening "${TACAI_GATEWAY_PORT}"; then
    echo "SKIP gateway: port ${TACAI_GATEWAY_PORT} already listening ($(print_listener "${TACAI_GATEWAY_PORT}"))"
    return 0
  fi
  echo "Starting gateway on 0.0.0.0:${TACAI_GATEWAY_PORT}"
  nohup bash -lc "cd '${ROOT_DIR}' && TACAI_PUBLIC_HOST='${LAN_IP}' exec python3 deployment/remote-access/tacai_temp_gateway.py --host 0.0.0.0 --port '${TACAI_GATEWAY_PORT}'" >> "${log_file}" 2>&1 &
  disown $! 2>/dev/null || true
  sleep 0.5
  local pid=""
  pid="$(listener_pid "${TACAI_GATEWAY_PORT}")"
  [[ -n "${pid}" ]] && echo "${pid}" > "${pid_file}"
  echo "  pid=${pid:-unknown} log=${log_file}"
}

stop_gateway() {
  stop_service "gateway" "${TACAI_GATEWAY_PORT}"
}

start_remote_tunnel() {
  install_tools
  local log_file="${LOG_DIR}/cloudflared.log"
  local pid_file="${PID_DIR}/cloudflared.pid"
  if [[ -f "${pid_file}" ]]; then
    local existing_pid=""
    existing_pid="$(tr -d '[:space:]' < "${pid_file}")"
    if is_pid_running "${existing_pid}"; then
      echo "SKIP cloudflared: already running pid=${existing_pid}"
      grep -E 'https://[a-z0-9-]+\.trycloudflare\.com' "${log_file}" 2>/dev/null | tail -1 || true
      return 0
    fi
    rm -f "${pid_file}"
  fi
  echo "Starting Cloudflare Quick Tunnel -> http://127.0.0.1:${TACAI_GATEWAY_PORT}"
  rm -f "${log_file}"
  nohup "${CLOUDFLARED_BIN}" tunnel --url "http://127.0.0.1:${TACAI_GATEWAY_PORT}" --protocol http2 >> "${log_file}" 2>&1 &
  local pid="$!"
  disown "${pid}" 2>/dev/null || true
  echo "${pid}" > "${pid_file}"
  local url=""
  for _ in $(seq 1 30); do
    url="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "${log_file}" 2>/dev/null | head -1 || true)"
    if [[ -n "${url}" ]]; then
      break
    fi
    sleep 1
  done
  echo "  pid=${pid} log=${log_file}"
  if [[ -n "${url}" ]]; then
    echo "  Remote URL: ${url}/portal"
  else
    echo "  Remote URL: still starting; check ${log_file}"
  fi
}

stop_remote_tunnel() {
  local pid_file="${PID_DIR}/cloudflared.pid"
  if [[ -f "${pid_file}" ]]; then
    local pid=""
    pid="$(tr -d '[:space:]' < "${pid_file}")"
    if is_pid_running "${pid}"; then
      echo "Stopping cloudflared pid=${pid}"
      kill "${pid}" 2>/dev/null || true
    fi
    rm -f "${pid_file}"
  fi
}

print_access_summary() {
  local env_label="${1:-dev}"
  local portal_port="${2:-3000}"
  local auth_port="${3:-3001}"
  echo ""
  echo "=== Access URLs [$(upper "${env_label}")] ==="
  echo "Local Portal:     http://127.0.0.1:${portal_port}"
  echo "Wi-Fi Portal:     http://${LAN_IP}:${portal_port}"
  echo "Local Auth:       http://127.0.0.1:${auth_port}"
  echo "Wi-Fi Gateway:    http://${LAN_IP}:${TACAI_GATEWAY_PORT}/portal"
  if [[ -f "${LOG_DIR}/cloudflared.log" ]]; then
    local remote_url=""
    remote_url="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "${LOG_DIR}/cloudflared.log" 2>/dev/null | head -1 || true)"
    if [[ -n "${remote_url}" ]]; then
      echo "Remote Portal:    ${remote_url}/portal"
    fi
  fi
  echo ""
  echo "Portal modules:"
  echo "  8000 InterviewReady   8001 Payroll Legacy   8002 Timesheet"
  echo "  8003 Expense          8004 EmployeeAdmin    ${portal_port} Portal ($(upper "${env_label}"))"
  echo "  ${auth_port} User_admin ($(upper "${env_label}"))   8007 MasterData"
  echo "  8012 TACAI Msg Center 8016 TACAI Pay SG     8018 Self-Service"
  echo ""
  echo "Use one host consistently per browser session (127.0.0.1 OR ${LAN_IP}, not both)."
}

print_all_env_summary() {
  echo ""
  echo "=== All Environments Access URLs ==="
  for env in dev stg prd; do
    local env_file="${ROOT_DIR}/.env.${env}"
    if [[ -f "${env_file}" ]]; then
      local p="" a=""
      p="$(grep -E '^PORT=' "${env_file}" | head -1 | cut -d= -f2)"
      a="$(grep -E '^AUTH_PORT=' "${env_file}" | head -1 | cut -d= -f2)"
      echo "  [$(upper "${env}")] Portal: http://${LAN_IP}:${p:-?}  |  Auth: http://${LAN_IP}:${a:-?}  |  DB: $(grep -E '^DB_NAME=' "${env_file}" | head -1 | cut -d= -f2)"
    fi
  done
  echo ""
}

# ── Start one environment ────────────────────────────────────
start_env() {
  local env="$1"
  local env_file="${ROOT_DIR}/.env.${env}"

  if [[ ! -f "${env_file}" ]]; then
    echo "ERROR: Environment file not found: ${env_file}" >&2
    return 1
  fi

  # Read PORT and AUTH_PORT from env file
  local portal_port auth_port
  portal_port="$(grep -E '^PORT=' "${env_file}" | head -1 | cut -d= -f2)"
  auth_port="$(grep -E '^AUTH_PORT=' "${env_file}" | head -1 | cut -d= -f2)"

  if [[ -z "${portal_port}" || -z "${auth_port}" ]]; then
    echo "ERROR: PORT or AUTH_PORT missing in ${env_file}" >&2
    return 1
  fi

  load_env "${env}"
  export TACAI_ALLOWED_PUBLIC_HOSTS="${LAN_IP},127.0.0.1,localhost${TACAI_ALLOWED_PUBLIC_HOSTS:+,${TACAI_ALLOWED_PUBLIC_HOSTS}}"

  build_services "${env}" "${portal_port}" "${auth_port}"

  echo ""
  echo "=== Starting TACAI [$(upper "${env}")] environment ==="
  echo "LAN IP: ${LAN_IP}"
  echo "Portal: ${portal_port}  |  Auth: ${auth_port}  |  DB: ${DB_NAME}"
  echo "Logs: ${LOG_DIR}"
  echo ""

  for service in "${SERVICES[@]}"; do
    IFS='|' read -r name port relative_dir command <<< "${service}"
    start_service "${name}" "${port}" "${relative_dir}" "${command}"
  done
  sleep 2
  echo ""
  echo "Health checks through LAN IP:"
  for service in "${SERVICES[@]}"; do
    IFS='|' read -r name port relative_dir command <<< "${service}"
    [[ -d "${ROOT_DIR}/${relative_dir}" ]] && health_check "${name}" "${port}"
  done
  print_access_summary "${env}" "${portal_port}" "${auth_port}"
}

# ── Stop one environment (Portal + User_admin only) ─────────
stop_env() {
  local env="$1"
  local env_file="${ROOT_DIR}/.env.${env}"

  if [[ ! -f "${env_file}" ]]; then
    echo "SKIP ${env}: .env.${env} not found"
    return 0
  fi

  local portal_port auth_port
  portal_port="$(grep -E '^PORT=' "${env_file}" | head -1 | cut -d= -f2)"
  auth_port="$(grep -E '^AUTH_PORT=' "${env_file}" | head -1 | cut -d= -f2)"

  echo "--- Stopping [$(upper "${env}")] environment ---"
  stop_service "portal_${env}" "${portal_port}"
  stop_service "user_admin_${env}" "${auth_port}"
}

# ── Stop all shared services ─────────────────────────────────
stop_shared() {
  echo "--- Stopping shared services ---"
  for service in "${SHARED_SERVICES[@]}"; do
    IFS='|' read -r name port relative_dir command <<< "${service}"
    stop_service "${name}" "${port}"
  done
}

case "${ACTION}" in
  start)
    if [[ -z "${ENV_NAME}" ]]; then
      echo "Usage: $0 start <dev|stg|prd|all>" >&2
      echo "  dev  - Start DEV  environment (Portal:3000, Auth:3001, DB:tacai_dev)" >&2
      echo "  stg  - Start STG  environment (Portal:4000, Auth:4001, DB:tacai_stg)" >&2
      echo "  prd  - Start PRD  environment (Portal:6000, Auth:6001, DB:tacai_prd)" >&2
      echo "  all  - Start ALL three environments simultaneously" >&2
      exit 2
    fi

    if [[ "${ENV_NAME}" == "all" ]]; then
      for env in dev stg prd; do
        start_env "${env}"
      done
      print_all_env_summary
    elif [[ " ${VALID_ENVS[*]} " == *" ${ENV_NAME} "* ]]; then
      start_env "${ENV_NAME}"
    else
      echo "ERROR: Unknown environment '${ENV_NAME}'. Valid: dev, stg, prd, all" >&2
      exit 2
    fi
    echo "If macOS asks whether Python can accept incoming network connections, allow it for this local Wi-Fi test."
    ;;
  start-remote)
    if [[ -z "${ENV_NAME}" ]]; then
      ENV_NAME="dev"
    fi
    if [[ "${ENV_NAME}" == "all" ]]; then
      for env in dev stg prd; do
        start_env "${env}"
      done
    else
      start_env "${ENV_NAME}"
    fi
    start_gateway
    sleep 1
    start_remote_tunnel
    if [[ "${ENV_NAME}" == "all" ]]; then
      print_all_env_summary
    fi
    ;;
  stop)
    if [[ -z "${ENV_NAME}" ]]; then
      echo "Usage: $0 stop <dev|stg|prd|all>" >&2
      echo "  all  - Stop ALL environments and shared services" >&2
      exit 2
    fi

    stop_remote_tunnel
    stop_gateway

    if [[ "${ENV_NAME}" == "all" ]]; then
      for env in dev stg prd; do
        stop_env "${env}"
      done
      stop_shared
    elif [[ " ${VALID_ENVS[*]} " == *" ${ENV_NAME} "* ]]; then
      stop_env "${ENV_NAME}"
      stop_shared
    else
      echo "ERROR: Unknown environment '${ENV_NAME}'. Valid: dev, stg, prd, all" >&2
      exit 2
    fi
    ;;
  restart)
    if [[ -z "${ENV_NAME}" ]]; then
      echo "Usage: $0 restart <dev|stg|prd|all>" >&2
      exit 2
    fi
    bash "${BASH_SOURCE[0]}" stop "${ENV_NAME}"
    bash "${BASH_SOURCE[0]}" start "${ENV_NAME}"
    ;;
  restart-remote)
    if [[ -z "${ENV_NAME}" ]]; then
      ENV_NAME="dev"
    fi
    bash "${BASH_SOURCE[0]}" stop "${ENV_NAME}"
    bash "${BASH_SOURCE[0]}" start-remote "${ENV_NAME}"
    ;;
  status)
    status_services
    ;;
  install-tools)
    install_tools
    ;;
  desktop)
    osascript <<APPLESCRIPT
tell application "Terminal"
    do script "cd '${ROOT_DIR}' && unset TACAI_PUBLIC_HOST && bash start_tacai_lan.sh start-remote dev; echo 'TACAI stack running. Keep this Terminal window open.'"
    activate
end tell
APPLESCRIPT
    echo "Opened Terminal to start TACAI services in a persistent session."
    ;;
  *)
    echo "Usage: $0 <action> [env]" >&2
    echo "" >&2
    echo "Actions:" >&2
    echo "  start <dev|stg|prd|all>    Start services for environment(s)" >&2
    echo "  start-remote [dev|stg|prd|all]  Start + gateway + Cloudflare tunnel" >&2
    echo "  stop <dev|stg|prd|all>     Stop services for environment(s)" >&2
    echo "  restart <dev|stg|prd|all>  Restart services" >&2
    echo "  restart-remote [env]       Restart with remote tunnel" >&2
    echo "  status                     Show all services status" >&2
    echo "  install-tools              Install cloudflared" >&2
    echo "  desktop                    Open Terminal with remote tunnel" >&2
    echo "" >&2
    echo "Port mappings:" >&2
    echo "  DEV: Portal=3000, Auth=3001, DB=tacai_dev" >&2
    echo "  STG: Portal=4000, Auth=4001, DB=tacai_stg" >&2
    echo "  PRD: Portal=6000, Auth=6001, DB=tacai_prd" >&2
    exit 2
    ;;
esac
