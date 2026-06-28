#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${ROOT_DIR}/.lan-logs"
PID_DIR="${LOG_DIR}/pids"
LAN_INTERFACE="${LAN_INTERFACE:-en0}"
ACTION="${1:-start}"

mkdir -p "${PID_DIR}"

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
export PORTAL_PUBLIC_BASE_URL="http://${LAN_IP}:8005"
export PORTAL_BASE_URL="${PORTAL_PUBLIC_BASE_URL}"
export USER_ADMIN_PUBLIC_BASE_URL="http://${LAN_IP}:8006"
export USER_ADMIN_BASE_URL="${USER_ADMIN_PUBLIC_BASE_URL}"
export USER_ADMIN_INTERNAL_BASE_URL="http://127.0.0.1:8006"
export TIMESHEET_PUBLIC_BASE_URL="http://${LAN_IP}:8002"
export EXPENSE_PUBLIC_BASE_URL="http://${LAN_IP}:8003"
export EMPLOYEEADMIN_PUBLIC_BASE_URL="http://${LAN_IP}:8004"
export MASTERDATA_PUBLIC_BASE_URL="http://${LAN_IP}:8007"
export MASTERDATA_INTERNAL_BASE_URL="http://127.0.0.1:8007"
export PAYROLL_PUBLIC_BASE_URL="http://${LAN_IP}:8001"
export TAC_PAYROLL_PUBLIC_BASE_URL="http://${LAN_IP}:8015"
export SALARY_PUBLIC_BASE_URL="${TAC_PAYROLL_PUBLIC_BASE_URL}"
export TACAIPAYJP_PUBLIC_BASE_URL="http://${LAN_IP}:8017"
export TACAIPAYJP_BASE_URL="${TACAIPAYJP_PUBLIC_BASE_URL}"
export TACAIPAYSG_PUBLIC_BASE_URL="http://${LAN_IP}:8016"
export TACAIPAYSG_BASE_URL="${TACAIPAYSG_PUBLIC_BASE_URL}"
export INTERVIEW_READY_PUBLIC_BASE_URL="http://${LAN_IP}:8000"
export VENDOR_PAYABLES_PUBLIC_BASE_URL="http://${LAN_IP}:8008"
export CUSTOMER_BILLING_PUBLIC_BASE_URL="http://${LAN_IP}:8009"
export FILEADMIN_PUBLIC_BASE_URL="http://${LAN_IP}:8011"
export TACAIMSG_PUBLIC_BASE_URL="http://${LAN_IP}:8012"
export SELFSERVICE_PUBLIC_BASE_URL="http://${LAN_IP}:8018"
export TACAI_ALLOWED_PUBLIC_HOSTS="${LAN_IP},127.0.0.1,localhost${TACAI_ALLOWED_PUBLIC_HOSTS:+,${TACAI_ALLOWED_PUBLIC_HOSTS}}"
export PYTHONUNBUFFERED="1"
export TACAI_GATEWAY_PORT="${TACAI_GATEWAY_PORT:-8010}"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-${HOME}/.local/bin/cloudflared}"

