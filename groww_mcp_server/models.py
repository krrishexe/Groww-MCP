"""
Data models for Groww MCP Server.
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
import uuid


class OrderType(str, Enum):
    """Order type enumeration."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL_M"


class OrderSide(str, Enum):
    """Order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Order status enumeration."""
    NEW = "NEW"
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    PARTIAL = "PARTIAL"


class ProductType(str, Enum):
    """Product type enumeration."""
    CNC = "CNC"  # Cash and Carry
    MIS = "MIS"  # Margin Intraday Square-off
    NRML = "NRML"  # Normal


class AlertType(str, Enum):
    """Alert type enumeration."""
    PERCENTAGE_INCREASE = "percentage_increase"
    PERCENTAGE_DECREASE = "percentage_decrease"
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    VOLUME_ABOVE = "volume_above"


class AlertStatus(str, Enum):
    """Alert status enumeration."""
    ACTIVE = "active"
    TRIGGERED = "triggered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class StockInfo(BaseModel):
    """Stock information model."""
    symbol: str = Field(..., description="Stock symbol (e.g., RELIANCE)")
    name: str = Field(..., description="Company name")
    exchange: str = Field(..., description="Exchange (NSE/BSE)")
    isin: Optional[str] = Field(None, description="ISIN code")
    sector: Optional[str] = Field(None, description="Sector")
    industry: Optional[str] = Field(None, description="Industry")


class StockPrice(BaseModel):
    """Stock price information model."""
    symbol: str = Field(..., description="Stock symbol")
    ltp: float = Field(..., description="Last traded price")
    open: float = Field(..., description="Opening price")
    high: float = Field(..., description="Day high")
    low: float = Field(..., description="Day low")
    close: float = Field(..., description="Previous close")
    volume: int = Field(..., description="Volume traded")
    change: float = Field(..., description="Price change")
    change_percent: float = Field(..., description="Price change percentage")
    timestamp: datetime = Field(..., description="Last update timestamp")


class PriceAlert(BaseModel):
    """Price alert model."""
    id: str = Field(default_factory=lambda: str(
        uuid.uuid4()), description="Unique alert ID")
    symbol: str = Field(..., description="Stock symbol to monitor")
    alert_type: AlertType = Field(..., description="Type of alert")
    threshold: float = Field(..., description="Alert threshold value")
    base_price: Optional[float] = Field(
        None, description="Base price for percentage alerts")
    current_price: Optional[float] = Field(
        None, description="Last checked price")
    status: AlertStatus = Field(AlertStatus.ACTIVE, description="Alert status")
    created_at: datetime = Field(
        default_factory=datetime.now, description="Alert creation time")
    triggered_at: Optional[datetime] = Field(
        None, description="Alert trigger time")
    message: Optional[str] = Field(None, description="Custom alert message")

    def is_triggered(self, current_price: float, current_volume: Optional[int] = None) -> bool:
        """Check if alert condition is met."""
        if self.status != AlertStatus.ACTIVE:
            return False

        if self.alert_type == AlertType.PERCENTAGE_INCREASE:
            if self.base_price is None:
                return False
            percentage_change = (
                (current_price - self.base_price) / self.base_price) * 100
            return percentage_change >= self.threshold

        elif self.alert_type == AlertType.PERCENTAGE_DECREASE:
            if self.base_price is None:
                return False
            percentage_change = (
                (self.base_price - current_price) / self.base_price) * 100
            return percentage_change >= self.threshold

        elif self.alert_type == AlertType.PRICE_ABOVE:
            return current_price >= self.threshold

        elif self.alert_type == AlertType.PRICE_BELOW:
            return current_price <= self.threshold

        elif self.alert_type == AlertType.VOLUME_ABOVE:
            return current_volume is not None and current_volume >= self.threshold

        return False

    def get_trigger_message(self, current_price: float, current_volume: Optional[int] = None) -> str:
        """Get formatted trigger message."""
        if self.alert_type == AlertType.PERCENTAGE_INCREASE:
            percentage = ((current_price - self.base_price) /
                          self.base_price) * 100
            return f"🚀 {self.symbol} is up {percentage:.2f}% (₹{self.base_price:.2f} → ₹{current_price:.2f})"

        elif self.alert_type == AlertType.PERCENTAGE_DECREASE:
            percentage = ((self.base_price - current_price) /
                          self.base_price) * 100
            return f"📉 {self.symbol} is down {percentage:.2f}% (₹{self.base_price:.2f} → ₹{current_price:.2f})"

        elif self.alert_type == AlertType.PRICE_ABOVE:
            return f"📈 {self.symbol} price is above ₹{self.threshold} (Current: ₹{current_price:.2f})"

        elif self.alert_type == AlertType.PRICE_BELOW:
            return f"📉 {self.symbol} price is below ₹{self.threshold} (Current: ₹{current_price:.2f})"

        elif self.alert_type == AlertType.VOLUME_ABOVE:
            return f"📊 {self.symbol} volume is above {self.threshold:,} (Current: {current_volume:,})"

        return f"Alert triggered for {self.symbol}"


