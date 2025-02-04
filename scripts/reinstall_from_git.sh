#/bin/sh
# Example usages:
#   $0
#   $0 "/volume3/services/chromecastsoundbridge" "python3"

set -e  # Bail out if anything goes wrong.

# Root directory of your virtual Python environment.
if [[ "$1" == "" ]] ; then
    PY_ENV_ROOT="/volume1/chromecastsoundbridge"
else
    PY_ENV_ROOT="$1"
fi

# Basename of the Python executable.
if [[ "$2" == "" ]] ; then
    PYTHON_NAME="python3.10"
else
    PYTHON_NAME="$2"
fi

echo "Press a key to install to \"${PY_ENV_ROOT}\" using Python binary \"${PYTHON_NAME}\" or CTRL+C to abort."
read foo

rm -rf "${PY_ENV_ROOT}/script/"
mkdir "${PY_ENV_ROOT}/script/"
cd "${PY_ENV_ROOT}/script"
wget https://github.com/mikerofone/chromecastsoundbridge/archive/refs/heads/master.zip
7z e master.zip
rm master.zip
source "${PY_ENV_ROOT}/bin/activate"
"${PY_ENV_ROOT}/bin/${PYTHON_NAME}" -m pip install -r ./requirements.txt