"""
AppleScript wrappers and utility functions for macOS activity tracking.
"""

import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def run_applescript(script: str) -> Optional[str]:
    """
    Execute an AppleScript and return the result.

    Args:
        script: AppleScript code to execute

    Returns:
        Script output as string, or None if execution failed
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.debug(f"AppleScript error: {result.stderr.strip()}")
            return None
    except subprocess.TimeoutExpired:
        logger.warning("AppleScript execution timed out")
        return None
    except Exception as e:
        logger.error(f"Failed to run AppleScript: {e}")
        return None


def get_active_app() -> Optional[str]:
    """
    Get the bundle identifier of the currently active application.

    Returns:
        Bundle identifier string (e.g., "com.google.Chrome") or None
    """
    script = '''
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        return bundle identifier of frontApp
    end tell
    '''
    return run_applescript(script)


def get_active_app_name() -> Optional[str]:
    """
    Get the display name of the currently active application.

    Returns:
        Application name (e.g., "Google Chrome") or None
    """
    script = '''
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        return name of frontApp
    end tell
    '''
    return run_applescript(script)


def get_active_window_title() -> Optional[str]:
    """
    Get the title of the frontmost window of the active application.

    Returns:
        Window title string or None
    """
    script = '''
    tell application "System Events"
        set frontApp to first application process whose frontmost is true
        tell frontApp
            if (count of windows) > 0 then
                return name of front window
            else
                return ""
            end if
        end tell
    end tell
    '''
    result = run_applescript(script)
    return result if result else None


def get_chrome_url() -> Optional[str]:
    """
    Get the URL of the active tab in Google Chrome.

    Returns:
        URL string or None if Chrome is not running or has no tabs
    """
    script = '''
    tell application "Google Chrome"
        if (count of windows) > 0 then
            return URL of active tab of front window
        else
            return ""
        end if
    end tell
    '''
    result = run_applescript(script)
    return result if result else None


def get_safari_url() -> Optional[str]:
    """
    Get the URL of the active tab in Safari.

    Returns:
        URL string or None if Safari is not running or has no tabs
    """
    script = '''
    tell application "Safari"
        if (count of windows) > 0 then
            return URL of current tab of front window
        else
            return ""
        end if
    end tell
    '''
    result = run_applescript(script)
    return result if result else None


def get_arc_url() -> Optional[str]:
    """
    Get the URL of the active tab in Arc browser.

    Returns:
        URL string or None if Arc is not running or has no tabs
    """
    script = '''
    tell application "Arc"
        if (count of windows) > 0 then
            return URL of active tab of front window
        else
            return ""
        end if
    end tell
    '''
    result = run_applescript(script)
    return result if result else None


def get_firefox_url() -> Optional[str]:
    """
    Get the URL from Firefox (limited support - uses window title).
    Firefox doesn't have full AppleScript support, so we extract from title.

    Returns:
        URL from window title if present, or None
    """
    # Firefox includes URL in window title for some pages
    # This is a fallback method with limited accuracy
    title = get_active_window_title()
    if title and " - Mozilla Firefox" in title:
        # Some Firefox configurations show URL in title
        return None  # Firefox doesn't expose URL via AppleScript
    return None


def get_browser_url(app_name: str) -> Optional[str]:
    """
    Get the current URL for supported browsers.

    Args:
        app_name: Name of the browser application

    Returns:
        URL string or None if not a supported browser or URL unavailable
    """
    browser_handlers = {
        "Google Chrome": get_chrome_url,
        "Chrome": get_chrome_url,
        "Safari": get_safari_url,
        "Arc": get_arc_url,
        "Firefox": get_firefox_url,
    }

    handler = browser_handlers.get(app_name)
    if handler:
        return handler()
    return None


def is_browser(app_name: str) -> bool:
    """
    Check if the given application is a known web browser.

    Args:
        app_name: Name of the application

    Returns:
        True if the application is a recognized browser
    """
    browsers = {
        "Google Chrome", "Chrome", "Safari", "Arc",
        "Firefox", "Microsoft Edge", "Brave Browser", "Opera"
    }
    return app_name in browsers


def get_all_apps_with_windows() -> list[str]:
    """
    Get list of all foreground applications (apps with UI windows).
    Uses lsappinfo for speed (~30ms vs ~2500ms with AppleScript).

    Returns:
        List of application names with visible windows
    """
    try:
        result = subprocess.run(
            ["bash", "-c",
             "lsappinfo list | awk -F'\"' '/^[[:space:]]*[0-9]+\\)/{name=$2} /type=\"Foreground\"/{print name}'"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout:
            apps = [app.strip() for app in result.stdout.strip().split("\n") if app.strip()]
            return apps
    except Exception as e:
        logger.debug(f"Failed to get app list: {e}")
    return []
