# ActivityGoblin

**Automatic time tracking for macOS** - Track what apps you use, generate timesheets with local AI

[![macOS](https://img.shields.io/badge/macOS-Sonoma%2B-blue)](https://www.apple.com/macos/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Privacy](https://img.shields.io/badge/Privacy-100%25%20Local-brightgreen)](#privacy)

A lightweight, privacy-focused time tracker that runs locally on your Mac. It automatically logs your active applications and browser tabs, then uses a local LLM (Ollama) to generate human-readable timesheet summaries. Perfect for freelancers, consultants, and anyone who needs to track billable hours.

## Why ActivityGoblin?

- **Automatic**: Set it and forget it - logs run in the background
- **Private**: 100% local, no cloud, no telemetry, your data never leaves your machine
- **Smart**: AI-powered summaries turn raw logs into meaningful work descriptions
- **Lightweight**: ~11MB RAM, <0.1% CPU - you won't notice it's running
- **Simple**: Pure Python, no dependencies, just clone and run
- **Flexible**: Configurable work hours, intervals, and weekend skipping

## Use Cases

- **Freelancers**: Automatically track time spent on client projects
- **Remote Workers**: Generate accurate timesheets for billing
- **Developers**: See how much time you spend coding vs. browsing
- **Personal Productivity**: Understand your computer usage patterns
- **Project Tracking**: Break down time by application and website

## Quick Start

```bash
# Clone the repo
git clone https://github.com/Mazurevitz/ActivityGoblin.git
cd ActivityGoblin

# Start tracking (8 AM - 6 PM, weekdays only)
python3 -m tracker.logger -w 8-18 --skip-weekends

# Generate today's timesheet
python3 -m tracker.summarize
```

## Features

- **Application Tracking**: Captures active app name and window title
- **Background Apps**: Logs all open applications, not just the focused one
- **Browser URL Logging**: Extracts URLs from Chrome, Safari, and Arc
- **Work Hours Mode**: Only track during specified hours (e.g., 8-18)
- **Weekend Skipping**: Optionally pause tracking on weekends
- **Daily JSONL Logs**: Simple, parseable format organized by date
- **AI Summaries**: Local Ollama LLM generates timesheet descriptions
- **Configurable Intervals**: Default 5 minutes, adjustable as needed
- **Lightweight**: ~200ms per capture, <0.01% CPU impact

## Requirements

- macOS Sonoma (14.0+) / Apple Silicon or Intel
- Python 3.10+
- [Ollama](https://ollama.ai) with `llama3` model (optional, for AI summaries)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Mazurevitz/ActivityGoblin.git
   cd ActivityGoblin
   ```

2. **Grant Accessibility permissions:**
   - Open **System Settings > Privacy & Security > Accessibility**
   - Add and enable your terminal app (Terminal, iTerm2, etc.)

3. **Install Ollama** (optional, for AI summaries):
   ```bash
   # Download from https://ollama.ai then:
   ollama pull llama3
   ```

## Usage

### Activity Logger

```bash
# Run continuously (default: every 5 minutes)
python3 -m tracker.logger

# Track only during work hours (8 AM - 6 PM)
python3 -m tracker.logger -w 8-18

# Skip weekends too
python3 -m tracker.logger -w 8-18 --skip-weekends

# Custom interval (every 2 minutes)
python3 -m tracker.logger -i 120

# Single snapshot (for testing)
python3 -m tracker.logger --once
```

### Background Process

```bash
# Start in background
./run_logger.sh start

# With work hours
ACTIVITY_WORK_HOURS=8-18 ACTIVITY_SKIP_WEEKENDS=1 ./run_logger.sh start

# Check status
./run_logger.sh status

# Stop
./run_logger.sh stop

# View logs
./run_logger.sh logs
```

### Daily Summarizer

```bash
# Summarize today
python3 -m tracker.summarize

# Summarize specific date
python3 -m tracker.summarize 2024-12-01

# Work-only mode (excludes YouTube, social media, etc.)
python3 -m tracker.summarize --work-only

# Save to file instead of stdout
python3 -m tracker.summarize --work-only -o summaries

# Summarize yesterday (for midnight cron jobs)
python3 -m tracker.summarize --yesterday --work-only -o summaries

# Just show activity blocks (no AI)
python3 -m tracker.summarize --no-llm

# Use different Ollama model
python3 -m tracker.summarize -m mistral
```

### Auto-Summary at Midnight

The summarizer can run automatically at midnight to generate work-only summaries:

```bash
launchctl load ~/Library/LaunchAgents/com.activitygoblin.summarize.plist
```

This creates daily summaries in `summaries/YYYY-MM-DD-summary.json` with YouTube and entertainment filtered out.

## Tempo Timesheet Integration

Export your activity to Jira Tempo with interactive review and pattern learning.

### Setup

```bash
# Install dependencies
pip install pyyaml requests

# Create your config from template
cp config.example.yaml config.yaml

# Edit config.yaml with your clients, tasks, and patterns
```

### Interactive Review

```bash
# Review today's timesheet
python3 -m tracker.tempo

# Review specific date
python3 -m tracker.tempo 2024-12-01

# Review yesterday
python3 -m tracker.tempo --yesterday
```

The interactive CLI shows:
```
═══════════════════════════════════════════════════════════
  TIMESHEET REVIEW - 2024-12-08
═══════════════════════════════════════════════════════════
  Total: 7.5h / 8.0h target
  Assigned: 6.0h | Unassigned entries: 3
───────────────────────────────────────────────────────────

[ 1] 09:52-11:06 (1.25h) → CLIENTA-100
     Development
     ✓ Citrix Viewer | MVW US ZUE2 Azure PRD
     Client: Client A

[ 2] 14:00-15:00 (1.00h) → UNASSIGNED
     ⚠ Terminal | ActivityGoblin project
```

Commands: `[a]pprove`, `[e N]dit entry`, `[d]efault all`, `[u]pload to Tempo`

### Auto-Export (No Review)

```bash
# Export without interactive review
python3 -m tracker.tempo --export-only

# Export and upload to Tempo API
python3 -m tracker.tempo --export-only --upload
```

### Pattern Learning

When you correct a task assignment, the system learns:
- First correction: Pattern saved with low confidence
- After 5 uses: Auto-applied without prompting
- Patterns stored in `learned_patterns.yaml`

### Config Example

```yaml
clients:
  - name: "Client A"
    tasks:
      - key: "CLIENTA-100"
        name: "Development"
    patterns:
      - app_contains: "Citrix"
        title_contains: "MVW"
        default_task: "CLIENTA-100"

default_task:
  key: "ADMIN-001"
  name: "Administrative"

rounding: "15min"  # none, 15min, 30min
```

### Security

- `config.yaml` is gitignored (contains API token)
- Use `TEMPO_API_TOKEN` env var instead of storing in file
- `learned_patterns.yaml` is gitignored (user-specific)

## Output Examples

### Raw Log Entry (JSONL)
```json
{"ts": "2024-12-01T09:15:00", "app": "Google Chrome", "title": "GitHub - PR #123", "url": "https://github.com/...", "open_apps": ["VS Code", "Terminal", "Slack", "Spotify"]}
{"ts": "2024-12-01T09:20:00", "app": "VS Code", "title": "main.py - MyProject", "open_apps": ["Google Chrome", "Terminal", "Slack"]}
```

Each entry includes:
- `app` - Focused application
- `title` - Window title
- `url` - Browser URL (if applicable)
- `open_apps` - All other apps with open windows

### AI-Generated Summary
```json
{
  "summary": [
    {"from": "09:00", "to": "10:30", "summary": "Code review on GitHub, reviewing pull request for authentication module"},
    {"from": "10:30", "to": "12:00", "summary": "Python development in VS Code, implementing API endpoints"}
  ]
}
```

## Auto-Start on Login

Create a launch agent to start tracking automatically:

```bash
cat > ~/Library/LaunchAgents/com.activitygoblin.logger.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.activitygoblin.logger</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>-m</string>
        <string>tracker.logger</string>
        <string>-w</string>
        <string>8-18</string>
        <string>--skip-weekends</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/PATH/TO/ActivityGoblin</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/PATH/TO/ActivityGoblin/logger.log</string>
    <key>StandardErrorPath</key>
    <string>/PATH/TO/ActivityGoblin/logger.log</string>
</dict>
</plist>
EOF

# Update paths, then load
launchctl load ~/Library/LaunchAgents/com.activitygoblin.logger.plist
```

## Privacy

ActivityGoblin is designed with privacy as a core principle:

- **100% Local**: All data stays on your machine
- **No Cloud**: No external APIs, no data upload, no telemetry
- **No Dependencies**: Pure Python standard library (no tracking packages)
- **Transparent**: Simple JSONL format you can inspect anytime
- **Your Data**: Delete `data/*.jsonl` anytime to clear history

## Project Structure

```
ActivityGoblin/
├── tracker/
│   ├── logger.py      # Activity capture daemon
│   ├── summarize.py   # AI-powered timesheet generator
│   └── utils.py       # AppleScript wrappers
├── data/              # Daily logs (YYYY-MM-DD.jsonl)
├── run_logger.sh      # Background process control
└── README.md
```

## CLI Reference

### logger.py
```
python3 -m tracker.logger [-h] [-i INTERVAL] [-d DATA_DIR] [-w START-END] [--skip-weekends] [--once] [-v]

Options:
  -i, --interval     Seconds between snapshots (default: 300)
  -d, --data-dir     Log file directory (default: data)
  -w, --work-hours   Only log during hours, e.g., '8-18'
  --skip-weekends    Skip Saturday and Sunday
  --once             Single snapshot and exit
  -v, --verbose      Debug logging
```

### summarize.py
```
python3 -m tracker.summarize [-h] [-d DATA_DIR] [-m MODEL] [-g GAP] [--no-llm] [--blocks-only] [-v] [date]

Arguments:
  date               Date to summarize (YYYY-MM-DD, default: today)

Options:
  -d, --data-dir     Log file directory (default: data)
  -m, --model        Ollama model (default: llama3)
  -g, --gap          Minutes gap for new block (default: 15)
  --no-llm           Skip AI summary
  --blocks-only      Raw block JSON only
  -v, --verbose      Debug logging
```

## Troubleshooting

**"Not authorized to send Apple events"**
→ Grant Accessibility permissions: System Settings > Privacy & Security > Accessibility

**Browser URLs not captured**
→ Firefox doesn't support AppleScript URL extraction. Chrome, Safari, Arc work.

**Ollama not found**
→ Install from https://ollama.ai and run `ollama pull llama3`

## Keywords

macos time tracking, automatic timesheet, activity monitor, app usage tracker, local time tracker, privacy time tracking, ollama timesheet, freelancer time tracking, billable hours tracker, work hours logger, application tracker macos, browser history tracker, productivity tracker mac, time logging automation, self-hosted time tracker

## License

MIT License - See [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please open an issue or PR.