class OrderRequest(BaseModel):
    """Order request model."""
    symbol: str = Field(..., description="Stock symbol")
    quantity: int = Field(..., description="Number of shares")
    order_type: OrderType = Field(..., description="Order type")
    order_side: OrderSide = Field(..., description="Buy or Sell")
    product_type: ProductType = Field(
        ProductType.CNC, description="Product type")
    price: Optional[float] = Field(
        None, description="Limit price (for limit orders)")
    trigger_price: Optional[float] = Field(
        None, description="Trigger price (for SL orders)")
    validity: str = Field("DAY", description="Order validity")


class Order(BaseModel):
    """Order model."""
    order_id: str = Field(..., description="Unique order ID")
    symbol: str = Field(..., description="Stock symbol")
    quantity: int = Field(..., description="Number of shares")
    executed_quantity: int = Field(0, description="Number of shares executed")
    order_type: OrderType = Field(..., description="Order type")
    order_side: OrderSide = Field(..., description="Buy or Sell")
    product_type: ProductType = Field(..., description="Product type")
    price: Optional[float] = Field(None, description="Order price")
    trigger_price: Optional[float] = Field(None, description="Trigger price")
    status: OrderStatus = Field(..., description="Order status")
    order_time: datetime = Field(..., description="Order placement time")
    execution_time: Optional[datetime] = Field(
        None, description="Order execution time")
    average_price: Optional[float] = Field(
        None, description="Average execution price")


class Holding(BaseModel):
    """Stock holding model."""
    symbol: str = Field(..., description="Stock symbol")
    quantity: int = Field(..., description="Number of shares held")
    average_price: float = Field(..., description="Average purchase price")
    current_price: float = Field(..., description="Current market price")
    market_value: float = Field(..., description="Current market value")
    pnl: float = Field(..., description="Profit/Loss")
    pnl_percent: float = Field(..., description="Profit/Loss percentage")
    product_type: ProductType = Field(..., description="Product type")


class Portfolio(BaseModel):
    """Portfolio model."""
    total_value: float = Field(..., description="Total portfolio value")
    invested_value: float = Field(..., description="Total invested amount")
    current_value: float = Field(..., description="Current market value")
    total_pnl: float = Field(..., description="Total profit/loss")
    total_pnl_percent: float = Field(..., description="Total P&L percentage")
    day_pnl: float = Field(..., description="Day's profit/loss")
    holdings: List[Holding] = Field(..., description="List of holdings")
    cash_balance: float = Field(..., description="Available cash balance")


class TradeCommand(BaseModel):
    """Natural language trade command model."""
    action: Literal["buy", "sell"] = Field(..., description="Trade action")
    symbol: str = Field(..., description="Stock symbol")
    quantity: Optional[int] = Field(None, description="Number of shares")
    amount: Optional[float] = Field(None, description="Amount in rupees")
    order_type: OrderType = Field(OrderType.MARKET, description="Order type")
    price: Optional[float] = Field(None, description="Limit price")


class APIResponse(BaseModel):
    """Standard API response model."""
    success: bool = Field(..., description="Request success status")
    message: str = Field(..., description="Response message")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")
    error: Optional[str] = Field(None, description="Error message if any")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Response timestamp")
