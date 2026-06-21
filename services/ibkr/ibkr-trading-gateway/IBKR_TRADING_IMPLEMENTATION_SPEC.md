# IBKR Trading API Implementation Specification

## Executive Summary

This document specifies the implementation of a trading execution layer using Interactive Brokers TWS API. The system enables autonomous trade execution with Kelly Criterion-based position sizing (halved for risk management), comprehensive safety controls, and integration with the existing multi-Claude orchestration architecture.

**Critical Safety Principle**: All monetary transactions must pass through multiple validation layers with hard limits, extensive logging, and manual override capabilities.

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Overseer Claude                          │
│  (Coordinates analysis, makes trading decisions)            │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│              Trading API Layer (Python)                      │
│  - Position sizing (Half-Kelly Criterion)                   │
│  - Risk validation                                           │
│  - Order management                                          │
│  - Database logging                                          │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│         IB Gateway Container (Always Running)                │
│  - Maintains connection to IBKR                              │
│  - Handles authentication                                    │
│  - Provides API endpoint (localhost:4002 for paper)         │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│              Interactive Brokers                             │
│  - Paper trading account (initial testing)                  │
│  - Live trading account (post-validation)                   │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow for Trade Execution

1. **Decision Phase**: Overseer Claude analyzes all data sources and decides on a trade
2. **Validation Phase**: Trading API validates against safety rules
3. **Sizing Phase**: Kelly Criterion calculation determines position size, then halved
4. **Pre-flight Check**: Final validation of available capital, existing positions
5. **Execution Phase**: Order submitted to IB Gateway
6. **Confirmation Phase**: Wait for fill, log outcome
7. **Post-trade Phase**: Update portfolio state, notify via Discord if needed

---

## Library Selection: ib_insync

### Rationale

**Primary Choice**: `ib_insync` over raw `ibapi`

**Advantages**:
- Pythonic async/await syntax (cleaner than callback-based ibapi)
- Built-in reconnection logic
- Better error handling
- Active maintenance
- Extensive documentation
- Synchronous and asynchronous modes

**Installation**:
```bash
pip install ib_insync
```

**Alternative**: If ib_insync proves problematic, fall back to raw `ibapi` with custom wrapper layer

---

## IB Gateway Setup

### Docker Container Configuration

**Dockerfile for IB Gateway**:

```dockerfile
FROM ghcr.io/unusualvultures/ib-gateway:latest

# Configuration
ENV TWS_USERID=${IBKR_USERNAME}
ENV TWS_PASSWORD=${IBKR_PASSWORD}
ENV TRADING_MODE=paper
ENV TWS_PORT=4002
ENV VNC_SERVER_PASSWORD=${VNC_PASSWORD}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD netstat -an | grep 4002 > /dev/null || exit 1

EXPOSE 4002 5900
```

**Docker Compose Entry**:

```yaml
services:
  ib-gateway:
    build: ./ib-gateway
    container_name: trading-ib-gateway
    restart: unless-stopped
    environment:
      - TWS_USERID=${IBKR_USERNAME}
      - TWS_PASSWORD=${IBKR_PASSWORD}
      - TRADING_MODE=paper  # Switch to 'live' for real trading
      - TWS_PORT=4002
      - VNC_SERVER_PASSWORD=${VNC_PASSWORD}
    ports:
      - "4002:4002"  # API port
      - "5900:5900"  # VNC for monitoring
    volumes:
      - ./ib-gateway-settings:/root/Jts
    networks:
      - trading-network
    healthcheck:
      test: ["CMD", "netstat", "-an", "|", "grep", "4002"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  trading-network:
    driver: bridge
```

### Connection Management

**Key Considerations**:
- IB Gateway must stay connected during market hours
- Automatic reconnection on disconnect
- Session management (IBKR times out after inactivity)
- Paper vs Live mode switching via environment variable

---

## Kelly Criterion Position Sizing

### Mathematical Foundation

**Kelly Criterion Formula**:
```
f = (bp - q) / b

Where:
f = fraction of capital to wager
b = odds received on the wager (e.g., 2.0 for 2:1)
p = probability of winning
q = probability of losing (1 - p)
```

**For Stock Trading**:
```
f = (expected_return × p - (1 - p) × expected_loss) / expected_return

Simplified:
f = (win_rate × avg_win - loss_rate × avg_loss) / avg_win
```

**Half-Kelly Implementation**:
```python
kelly_fraction = calculate_kelly(win_rate, avg_win, avg_loss)
position_fraction = kelly_fraction * 0.5  # Halve for reduced volatility
position_size_usd = portfolio_value * position_fraction
```

### Implementation Details

**Input Requirements**:
1. **Win Rate**: From historical backtesting or Claude's confidence assessment
2. **Average Win**: Expected gain on winning trades (%)
3. **Average Loss**: Expected loss on losing trades (%)
4. **Current Portfolio Value**: From IBKR account

**Calculation Module** (`kelly_calculator.py`):

