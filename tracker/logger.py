#!/usr/bin/env python3
"""
Activity Logger - Tracks active application, window title, and browser URLs.

Runs continuously and logs activity snapshots to daily JSONL files.
"""

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from tracker.utils import (
    get_active_app_name,
    get_active_window_title,
    get_browser_url,
    is_browser,
)

# Default configuration
DEFAULT_INTERVAL = 300  # 5 minutes
DEFAULT_DATA_DIR = "data"
DEFAULT_WORK_HOURS = (8, 18)  # 8:00 to 18:00

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class ActivityLogger:
    """Logs user activity to daily JSONL files."""

    def __init__(
        self,
        data_dir: str = DEFAULT_DATA_DIR,
        interval: int = DEFAULT_INTERVAL,
        work_hours: Optional[tuple[int, int]] = None,
        skip_weekends: bool = False,
    ):
        """
        Initialize the activity logger.

        Args:
            data_dir: Directory to store log files
            interval: Seconds between activity snapshots
            work_hours: Tuple of (start_hour, end_hour) to limit logging, None for always
            skip_weekends: If True, skip logging on Saturday and Sunday
        """
        self.data_dir = Path(data_dir)
        self.interval = interval
        self.work_hours = work_hours
        self.skip_weekends = skip_weekends
        self.running = False
        self._ensure_data_dir()

    def _ensure_data_dir(self) -> None:
        """Create the data directory if it doesn't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Data directory: {self.data_dir.absolute()}")

    def _is_work_time(self) -> bool:
        """
        Check if current time is within configured work hours.

        Returns:
            True if logging should occur, False if outside work hours
        """
        now = datetime.now()

        # Check weekend
        if self.skip_weekends and now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        # Check work hours
        if self.work_hours:
            start_hour, end_hour = self.work_hours
            if not (start_hour <= now.hour < end_hour):
                return False

        return True

    def _get_log_path(self, date: Optional[datetime] = None) -> Path:
        """
        Get the path to the log file for a given date.

        Args:
            date: Date for the log file (defaults to today)

        Returns:
            Path to the JSONL log file
        """
        if date is None:
            date = datetime.now()
        filename = date.strftime("%Y-%m-%d") + ".jsonl"
        return self.data_dir / filename

    def capture_activity(self) -> dict:
        """
        Capture the current user activity.

        Returns:
            Dictionary containing timestamp, app, title, and optionally URL
        """
        timestamp = datetime.now().isoformat()
        app_name = get_active_app_name()
        window_title = get_active_window_title()

        entry = {
            "ts": timestamp,
            "app": app_name or "Unknown",
            "title": window_title or "",
        }

        # Capture browser URL if applicable
        if app_name and is_browser(app_name):
            url = get_browser_url(app_name)
            if url:
                entry["url"] = url

        return entry

    def write_entry(self, entry: dict) -> None:
        """
        Write an activity entry to the daily log file.

        Args:
            entry: Activity entry dictionary
        """
        log_path = self._get_log_path()
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            logger.debug(f"Logged: {entry['app']} - {entry['title'][:50]}...")
        except IOError as e:
            logger.error(f"Failed to write log entry: {e}")

    def log_once(self) -> dict:
        """
        Capture and log a single activity snapshot.

        Returns:
            The logged activity entry
        """
        entry = self.capture_activity()
        self.write_entry(entry)
        return entry

    def run(self) -> None:
        """Run the activity logger continuously."""
        self.running = True
        logger.info(f"Starting activity logger (interval: {self.interval}s)")
        if self.work_hours:
            logger.info(f"Work hours: {self.work_hours[0]:02d}:00 - {self.work_hours[1]:02d}:00")
        if self.skip_weekends:
            logger.info("Skipping weekends")
        logger.info("Press Ctrl+C to stop")

        outside_hours_logged = False

        while self.running:
            # Check if within work hours
            if not self._is_work_time():
                if not outside_hours_logged:
                    logger.info("Outside work hours - paused (still running, will resume automatically)")
                    outside_hours_logged = True
                time.sleep(60)  # Check every minute when outside work hours
                continue

            outside_hours_logged = False  # Reset when back in work hours

            try:
                entry = self.log_once()
                app_display = entry.get("app", "Unknown")
                title_display = entry.get("title", "")[:40]
                url_display = entry.get("url", "")[:30] if "url" in entry else ""

                status = f"[{entry['ts'][:19]}] {app_display}"
                if title_display:
                    status += f" | {title_display}"
                if url_display:
                    status += f" | {url_display}..."

                logger.info(status)

            except Exception as e:
                logger.error(f"Error capturing activity: {e}")

            # Sleep in smaller increments for responsive shutdown
            sleep_time = self.interval
            while sleep_time > 0 and self.running:
                time.sleep(min(1, sleep_time))
                sleep_time -= 1

    def stop(self) -> None:
        """Stop the activity logger."""
        logger.info("Stopping activity logger...")
        self.running = False


def setup_signal_handlers(tracker: ActivityLogger) -> None:
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        tracker.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def parse_work_hours(value: str) -> tuple[int, int]:
    """Parse work hours string like '8-18' into tuple."""
    try:
        start, end = value.split("-")
        start_hour = int(start)
        end_hour = int(end)
        if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):
            raise ValueError("Hours must be 0-23")
        if start_hour >= end_hour:
            raise ValueError("Start hour must be less than end hour")
        return (start_hour, end_hour)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"Invalid work hours '{value}': {e}. Use format like '8-18'")


def main():
    """Main entry point for the activity logger."""
    parser = argparse.ArgumentParser(
        description="Track active application and window activity on macOS"
    )
    parser.add_argument(
        "-i", "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Seconds between activity snapshots (default: {DEFAULT_INTERVAL})"
    )
    parser.add_argument(
        "-d", "--data-dir",
        type=str,
        default=DEFAULT_DATA_DIR,
        help=f"Directory to store log files (default: {DEFAULT_DATA_DIR})"
    )
    parser.add_argument(
        "-w", "--work-hours",
        type=parse_work_hours,
        default=None,
        metavar="START-END",
        help="Only log during work hours, e.g., '8-18' for 8:00-18:00"
    )
    parser.add_argument(
        "--skip-weekends",
        action="store_true",
        help="Skip logging on Saturday and Sunday"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Capture a single snapshot and exit"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    tracker = ActivityLogger(
        data_dir=args.data_dir,
        interval=args.interval,
        work_hours=args.work_hours,
        skip_weekends=args.skip_weekends,
    )

    if args.once:
        entry = tracker.log_once()
        print(json.dumps(entry, indent=2))
    else:
        setup_signal_handlers(tracker)
        tracker.run()


if __name__ == "__main__":
    main()
