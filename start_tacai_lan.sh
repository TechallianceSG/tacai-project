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

LAN_IP="${TACAI_PUBLIC_HOST:-$(find_lan_ip)}"

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
export INTERVIEW_READY_PUBLIC_BASE_URL="http://${LAN_IP}:8000"
export VENDOR_PAYABLES_PUBLIC_BASE_URL="http://${LAN_IP}:8008"
export CUSTOMER_BILLING_PUBLIC_BASE_URL="http://${LAN_IP}:8009"
export FILEADMIN_PUBLIC_BASE_URL="http://${LAN_IP}:8011"
export TACAI_ALLOWED_PUBLIC_HOSTS="${LAN_IP}${TACAI_ALLOWED_PUBLIC_HOSTS:+,${TACAI_ALLOWED_PUBLIC_HOSTS}}"
export PYTHONUNBUFFERED="1"

SERVICES=(
  "user_admin|8006|TACAI-Core/User_admin|python3 backend/app.py --host 0.0.0.0 --port 8006"
  "portal|8005|TACAI-Core/tacai-portal|python3 backend/app.py --host 0.0.0.0 --port 8005"
  "interview_ready|8000|InterviewReady|python3 -m app.cli web --host 0.0.0.0 --port 8000"
  "payroll|8001|TACAI-PRJ|python3 backend/app.py --host 0.0.0.0 --port 8001"
  "timesheet|8002|TAC-timesheet|python3 backend/app.py --host 0.0.0.0 --port 8002"
  "expense|8003|TAC-reimbursement|python3 backend/app.py --host 0.0.0.0 --port 8003"
  "employee_admin|8004|TAC-employeeadmin|python3 backend/app.py --host 0.0.0.0 --port 8004"
  "tac_payroll|8015|TAC-salary|python3 backend/app.py --host 0.0.0.0 --port 8015"
  "masterdata|8007|TACAI-Core/masterdata|python3 backend/app.py --host 0.0.0.0 --port 8007"
  "vendor_payables|8008|VendorPayables|python3 backend/app.py --host 0.0.0.0 --port 8008"
  "customer_billing|8009|customerbilling|python3 backend/app.py --host 0.0.0.0 --port 8009"
  "fileadmin|8011|fileadmin|python3 backend/app.py --host 0.0.0.0 --port 8011"
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
  (
    cd "${dir}"
    bash -lc "${command}"
  ) > "${log_file}" 2>&1 &
  local background_pid="$!"
  sleep 0.2
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
    echo ""
    echo "Portal:      http://${LAN_IP}:8005"
    echo "User_admin:  http://${LAN_IP}:8006"
    echo "TAC-payroll: http://${LAN_IP}:8015"
    echo ""
    echo "Open this from another computer on the same Wi-Fi:"
    echo "  http://${LAN_IP}:8005"
    echo ""
    echo "If macOS asks whether Python can accept incoming network connections, allow it for this local Wi-Fi test."
    ;;
  stop)
    for service in "${SERVICES[@]}"; do
      IFS='|' read -r name port relative_dir command <<< "${service}"
      stop_service "${name}" "${port}"
    done
    ;;
  restart)
    "${BASH_SOURCE[0]}" stop
    "${BASH_SOURCE[0]}" start
    ;;
  status)
    status_services
    ;;
  *)
    echo "Usage: $0 [start|stop|restart|status]" >&2
    exit 2
    ;;
esac
