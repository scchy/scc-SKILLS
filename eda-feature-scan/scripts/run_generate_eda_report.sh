#!/usr/bin/env bash
# =============================================================================
# EDA report generation script
# =============================================================================
#
# Function: Calls generate_eda_report.py to generate EDA report and feature engineering config files
#
# Prerequisites:
#   Typically run run_feature_scan.sh first to generate num/cat/cross feature JSONs,
#   then run this script to generate readable Markdown report and encoding maps.
#
# Usage examples:
#   ./run_generate_eda_report.sh                           # Use default input/output
#   ./run_generate_eda_report.sh -o outputs/eda_report     # Specify output directory
#   ./run_generate_eda_report.sh -n data/num_features.json # Specify numerical features file
#
# Full pipeline usage:
#   ./run_feature_scan.sh -d data/cb_data -o outputs/eda_scan
#   ./run_generate_eda_report.sh \
#       -n outputs/eda_scan/num_features.json \
#       -c outputs/eda_scan/cat_features.json \
#       -x outputs/eda_scan/cross_cat_features.json \
#       -o outputs/eda_report
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

# Defaults (aligned with run_feature_scan.sh default output)
SCAN_OUTPUT="${PROJ_ROOT}/data_engineering/eda/output/feature_summary"
NUM_FEATURES="${NUM_FEATURES:-${SCAN_OUTPUT}/num_features.json}"
CAT_FEATURES="${CAT_FEATURES:-${SCAN_OUTPUT}/cat_features.json}"
CROSS_FEATURES="${CROSS_FEATURES:-${SCAN_OUTPUT}/cross_cat_features.json}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJ_ROOT}/data_engineering/eda/output}"

# Usage info
usage() {
    echo -e "${GREEN}EDA report generation script${NC}"
    echo ""
    echo "Usage: $0 [options]"
    echo ""
    echo -e "${CYAN}Options:${NC}"
    echo "  -n, --num <path>       Numerical feature stats JSON (default: output/feature_summary/num_features.json)"
    echo "  -c, --cat <path>       Categorical feature stats JSON (default: output/feature_summary/cat_features.json)"
    echo "  -x, --cross <path>     Cross-categorical feature stats JSON (default: output/feature_summary/cross_cat_features.json)"
    echo "  -o, --output <dir>     Output directory (default: eda/output/)"
    echo "  -h, --help             Show this help"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  $0                           # Generate report with default paths"
    echo "  $0 -o outputs/eda_report     # Specify output directory"
    echo ""
    echo -e "${CYAN}Full EDA pipeline example:${NC}"
    echo "  ./run_feature_scan.sh -d data/cb_data -o outputs/eda_scan"
    echo "  $0 -n outputs/eda_scan/num_features.json \\"
    echo "     -c outputs/eda_scan/cat_features.json \\"
    echo "     -x outputs/eda_scan/cross_cat_features.json \\"
    echo "     -o outputs/eda_report"
    echo ""
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--num)
            NUM_FEATURES="$2"
            shift 2
            ;;
        -c|--cat)
            CAT_FEATURES="$2"
            shift 2
            ;;
        -x|--cross)
            CROSS_FEATURES="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
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

# Check input files
check_file() {
    if [[ ! -f "$1" ]]; then
        echo -e "${RED}Error: file does not exist: $1${NC}"
        return 1
    fi
    return 0
}

MISSING=0
check_file "${NUM_FEATURES}" || MISSING=1
check_file "${CAT_FEATURES}" || MISSING=1
check_file "${CROSS_FEATURES}" || MISSING=1

if [[ ${MISSING} -eq 1 ]]; then
    echo ""
    echo -e "${YELLOW}Hint: please run run_feature_scan.sh first to generate input files${NC}"
    echo -e "${YELLOW}   ./run_feature_scan.sh -d <data_dir> -o ${SCAN_OUTPUT}${NC}"
    exit 1
fi

# Create output directory
mkdir -p "${OUTPUT_DIR}"

echo ""
echo "========================================"
echo -e "${GREEN}📝 Generating EDA report${NC}"
echo "========================================"
echo -e "${BLUE}Numerical features :${NC} ${NUM_FEATURES}"
echo -e "${BLUE}Categorical features:${NC} ${CAT_FEATURES}"
echo -e "${BLUE}Cross features     :${NC} ${CROSS_FEATURES}"
echo -e "${BLUE}Output directory   :${NC} ${OUTPUT_DIR}"
echo "========================================"
echo ""

# Run report generation
python3 -c "
import sys, os
sys.path.insert(0, '${SCRIPT_DIR}')
from generate_eda_report import EDAReportGenerator
generator = EDAReportGenerator('${NUM_FEATURES}', '${CAT_FEATURES}', '${CROSS_FEATURES}')
generator.save_outputs('${OUTPUT_DIR}')
"

GEN_EXIT_CODE=$?

echo ""
if [ ${GEN_EXIT_CODE} -eq 0 ]; then
    echo -e "${GREEN}✅ EDA report generation completed${NC}"
    echo ""
    echo -e "${CYAN}Output files:${NC}"
    for f in EDA_report.md encoding_map.json fill_na_map.json numerical_stats.json; do
        filepath="${OUTPUT_DIR}/${f}"
        if [[ -f "${filepath}" ]]; then
            size=$(ls -lh "${filepath}" | awk '{print $5}')
            echo "  ${f} (${size})"
        fi
    done
else
    echo -e "${RED}❌ Report generation failed (exit code: ${GEN_EXIT_CODE})${NC}"
fi

exit ${GEN_EXIT_CODE}
