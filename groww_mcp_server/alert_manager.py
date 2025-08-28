"""
Alert Manager for Groww MCP Server.
Handles alert storage, checking, and comparison logic.
"""

import json
import logging
import asyncio
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path

from .models import PriceAlert, AlertType, AlertStatus
from .groww_client import GrowwClient
from .market_utils import (
    should_monitor_alerts, get_monitoring_interval, get_market_status,
    is_market_hours, get_ist_now
)
from .email_service import EmailService
from .email_config import email_config_manager

logger = logging.getLogger(__name__)


class AlertManager:
    """Manages price alerts for stocks."""

    def __init__(self, groww_client: GrowwClient, alerts_file: str = "alerts.json"):
        self.groww_client = groww_client
        self.alerts_file = Path(alerts_file)
        self.alerts: List[PriceAlert] = []
        self.monitoring_task: Optional[asyncio.Task] = None
        self.monitoring_interval = 180  # Default 3 minutes, will be dynamic
        self.email_service: Optional[EmailService] = None
        self.load_alerts()
        self._initialize_email_service()

    def _initialize_email_service(self) -> None:
        """Initialize email service if configuration is available."""
        try:
            if email_config_manager.is_configured():
                config = email_config_manager.get_config()
                self.email_service = EmailService(
                    smtp_server=config.smtp_server,
                    smtp_port=config.smtp_port,
                    username=config.username,
                    password=config.password,
                    from_email=config.from_email,
                    to_emails=config.to_emails,
                    use_tls=config.use_tls
                )
                logger.info(
                    f"Email service initialized successfully for {len(config.to_emails)} recipients")
            else:
                logger.info(
                    "Email service not configured - alerts will only be logged")
        except Exception as e:
            logger.error(f"Failed to initialize email service: {e}")
            self.email_service = None

    async def send_alert_notification(self, alert: PriceAlert, trigger_message: str, current_price: float) -> bool:
        """Send email notification for triggered alert."""
        if not self.email_service:
            logger.info(
                f"Email not configured - alert triggered: {trigger_message}")
            return False

        try:
            # Calculate percentage change if applicable
            percentage_change = None
            if alert.base_price and alert.alert_type in [AlertType.PERCENTAGE_INCREASE, AlertType.PERCENTAGE_DECREASE]:
                percentage_change = (
                    (current_price - alert.base_price) / alert.base_price) * 100

            # Send email
            success = await self.email_service.send_alert_email(
                alert_message=trigger_message,
                symbol=alert.symbol,
                current_price=current_price,
                base_price=alert.base_price,
                percentage_change=percentage_change
            )

            if success:
                logger.info(f"Email notification sent for alert {alert.id}")
                return True
            else:
                logger.warning(
                    f"Failed to send email notification for alert {alert.id}")
                return False

        except Exception as e:
            logger.error(
                f"Error sending email notification for alert {alert.id}: {e}")
            return False

    def load_alerts(self) -> None:
        """Load alerts from JSON file."""
        try:
            if self.alerts_file.exists():
                with open(self.alerts_file, 'r') as f:
                    data = json.load(f)
                    self.alerts = [PriceAlert(**alert)
                                   for alert in data.get('alerts', [])]
                logger.info(
                    f"Loaded {len(self.alerts)} alerts from {self.alerts_file}")
            else:
                self.alerts = []
                logger.info(
                    "No existing alerts file found, starting with empty alerts")
        except Exception as e:
            logger.error(f"Error loading alerts: {e}")
            self.alerts = []

    def save_alerts(self) -> None:
        """Save alerts to JSON file."""
        try:
            data = {
                'alerts': [alert.dict() for alert in self.alerts],
                'last_updated': datetime.now().isoformat()
            }
            with open(self.alerts_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.info(
                f"Saved {len(self.alerts)} alerts to {self.alerts_file}")
        except Exception as e:
            logger.error(f"Error saving alerts: {e}")

    async def create_alert(self, symbol: str, alert_type: AlertType, threshold: float,
                           base_price: Optional[float] = None, message: Optional[str] = None) -> PriceAlert:
        """Create a new price alert."""
        # Validate and normalize symbol
        symbol = symbol.upper().strip()

        # Try to get current price to validate symbol exists
        validated_symbol = symbol
        current_price_data = None

        # First try the symbol as-is
        try:
            current_price_data = await self.groww_client.get_stock_price(symbol)
            validated_symbol = symbol
        except Exception as e:
            logger.warning(
                f"Could not find stock with symbol '{symbol}', trying to search...")

            # If direct lookup fails, try searching for the symbol
            try:
                search_results = await self.groww_client.search_stocks(symbol)
                if search_results and len(search_results) > 0:
                    # Use the first search result
                    first_result = search_results[0]
                    validated_symbol = first_result.get(
                        'symbol', first_result.get('search_id', symbol))

                    # Try to get price with the found symbol
                    current_price_data = await self.groww_client.get_stock_price(validated_symbol)
                    logger.info(
                        f"Found stock '{validated_symbol}' through search for '{symbol}'")
                else:
                    raise ValueError(f"No stocks found matching '{symbol}'")
            except Exception as search_error:
                logger.error(
                    f"Error searching for stock '{symbol}': {search_error}")
                raise ValueError(
                    f"Could not find or validate stock symbol '{symbol}'. Please check the symbol and try again.")

        # If base_price not provided for percentage alerts, use the current price we just fetched
        if alert_type in [AlertType.PERCENTAGE_INCREASE, AlertType.PERCENTAGE_DECREASE]:
            if base_price is None:
                if current_price_data and hasattr(current_price_data, 'ltp'):
                    base_price = current_price_data.ltp
                elif current_price_data and isinstance(current_price_data, dict):
                    base_price = current_price_data.get(
                        'ltp') or current_price_data.get('price')
                else:
                    raise ValueError(
                        f"Could not get current price for {validated_symbol}")

        alert = PriceAlert(
            symbol=validated_symbol,
            alert_type=alert_type,
            threshold=threshold,
            base_price=base_price,
            message=message
        )

        self.alerts.append(alert)
        self.save_alerts()

        logger.info(
            f"Created alert {alert.id} for {validated_symbol}: {alert_type.value} {threshold}")
        return alert

    def get_alerts(self, symbol: Optional[str] = None, status: Optional[AlertStatus] = None) -> List[PriceAlert]:
        """Get alerts filtered by symbol and/or status."""
        filtered_alerts = self.alerts

        if symbol:
            filtered_alerts = [
                alert for alert in filtered_alerts if alert.symbol.upper() == symbol.upper()]

        if status:
            filtered_alerts = [
                alert for alert in filtered_alerts if alert.status == status]

        return filtered_alerts

    def get_alert_by_id(self, alert_id: str) -> Optional[PriceAlert]:
        """Get alert by ID."""
        for alert in self.alerts:
            if alert.id == alert_id:
                return alert
        return None

    def remove_alert(self, alert_id: str) -> bool:
        """Remove alert by ID (supports both full and partial IDs)."""
        # First try exact match
        for i, alert in enumerate(self.alerts):
            if alert.id == alert_id:
                removed_alert = self.alerts.pop(i)
                self.save_alerts()
                logger.info(
                    f"Removed alert {alert_id} for {removed_alert.symbol}")
                return True

        # If no exact match, try partial ID matching
        matching_alerts = [
            (i, alert) for i, alert in enumerate(self.alerts)
            if alert.id.startswith(alert_id)
        ]

        if len(matching_alerts) == 1:
            # Exactly one match found
            i, alert = matching_alerts[0]
            removed_alert = self.alerts.pop(i)
            self.save_alerts()
            logger.info(
                f"Removed alert {alert.id} (matched partial ID {alert_id}) for {removed_alert.symbol}")
            return True
        elif len(matching_alerts) > 1:
            # Multiple matches - this shouldn't happen in normal usage but let's be safe
            logger.warning(
                f"Multiple alerts match partial ID {alert_id}: {[alert.id for _, alert in matching_alerts]}")
            return False

        # No matches found
        logger.warning(f"No alert found matching ID: {alert_id}")
        return False

    def cancel_alert(self, alert_id: str) -> bool:
        """Cancel alert by ID (mark as cancelled)."""
        alert = self.get_alert_by_id(alert_id)
        if alert:
            alert.status = AlertStatus.CANCELLED
            self.save_alerts()
            logger.info(f"Cancelled alert {alert_id} for {alert.symbol}")
            return True
        return False

    async def check_single_alert(self, alert: PriceAlert) -> Optional[str]:
        """Check a single alert and return trigger message if triggered."""
        try:
            # Get current stock price
            price_data = await self.groww_client.get_stock_price(alert.symbol)
            current_price = price_data.ltp
            current_volume = price_data.volume

            # Update current price in alert
            alert.current_price = current_price

            # Check if alert is triggered
            if alert.is_triggered(current_price, current_volume):
                # Mark as triggered
                alert.status = AlertStatus.TRIGGERED
                alert.triggered_at = datetime.now()

                # Get trigger message
                trigger_message = alert.get_trigger_message(
                    current_price, current_volume)

                logger.info(f"Alert {alert.id} triggered: {trigger_message}")

                # Send email notification
                await self.send_alert_notification(alert, trigger_message, current_price)

                return trigger_message

            return None

        except Exception as e:
            logger.error(
                f"Error checking alert {alert.id} for {alert.symbol}: {e}")
            return None

    async def check_all_alerts(self) -> List[str]:
        """Check all active alerts and return list of trigger messages."""
        active_alerts = self.get_alerts(status=AlertStatus.ACTIVE)
        triggered_messages = []

        # Check market status before proceeding
        market_status = get_market_status()
        logger.info(
            f"Checking {len(active_alerts)} active alerts - Market: {market_status['status']}")

        # Only check alerts if we should be monitoring
        if not should_monitor_alerts():
            logger.info(
                f"Skipping alert check - market closed. Next session: {market_status['next_session']}")
            return triggered_messages

        for alert in active_alerts:
            trigger_message = await self.check_single_alert(alert)
            if trigger_message:
                triggered_messages.append(trigger_message)

        # Save alerts after checking (to update current prices and statuses)
        if active_alerts:
            self.save_alerts()

        return triggered_messages

    def start_monitoring(self, interval_seconds: int = None) -> None:
        """Start background monitoring of alerts with market-aware intervals."""
        # Use market-aware interval if not specified
        if interval_seconds is None:
            interval_seconds = get_monitoring_interval()

        self.monitoring_interval = interval_seconds

        if self.monitoring_task and not self.monitoring_task.done():
            logger.warning("Monitoring already started")
            return

        self.monitoring_task = asyncio.create_task(self._monitoring_loop())

        market_status = get_market_status()
        logger.info(
            f"Started alert monitoring - Market: {market_status['status']}, Interval: {interval_seconds}s")

    def stop_monitoring(self) -> None:
        """Stop background monitoring of alerts."""
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            logger.info("Stopped alert monitoring")
        else:
            logger.warning("No monitoring task to stop")

    async def _monitoring_loop(self) -> None:
        """Background monitoring loop with market hours awareness."""
        logger.info("Alert monitoring loop started (market-aware)")

        try:
            while True:
                market_status = get_market_status()

                # Check if we should monitor based on market hours
                if should_monitor_alerts():
                    logger.debug(
                        f"Market open - checking alerts ({market_status['status']})")
                    triggered_messages = await self.check_all_alerts()

                    if triggered_messages:
                        logger.info(
                            f"Found {len(triggered_messages)} triggered alerts")
                        for message in triggered_messages:
                            # TODO: Send email notification here in next step
                            logger.info(f"ALERT TRIGGERED: {message}")

                    # Use market-appropriate interval
                    wait_time = get_monitoring_interval()
                else:
                    # Market is closed - wait longer
                    wait_time = 3600  # 1 hour
                    logger.info(
                        f"Market closed ({market_status['status']}) - sleeping for {wait_time}s until {market_status['next_session']}")

                # Wait for next check
                await asyncio.sleep(wait_time)

        except asyncio.CancelledError:
            logger.info("Alert monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")

    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status with market information."""
        is_running = self.monitoring_task and not self.monitoring_task.done()
        market_status = get_market_status()

        return {
            "monitoring_active": is_running,
            "monitoring_interval": get_monitoring_interval(),
            "market_status": market_status['status'],
            "market_hours": market_status['is_market_hours'],
            "should_monitor": should_monitor_alerts(),
            "next_session": market_status['next_session'],
            "total_alerts": len(self.alerts),
            "active_alerts": len(self.get_alerts(status=AlertStatus.ACTIVE)),
            "triggered_alerts": len(self.get_alerts(status=AlertStatus.TRIGGERED)),
            "cancelled_alerts": len(self.get_alerts(status=AlertStatus.CANCELLED)),
            "ist_time": get_ist_now().strftime('%Y-%m-%d %H:%M:%S IST')
        }

    async def parse_alert_command(self, command: str) -> Dict[str, Any]:
        """
        Parse natural language alert command using LLM-extracted structured data.

        This method expects the calling LLM to have already extracted the key information
        and now focuses on validation and stock symbol resolution.

        The LLM should extract and provide:
        - stock_name: The company name or symbol mentioned
        - alert_type_hint: The type of alert (percentage_up, percentage_down, price_above, price_below)
        - threshold_value: The numeric threshold
        - original_command: The full original command for context

        Args:
            command: Either the original natural language command OR a JSON string 
                    containing pre-parsed structured data from the LLM

        Returns:
            Dict containing validated alert parameters
        """
        # Try to parse as JSON first (structured data from LLM)
        try:
            import json
            parsed_data = json.loads(command)

            # Extract structured data
            stock_name = parsed_data.get('stock_name', '').strip()
            alert_type_hint = parsed_data.get(
                'alert_type_hint', '').lower().strip()
            threshold_value = parsed_data.get('threshold_value')
            original_command = parsed_data.get('original_command', command)

            logger.info(
                f"Processing structured alert data: {stock_name}, {alert_type_hint}, {threshold_value}")

        except (json.JSONDecodeError, TypeError):
            # Fallback: Try to extract basic information from natural language
            # This is a simple fallback - the LLM should ideally provide structured data
            logger.info(
                "No structured data provided, attempting basic extraction from natural language")

            stock_name, alert_type_hint, threshold_value = await self._extract_basic_alert_info(command)
            original_command = command

            if not stock_name:
                return {
                    "error": "Could not identify stock name. Please provide the company name or stock symbol clearly.",
                    "suggestion": "Try: 'Set alert for RELIANCE when it goes up by 5%' or 'Alert me when TCS price goes above ₹3500'"
                }

        # Validate and resolve stock symbol
        try:
            validated_symbol = await self._resolve_and_validate_stock(stock_name)
        except ValueError as e:
            return {
                "error": str(e),
                "suggestion": f"Stock '{stock_name}' not found. Try searching for the stock first or use the exact stock symbol."
            }

        # Map alert type hint to AlertType enum
        alert_type = self._map_alert_type(alert_type_hint)
        if not alert_type:
            return {
                "error": f"Could not determine alert type from '{alert_type_hint}'",
                "suggestion": "Supported alert types: percentage increase/decrease, price above/below threshold"
            }

        # Validate threshold value
        if threshold_value is None or not isinstance(threshold_value, (int, float)):
            return {
                "error": "Could not determine threshold value",
                "suggestion": "Please specify a clear numeric threshold (e.g., '5%', '₹2500', 'above 1800')"
            }

        threshold_value = float(threshold_value)

        # For percentage alerts, get current price as base price
        base_price = None
        if alert_type in [AlertType.PERCENTAGE_INCREASE, AlertType.PERCENTAGE_DECREASE]:
            try:
                current_price_data = await self.groww_client.get_stock_price(validated_symbol)
                base_price = current_price_data.ltp
                logger.info(
                    f"Using current price ₹{base_price} as base for percentage alert")
            except Exception as e:
                return {
                    "error": f"Could not get current price for {validated_symbol}: {str(e)}",
                    "suggestion": "Please try again or specify a base price manually"
                }

                return {
                    "symbol": validated_symbol,
                    "alert_type": alert_type,
                    "threshold": threshold_value,
                    "base_price": base_price,
                    "message": f"Alert created from: {original_command}"
                }

    async def _extract_basic_alert_info(self, command: str) -> Tuple[str, str, float]:
        """
        Basic fallback extraction for when structured data isn't provided.
        This is much simpler than the old hardcoded approach.
        """
        import re

        # Simple patterns for fallback (much more flexible than before)
        stock_pattern = r'\b([A-Z]{2,}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        percentage_pattern = r'(\d+(?:\.\d+)?)\s*%'
        price_pattern = r'(?:₹|Rs\.?\s*)?(\d+(?:\.\d+)?)'

        # Extract potential stock names (any capitalized words)
        stock_matches = re.findall(stock_pattern, command)
        # Filter out common words
        common_words = {'SET', 'ALERT', 'FOR', 'IF', 'IT', 'GOES', 'UP',
                        'DOWN', 'BY', 'WHEN', 'ABOVE', 'BELOW', 'ME', 'THE', 'A', 'AND', 'OR'}
        potential_stocks = [
            s for s in stock_matches if s.upper() not in common_words and len(s) >= 2]

        stock_name = potential_stocks[0] if potential_stocks else ""

        # Determine alert type and threshold
        alert_type_hint = ""
        threshold_value = 0.0

        if "up" in command.lower() and "%" in command:
            alert_type_hint = "percentage_increase"
            percentage_match = re.search(percentage_pattern, command)
            if percentage_match:
                threshold_value = float(percentage_match.group(1))

        elif "down" in command.lower() and "%" in command:
            alert_type_hint = "percentage_decrease"
            percentage_match = re.search(percentage_pattern, command)
            if percentage_match:
                threshold_value = float(percentage_match.group(1))

        elif "above" in command.lower():
            alert_type_hint = "price_above"
            price_match = re.search(price_pattern, command)
            if price_match:
                threshold_value = float(price_match.group(1))

        elif "below" in command.lower():
            alert_type_hint = "price_below"
            price_match = re.search(price_pattern, command)
            if price_match:
                threshold_value = float(price_match.group(1))

        return stock_name, alert_type_hint, threshold_value

    async def _resolve_and_validate_stock(self, stock_name: str) -> str:
        """
        Resolve stock name to symbol and validate it exists.
        Uses the existing dynamic search logic but simplified.
        """
        stock_name = stock_name.upper().strip()

        # Try direct lookup first
        try:
            price_data = await self.groww_client.get_stock_price(stock_name)
            logger.info(f"Direct stock lookup successful for '{stock_name}'")
            return stock_name
        except Exception:
            logger.debug(
                f"Direct lookup failed for '{stock_name}', trying search...")

        # Search for the stock
        try:
            search_results = await self.groww_client.search_stocks(stock_name)
            if search_results and len(search_results) > 0:
                # Use the first/best result
                best_result = search_results[0]
                validated_symbol = best_result.get(
                    'symbol', best_result.get('search_id', stock_name))

                # Verify the found symbol works
                await self.groww_client.get_stock_price(validated_symbol)
                logger.info(
                    f"Found and validated stock '{validated_symbol}' for search '{stock_name}'")
                return validated_symbol
            else:
                raise ValueError(f"No stocks found matching '{stock_name}'")

        except Exception as e:
            logger.error(f"Stock resolution failed for '{stock_name}': {e}")
            raise ValueError(
                f"Could not find or validate stock '{stock_name}'. Please check the name and try again.")

    def _map_alert_type(self, alert_type_hint: str) -> Optional[AlertType]:
        """Map natural language alert type hints to AlertType enum."""
        alert_type_hint = alert_type_hint.lower().strip()

        # Flexible mapping for various ways to express alert types
        type_mappings = {
            # Percentage increase
            'percentage_increase': AlertType.PERCENTAGE_INCREASE,
            'percent_increase': AlertType.PERCENTAGE_INCREASE,
            'percentage_up': AlertType.PERCENTAGE_INCREASE,
            'percent_up': AlertType.PERCENTAGE_INCREASE,
            'up_by_percent': AlertType.PERCENTAGE_INCREASE,
            'increase_by_percent': AlertType.PERCENTAGE_INCREASE,
            'rise_by_percent': AlertType.PERCENTAGE_INCREASE,

            # Percentage decrease
            'percentage_decrease': AlertType.PERCENTAGE_DECREASE,
            'percent_decrease': AlertType.PERCENTAGE_DECREASE,
            'percentage_down': AlertType.PERCENTAGE_DECREASE,
            'percent_down': AlertType.PERCENTAGE_DECREASE,
            'down_by_percent': AlertType.PERCENTAGE_DECREASE,
            'decrease_by_percent': AlertType.PERCENTAGE_DECREASE,
            'fall_by_percent': AlertType.PERCENTAGE_DECREASE,
            'drop_by_percent': AlertType.PERCENTAGE_DECREASE,

            # Price above
            'price_above': AlertType.PRICE_ABOVE,
            'above_price': AlertType.PRICE_ABOVE,
            'price_over': AlertType.PRICE_ABOVE,
            'over_price': AlertType.PRICE_ABOVE,
            'price_exceeds': AlertType.PRICE_ABOVE,
            'exceeds_price': AlertType.PRICE_ABOVE,
            'price_crosses_up': AlertType.PRICE_ABOVE,
            'goes_above': AlertType.PRICE_ABOVE,

            # Price below
            'price_below': AlertType.PRICE_BELOW,
            'below_price': AlertType.PRICE_BELOW,
            'price_under': AlertType.PRICE_BELOW,
            'under_price': AlertType.PRICE_BELOW,
            'price_falls_below': AlertType.PRICE_BELOW,
            'falls_below': AlertType.PRICE_BELOW,
            'price_crosses_down': AlertType.PRICE_BELOW,
            'goes_below': AlertType.PRICE_BELOW,

            # Volume alerts
            'volume_above': AlertType.VOLUME_ABOVE,
            'volume_over': AlertType.VOLUME_ABOVE,
            'high_volume': AlertType.VOLUME_ABOVE,
        }

        return type_mappings.get(alert_type_hint)
