#!/usr/bin/env bash
set -eo pipefail
workspace=$1
log_directory=$2
mkdir -p "$log_directory"
cd "$workspace"
set +e
colcon test --return-code-on-test-failure --event-handlers console_direct+ 2>&1 | tee "$log_directory/test.log"
test_status=${PIPESTATUS[0]}
colcon test-result --verbose 2>&1 | tee "$log_directory/test-result.log"
result_status=${PIPESTATUS[0]}
set -e
if (( test_status != 0 || result_status != 0 )); then exit 1; fi
