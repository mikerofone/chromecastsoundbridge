#/bin/sh
# Example usages:
#   $0 192.168.13.37
#   $0 192.168.13.37 "Living Room,Bedroom"
#   $0 192.168.13.37 "" "/volume3/services/chromecastsoundbridge" "python3"

# Required.
if [[ "$1" == "" ]] ; then
    echo "Error: Must specify IP or name of Soundbridge as first argument."
    exit 2
else
    export SOUNDBRIDGE_IP="$1"
fi

# Optional.
if [[ "$2" == "" ]] ; then
    export CHROMECAST_FILTER=""
else
    export CHROMECAST_FILTER="$2"
fi

# Optional: Root directory of your virtual Python environment.

if [[ "$3" == "" ]] ; then
    PY_ENV_ROOT="/volume1/chromecastsoundbridge"
else
    PY_ENV_ROOT="$3"
fi

# Optional: Basename of the Python executable.
if [[ "$4" == "" ]] ; then
    PYTHON_NAME="python3.10"
else
    PYTHON_NAME="$4"
fi

source "${PY_ENV_ROOT}/bin/activate"
cd "${PY_ENV_ROOT}/chromecastsoundbridge-master"
PID_FILE="${PY_ENV_ROOT}/chromecastsoundbridge-master/current_pid" "${PYTHON_NAME}" "${PY_ENV_ROOT}/chromecastsoundbridge-master/listener.py"
