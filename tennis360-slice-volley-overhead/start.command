#!/bin/bash
# Finder launcher; keep paths quoted for spaces and non-ASCII folder names.
cd "$(dirname "$0")" || exit 1
python_bin=""
for candidate in "$PWD/.venv/bin/python" python3.11 /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11 /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 python3; do
    if "$candidate" -c 'import sys, struct; sys.exit(not (sys.version_info[:2] == (3, 11) and struct.calcsize("P") == 8))' >/dev/null 2>&1; then
        python_bin="$candidate"
        break
    fi
done
if [ -z "$python_bin" ]; then
    echo "Python 3.11 (64-bit) is required. Install it from python.org, then retry."
    echo "See README.md and docs/teaching-guide.zh-TW.md for classroom setup."
    result=1
else
    "$python_bin" scripts/bootstrap.py "$@"
    result=$?
fi
if [ "$result" -ne 0 ]; then
    echo "Startup failed. Keep the error above and show it to your teacher."
    read -r -p "Press Enter to close... "
fi
exit "$result"
