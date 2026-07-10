#!/usr/bin/env bash
# =============================================================================
# Streaming feature distribution statistics aggregation runner
# =============================================================================
#
# Function: Calls parquet_feature_scan.py to compute feature distribution stats on parquet or csv data
#
# Usage examples:
#   ./run_feature_scan.sh                          # Run with default config
#   ./run_feature_scan.sh -d /path/to/data         # Specify data directory
#   ./run_feature_scan.sh -o /path/to/output       # Specify output directory
#   ./run_feature_scan.sh -c /path/to/config.yaml  # Specify config file
#   ./run_feature_scan.sh -t csv                   # Force CSV input
#   ./run_feature_scan.sh -d data -o outputs/eda   # Combined usage
#
# Environment variables (script arguments take precedence):
#   DATA_DIR=/path/to/data ./run_feature_scan.sh
#   OUTPUT_DIR=/path/to/out CONFIG_FILE=/path/to/cfg.yaml ./run_feature_scan.sh
#
# Run in background:
#   nohup ./run_feature_scan.sh -d data/cb_data > eda.log 2>&1 &
#   tail -f eda.log
#
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Defaults
DATA_DIR="${DATA_DIR:-${PROJ_ROOT}/data/sample_data}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJ_ROOT}/data_engineering/eda/output/feature_summary}"
CONFIG_FILE="${CONFIG_FILE:-${PROJ_ROOT}/configs/eda.yaml}"
SAMPLE_RATIO="${SAMPLE_RATIO:-}"
FILE_TYPE="${FILE_TYPE:-}"

# Usage info
usage() {
    echo -e "${GREEN}Streaming feature distribution statistics aggregation runner${NC}"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo -e "${CYAN}Options:${NC}"
    echo "  -d, --data <dir>       Input parquet/csv data directory"
    echo "  -o, --output <dir>     Output directory"
    echo "  -c, --config <path>    EDA config file path (default: configs/eda.yaml)"
    echo "  -s, --sample-ratio <f> EDA sample ratio, 0~1 (default from config, fallback 0.3)"
    echo "  -t, --file-type <type> Input file type: parquet|csv (default: auto-detect, fallback parquet)"
    echo "  -h, --help             Show this help"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  $0                           # Run with default config"
    echo "  $0 -d data/cb_data           # Specify data directory"
    echo "  $0 -o outputs/eda_scan       # Specify output directory"
    echo "  $0 -c configs/my_eda.yaml    # Specify custom EDA config"
    echo "  $0 -t csv -d data/cb_csv     # Force CSV input"
    echo ""
    echo "  $0 -d data/cb_data -o outputs/eda_v2 -c configs/eda.yaml   # Fully custom"
    echo ""
    echo -e "${CYAN}Run in background:${NC}"
    echo "  nohup $0 -d data/cb_data > eda.log 2>&1 &"
    echo "  tail -f eda.log"
    echo ""
    echo -e "${CYAN}Environment variables:${NC}"
    echo "  DATA_DIR=data/cb_data OUTPUT_DIR=outputs/eda $0"
    echo ""
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--data)
            DATA_DIR="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -c|--config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        -s|--sample-ratio)
            SAMPLE_RATIO="$2"
            shift 2
            ;;
        -t|--file-type)
            FILE_TYPE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown argument: $1${NC}"
            usage
            ;;
    esac
done

# Convert paths to absolute paths (avoid relative path issues after cd)
DATA_DIR="$(cd "${DATA_DIR}" 2>/dev/null && pwd || echo "${DATA_DIR}")"
OUTPUT_DIR="$(mkdir -p "${OUTPUT_DIR}" && cd "${OUTPUT_DIR}" && pwd)"
CONFIG_FILE="$(cd "$(dirname "${CONFIG_FILE}")" 2>/dev/null && pwd)/$(basename "${CONFIG_FILE}")" 2>/dev/null || echo "${CONFIG_FILE}"

# Check dependencies
check_dependency() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}Error: $1 not found, please install first${NC}"
        exit 1
    fi
}

check_dependency python

# Check data directory
if [[ ! -d "${DATA_DIR}" ]]; then
    echo -e "${RED}Error: data directory does not exist: ${DATA_DIR}${NC}"
    exit 1
fi

# Check config file
if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo -e "${RED}Error: config file does not exist: ${CONFIG_FILE}${NC}"
    exit 1
fi

# Check data files
PARQUET_COUNT=$(find "${DATA_DIR}" -name "*.parquet" | wc -l)
CSV_COUNT=$(find "${DATA_DIR}" -name "*.csv" | wc -l)
if [[ ${PARQUET_COUNT} -eq 0 && ${CSV_COUNT} -eq 0 ]]; then
    echo -e "${YELLOW}Warning: no parquet or csv files found in data directory: ${DATA_DIR}${NC}"
fi

# Set PYTHONPATH
export PYTHONPATH="${PROJ_ROOT}:${PYTHONPATH:-}"

echo ""
echo "========================================"
echo -e "${GREEN}📊 Starting feature distribution statistics${NC}"
echo "========================================"
echo -e "${BLUE}Project directory :${NC} ${PROJ_ROOT}"
echo -e "${BLUE}Data directory    :${NC} ${DATA_DIR}"
echo -e "${BLUE}Output directory  :${NC} ${OUTPUT_DIR}"
echo -e "${BLUE}Config file       :${NC} ${CONFIG_FILE}"
if [[ -n "${SAMPLE_RATIO}" ]]; then
    echo -e "${BLUE}Sample ratio      :${NC} ${SAMPLE_RATIO}"
fi
echo -e "${BLUE}Parquet file count:${NC} ${PARQUET_COUNT}"
echo -e "${BLUE}CSV file count     :${NC} ${CSV_COUNT}"
if [[ -n "${FILE_TYPE}" ]]; then
    echo -e "${BLUE}Forced file type   :${NC} ${FILE_TYPE}"
fi
echo "========================================"
echo ""

# Run scan
SAMPLE_RATIO_ARG=""
if [[ -n "${SAMPLE_RATIO}" ]]; then
    SAMPLE_RATIO_ARG="--sample_ratio ${SAMPLE_RATIO}"
fi

FILE_TYPE_ARG=""
if [[ -n "${FILE_TYPE}" ]]; then
    FILE_TYPE_ARG="--file_type ${FILE_TYPE}"
fi

python "${SCRIPT_DIR}/parquet_feature_scan.py" \
    --data_dir "${DATA_DIR}" \
    --output_dir "${OUTPUT_DIR}" \
    --config "${CONFIG_FILE}" \
    ${SAMPLE_RATIO_ARG} \
    ${FILE_TYPE_ARG}

SCAN_EXIT_CODE=$?

echo ""
if [ ${SCAN_EXIT_CODE} -eq 0 ]; then
    echo -e "${GREEN}✅ Scan completed, results saved to: ${OUTPUT_DIR}${NC}"
    echo ""
    echo -e "${CYAN}Output files:${NC}"
    ls -lh "${OUTPUT_DIR}" 2>/dev/null || echo "  (please check output directory)"
else
    echo -e "${RED}❌ Scan failed (exit code: ${SCAN_EXIT_CODE})${NC}"
fi

exit ${SCAN_EXIT_CODE}
