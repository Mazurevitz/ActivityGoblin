#!/bin/bash
#
# ActivityGoblin - Run the activity logger as a background process
#
# Usage:
#   ./run_logger.sh start   - Start the logger in background
#   ./run_logger.sh stop    - Stop the running logger
#   ./run_logger.sh status  - Check if logger is running
#   ./run_logger.sh logs    - View recent logs
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/.logger.pid"
LOG_FILE="$SCRIPT_DIR/logger.log"

# Default interval (5 minutes = 300 seconds)
INTERVAL="${ACTIVITY_INTERVAL:-300}"
# Default work hours (empty = always on)
WORK_HOURS="${ACTIVITY_WORK_HOURS:-}"
# Skip weekends (set to 1 to enable)
SKIP_WEEKENDS="${ACTIVITY_SKIP_WEEKENDS:-}"

start_logger() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Logger is already running (PID: $PID)"
            exit 1
        else
            rm "$PID_FILE"
        fi
    fi

    # Build command arguments
    CMD_ARGS="-i $INTERVAL"
    if [ -n "$WORK_HOURS" ]; then
        CMD_ARGS="$CMD_ARGS -w $WORK_HOURS"
    fi
    if [ "$SKIP_WEEKENDS" = "1" ]; then
        CMD_ARGS="$CMD_ARGS --skip-weekends"
    fi

    echo "Starting ActivityGoblin logger (interval: ${INTERVAL}s)..."
    [ -n "$WORK_HOURS" ] && echo "Work hours: $WORK_HOURS"
    [ "$SKIP_WEEKENDS" = "1" ] && echo "Skipping weekends"
    cd "$SCRIPT_DIR"

    # Run the logger in background
    nohup python3 -m tracker.logger $CMD_ARGS >> "$LOG_FILE" 2>&1 &
    LOGGER_PID=$!

    echo "$LOGGER_PID" > "$PID_FILE"
    echo "Logger started with PID: $LOGGER_PID"
    echo "Logs: $LOG_FILE"
    echo "Data: $SCRIPT_DIR/data/"
}

stop_logger() {
    if [ ! -f "$PID_FILE" ]; then
        echo "Logger is not running (no PID file)"
        exit 1
    fi

    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping logger (PID: $PID)..."
        kill "$PID"
        sleep 2

        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Force stopping..."
            kill -9 "$PID"
        fi

        rm "$PID_FILE"
        echo "Logger stopped"
    else
        echo "Logger process not found (stale PID file)"
        rm "$PID_FILE"
    fi
}

status_logger() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Logger is running (PID: $PID)"
            echo ""
            echo "Process info:"
            ps -p "$PID" -o pid,ppid,stat,time,command
            exit 0
        else
            echo "Logger is not running (stale PID file)"
            exit 1
        fi
    else
        echo "Logger is not running"
        exit 1
    fi
}

view_logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -50 "$LOG_FILE"
    else
        echo "No log file found at $LOG_FILE"
    fi
}

case "${1:-help}" in
    start)
        start_logger
        ;;
    stop)
        stop_logger
        ;;
    restart)
        stop_logger 2>/dev/null
        sleep 1
        start_logger
        ;;
    status)
        status_logger
        ;;
    logs)
        view_logs
        ;;
    *)
        echo "ActivityGoblin - Activity Logger Control"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the logger in background"
        echo "  stop    - Stop the running logger"
        echo "  restart - Restart the logger"
        echo "  status  - Check if logger is running"
        echo "  logs    - View recent log output"
        echo ""
        echo "Environment variables:"
        echo "  ACTIVITY_INTERVAL      - Seconds between captures (default: 300)"
        echo "  ACTIVITY_WORK_HOURS    - Work hours range, e.g., '8-18'"
        echo "  ACTIVITY_SKIP_WEEKENDS - Set to '1' to skip weekends"
        echo ""
        echo "Example:"
        echo "  ACTIVITY_WORK_HOURS=8-18 ACTIVITY_SKIP_WEEKENDS=1 $0 start"
        ;;
esac
