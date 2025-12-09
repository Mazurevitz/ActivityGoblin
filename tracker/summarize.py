#!/usr/bin/env python3
"""
Daily Activity Summarizer - Groups activity logs and generates summaries using local LLM.

Reads JSONL log files, groups continuous activity into blocks, and uses Ollama
to generate human-readable summaries of work sessions.
"""

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Default configuration
DEFAULT_DATA_DIR = "data"
DEFAULT_SUMMARY_DIR = "summaries"
DEFAULT_MODEL = "llama3"
DEFAULT_GAP_MINUTES = 15  # Minutes of gap to consider as new block

# Work-related apps (case-insensitive matching)
WORK_APPS = {
    "citrix viewer", "microsoft outlook", "outlook", "microsoft teams", "msteams",
    "teams", "slack", "zoom", "google chrome", "chrome", "safari", "arc",
    "visual studio code", "code", "vs code", "xcode", "terminal", "iterm",
    "finder", "preview", "notes", "notion", "obsidian", "microsoft word",
    "microsoft excel", "microsoft powerpoint", "word", "excel", "powerpoint",
    "figma", "sketch", "postman", "docker", "github desktop", "sourcetree",
    "intellij", "pycharm", "webstorm", "datagrip", "sublime text", "atom",
    "1password", "bitwarden", "keynote", "pages", "numbers", "mail",
}

