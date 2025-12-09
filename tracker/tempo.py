#!/usr/bin/env python3
"""
Tempo Integration - Interactive review CLI and Tempo API export.
"""

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from tracker.mapper import TaskMapper
from tracker.summarize import ActivitySummarizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = "data"
DEFAULT_TEMPO_DIR = "tempo"
DEFAULT_CONFIG_PATH = "config.yaml"


class TimesheetEntry:
    """Represents a single timesheet entry."""

    def __init__(
        self,
        start_time: datetime,
        end_time: datetime,
        app: str,
        titles: list[str],
        urls: list[str],
        task_key: Optional[str] = None,
        task_name: str = "",
        client: str = "",
        confidence: str = "none",
        description: str = "",
    ):
        self.start_time = start_time
        self.end_time = end_time
        self.app = app
        self.titles = titles
        self.urls = urls
        self.task_key = task_key
        self.task_name = task_name
        self.client = client
        self.confidence = confidence
        self.description = description

    @property
    def duration_hours(self) -> float:
        """Duration in hours."""
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 3600

    @property
    def duration_minutes(self) -> float:
        """Duration in minutes."""
        return self.duration_hours * 60

    def round_duration(self, rounding: str) -> float:
        """Get rounded duration in hours."""
        hours = self.duration_hours

        if rounding == "15min":
            return round(hours * 4) / 4
        elif rounding == "30min":
            return round(hours * 2) / 2
        else:
            return round(hours, 2)

    @property
    def time_range(self) -> str:
        """Formatted time range string."""
        return f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}"

    @property
    def status_icon(self) -> str:
        """Status icon based on confidence."""
        if self.confidence == "high":
            return "✓"
        elif self.confidence == "low":
            return "?"
        else:
            return "⚠"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "date": self.start_time.strftime("%Y-%m-%d"),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_hours": self.duration_hours,
            "app": self.app,
            "titles": self.titles,
            "urls": self.urls,
            "task_key": self.task_key,
            "task_name": self.task_name,
            "client": self.client,
            "description": self.description,
        }


