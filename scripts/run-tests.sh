#!/bin/bash
# DEPRECATED: Use ./scripts/run-tests.py --level L1 --level L2 instead
echo "NOTE: Deprecated. Use: ./scripts/run-tests.py --level L1 --level L2" >&2
exec "$(dirname "$0")/run-tests.py" --level L1 --level L2 "$@"