```python
import logging
from typing import Dict, Optional
from dataclasses import dataclass

@dataclass
class KellyInputs:
    """Inputs for Kelly Criterion calculation"""
    win_rate: float  # 0.0 to 1.0
    avg_win_pct: float  # Average winning trade return (e.g., 0.15 for 15%)
    avg_loss_pct: float  # Average losing trade return (e.g., 0.08 for 8% loss)
    confidence_adjustment: float = 1.0  # Reduce Kelly based on confidence
    
@dataclass
class PositionSizeResult:
    """Result of position sizing calculation"""
    kelly_fraction: float
    half_kelly_fraction: float
    position_size_usd: float
    position_size_shares: int
    warnings: list[str]
    
class KellyCalculator:
    """
    Calculates position sizes using Half-Kelly Criterion
    """
    
    # Safety limits
    MAX_POSITION_FRACTION = 0.25  # Never exceed 25% of portfolio
    MIN_POSITION_SIZE_USD = 5  # Minimum trade size
    MAX_POSITION_SIZE_USD = 50000  # Maximum single position (adjust as needed)
    
    def __init__(self, portfolio_value: float):
        self.portfolio_value = portfolio_value
        self.logger = logging.getLogger(__name__)
        
    def calculate_position_size(
        self,
        ticker: str,
        current_price: float,
        inputs: KellyInputs
    ) -> PositionSizeResult:
        """
        Calculate position size using Half-Kelly Criterion
        
        Args:
            ticker: Stock symbol
            current_price: Current share price
            inputs: Kelly calculation inputs
            
        Returns:
            PositionSizeResult with calculated size and warnings
        """
        warnings = []
        
        # Validate inputs
        if not (0 <= inputs.win_rate <= 1):
            raise ValueError(f"Win rate must be 0-1, got {inputs.win_rate}")
        if inputs.avg_win_pct <= 0:
            raise ValueError(f"Average win must be positive, got {inputs.avg_win_pct}")
        if inputs.avg_loss_pct >= 0:
            raise ValueError(f"Average loss must be negative, got {inputs.avg_loss_pct}")
            
        # Calculate Kelly fraction
        # f = (p * W - (1-p) * L) / W
        # Where W = average win, L = average loss (as positive number)
        p = inputs.win_rate
        W = inputs.avg_win_pct
        L = abs(inputs.avg_loss_pct)
        
        kelly_fraction = (p * W - (1 - p) * L) / W
        
        # Apply confidence adjustment
        kelly_fraction *= inputs.confidence_adjustment
        
        # Check if Kelly is negative (negative edge)
        if kelly_fraction <= 0:
            warnings.append(f"Negative Kelly fraction ({kelly_fraction:.4f}) - no edge detected")
            return PositionSizeResult(
                kelly_fraction=kelly_fraction,
                half_kelly_fraction=0,
                position_size_usd=0,
                position_size_shares=0,
                warnings=warnings
            )
        
        # Apply Half-Kelly
        half_kelly = kelly_fraction * 0.5
        
        # Check against maximum position fraction
        if half_kelly > self.MAX_POSITION_FRACTION:
            warnings.append(
                f"Half-Kelly ({half_kelly:.2%}) exceeds max ({self.MAX_POSITION_FRACTION:.2%}), "
                f"capping position size"
            )
            half_kelly = self.MAX_POSITION_FRACTION
            
        # Calculate dollar amount
        position_size_usd = self.portfolio_value * half_kelly
        
        # Apply absolute dollar limits
        if position_size_usd < self.MIN_POSITION_SIZE_USD:
            warnings.append(
                f"Position size ${position_size_usd:.2f} below minimum ${self.MIN_POSITION_SIZE_USD}, "
                f"skipping trade"
            )
            position_size_usd = 0
            
        if position_size_usd > self.MAX_POSITION_SIZE_USD:
            warnings.append(
                f"Position size ${position_size_usd:.2f} exceeds maximum ${self.MAX_POSITION_SIZE_USD}, "
                f"capping at max"
            )
            position_size_usd = self.MAX_POSITION_SIZE_USD
            
        # Calculate number of shares
        shares = int(position_size_usd / current_price)
        actual_position_usd = shares * current_price
        
        if shares == 0 and position_size_usd > 0:
            warnings.append(
                f"Share price ${current_price:.2f} too high for position size ${position_size_usd:.2f}"
            )
            
        self.logger.info(
            f"Position sizing for {ticker}: "
            f"Kelly={kelly_fraction:.4f}, Half-Kelly={half_kelly:.4f}, "
            f"${actual_position_usd:.2f} ({shares} shares @ ${current_price:.2f})"
        )
        
        return PositionSizeResult(
            kelly_fraction=kelly_fraction,
            half_kelly_fraction=half_kelly,
            position_size_usd=actual_position_usd,
            position_size_shares=shares,
            warnings=warnings
        )
    
    def get_kelly_inputs_from_analysis(
        self,
        claude_analysis: Dict
    ) -> KellyInputs:
        """
        Extract Kelly inputs from Claude's analysis
        
        Expected analysis format:
        {
            "win_probability": 0.65,  # 65% chance of profit
            "expected_gain_pct": 0.18,  # 18% expected gain
            "expected_loss_pct": -0.09,  # 9% expected loss
            "confidence": 0.8  # How confident Claude is (0-1)
        }
        """
        return KellyInputs(
            win_rate=claude_analysis.get("win_probability", 0.5),
            avg_win_pct=claude_analysis.get("expected_gain_pct", 0.15),
            avg_loss_pct=claude_analysis.get("expected_loss_pct", -0.08),
            confidence_adjustment=claude_analysis.get("confidence", 1.0)
        )
```

