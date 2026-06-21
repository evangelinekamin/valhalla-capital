"""Emergency control system with panic button."""
import json
from datetime import datetime, timezone
from pathlib import Path

import structlog

log = structlog.get_logger()


class EmergencyController:
    """
    Emergency halt system with state persistence.

    Provides panic button to immediately stop all trading and
    cancel open orders.
    """

    def __init__(self, ib_connection, discord_notifier, state_file: Path):
        """
        Initialize emergency controller.

        Args:
            ib_connection: IBKR connection for order cancellation
            discord_notifier: Discord notifier for alerts
            state_file: Path to panic state persistence file
        """
        self.ib = ib_connection
        self.discord = discord_notifier
        self.state_file = Path(state_file)
        self.logger = log.bind(component="emergency_controller")

        # Ensure state file directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Load persisted panic state
        self._panic_mode = self._load_panic_state()

        if self._panic_mode:
            self.logger.warning("panic_mode_active_on_startup")

    def _load_panic_state(self) -> bool:
        """
        Load panic state from file (persists across restarts).

        Returns:
            True if panic mode was active
        """
        if not self.state_file.exists():
            return False

        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
            return state.get("panic_mode", False)
        except Exception as e:
            self.logger.error("failed_to_load_panic_state", error=str(e))
            return False

    def _save_panic_state(self) -> None:
        """Persist panic state to file."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(
                    {
                        "panic_mode": self._panic_mode,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    f,
                    indent=2,
                )
            self.logger.debug("panic_state_saved", panic_mode=self._panic_mode)
        except Exception as e:
            self.logger.error("failed_to_save_panic_state", error=str(e))

    def trigger_panic(self, reason: str) -> bool:
        """
        Immediately halt all trading and cancel open orders.

        Args:
            reason: Why panic was triggered

        Returns:
            True if panic triggered successfully
        """
        self.logger.critical("PANIC_TRIGGERED", reason=reason)

        self._panic_mode = True
        self._save_panic_state()

        # Cancel all open orders
        cancelled_count = 0
        try:
            cancelled_count = self.ib.cancel_all_orders()
            self.logger.info("orders_cancelled_during_panic", count=cancelled_count)
        except Exception as e:
            self.logger.error("failed_to_cancel_orders", error=str(e))

        # Send Discord alert
        try:
            self.discord.send_panic_triggered(reason)
        except Exception as e:
            self.logger.error("failed_to_send_panic_alert", error=str(e))

        return True

    def is_panic_mode(self) -> bool:
        """
        Check if system is in panic mode.

        Returns:
            True if panic mode is active
        """
        return self._panic_mode

    def reset_panic(self, authorization_code: str) -> bool:
        """
        Reset panic mode (requires authorization code for safety).

        Args:
            authorization_code: Authorization code for reset

        Returns:
            True if reset successfully
        """
        expected_code = "CONFIRM_RESET"  # Could be made configurable

        if authorization_code != expected_code:
            self.logger.warning(
                "panic_reset_unauthorized", provided_code=authorization_code
            )
            return False

        self._panic_mode = False
        self._save_panic_state()

        self.logger.info("panic_mode_reset")

        # Send Discord notification
        try:
            self.discord.send_panic_reset()
        except Exception as e:
            self.logger.error("failed_to_send_reset_alert", error=str(e))

        return True

    def check_triggers(
        self, daily_loss_pct: float, connection_failures: int
    ) -> str | None:
        """
        Check automatic panic triggers.

        Args:
            daily_loss_pct: Current daily loss percentage
            connection_failures: Number of consecutive connection failures

        Returns:
            Trigger reason if panic should be triggered, None otherwise
        """
        # Daily loss limit trigger
        if daily_loss_pct < -0.05:  # 5% daily loss
            return f"Daily loss {daily_loss_pct:.2%} exceeded 5% limit"

        # Connection failure trigger
        if connection_failures >= 3:
            return f"IBKR connection failed {connection_failures} times"

        return None
