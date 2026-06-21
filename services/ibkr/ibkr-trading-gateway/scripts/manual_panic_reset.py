#!/usr/bin/env python3
"""Manual panic mode reset script."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings
from src.adapters.ibkr_connection import IBKRConnection
from src.adapters.discord_notifier import DiscordNotifier
from src.services.emergency_controller import EmergencyController


def main():
    """Reset panic mode manually."""
    print("=" * 60)
    print("MANUAL PANIC MODE RESET")
    print("=" * 60)
    print()

    settings = Settings()

    # Initialize emergency controller
    ib = IBKRConnection(
        host=settings.ibkr_host,
        port=settings.ibkr_port,
        client_id=settings.ibkr_client_id + 100,  # Different client ID
    )

    discord = DiscordNotifier(webhook_url=settings.discord_webhook_url)

    panic_state_file = Path("/app/data/panic_state.json")
    emergency = EmergencyController(
        ib_connection=ib, discord_notifier=discord, state_file=panic_state_file
    )

    # Check current state
    if not emergency.is_panic_mode():
        print("✓ System is NOT in panic mode")
        print()
        return

    print("⚠ System IS in panic mode")
    print()

    # Confirm reset
    print("This will reset panic mode and resume trading.")
    confirmation = input("Type 'CONFIRM_RESET' to proceed: ").strip()
    print()

    if confirmation != "CONFIRM_RESET":
        print("Reset cancelled")
        return

    # Reset
    if emergency.reset_panic("CONFIRM_RESET"):
        print("✓ Panic mode reset successfully")
        print("✓ Trading can resume")
    else:
        print("✗ Failed to reset panic mode")
        sys.exit(1)


if __name__ == "__main__":
    main()