SERVICES=(
  "user_admin|8006|TACAI-Core/User_admin|python3 backend/app.py --host 0.0.0.0 --port 8006"
  "portal|8005|TACAI-Core/tacai-portal|python3 backend/app.py --host 0.0.0.0 --port 8005"
  "interview_ready|8000|InterviewReady|python3 -m app.cli web --host 0.0.0.0 --port 8000"
  "payroll|8001|backup/TACAI-PRJ|python3 backend/app.py --host 0.0.0.0 --port 8001"
  "timesheet|8002|TAC-timesheet|python3 backend/app.py --host 0.0.0.0 --port 8002"
  "expense|8003|TAC-reimbursement|python3 backend/app.py --host 0.0.0.0 --port 8003"
  "employee_admin|8004|TAC-employeeadmin|python3 backend/app.py --host 0.0.0.0 --port 8004"
  "masterdata|8007|TACAI-Core/masterdata|python3 backend/app.py --host 0.0.0.0 --port 8007"
  "vendor_payables|8008|VendorPayables|python3 backend/app.py --host 0.0.0.0 --port 8008"
  "customer_billing|8009|customerbilling|python3 backend/app.py --host 0.0.0.0 --port 8009"
  "fileadmin|8011|fileadmin|python3 backend/app.py --host 0.0.0.0 --port 8011"
  "tacaimsg|8012|TACAI-Core/tacaimsg|python3 backend/app.py --host 0.0.0.0 --port 8012"
  "tac_payroll|8015|TAC-salary|python3 backend/app.py --host 0.0.0.0 --port 8015"
  "tacaipay_sg|8016|TACAIPAY/tacaipaysg|python3 backend/app.py --host 0.0.0.0 --port 8016"
  "tacaipay_jp|8017|TACAIPAY/tacaipayjp|python3 backend/app.py --host 0.0.0.0 --port 8017"
  "selfservice|8018|TacSelfService/TacSelfVacation|python3 backend/app.py --host 0.0.0.0 --port 8018"
)

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
  for service in "${SERVICES[@]}"; do
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
  echo ""
  echo "=== Access URLs ==="
  echo "Local Portal:     http://127.0.0.1:8005"
  echo "Wi-Fi Portal:     http://${LAN_IP}:8005"
  echo "Wi-Fi Gateway:    http://${LAN_IP}:${TACAI_GATEWAY_PORT}/portal"
  if [[ -f "${LOG_DIR}/cloudflared.log" ]]; then
    local remote_url=""
    remote_url="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "${LOG_DIR}/cloudflared.log" 2>/dev/null | head -1 || true)"
    if [[ -n "${remote_url}" ]]; then
      echo "Remote Portal:    ${remote_url}/portal"
    fi
  fi
  echo ""
  echo "Portal modules (8000-8017):"
  echo "  8000 InterviewReady   8001 Payroll Legacy   8002 Timesheet"
  echo "  8003 Expense          8004 EmployeeAdmin    8005 Portal"
  echo "  8006 User_admin       8007 MasterData       8008 VendorPayables"
  echo "  8009 CustomerBilling  8010 Remote Gateway   8011 FileAdmin"
  echo "  8012 TACAI Msg Center 8015 TAC Payroll v2   8016 TACAI Pay SG     8017 TACAI Pay JP"
  echo "  8018 Self-Service"
  echo ""
  echo "Use one host consistently per browser session (127.0.0.1 OR ${LAN_IP}, not both)."
}

case "${ACTION}" in
  start)
    echo "Starting TACAI LAN test services"
    echo "LAN IP: ${LAN_IP}"
    echo "Logs: ${LOG_DIR}"
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
    print_access_summary
    echo "If macOS asks whether Python can accept incoming network connections, allow it for this local Wi-Fi test."
    ;;
  start-remote)
    bash "${BASH_SOURCE[0]}" start
    start_gateway
    sleep 1
    start_remote_tunnel
    print_access_summary
    ;;
  stop)
    stop_remote_tunnel
    stop_gateway
    for service in "${SERVICES[@]}"; do
      IFS='|' read -r name port relative_dir command <<< "${service}"
      stop_service "${name}" "${port}"
    done
    ;;
  restart)
    bash "${BASH_SOURCE[0]}" stop
    bash "${BASH_SOURCE[0]}" start
    ;;
  restart-remote)
    bash "${BASH_SOURCE[0]}" stop
    bash "${BASH_SOURCE[0]}" start-remote
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
    do script "cd '${ROOT_DIR}' && unset TACAI_PUBLIC_HOST && bash start_tacai_lan.sh start-remote; echo 'TACAI stack running. Keep this Terminal window open.'"
    activate
end tell
APPLESCRIPT
    echo "Opened Terminal to start TACAI services in a persistent session."
    ;;
  *)
    echo "Usage: $0 [start|start-remote|stop|restart|restart-remote|status|install-tools|desktop]" >&2
    exit 2
    ;;
esac
