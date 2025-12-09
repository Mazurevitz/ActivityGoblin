#!/usr/bin/env python3
"""
Task Mapper - Maps activity blocks to Jira tasks using patterns and learning.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "config.yaml"
LEARNED_PATTERNS_PATH = "learned_patterns.yaml"
CONFIDENCE_THRESHOLD = 5  # Auto-apply after 5 successful matches


class TaskMapper:
    """Maps activity entries to Jira tasks based on patterns."""

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = Path(config_path)
        self.learned_path = self.config_path.parent / LEARNED_PATTERNS_PATH
        self.config = self._load_config()
        self.learned = self._load_learned_patterns()

    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            logger.warning(f"Config not found: {self.config_path}")
            return {}

        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load_learned_patterns(self) -> dict:
        """Load learned patterns from YAML file."""
        if not self.learned_path.exists():
            return {"patterns": [], "corrections": []}

        with open(self.learned_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"patterns": [], "corrections": []}

    def _save_learned_patterns(self) -> None:
        """Save learned patterns to YAML file."""
        with open(self.learned_path, "w", encoding="utf-8") as f:
            yaml.dump(self.learned, f, default_flow_style=False, allow_unicode=True)

    def _pattern_matches(self, pattern: dict, entry: dict) -> bool:
        """Check if a pattern matches an entry."""
        app = entry.get("app", "").lower()
        title = entry.get("title", "").lower()
        url = entry.get("url", "").lower()

        # Check app_contains
        if "app_contains" in pattern:
            if pattern["app_contains"].lower() not in app:
                return False

        # Check title_contains
        if "title_contains" in pattern:
            if pattern["title_contains"].lower() not in title:
                return False

        # Check url_contains
        if "url_contains" in pattern:
            if pattern["url_contains"].lower() not in url:
                return False

        # Check app_equals
        if "app_equals" in pattern:
            if pattern["app_equals"].lower() != app:
                return False

        return True

    def _find_learned_match(self, entry: dict) -> Optional[dict]:
        """Find a matching learned pattern."""
        for pattern in self.learned.get("patterns", []):
            if self._pattern_matches(pattern, entry):
                times_used = pattern.get("times_used", 0)
                if times_used >= CONFIDENCE_THRESHOLD:
                    return {
                        "task_key": pattern["task_key"],
                        "task_name": pattern.get("task_name", ""),
                        "client": pattern.get("client", ""),
                        "confidence": "high",
                        "source": "learned",
                        "times_used": times_used,
                    }
                else:
                    return {
                        "task_key": pattern["task_key"],
                        "task_name": pattern.get("task_name", ""),
                        "client": pattern.get("client", ""),
                        "confidence": "low",
                        "source": "learned",
                        "times_used": times_used,
                    }
        return None

    def _find_config_match(self, entry: dict) -> Optional[dict]:
        """Find a matching pattern from config."""
        for client in self.config.get("clients", []):
            client_name = client.get("name", "Unknown")
            for pattern in client.get("patterns", []):
                if self._pattern_matches(pattern, entry):
                    task_key = pattern.get("default_task", "")
                    task_name = ""

                    # Find task name
                    for task in client.get("tasks", []):
                        if task.get("key") == task_key:
                            task_name = task.get("name", "")
                            break

                    return {
                        "task_key": task_key,
                        "task_name": task_name,
                        "client": client_name,
                        "confidence": "high",
                        "source": "config",
                    }
        return None

    def _find_category_match(self, entry: dict) -> Optional[dict]:
        """Find a matching category (fallback)."""
        app = entry.get("app", "")

        for category, cat_config in self.config.get("categories", {}).items():
            for cat_app in cat_config.get("apps", []):
                if cat_app.lower() in app.lower():
                    return {
                        "task_key": cat_config.get("default_task"),
                        "task_name": "",
                        "client": "",
                        "category": category,
                        "confidence": "low",
                        "source": "category",
                    }
        return None

    def map_entry(self, entry: dict) -> dict:
        """
        Map a single activity entry to a task.

        Returns dict with:
            - task_key: Jira issue key or None
            - task_name: Human-readable task name
            - client: Client name
            - confidence: 'high', 'low', or 'none'
            - source: 'learned', 'config', 'category', or 'none'
        """
        # Priority 1: Learned patterns (user corrections)
        match = self._find_learned_match(entry)
        if match and match.get("task_key"):
            return match

        # Priority 2: Config patterns
        match = self._find_config_match(entry)
        if match and match.get("task_key"):
            return match

        # Priority 3: Category fallback
        match = self._find_category_match(entry)
        if match:
            return match

        # No match found
        return {
            "task_key": None,
            "task_name": "",
            "client": "",
            "confidence": "none",
            "source": "none",
        }

    def map_block(self, block: dict) -> dict:
        """
        Map an activity block to a task.

        Takes a block dict (from summarizer) and returns mapping info.
        """
        # Create a pseudo-entry from block for matching
        entry = {
            "app": block.get("app", ""),
            "title": " | ".join(block.get("titles", [])),
            "url": block.get("urls", [""])[0] if block.get("urls") else "",
        }

        mapping = self.map_entry(entry)
        mapping["block"] = block
        return mapping

    def learn_correction(
        self,
        entry: dict,
        task_key: str,
        task_name: str = "",
        client: str = "",
    ) -> None:
        """
        Learn from a user correction.

        Creates or updates a learned pattern based on the entry.
        """
        # Create pattern from entry
        pattern = {}

        app = entry.get("app", "")
        title = entry.get("title", "")
        url = entry.get("url", "")

        # Build specific pattern
        if app:
            pattern["app_contains"] = app

        # Add title pattern if distinctive
        if title and len(title) > 3:
            # Extract most distinctive part of title
            words = title.split()
            if words:
                # Use first significant word
                for word in words:
                    if len(word) > 3 and word.lower() not in ["the", "and", "for"]:
                        pattern["title_contains"] = word
                        break

        # Add URL pattern if present
        if url:
            # Extract domain or path
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.netloc:
                pattern["url_contains"] = parsed.netloc

        if not pattern:
            logger.warning("Could not create pattern from entry")
            return

        # Check if pattern already exists
        for existing in self.learned.get("patterns", []):
            if all(existing.get(k) == v for k, v in pattern.items() if k not in ["task_key", "task_name", "client", "times_used", "last_used"]):
                # Update existing pattern
                existing["task_key"] = task_key
                existing["task_name"] = task_name
                existing["client"] = client
                existing["times_used"] = existing.get("times_used", 0) + 1
                existing["last_used"] = datetime.now().isoformat()
                self._save_learned_patterns()
                logger.info(f"Updated learned pattern: {pattern} -> {task_key}")
                return

        # Add new pattern
        pattern["task_key"] = task_key
        pattern["task_name"] = task_name
        pattern["client"] = client
        pattern["times_used"] = 1
        pattern["date_added"] = datetime.now().isoformat()
        pattern["last_used"] = datetime.now().isoformat()

        if "patterns" not in self.learned:
            self.learned["patterns"] = []

        self.learned["patterns"].append(pattern)
        self._save_learned_patterns()
        logger.info(f"Added learned pattern: {pattern}")

    def increment_pattern_usage(self, entry: dict, task_key: str) -> None:
        """Increment usage count for a matched pattern (when user approves)."""
        for pattern in self.learned.get("patterns", []):
            if pattern.get("task_key") == task_key and self._pattern_matches(pattern, entry):
                pattern["times_used"] = pattern.get("times_used", 0) + 1
                pattern["last_used"] = datetime.now().isoformat()
                self._save_learned_patterns()
                return

    def get_all_tasks(self) -> list[dict]:
        """Get all configured tasks from all clients."""
        tasks = []

        # Add default task
        default = self.config.get("default_task", {})
        if default:
            tasks.append({
                "key": default.get("key", "ADMIN-001"),
                "name": default.get("name", "Administrative"),
                "client": "Default",
            })

        # Add client tasks
        for client in self.config.get("clients", []):
            client_name = client.get("name", "Unknown")
            for task in client.get("tasks", []):
                tasks.append({
                    "key": task.get("key", ""),
                    "name": task.get("name", ""),
                    "client": client_name,
                })

        return tasks

    def get_default_task(self) -> dict:
        """Get the default task for unassigned time."""
        default = self.config.get("default_task", {})
        return {
            "key": default.get("key", "ADMIN-001"),
            "name": default.get("name", "Administrative / Unassigned"),
        }

    def get_rounding(self) -> str:
        """Get hour rounding setting."""
        return self.config.get("rounding", "15min")

    def get_daily_target(self) -> float:
        """Get daily hours target."""
        return self.config.get("daily_hours_target", 8.0)

    def get_min_duration(self) -> int:
        """Get minimum block duration in minutes."""
        return self.config.get("min_duration_minutes", 5)
