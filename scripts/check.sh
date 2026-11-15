#!/bin/sh
set -eu
PYTHON=${PYTHON:-.venv-mcp/bin/python}
node --check script.js
node --check enclave.js
node --check conversation.js
node --check moderation.js
node --test tests/site.test.cjs
"$PYTHON" -m compileall -q server
"$PYTHON" -m unittest discover -s tests -p 'test_*.py' -v