class TempoReview:
    """Interactive CLI for reviewing and exporting timesheets."""

    def __init__(
        self,
        data_dir: str = DEFAULT_DATA_DIR,
        tempo_dir: str = DEFAULT_TEMPO_DIR,
        config_path: str = DEFAULT_CONFIG_PATH,
    ):
        self.data_dir = Path(data_dir)
        self.tempo_dir = Path(tempo_dir)
        self.config_path = Path(config_path)
        self.tempo_dir.mkdir(parents=True, exist_ok=True)

        self.mapper = TaskMapper(config_path)
        self.summarizer = ActivitySummarizer(
            data_dir=data_dir,
            work_only=True,
            gap_minutes=15,
        )
        self.entries: list[TimesheetEntry] = []

    def load_day(self, date: str) -> list[TimesheetEntry]:
        """Load and map activity for a specific date."""
        blocks = self.summarizer.summarize_blocks_only(date)
        min_duration = self.mapper.get_min_duration()

        entries = []
        for block in blocks:
            # Parse times
            start = datetime.fromisoformat(block["from"])
            end = datetime.fromisoformat(block["to"])

            # Skip short blocks
            duration_min = (end - start).total_seconds() / 60
            if duration_min < min_duration:
                continue

            # Map to task
            mapping = self.mapper.map_block(block)

            entry = TimesheetEntry(
                start_time=start,
                end_time=end,
                app=block.get("app", "Unknown"),
                titles=block.get("titles", []),
                urls=block.get("urls", []),
                task_key=mapping.get("task_key"),
                task_name=mapping.get("task_name", ""),
                client=mapping.get("client", ""),
                confidence=mapping.get("confidence", "none"),
            )

            # Generate description
            entry.description = self._generate_description(entry)
            entries.append(entry)

        self.entries = entries
        return entries

    def _generate_description(self, entry: TimesheetEntry) -> str:
        """Generate a description for the entry."""
        parts = [entry.app]

        if entry.titles:
            # Use first title, truncated
            title = entry.titles[0][:50]
            if len(entry.titles[0]) > 50:
                title += "..."
            parts.append(title)

        return " - ".join(parts)

    def display_entries(self) -> None:
        """Display all entries for review."""
        if not self.entries:
            print("\nNo entries to review.\n")
            return

        rounding = self.mapper.get_rounding()
        target = self.mapper.get_daily_target()

        # Calculate totals
        total_hours = sum(e.round_duration(rounding) for e in self.entries)
        assigned_hours = sum(
            e.round_duration(rounding) for e in self.entries if e.task_key
        )
        unassigned = len([e for e in self.entries if not e.task_key])

        date_str = self.entries[0].start_time.strftime("%Y-%m-%d")

        print()
        print("=" * 70)
        print(f"  TIMESHEET REVIEW - {date_str}")
        print("=" * 70)
        print(f"  Total: {total_hours:.1f}h / {target:.1f}h target")
        print(f"  Assigned: {assigned_hours:.1f}h | Unassigned entries: {unassigned}")
        print("-" * 70)
        print()

        for i, entry in enumerate(self.entries, 1):
            hours = entry.round_duration(rounding)
            task_display = entry.task_key or "UNASSIGNED"
            task_name = entry.task_name or ""

            print(f"[{i:2d}] {entry.time_range} ({hours:.2f}h) → {task_display}")
            if task_name:
                print(f"     {task_name}")
            print(f"     {entry.status_icon} {entry.app}", end="")
            if entry.titles:
                print(f" | {entry.titles[0][:40]}", end="")
            print()
            if entry.client:
                print(f"     Client: {entry.client}")
            print()

        print("-" * 70)

    def display_tasks(self) -> list[dict]:
        """Display available tasks and return list."""
        tasks = self.mapper.get_all_tasks()

        print("\nAvailable tasks:")
        for i, task in enumerate(tasks, 1):
            print(f"  {i}) [{task['key']}] {task['name']}")
            if task.get("client"):
                print(f"     Client: {task['client']}")

        return tasks

    def edit_entry(self, index: int) -> None:
        """Edit a single entry."""
        if index < 1 or index > len(self.entries):
            print(f"Invalid entry number: {index}")
            return

        entry = self.entries[index - 1]

        print(f"\nEditing entry {index}:")
        print(f"  Current: {entry.task_key or 'UNASSIGNED'} - {entry.task_name}")
        print()

        tasks = self.display_tasks()

        print(f"\n  {len(tasks) + 1}) Enter custom task key")
        print(f"  {len(tasks) + 2}) Skip (keep current)")

        try:
            choice = input("\nSelect task number: ").strip()
            choice_num = int(choice)

            if choice_num == len(tasks) + 2:
                return  # Skip

            if choice_num == len(tasks) + 1:
                # Custom task key
                custom_key = input("Enter task key (e.g., PROJ-123): ").strip()
                if custom_key:
                    entry.task_key = custom_key
                    entry.task_name = ""
                    entry.confidence = "high"

                    # Learn from correction
                    self._learn_correction(entry, custom_key, "", "")
            elif 1 <= choice_num <= len(tasks):
                task = tasks[choice_num - 1]
                entry.task_key = task["key"]
                entry.task_name = task["name"]
                entry.client = task.get("client", "")
                entry.confidence = "high"

                # Learn from correction
                self._learn_correction(entry, task["key"], task["name"], task.get("client", ""))

            print(f"Updated entry {index} → {entry.task_key}")

        except (ValueError, KeyboardInterrupt):
            print("Cancelled")

    def _learn_correction(self, entry: TimesheetEntry, task_key: str, task_name: str, client: str) -> None:
        """Learn from a user correction."""
        pseudo_entry = {
            "app": entry.app,
            "title": entry.titles[0] if entry.titles else "",
            "url": entry.urls[0] if entry.urls else "",
        }
        self.mapper.learn_correction(pseudo_entry, task_key, task_name, client)

    def assign_default_to_unassigned(self) -> int:
        """Assign default task to all unassigned entries."""
        default = self.mapper.get_default_task()
        count = 0

        for entry in self.entries:
            if not entry.task_key:
                entry.task_key = default["key"]
                entry.task_name = default["name"]
                entry.confidence = "low"
                count += 1

        return count

    def export_csv(self, date: str) -> Path:
        """Export entries to CSV file."""
        rounding = self.mapper.get_rounding()
        output_path = self.tempo_dir / f"{date}-timesheet.csv"

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Hours", "Issue Key", "Description"])

            for entry in self.entries:
                if entry.task_key:
                    hours = entry.round_duration(rounding)
                    writer.writerow([
                        entry.start_time.strftime("%Y-%m-%d"),
                        f"{hours:.2f}",
                        entry.task_key,
                        entry.description,
                    ])

        logger.info(f"Exported to {output_path}")
        return output_path

    def export_json(self, date: str) -> Path:
        """Export entries to JSON file."""
        rounding = self.mapper.get_rounding()
        output_path = self.tempo_dir / f"{date}-timesheet.json"

        data = {
            "date": date,
            "rounding": rounding,
            "entries": [],
        }

        for entry in self.entries:
            if entry.task_key:
                data["entries"].append({
                    "date": entry.start_time.strftime("%Y-%m-%d"),
                    "hours": entry.round_duration(rounding),
                    "issue_key": entry.task_key,
                    "description": entry.description,
                    "start_time": entry.start_time.strftime("%H:%M"),
                    "end_time": entry.end_time.strftime("%H:%M"),
                })

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Exported to {output_path}")
        return output_path

    def upload_to_tempo(self, date: str) -> bool:
        """Upload entries to Tempo API."""
        if not HAS_REQUESTS:
            print("\n[!] Cannot upload: 'requests' library not installed")
            print("    Run: pip install requests")
            print("    Your timesheet was still exported to CSV/JSON files.\n")
            return False

        # Get API token from environment first
        api_token = os.environ.get("TEMPO_API_TOKEN")
        api_url = "https://api.tempo.io/4"

        # Try to load from config if env var not set
        if not api_token and HAS_YAML and self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    config = yaml.safe_load(f) or {}
                tempo_config = config.get("tempo", {})
                api_url = tempo_config.get("api_url", api_url)
                api_token = tempo_config.get("api_token")
            except Exception as e:
                logger.debug(f"Could not load config for API: {e}")

        if not api_token:
            print("\n[!] Cannot upload: Tempo API token not configured")
            print("    Set TEMPO_API_TOKEN environment variable, or")
            print("    Add api_token to tempo section in config.yaml")
            print("    Your timesheet was still exported to CSV/JSON files.\n")
            return False

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

        rounding = self.mapper.get_rounding()
        success_count = 0
        error_count = 0

        for entry in self.entries:
            if not entry.task_key:
                continue

            hours = entry.round_duration(rounding)
            if hours <= 0:
                continue

            # Tempo API worklog format
            payload = {
                "issueKey": entry.task_key,
                "timeSpentSeconds": int(hours * 3600),
                "startDate": entry.start_time.strftime("%Y-%m-%d"),
                "startTime": entry.start_time.strftime("%H:%M:%S"),
                "description": entry.description,
            }

            try:
                response = requests.post(
                    urljoin(api_url, "/worklogs"),
                    headers=headers,
                    json=payload,
                    timeout=30,
                )

                if response.status_code in (200, 201):
                    success_count += 1
                    logger.debug(f"Uploaded: {entry.task_key} - {hours}h")
                else:
                    error_count += 1
                    logger.error(f"Failed to upload {entry.task_key}: {response.status_code} - {response.text}")

            except Exception as e:
                error_count += 1
                logger.error(f"Failed to upload {entry.task_key}: {e}")

        logger.info(f"Upload complete: {success_count} succeeded, {error_count} failed")
        return error_count == 0

    def interactive_review(self, date: str) -> None:
        """Run interactive review session."""
        self.load_day(date)

        while True:
            self.display_entries()

            if not self.entries:
                break

            print("Commands:")
            print("  [a] Approve all and export")
            print("  [e N] Edit entry N")
            print("  [d] Assign default to unassigned")
            print("  [u] Upload to Tempo API")
            print("  [q] Quit without saving")
            print()

            try:
                cmd = input("> ").strip().lower()

                if cmd == "q":
                    print("Exiting without saving.")
                    break

                elif cmd == "a":
                    # Check for unassigned
                    unassigned = len([e for e in self.entries if not e.task_key])
                    if unassigned > 0:
                        confirm = input(f"{unassigned} entries unassigned. Assign default? [y/n]: ")
                        if confirm.lower() == "y":
                            self.assign_default_to_unassigned()

                    csv_path = self.export_csv(date)
                    json_path = self.export_json(date)
                    print(f"\nExported to:")
                    print(f"  {csv_path}")
                    print(f"  {json_path}")
                    break

                elif cmd == "d":
                    count = self.assign_default_to_unassigned()
                    print(f"Assigned default task to {count} entries")

                elif cmd.startswith("e "):
                    try:
                        index = int(cmd[2:])
                        self.edit_entry(index)
                    except ValueError:
                        print("Invalid entry number")

                elif cmd == "u":
                    confirm = input("Upload to Tempo API? [y/n]: ")
                    if confirm.lower() == "y":
                        if self.upload_to_tempo(date):
                            print("Upload successful!")
                        else:
                            print("Upload had errors. Check logs.")

                else:
                    print("Unknown command")

            except KeyboardInterrupt:
                print("\nExiting.")
                break


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Review and export timesheets to Tempo"
    )
    parser.add_argument(
        "date",
        nargs="?",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Date to review (YYYY-MM-DD format, default: today)"
    )
    parser.add_argument(
        "-d", "--data-dir",
        type=str,
        default=DEFAULT_DATA_DIR,
        help=f"Directory containing log files (default: {DEFAULT_DATA_DIR})"
    )
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=DEFAULT_CONFIG_PATH,
        help=f"Config file path (default: {DEFAULT_CONFIG_PATH})"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=DEFAULT_TEMPO_DIR,
        help=f"Output directory for exports (default: {DEFAULT_TEMPO_DIR})"
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Export without interactive review (auto-assign defaults)"
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload to Tempo API after export"
    )
    parser.add_argument(
        "--yesterday",
        action="store_true",
        help="Review yesterday's activity"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle yesterday flag
    if args.yesterday:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        target_date = args.date

    review = TempoReview(
        data_dir=args.data_dir,
        tempo_dir=args.output,
        config_path=args.config,
    )

    if args.export_only:
        review.load_day(target_date)
        review.assign_default_to_unassigned()
        review.export_csv(target_date)
        review.export_json(target_date)

        if args.upload:
            review.upload_to_tempo(target_date)
    else:
        review.interactive_review(target_date)


if __name__ == "__main__":
    main()
