#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Instala las dependencias siguiendo README.md.'
  exit 1
fi
if [ ! -f output/index.html ]; then
  echo 'Clasifica primero: .venv/bin/python -m jevdocs classify'
  exit 1
fi
exec .venv/bin/python -m jevdocs serve "$@"