### Guardrails

**Hard Limits**:
- Maximum 25% of portfolio in any single position
- Minimum trade size: $100 (avoid excessive commission drag)
- Maximum position size: $50,000 (adjust based on account size)
- If Kelly is negative, do NOT trade (no edge)

**Dynamic Adjustments**:
- Reduce position size if Claude's confidence is low
- Scale down if portfolio is below certain threshold
- Increase minimum position size as portfolio grows

---

## Trading API Layer

### Core Module Structure

```
trading_api/
├── __init__.py
├── connection.py          # IB Gateway connection management
├── kelly_calculator.py    # Position sizing
├── order_manager.py       # Order creation and execution
├── risk_validator.py      # Pre-trade risk checks
├── portfolio_tracker.py   # Position and balance tracking
├── trade_logger.py        # Database logging
├── emergency.py           # Panic button and alerts
└── config.py             # Configuration management
```

### Connection Manager (`connection.py`)

```python
import logging
from typing import Optional
from ib_insync import IB, util
from contextlib import contextmanager
import time

class IBConnection:
    """Manages connection to IB Gateway"""
    
    def __init__(
        self,
        host: str = '127.0.0.1',
        port: int = 4002,
        client_id: int = 1,
        readonly: bool = False
    ):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.readonly = readonly
        self.ib = IB()
        self.logger = logging.getLogger(__name__)
        self._connected = False
        
    def connect(self, timeout: int = 30) -> bool:
        """
        Establish connection to IB Gateway
        
        Returns:
            True if connected successfully
        """
        if self._connected:
            self.logger.warning("Already connected")
            return True
            
        try:
            self.ib.connect(
                self.host,
                self.port,
                clientId=self.client_id,
                readonly=self.readonly,
                timeout=timeout
            )
            self._connected = True
            self.logger.info(f"Connected to IB Gateway at {self.host}:{self.port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to IB Gateway: {e}")
            return False
            
    def disconnect(self):
        """Disconnect from IB Gateway"""
        if self._connected:
            self.ib.disconnect()
            self._connected = False
            self.logger.info("Disconnected from IB Gateway")
            
    def is_connected(self) -> bool:
        """Check if connection is active"""
        return self._connected and self.ib.isConnected()
        
    def reconnect(self, max_attempts: int = 3) -> bool:
        """
        Attempt to reconnect with exponential backoff
        
        Returns:
            True if reconnected successfully
        """
        self.disconnect()
        
        for attempt in range(max_attempts):
            wait_time = 2 ** attempt
            self.logger.info(f"Reconnection attempt {attempt + 1}/{max_attempts}")
            
            if self.connect():
                return True
                
            if attempt < max_attempts - 1:
                self.logger.info(f"Waiting {wait_time}s before retry")
                time.sleep(wait_time)
                
        return False
        
    @contextmanager
    def connection_context(self):
        """Context manager for connection"""
        try:
            self.connect()
            yield self.ib
        finally:
            self.disconnect()
            
    def get_account_value(self, tag: str = 'NetLiquidation') -> float:
        """
        Get account value
        
        Args:
            tag: Account value tag (NetLiquidation, TotalCashValue, etc.)
            
        Returns:
            Account value as float
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to IB Gateway")
            
        account_values = self.ib.accountValues()
        
        for av in account_values:
            if av.tag == tag:
                return float(av.value)
                
        raise ValueError(f"Account value tag '{tag}' not found")
```

### Risk Validator (`risk_validator.py`)

