#!/bin/bash
# DEPRECATED: Use ./scripts/run-tests.py --level L3 --level L4 instead
echo "NOTE: Deprecated. Use: ./scripts/run-tests.py --level L3 --level L4" >&2
exec "$(dirname "$0")/run-tests.py" --level L3 --level L4 "$@"