# URL patterns to exclude (entertainment, social media, etc.)
EXCLUDED_URL_PATTERNS = [
    "youtube.com", "netflix.com", "twitch.tv", "reddit.com",
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "tiktok.com", "discord.com", "spotify.com", "music.apple.com",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class ActivityBlock:
    """Represents a continuous block of similar activity."""

    def __init__(self, start_time: datetime, app: str, title: str, url: Optional[str] = None):
        self.start_time = start_time
        self.end_time = start_time
        self.app = app
        self.titles: list[str] = [title] if title else []
        self.urls: list[str] = [url] if url else []
        self.entry_count = 1

    def extend(self, end_time: datetime, title: str, url: Optional[str] = None) -> None:
        """Extend this block with a new entry."""
        self.end_time = end_time
        if title and title not in self.titles:
            self.titles.append(title)
        if url and url not in self.urls:
            self.urls.append(url)
        self.entry_count += 1

    def duration_minutes(self) -> float:
        """Get the duration of this block in minutes."""
        delta = self.end_time - self.start_time
        return delta.total_seconds() / 60

    def to_dict(self) -> dict:
        """Convert block to dictionary for JSON serialization."""
        result = {
            "from": self.start_time.isoformat(),
            "to": self.end_time.isoformat(),
            "duration_minutes": round(self.duration_minutes(), 1),
            "app": self.app,
            "titles": self.titles[:5],  # Limit to 5 unique titles
            "entry_count": self.entry_count,
        }
        if self.urls:
            result["urls"] = self.urls[:5]  # Limit to 5 unique URLs
        return result


class ActivitySummarizer:
    """Groups and summarizes daily activity logs."""

    def __init__(
        self,
        data_dir: str = DEFAULT_DATA_DIR,
        model: str = DEFAULT_MODEL,
        gap_minutes: int = DEFAULT_GAP_MINUTES,
        work_only: bool = False,
        summary_dir: str = DEFAULT_SUMMARY_DIR,
    ):
        self.data_dir = Path(data_dir)
        self.summary_dir = Path(summary_dir)
        self.model = model
        self.gap_threshold = timedelta(minutes=gap_minutes)
        self.work_only = work_only

    def _is_work_entry(self, entry: dict) -> bool:
        """Check if an entry is work-related."""
        app = entry.get("app", "").lower()
        url = entry.get("url", "").lower()

        # Check if app is in work apps list
        app_is_work = any(work_app in app for work_app in WORK_APPS)

        # Check if URL contains excluded patterns
        url_is_excluded = any(pattern in url for pattern in EXCLUDED_URL_PATTERNS)

        # Work entry = work app AND not excluded URL
        if url_is_excluded:
            return False

        return app_is_work

    def _filter_work_entries(self, entries: list[dict]) -> list[dict]:
        """Filter entries to only include work-related activity."""
        filtered = [e for e in entries if self._is_work_entry(e)]
        logger.info(f"Filtered to {len(filtered)} work entries (from {len(entries)} total)")
        return filtered

    def load_entries(self, date: str) -> list[dict]:
        """
        Load log entries for a specific date.

        Args:
            date: Date string in YYYY-MM-DD format

        Returns:
            List of log entry dictionaries
        """
        log_path = self.data_dir / f"{date}.jsonl"

        if not log_path.exists():
            logger.error(f"Log file not found: {log_path}")
            return []

        entries = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON on line {line_num}: {e}")

        logger.info(f"Loaded {len(entries)} entries from {log_path}")

        if self.work_only:
            entries = self._filter_work_entries(entries)

        return entries

    def _should_merge(self, block: ActivityBlock, entry: dict, entry_time: datetime) -> bool:
        """
        Determine if an entry should be merged into an existing block.

        Args:
            block: Current activity block
            entry: New log entry
            entry_time: Parsed timestamp of the entry

        Returns:
            True if the entry should be merged into the block
        """
        # Check time gap
        time_gap = entry_time - block.end_time
        if time_gap > self.gap_threshold:
            return False

        # Check if same app
        if entry.get("app") != block.app:
            return False

        return True

    def group_into_blocks(self, entries: list[dict]) -> list[ActivityBlock]:
        """
        Group log entries into continuous activity blocks.

        Args:
            entries: List of log entry dictionaries

        Returns:
            List of ActivityBlock objects
        """
        if not entries:
            return []

        blocks: list[ActivityBlock] = []
        current_block: Optional[ActivityBlock] = None

        for entry in entries:
            try:
                ts = datetime.fromisoformat(entry["ts"])
            except (KeyError, ValueError) as e:
                logger.warning(f"Invalid timestamp in entry: {e}")
                continue

            app = entry.get("app", "Unknown")
            title = entry.get("title", "")
            url = entry.get("url")

            if current_block is None:
                current_block = ActivityBlock(ts, app, title, url)
            elif self._should_merge(current_block, entry, ts):
                current_block.extend(ts, title, url)
            else:
                blocks.append(current_block)
                current_block = ActivityBlock(ts, app, title, url)

        if current_block:
            blocks.append(current_block)

        logger.info(f"Grouped into {len(blocks)} activity blocks")
        return blocks

    def generate_prompt(self, blocks: list[ActivityBlock], date: str) -> str:
        """
        Generate a prompt for the LLM to summarize activity blocks.

        Args:
            blocks: List of activity blocks
            date: Date string for context

        Returns:
            Prompt string for the LLM
        """
        block_summaries = []
        for i, block in enumerate(blocks, 1):
            summary = f"Block {i}:\n"
            summary += f"  Time: {block.start_time.strftime('%H:%M')} - {block.end_time.strftime('%H:%M')}\n"
            summary += f"  Duration: {block.duration_minutes():.0f} minutes\n"
            summary += f"  Application: {block.app}\n"

            if block.titles:
                titles_str = "; ".join(block.titles[:3])
                summary += f"  Window titles: {titles_str}\n"

            if block.urls:
                urls_str = "; ".join(block.urls[:3])
                summary += f"  URLs visited: {urls_str}\n"

            block_summaries.append(summary)

        blocks_text = "\n".join(block_summaries)

        prompt = f"""Analyze the following computer activity log from {date} and provide a structured summary.

Activity Log:
{blocks_text}

Based on this activity, create a JSON array summarizing each work session. Each session should have:
- "from": start time (HH:MM format)
- "to": end time (HH:MM format)
- "summary": a brief description of what the user was likely doing (1-2 sentences)

Focus on identifying the actual work being done (coding, browsing, writing, etc.) rather than just listing applications.

Respond ONLY with a valid JSON array, no additional text. Example format:
[
  {{"from": "09:00", "to": "10:30", "summary": "Writing code in VS Code, working on authentication module"}},
  {{"from": "10:30", "to": "11:00", "summary": "Researching API documentation in browser"}}
]

JSON response:"""

        return prompt

    def call_ollama(self, prompt: str) -> Optional[str]:
        """
        Send a prompt to Ollama and get the response.

        Args:
            prompt: The prompt to send

        Returns:
            Model response string or None if failed
        """
        logger.info(f"Calling Ollama with model: {self.model}")

        try:
            result = subprocess.run(
                ["ollama", "run", self.model],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"Ollama error: {result.stderr}")
                return None

            return result.stdout.strip()

        except subprocess.TimeoutExpired:
            logger.error("Ollama request timed out")
            return None
        except FileNotFoundError:
            logger.error("Ollama not found. Please install Ollama first.")
            return None
        except Exception as e:
            logger.error(f"Failed to call Ollama: {e}")
            return None

    def parse_llm_response(self, response: str) -> Optional[list[dict]]:
        """
        Parse the LLM response to extract JSON.

        Args:
            response: Raw LLM response string

        Returns:
            Parsed JSON list or None if parsing failed
        """
        # Try to find JSON array in response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if not json_match:
            logger.error("No JSON array found in LLM response")
            return None

        try:
            result = json.loads(json_match.group())
            if isinstance(result, list):
                return result
            else:
                logger.error("LLM response is not a JSON array")
                return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return None

    def summarize(self, date: str, use_llm: bool = True) -> dict:
        """
        Generate a summary for a specific date.

        Args:
            date: Date string in YYYY-MM-DD format
            use_llm: Whether to use LLM for summary generation

        Returns:
            Summary dictionary with blocks and optional LLM summary
        """
        entries = self.load_entries(date)
        if not entries:
            return {"date": date, "error": "No entries found", "blocks": []}

        blocks = self.group_into_blocks(entries)
        blocks_data = [block.to_dict() for block in blocks]

        result = {
            "date": date,
            "total_entries": len(entries),
            "blocks": blocks_data,
        }

        if use_llm and blocks:
            prompt = self.generate_prompt(blocks, date)
            logger.debug(f"Generated prompt:\n{prompt}")

            response = self.call_ollama(prompt)
            if response:
                logger.debug(f"LLM response:\n{response}")
                llm_summary = self.parse_llm_response(response)
                if llm_summary:
                    result["summary"] = llm_summary
                else:
                    result["llm_raw"] = response
                    result["summary_error"] = "Failed to parse LLM response"
            else:
                result["summary_error"] = "Failed to get LLM response"

        return result

    def summarize_blocks_only(self, date: str) -> list[dict]:
        """
        Generate block summaries without LLM.

        Args:
            date: Date string in YYYY-MM-DD format

        Returns:
            List of block dictionaries
        """
        entries = self.load_entries(date)
        blocks = self.group_into_blocks(entries)
        return [block.to_dict() for block in blocks]

    def save_summary(self, result: dict, date: str) -> Path:
        """
        Save summary to file.

        Args:
            result: Summary dictionary
            date: Date string for filename

        Returns:
            Path to saved file
        """
        self.summary_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.summary_dir / f"{date}-summary.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"Summary saved to {output_path}")
        return output_path


def main():
    """Main entry point for the summarizer."""
    parser = argparse.ArgumentParser(
        description="Summarize daily activity logs using local LLM"
    )
    parser.add_argument(
        "date",
        nargs="?",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Date to summarize (YYYY-MM-DD format, default: today)"
    )
    parser.add_argument(
        "-d", "--data-dir",
        type=str,
        default=DEFAULT_DATA_DIR,
        help=f"Directory containing log files (default: {DEFAULT_DATA_DIR})"
    )
    parser.add_argument(
        "-m", "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"Ollama model to use (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "-g", "--gap",
        type=int,
        default=DEFAULT_GAP_MINUTES,
        help=f"Minutes of inactivity to start new block (default: {DEFAULT_GAP_MINUTES})"
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM summarization, only show grouped blocks"
    )
    parser.add_argument(
        "--blocks-only",
        action="store_true",
        help="Output only the activity blocks as JSON"
    )
    parser.add_argument(
        "--work-only",
        action="store_true",
        help="Filter to work-related apps only (exclude YouTube, social media, etc.)"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        metavar="DIR",
        help="Save summary to directory (default: print to stdout)"
    )
    parser.add_argument(
        "--yesterday",
        action="store_true",
        help="Summarize yesterday's activity (useful for midnight cron)"
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

    # Validate date format
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        logger.error(f"Invalid date format: {target_date}. Use YYYY-MM-DD.")
        sys.exit(1)

    summarizer = ActivitySummarizer(
        data_dir=args.data_dir,
        model=args.model,
        gap_minutes=args.gap,
        work_only=args.work_only,
        summary_dir=args.output or DEFAULT_SUMMARY_DIR,
    )

    if args.blocks_only:
        blocks = summarizer.summarize_blocks_only(target_date)
        print(json.dumps(blocks, indent=2))
    else:
        result = summarizer.summarize(target_date, use_llm=not args.no_llm)

        if args.output:
            summarizer.save_summary(result, target_date)
        else:
            print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