```python
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, time as dt_time
import pytz

class RiskCheckResult(Enum):
    """Result of risk validation"""
    APPROVED = "approved"
    REJECTED = "rejected"
    WARNING = "warning"

@dataclass
class RiskCheck:
    """Individual risk check result"""
    name: str
    result: RiskCheckResult
    message: str
    details: Optional[Dict] = None

class RiskValidator:
    """
    Validates trades against safety rules before execution
    """
    
    # Trading limits
    MAX_TRADES_PER_DAY = 10
    MAX_TRADES_PER_WEEK = 30
    MAX_PORTFOLIO_CONCENTRATION = 0.30  # 30% max in any sector
    MAX_DAILY_LOSS_PCT = 0.03  # 3% max daily loss
    MAX_POSITION_PERCENT = 0.25  # 25% max per position
    
    # Market hours (US Eastern)
    MARKET_OPEN = dt_time(9, 30)
    MARKET_CLOSE = dt_time(16, 0)
    
    def __init__(self, db_connection, ib_connection):
        self.db = db_connection
        self.ib = ib_connection
        self.logger = logging.getLogger(__name__)
        
    def validate_trade(
        self,
        ticker: str,
        action: str,  # 'BUY' or 'SELL'
        quantity: int,
        current_price: float,
        reason: str
    ) -> List[RiskCheck]:
        """
        Run all risk checks on a proposed trade
        
        Returns:
            List of RiskCheck results
        """
        checks = []
        
        # 1. Market hours check
        checks.append(self._check_market_hours())
        
        # 2. Daily trade limit
        checks.append(self._check_daily_trade_limit())
        
        # 3. Weekly trade limit
        checks.append(self._check_weekly_trade_limit())
        
        # 4. Position size check
        checks.append(self._check_position_size(ticker, quantity, current_price))
        
        # 5. Portfolio concentration
        checks.append(self._check_portfolio_concentration(ticker, quantity, current_price))
        
        # 6. Daily loss limit
        checks.append(self._check_daily_loss_limit())
        
        # 7. Duplicate trade check
        checks.append(self._check_duplicate_trade(ticker, action))
        
        # 8. Account balance check
        checks.append(self._check_account_balance(quantity, current_price))
        
        return checks
        
    def _check_market_hours(self) -> RiskCheck:
        """Verify trading during market hours"""
        now = datetime.now(pytz.timezone('US/Eastern'))
        current_time = now.time()
        
        # Check if weekend
        if now.weekday() >= 5:  # Saturday or Sunday
            return RiskCheck(
                name="market_hours",
                result=RiskCheckResult.REJECTED,
                message="Market closed (weekend)"
            )
        
        # Check if during market hours
        if not (self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE):
            return RiskCheck(
                name="market_hours",
                result=RiskCheckResult.REJECTED,
                message=f"Outside market hours ({current_time.strftime('%H:%M')} ET)"
            )
            
        return RiskCheck(
            name="market_hours",
            result=RiskCheckResult.APPROVED,
            message="Within market hours"
        )
        
    def _check_daily_trade_limit(self) -> RiskCheck:
        """Check if daily trade limit exceeded"""
        today_trades = self._get_today_trade_count()
        
        if today_trades >= self.MAX_TRADES_PER_DAY:
            return RiskCheck(
                name="daily_trade_limit",
                result=RiskCheckResult.REJECTED,
                message=f"Daily trade limit reached ({today_trades}/{self.MAX_TRADES_PER_DAY})"
            )
            
        if today_trades >= self.MAX_TRADES_PER_DAY * 0.8:
            return RiskCheck(
                name="daily_trade_limit",
                result=RiskCheckResult.WARNING,
                message=f"Approaching daily limit ({today_trades}/{self.MAX_TRADES_PER_DAY})"
            )
            
        return RiskCheck(
            name="daily_trade_limit",
            result=RiskCheckResult.APPROVED,
            message=f"Daily trades: {today_trades}/{self.MAX_TRADES_PER_DAY}"
        )
        
    def _check_weekly_trade_limit(self) -> RiskCheck:
        """Check if weekly trade limit exceeded"""
        week_trades = self._get_week_trade_count()
        
        if week_trades >= self.MAX_TRADES_PER_WEEK:
            return RiskCheck(
                name="weekly_trade_limit",
                result=RiskCheckResult.REJECTED,
                message=f"Weekly trade limit reached ({week_trades}/{self.MAX_TRADES_PER_WEEK})"
            )
            
        return RiskCheck(
            name="weekly_trade_limit",
            result=RiskCheckResult.APPROVED,
            message=f"Weekly trades: {week_trades}/{self.MAX_TRADES_PER_WEEK}"
        )
        
    def _check_position_size(
        self,
        ticker: str,
        quantity: int,
        price: float
    ) -> RiskCheck:
        """Verify position size within limits"""
        portfolio_value = self.ib.get_account_value('NetLiquidation')
        position_value = quantity * price
        position_pct = position_value / portfolio_value
        
        if position_pct > self.MAX_POSITION_PERCENT:
            return RiskCheck(
                name="position_size",
                result=RiskCheckResult.REJECTED,
                message=f"Position {position_pct:.1%} exceeds max {self.MAX_POSITION_PERCENT:.1%}",
                details={
                    "position_value": position_value,
                    "portfolio_value": portfolio_value,
                    "position_pct": position_pct
                }
            )
            
        return RiskCheck(
            name="position_size",
            result=RiskCheckResult.APPROVED,
            message=f"Position size {position_pct:.1%} within limits"
        )
        
    def _check_portfolio_concentration(
        self,
        ticker: str,
        quantity: int,
        price: float
    ) -> RiskCheck:
        """Check sector/industry concentration limits"""
        # This requires sector mapping - implement based on your data
        # For now, placeholder
        return RiskCheck(
            name="portfolio_concentration",
            result=RiskCheckResult.APPROVED,
            message="Concentration check passed"
        )
        
    def _check_daily_loss_limit(self) -> RiskCheck:
        """Check if daily loss limit exceeded"""
        daily_pnl_pct = self._get_daily_pnl_percent()
        
        if daily_pnl_pct < -self.MAX_DAILY_LOSS_PCT:
            return RiskCheck(
                name="daily_loss_limit",
                result=RiskCheckResult.REJECTED,
                message=f"Daily loss {daily_pnl_pct:.2%} exceeds limit {-self.MAX_DAILY_LOSS_PCT:.2%}"
            )
            
        return RiskCheck(
            name="daily_loss_limit",
            result=RiskCheckResult.APPROVED,
            message=f"Daily P&L: {daily_pnl_pct:.2%}"
        )
        
    def _check_duplicate_trade(self, ticker: str, action: str) -> RiskCheck:
        """Prevent duplicate trades within short timeframe"""
        recent_trade = self._get_recent_trade(ticker, minutes=30)
        
        if recent_trade and recent_trade['action'] == action:
            return RiskCheck(
                name="duplicate_trade",
                result=RiskCheckResult.WARNING,
                message=f"Similar trade executed {recent_trade['minutes_ago']} minutes ago"
            )
            
        return RiskCheck(
            name="duplicate_trade",
            result=RiskCheckResult.APPROVED,
            message="No recent duplicate trades"
        )
        
    def _check_account_balance(self, quantity: int, price: float) -> RiskCheck:
        """Verify sufficient buying power"""
        required_cash = quantity * price * 1.05  # 5% buffer for fees
        available_cash = self.ib.get_account_value('TotalCashValue')
        
        if available_cash < required_cash:
            return RiskCheck(
                name="account_balance",
                result=RiskCheckResult.REJECTED,
                message=f"Insufficient funds (need ${required_cash:,.2f}, have ${available_cash:,.2f})"
            )
            
        return RiskCheck(
            name="account_balance",
            result=RiskCheckResult.APPROVED,
            message=f"Sufficient funds (${available_cash:,.2f} available)"
        )
        
    # Helper methods (implement based on your database schema)
    def _get_today_trade_count(self) -> int:
        """Get number of trades executed today"""
        # Query database for today's trades
        pass
        
    def _get_week_trade_count(self) -> int:
        """Get number of trades executed this week"""
        # Query database for this week's trades
        pass
        
    def _get_daily_pnl_percent(self) -> float:
        """Calculate today's P&L as percentage"""
        # Query account history or calculate from positions
        pass
        
    def _get_recent_trade(self, ticker: str, minutes: int) -> Optional[Dict]:
        """Get most recent trade for ticker within timeframe"""
        # Query database for recent trades
        pass
        
    def is_trade_approved(self, checks: List[RiskCheck]) -> bool:
        """
        Determine if trade should proceed based on checks
        
        Returns:
            True if no REJECTED checks found
        """
        return all(check.result != RiskCheckResult.REJECTED for check in checks)
```

