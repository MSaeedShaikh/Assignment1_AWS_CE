#!/bin/bash
# UniEvent server management script
# Usage: ./server.sh [start|stop|restart|status]

APP_DIR="$(cd "$(dirname "$0")/app" && pwd)"
PIDFILE="/tmp/unievent.pid"
LOGFILE="/tmp/unievent.log"
BIND="0.0.0.0:5000"
WORKERS=2

start() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "UniEvent is already running (PID $(cat "$PIDFILE"))."
        exit 1
    fi
    echo "Starting UniEvent..."
    cd "$APP_DIR" || exit 1
    gunicorn --bind "$BIND" \
             --workers "$WORKERS" \
             --pid "$PIDFILE" \
             --daemon \
             --log-file "$LOGFILE" \
             --access-logfile "$LOGFILE" \
             app:app
    sleep 1
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "UniEvent started (PID $(cat "$PIDFILE")). Listening on $BIND."
        echo "Logs: $LOGFILE"
    else
        echo "Failed to start UniEvent. Check $LOGFILE for details."
        exit 1
    fi
}

stop() {
    if [ ! -f "$PIDFILE" ] || ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "UniEvent is not running."
        exit 0
    fi
    echo "Stopping UniEvent (PID $(cat "$PIDFILE"))..."
    kill "$(cat "$PIDFILE")"
    rm -f "$PIDFILE"
    echo "Stopped."
}

restart() {
    stop
    sleep 1
    start
}

status() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "UniEvent is running (PID $(cat "$PIDFILE")). Bound to $BIND."
    else
        echo "UniEvent is not running."
    fi
}

case "$1" in
    start)   start   ;;
    stop)    stop    ;;
    restart) restart ;;
    status)  status  ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
