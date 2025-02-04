#/bin/sh
# Example usages:
#   $0
#   $0 "/volume3/services/chromecastsoundbridge"

# Root directory of your virtual Python environment.
if [[ "$1" == "" ]] ; then
    PY_ENV_ROOT="/volume1/chromecastsoundbridge"
else
    PY_ENV_ROOT="$1"
fi

PID_FILE="${PY_ENV_ROOT}/chromecastsoundbridge-master/current_pid"
if [ ! -e "${PID_FILE}" ] ; then
    echo "No old process to kill (file \"${PID_FILE}\" doesn't exist)"
    exit 1
fi
SERVICE_PID=$(cat "${PID_FILE}")
if ! kill -9 "${SERVICE_PID}" ; then
    if ps "${SERVICE_PID}" ; then
        echo "Process ${SERVICE_PID} found but refused to die, giving up."
        exit 2
    else
        echo "No such process ${SERVICE_PID}, removing stale PID_FILE."
    fi
fi
rm "${PID_FILE}"