### Order Manager (`order_manager.py`)

```python
import logging
from typing import Optional, Dict
from ib_insync import Stock, MarketOrder, LimitOrder, Order
from dataclasses import dataclass
from enum import Enum

class OrderStatus(Enum):
    """Order execution status"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"

@dataclass
class TradeResult:
    """Result of trade execution"""
    ticker: str
    action: str
    quantity: int
    order_type: str
    status: OrderStatus
    filled_price: Optional[float] = None
    commission: Optional[float] = None
    order_id: Optional[int] = None
    message: str = ""
    
class OrderManager:
    """Manages order creation and execution"""
    
    def __init__(self, ib_connection, trade_logger):
        self.ib = ib_connection
        self.logger = logging.getLogger(__name__)
        self.trade_logger = trade_logger
        
    def execute_market_order(
        self,
        ticker: str,
        action: str,  # 'BUY' or 'SELL'
        quantity: int,
        reason: str,
        dry_run: bool = False
    ) -> TradeResult:
        """
        Execute a market order
        
        Args:
            ticker: Stock symbol
            action: 'BUY' or 'SELL'
            quantity: Number of shares
            reason: Why this trade is being made
            dry_run: If True, simulate without executing
            
        Returns:
            TradeResult with execution details
        """
        self.logger.info(
            f"{'[DRY RUN] ' if dry_run else ''}Executing {action} {quantity} shares of {ticker}"
        )
        
        if dry_run:
            return TradeResult(
                ticker=ticker,
                action=action,
                quantity=quantity,
                order_type="MARKET",
                status=OrderStatus.PENDING,
                message="Dry run - order not submitted"
            )
            
        try:
            # Create stock contract
            contract = Stock(ticker, 'SMART', 'USD')
            
            # Qualify the contract
            self.ib.ib.qualifyContracts(contract)
            
            # Create market order
            order = MarketOrder(action, quantity)
            
            # Place order
            trade = self.ib.ib.placeOrder(contract, order)
            
            # Wait for fill (with timeout)
            self.ib.ib.sleep(1)  # Brief wait
            
            # Check status
            if trade.orderStatus.status == 'Filled':
                result = TradeResult(
                    ticker=ticker,
                    action=action,
                    quantity=quantity,
                    order_type="MARKET",
                    status=OrderStatus.FILLED,
                    filled_price=trade.orderStatus.avgFillPrice,
                    commission=trade.orderStatus.commission,
                    order_id=trade.order.orderId,
                    message="Order filled successfully"
                )
            else:
                result = TradeResult(
                    ticker=ticker,
                    action=action,
                    quantity=quantity,
                    order_type="MARKET",
                    status=OrderStatus.SUBMITTED,
                    order_id=trade.order.orderId,
                    message=f"Order submitted, status: {trade.orderStatus.status}"
                )
                
            # Log trade
            self.trade_logger.log_trade(result, reason)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to execute order: {e}")
            return TradeResult(
                ticker=ticker,
                action=action,
                quantity=quantity,
                order_type="MARKET",
                status=OrderStatus.FAILED,
                message=str(e)
            )
            
    def execute_limit_order(
        self,
        ticker: str,
        action: str,
        quantity: int,
        limit_price: float,
        reason: str,
        dry_run: bool = False
    ) -> TradeResult:
        """
        Execute a limit order
        
        Similar to market order but with price limit
        """
        # Implementation similar to execute_market_order but with LimitOrder
        pass
        
    def cancel_order(self, order_id: int) -> bool:
        """Cancel a pending order"""
        try:
            self.ib.ib.cancelOrder(order_id)
            self.logger.info(f"Cancelled order {order_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
            
    def get_open_orders(self) -> list:
        """Get list of open orders"""
        return self.ib.ib.openOrders()
```

