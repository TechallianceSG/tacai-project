#!/usr/bin/env bash
# ============================================================
# TACAI Project: Rollback from PostgreSQL to JSON files
# ============================================================
# Usage: bash deployment/rollback_to_json.sh
#
# This script disables PostgreSQL and reverts all services to
# use their original JSON file storage.
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=============================================="
echo "TACAI: Rolling back to JSON file storage"
echo "=============================================="
echo ""

# 1. Stop all running services
echo "🛑 Stopping all services..."
bash "${ROOT_DIR}/start_tacai_lan.sh" stop 2>/dev/null || true
sleep 2

# 2. Kill any remaining Python processes on TACAI ports
echo "🧹 Cleaning up remaining processes..."
for port in 3000 3001 4000 4001 5000 5001 8000 8001 8002 8003 8004 8005 8006 8007 8010 8012 8016 8018; do
  pid=$(lsof -ti :$port 2>/dev/null || true)
  if [[ -n "$pid" ]]; then
    kill "$pid" 2>/dev/null || true
    echo "  Killed PID $pid on port $port"
  fi
done
sleep 1

# 3. Restore original app.py files from git
echo "📦 Restoring original app.py files..."
cd "${ROOT_DIR}"
for f in \
  TAC-timesheet/backend/app.py \
  TAC-employeeadmin/backend/app.py \
  TAC-reimbursement/backend/app.py \
  TACAI-Core/User_admin/backend/app.py \
  TACAI-Core/masterdata/backend/app.py \
  TACAI-Core/tacaimsg/backend/app.py \
  TacSelfService/TacSelfVacation/backend/app.py; do
  if [[ -f "$f" ]]; then
    git checkout -- "$f" 2>/dev/null && echo "  ✅ $f" || echo "  ⚠️  $f (not in git)"
  fi
done

# 4. Verify JSON files are intact
echo ""
echo "🔍 Verifying JSON database files..."
_json_count=0
for db_dir in \
  TAC-timesheet/database \
  TAC-employeeadmin/database \
  TAC-reimbursement/database \
  TACAIPAY/tacaipaysg/database \
  TACAI-Core/User_admin/database \
  TACAI-Core/masterdata/database \
  TACAI-Core/tacai-portal/database \
  TACAI-Core/tacaimsg/database \
  InterviewReady/database \
  TacSelfService/TacSelfVacation/database; do
  if [[ -d "${ROOT_DIR}/${db_dir}" ]]; then
    count=$(ls "${ROOT_DIR}/${db_dir}"/*.json 2>/dev/null | wc -l | tr -d ' ')
    _json_count=$((_json_count + count))
  fi
done
echo "  Found ${_json_count} JSON data files"

echo ""
echo "=============================================="
echo "✅ Rollback complete!"
echo ""
echo "To restart with JSON storage:"
echo "  TACAI_DB_ENABLED=false bash start_tacai_lan.sh start"
echo ""
echo "PostgreSQL data is still preserved in:"
echo "  - tacai_dev  (localhost:5432)"
echo "  - tacai_stg  (localhost:5432)"
echo "  - tacai_prd  (localhost:5432)"
echo "=============================================="
