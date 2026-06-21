#!/usr/bin/env python3
"""Test script for Discord webhook notifications.

Usage:
    python test_discord.py                    # Use webhook from config.yaml or DISCORD_WEBHOOK_URL env var
    python test_discord.py <webhook-url>      # Test with specific webhook URL
"""
import sys
from discord_notifier import DiscordNotifier


def test_notifications(webhook_url):
    """Test Discord notifications with various message types."""
    print(f"Testing Discord webhook...")
    print(f"Webhook URL: {webhook_url[:50]}..." if len(webhook_url) > 50 else webhook_url)

    notifier = DiscordNotifier(webhook_url=webhook_url, enabled=True)

    # Test 1: Simple info message
    print("\n[1/4] Sending info message...")
    success = notifier.send_message(
        "Test notification from Substack pipeline - INFO level",
        severity="info"
    )
    print(f"  {'✓ Success' if success else '✗ Failed'}")

    # Test 2: Warning message
    print("\n[2/4] Sending warning message...")
    success = notifier.send_message(
        "Test notification from Substack pipeline - WARNING level",
        severity="warning"
    )
    print(f"  {'✓ Success' if success else '✗ Failed'}")

    # Test 3: Error notification with context
    print("\n[3/4] Sending error notification...")
    try:
        raise ValueError("This is a test error for Discord notification")
    except Exception as e:
        success = notifier.send_error(
            error=e,
            stage="test",
            context={"test_id": 123, "component": "test_discord.py"},
            severity="error"
        )
        print(f"  {'✓ Success' if success else '✗ Failed'}")

    # Test 4: Critical error notification
    print("\n[4/4] Sending critical error notification...")
    try:
        raise RuntimeError("Critical test error - pipeline failure simulation")
    except Exception as e:
        success = notifier.send_error(
            error=e,
            stage="pipeline",
            context={"stage": "all", "batch_num": 5},
            severity="critical"
        )
        print(f"  {'✓ Success' if success else '✗ Failed'}")

    print("\n✓ Test complete! Check your Discord channel for notifications.")


def main():
    if len(sys.argv) > 1:
        webhook_url = sys.argv[1]
    else:
        # Try to load from config
        try:
            from config import load_config
            cfg = load_config()
            webhook_url = cfg.discord.webhook_url

            if not webhook_url:
                print("Error: No webhook URL found in config.yaml or DISCORD_WEBHOOK_URL environment variable")
                print("\nUsage:")
                print("  python test_discord.py <webhook-url>")
                print("  OR set DISCORD_WEBHOOK_URL in .env file")
                print("  OR configure webhook_url in config.yaml")
                sys.exit(1)
        except Exception as e:
            print(f"Error loading config: {e}")
            print("\nUsage:")
            print("  python test_discord.py <webhook-url>")
            sys.exit(1)

    test_notifications(webhook_url)


if __name__ == "__main__":
    main()