---

## Database Schema

### Trade Logging Tables

```sql
-- Trades table
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    ticker VARCHAR(10) NOT NULL,
    action VARCHAR(4) NOT NULL,  -- 'BUY' or 'SELL'
    quantity INTEGER NOT NULL,
    order_type VARCHAR(20) NOT NULL,  -- 'MARKET', 'LIMIT', etc.
    status VARCHAR(20) NOT NULL,
    filled_price DECIMAL(10, 4),
    commission DECIMAL(10, 4),
    order_id INTEGER,
    reason TEXT,
    kelly_fraction DECIMAL(10, 6),
    half_kelly_fraction DECIMAL(10, 6),
    portfolio_value_at_trade DECIMAL(15, 2),
    dry_run BOOLEAN DEFAULT 0,
    INDEX idx_ticker (ticker),
    INDEX idx_timestamp (timestamp),
    INDEX idx_status (status)
);

-- Risk checks table
CREATE TABLE risk_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,
    check_name VARCHAR(50) NOT NULL,
    result VARCHAR(20) NOT NULL,  -- 'APPROVED', 'REJECTED', 'WARNING'
    message TEXT,
    details JSON,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trade_id) REFERENCES trades(id),
    INDEX idx_trade_id (trade_id)
);

-- Portfolio snapshots table
CREATE TABLE portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_value DECIMAL(15, 2),
    cash_balance DECIMAL(15, 2),
    positions JSON,  -- Array of current positions
    daily_pnl DECIMAL(15, 2),
    daily_pnl_pct DECIMAL(10, 4),
    INDEX idx_timestamp (timestamp)
);

-- Claude decisions table (for analysis)
CREATE TABLE claude_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    ticker VARCHAR(10),
    decision VARCHAR(20),  -- 'BUY', 'SELL', 'HOLD'
    confidence DECIMAL(5, 4),
    win_probability DECIMAL(5, 4),
    expected_gain_pct DECIMAL(10, 6),
    expected_loss_pct DECIMAL(10, 6),
    reasoning TEXT,
    data_sources JSON,  -- Which sources contributed
    trade_id INTEGER,  -- Link to actual trade if executed
    FOREIGN KEY (trade_id) REFERENCES trades(id),
    INDEX idx_ticker (ticker),
    INDEX idx_timestamp (timestamp)
);
```

---

## Emergency Controls

### Panic Button Implementation

```python
import requests
import logging
from typing import Optional

class EmergencyControls:
    """Emergency stop and alert system"""
    
    def __init__(self, discord_webhook_url: str, ib_connection):
        self.webhook_url = discord_webhook_url
        self.ib = ib_connection
        self.logger = logging.getLogger(__name__)
        self._panic_mode = False
        
    def trigger_panic(self, reason: str) -> bool:
        """
        Immediately halt all trading and alert
        
        Args:
            reason: Why panic was triggered
            
        Returns:
            True if successfully halted
        """
        self.logger.critical(f"PANIC TRIGGERED: {reason}")
        self._panic_mode = True
        
        # Cancel all open orders
        try:
            open_orders = self.ib.ib.openOrders()
            for order in open_orders:
                self.ib.ib.cancelOrder(order)
            self.logger.info(f"Cancelled {len(open_orders)} open orders")
        except Exception as e:
            self.logger.error(f"Failed to cancel orders during panic: {e}")
            
        # Send Discord alert
        self._send_alert(
            title="🚨 TRADING HALTED - PANIC MODE 🚨",
            description=f"Reason: {reason}",
            color=0xFF0000  # Red
        )
        
        return True
        
    def is_panic_mode(self) -> bool:
        """Check if system is in panic mode"""
        return self._panic_mode
        
    def reset_panic(self, authorized: bool = False) -> bool:
        """
        Reset panic mode (requires authorization)
        
        Args:
            authorized: Must be True to reset (prevents accidental reset)
        """
        if not authorized:
            self.logger.warning("Attempted to reset panic mode without authorization")
            return False
            
        self._panic_mode = False
        self.logger.info("Panic mode reset")
        
        self._send_alert(
            title="✅ Trading Resumed",
            description="Panic mode has been manually reset",
            color=0x00FF00  # Green
        )
        
        return True
        
    def send_trade_alert(
        self,
        ticker: str,
        action: str,
        quantity: int,
        price: float,
        reason: str
    ):
        """Send notification of trade execution"""
        self._send_alert(
            title=f"Trade Executed: {action} {ticker}",
            description=f"{quantity} shares @ ${price:.2f}\\nReason: {reason}",
            color=0x0099FF  # Blue
        )
        
    def send_risk_rejection(
        self,
        ticker: str,
        action: str,
        failed_checks: list
    ):
        """Send notification of rejected trade"""
        checks_str = "\\n".join([f"- {c.name}: {c.message}" for c in failed_checks])
        
        self._send_alert(
            title=f"Trade Rejected: {action} {ticker}",
            description=f"Failed checks:\\n{checks_str}",
            color=0xFFAA00  # Orange
        )
        
    def _send_alert(
        self,
        title: str,
        description: str,
        color: int = 0x0099FF
    ):
        """Send Discord webhook alert"""
        try:
            payload = {
                "embeds": [{
                    "title": title,
                    "description": description,
                    "color": color,
                    "timestamp": datetime.utcnow().isoformat()
                }]
            }
            
            response = requests.post(self.webhook_url, json=payload)
            response.raise_for_status()
            
        except Exception as e:
            self.logger.error(f"Failed to send Discord alert: {e}")
```

---

## Configuration Management

### Config File Structure (`config.json`)

```json
{
  "ibkr": {
    "host": "127.0.0.1",
    "port": 4002,
    "client_id": 1,
    "paper_trading": true
  },
  "risk_limits": {
    "max_position_percent": 0.25,
    "max_trades_per_day": 10,
    "max_trades_per_week": 30,
    "max_daily_loss_pct": 0.03,
    "min_position_size_usd": 100,
    "max_position_size_usd": 50000
  },
  "kelly": {
    "use_half_kelly": true,
    "max_kelly_fraction": 0.25,
    "default_confidence": 0.8
  },
  "trading": {
    "dry_run_mode": true,
    "market_orders_only": true,
    "require_manual_approval": false
  },
  "database": {
    "path": "/data/trading.db"
  },
  "alerts": {
    "discord_webhook_url": "${DISCORD_WEBHOOK_URL}",
    "alert_on_every_trade": false,
    "alert_on_rejected_trades": true,
    "alert_on_daily_loss_threshold": true
  }
}
```

---

## Integration with Overseer Claude

### API Interface for Overseer

The overseer Claude needs a simple, clean interface to request trades:

```python
from trading_api import TradingSystem

class OverseerInterface:
    """Clean interface for overseer Claude to request trades"""
    
    def __init__(self, config_path: str):
        self.trading_system = TradingSystem(config_path)
        
    def propose_trade(
        self,
        ticker: str,
        action: str,
        claude_analysis: Dict,
        reasoning: str
    ) -> Dict:
        """
        Propose a trade based on Claude's analysis
        
        Args:
            ticker: Stock symbol
            action: 'BUY' or 'SELL'
            claude_analysis: Dictionary with:
                - win_probability (0-1)
                - expected_gain_pct
                - expected_loss_pct
                - confidence (0-1)
            reasoning: Text explanation of trade rationale
            
        Returns:
            Dictionary with:
                - approved: bool
                - trade_result: TradeResult if executed
                - risk_checks: List of RiskCheck
                - position_size: Calculated position size
        """
        return self.trading_system.process_trade_request(
            ticker=ticker,
            action=action,
            analysis=claude_analysis,
            reason=reasoning
        )
        
    def get_portfolio_status(self) -> Dict:
        """Get current portfolio state"""
        return self.trading_system.get_portfolio_summary()
        
    def emergency_halt(self, reason: str):
        """Trigger emergency stop"""
        self.trading_system.emergency.trigger_panic(reason)
```

### Example Usage by Overseer

```python
# Overseer Claude makes a decision
overseer = OverseerInterface('/config/trading.json')

# Based on analysis from specialized Claude instances
analysis = {
    "win_probability": 0.68,
    "expected_gain_pct": 0.15,
    "expected_loss_pct": -0.07,
    "confidence": 0.85
}

result = overseer.propose_trade(
    ticker="AAPL",
    action="BUY",
    claude_analysis=analysis,
    reasoning="Strong technical setup + positive earnings surprise + sector momentum"
)

if result['approved']:
    print(f"Trade executed: {result['trade_result']}")
else:
    print(f"Trade rejected: {result['risk_checks']}")
```

---

## Testing Strategy

### Phase 1: Paper Trading (4-8 weeks)

**Objectives**:
- Validate Kelly Criterion calculations
- Test risk validation logic
- Verify IB Gateway integration
- Confirm logging and alerting

**Metrics to Track**:
- Trade execution success rate
- Position sizing accuracy
- Risk check effectiveness (false positives/negatives)
- System uptime and connection stability

**Success Criteria**:
- 95%+ successful order execution
- Zero violations of hard limits
- All alerts functioning correctly
- Complete audit trail in database

### Phase 2: Small Capital Live Trading (2-4 weeks)

**Starting Capital**: $1,000 - $5,000

**Objectives**:
- Validate real money execution
- Test emotional resilience of autonomous system
- Identify any paper-to-live discrepancies

**Additional Safeguards**:
- Manual review of first 20 trades
- Daily portfolio reviews
- Weekly performance analysis

### Phase 3: Full Deployment

**Only proceed if**:
- Positive returns in paper trading
- No critical bugs in small capital phase
- Risk systems proven effective
- Comfortable with autonomous operation

---

## Deployment Checklist

### Pre-Deployment

- [ ] IB Gateway container tested and stable
- [ ] Paper trading account configured
- [ ] Database schema created and tested
- [ ] All configuration files validated
- [ ] Discord webhooks tested
- [ ] Kelly calculator unit tests passed
- [ ] Risk validator unit tests passed
- [ ] Connection manager handles reconnections
- [ ] Dry-run mode tested extensively

### Paper Trading Phase

- [ ] Execute 50+ paper trades successfully
- [ ] All trade types tested (market, limit)
- [ ] Emergency halt tested
- [ ] Daily loss limit tested
- [ ] Position size limits tested
- [ ] Trade frequency limits tested
- [ ] Logging verified complete
- [ ] Performance tracking implemented

### Live Trading Preparation

- [ ] Review paper trading results
- [ ] Adjust Kelly parameters based on results
- [ ] Set initial capital allocation
- [ ] Configure live account credentials
- [ ] Test with minimum position sizes
- [ ] Establish monitoring routine
- [ ] Document emergency procedures

---

## Monitoring and Maintenance

### Daily Checks

- Portfolio value and positions
- Open orders status
- Risk limit usage (trades remaining, etc.)
- Database integrity
- IB Gateway connection status

### Weekly Reviews

- Trade performance analysis
- Kelly Criterion accuracy assessment
- Risk parameter adjustments if needed
- System logs review
- Database backups

### Monthly Analysis

- Overall portfolio performance
- Win rate vs. Kelly assumptions
- Average win/loss vs. expectations
- Sector concentration trends
- Commission costs analysis

---

## Security Considerations

### Credentials Management

- NEVER commit API keys or passwords to git
- Use environment variables for secrets
- Encrypt database at rest
- Secure Discord webhook URL

### Access Control

- IB Gateway VNC password protected
- Database file permissions restricted
- Trading API only accessible from trusted containers
- Emergency controls require authorization

### Audit Trail

- All trades logged with full context
- Risk check results preserved
- Claude decision reasoning stored
- Configuration changes tracked

---

## Cost Estimates

### Monthly Operational Costs

- **IBKR Paper Trading**: Free
- **IBKR Live Trading**: $0 with sufficient activity
- **FMP API**: $29/month (already planned)
- **Yellowbrick**: $30/month (already planned)
- **Substack**: $7/month (already planned)
- **Claude API**: $25/month estimated (already planned)
- **Server Costs**: Minimal (existing hardware)

**Total Additional Cost for Trading**: ~$0/month (using paper account initially)

### Break-Even Analysis

**With current data costs** (~$91/month):
- Need ~0.5-1% monthly return on $10k to cover costs
- At $20k: 0.25-0.5% monthly needed
- At $50k: 0.1-0.2% monthly needed

**Realistic Expectation**: Breaking even after costs is a success for an experimental autonomous system.

---

## Future Enhancements

### Phase 2 Features (Post-Initial Deployment)

1. **Options Trading**: Expand beyond stocks
2. **Short Selling**: Implement with stricter risk controls
3. **Portfolio Rebalancing**: Automated sector/position balancing
4. **Machine Learning**: Refine Kelly inputs based on historical accuracy
5. **Multi-Account Support**: Separate accounts for different strategies
6. **Advanced Orders**: Stop-loss, trailing stops, bracket orders

### Performance Optimization

1. **Backtesting Engine**: Historical validation of strategies
2. **Parameter Optimization**: Automated tuning of risk limits
3. **Cost Reduction**: Batch trades, optimize commission structure
4. **Latency Reduction**: Faster execution for time-sensitive trades

---

## Conclusion

This specification provides a comprehensive foundation for implementing autonomous trading execution with Interactive Brokers. The system emphasizes:

1. **Safety First**: Multiple layers of validation and hard limits
2. **Intelligent Sizing**: Kelly Criterion with conservative half-Kelly approach
3. **Complete Auditability**: Every decision and trade logged
4. **Emergency Controls**: Immediate halt capability with alerts
5. **Gradual Deployment**: Paper → Small Capital → Full deployment

The modular architecture allows for iterative development and testing, ensuring each component works correctly before integration. The extensive logging and monitoring enable continuous improvement based on actual performance data.

**Next Steps**:
1. Implement core modules (connection, kelly_calculator, risk_validator)
2. Set up IB Gateway container
3. Create database schema
4. Test with paper trading account
5. Integrate with overseer Claude
6. Begin paper trading phase

**Remember**: This is a learning experiment. The goal is to build a robust, safe, autonomous trading system while maintaining realistic expectations about profitability. The real value is in the knowledge gained about quantitative investing, system design, and risk management.


A Few Additional Thoughts:

IB Gateway Container: The spec uses the unusualvultures/ib-gateway Docker image. You might want to test this first - some people have success with it, others build their own. VNC access on port 5900 lets you monitor the Gateway visually if needed.
Paper Trading Duration: I suggested 4-8 weeks, but honestly you could probably compress this to 2-4 weeks if the system is executing flawlessly. The goal is pattern validation, not profitability testing.
Kelly Inputs: The spec assumes Claude provides win probability and expected gain/loss. You'll want to think about how the overseer derives these - historical analysis? Technical patterns? Might want to start conservative (0.5 win rate, 10% expected moves) until you have real data.
Database Choice: I went with SQLite for simplicity, but if you're doing serious analysis you might want PostgreSQL in its own container. SQLite is fine for < 10k trades though.
One Thing Missing: The spec doesn't include a "trade journal" where Claude reflects on why trades worked/failed. You might want to add a weekly review module where Claude analyzes trade outcomes vs. initial reasoning to improve future decisions. 
