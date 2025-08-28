"""
Groww MCP Server - Main server implementation.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Sequence, Dict, List, Optional
from datetime import datetime

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .config import config
from .groww_client import GrowwClient, GrowwAPIError
from .command_parser import command_parser
from .alert_manager import AlertManager
from .models import (
    OrderRequest, OrderType, OrderSide, ProductType,
    TradeCommand, APIResponse, AlertType, AlertStatus
)

# Configure logging to use stderr and avoid interfering with MCP protocol
logging.basicConfig(
    level=getattr(logging, config.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Initialize MCP server
server = Server("groww-mcp-server")

# Global alert manager instance (will be initialized in main)
alert_manager: Optional[AlertManager] = None


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """List all available tools."""
    return [
        types.Tool(
            name="buy_stock",
            description="Execute a buy order for stocks. Supports both quantity and amount-based orders.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Natural language buy command (e.g., 'buy 5 stocks of RELIANCE' or 'buy ₹1000 worth of TCS')"
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol (e.g., RELIANCE, TCS) - optional if included in command"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Number of shares to buy - optional if amount is specified"
                    },
                    "amount": {
                        "type": "number",
                        "description": "Amount in rupees to buy - optional if quantity is specified"
                    },
                    "order_type": {
                        "type": "string",
                        "enum": ["MARKET", "LIMIT"],
                        "description": "Order type - defaults to MARKET"
                    },
                    "price": {
                        "type": "number",
                        "description": "Limit price (required for LIMIT orders)"
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "Confirmation flag - must be true to execute the order"
                    }
                },
                "required": ["command"]
            }
        ),
        types.Tool(
            name="sell_stock",
            description="Execute a sell order for stocks. Supports both quantity and amount-based orders.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Natural language sell command (e.g., 'sell 10 stocks of TCS' or 'sell all my RELIANCE')"
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol (e.g., RELIANCE, TCS) - optional if included in command"
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Number of shares to sell - optional if amount is specified"
                    },
                    "amount": {
                        "type": "number",
                        "description": "Amount in rupees to sell - optional if quantity is specified"
                    },
                    "order_type": {
                        "type": "string",
                        "enum": ["MARKET", "LIMIT"],
                        "description": "Order type - defaults to MARKET"
                    },
                    "price": {
                        "type": "number",
                        "description": "Limit price (required for LIMIT orders)"
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "Confirmation flag - must be true to execute the order"
                    }
                },
                "required": ["command"]
            }
        ),
        types.Tool(
            name="get_stock_price",
            description="Get current price information for a stock.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol (e.g., RELIANCE, TCS)"
                    }
                },
                "required": ["symbol"]
            }
        ),
        types.Tool(
            name="get_portfolio",
            description="Get complete portfolio information including holdings and P&L.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="get_holdings",
            description="Get current stock holdings.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="get_orders",
            description="Get list of recent orders.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["ALL", "PENDING", "EXECUTED", "CANCELLED"],
                        "description": "Filter orders by status - defaults to ALL"
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date for filtering orders (YYYY-MM-DD format) - optional"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date for filtering orders (YYYY-MM-DD format) - optional"
                    }
                }
            }
        ),
        types.Tool(
            name="cancel_order",
            description="Cancel a pending order.",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Order ID to cancel"
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "Confirmation flag - must be true to cancel the order"
                    }
                },
                "required": ["order_id", "confirm"]
            }
        ),
        types.Tool(
            name="search_stocks",
            description="Search for stocks by name or symbol.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (company name or stock symbol)"
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="get_market_status",
            description="Get current market status and trading hours.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="parse_trade_command",
            description="Parse and validate a natural language trading command without executing it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Natural language trading command to parse"
                    }
                },
                "required": ["command"]
            }
        ),
        types.Tool(
            name="set_price_alert",
            description="Set a price alert for a stock with various conditions (percentage change, price threshold, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Natural language alert command (e.g., 'Set alert for TRIDENT if it goes up by 2%' or 'Alert me when RELIANCE goes above ₹2500')"
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol (e.g., RELIANCE, TCS) - optional if included in command"
                    },
                    "alert_type": {
                        "type": "string",
                        "enum": ["percentage_increase", "percentage_decrease", "price_above", "price_below", "volume_above"],
                        "description": "Type of alert"
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Alert threshold value (percentage for percentage alerts, price for price alerts)"
                    },
                    "base_price": {
                        "type": "number",
                        "description": "Base price for percentage alerts (uses current price if not specified)"
                    }
                },
                "required": ["command"]
            }
        ),
        types.Tool(
            name="list_alerts",
            description="List all price alerts or filter by symbol/status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Filter alerts by stock symbol (optional)"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["active", "triggered", "cancelled", "expired"],
                        "description": "Filter alerts by status (optional)"
                    }
                }
            }
        ),
        types.Tool(
            name="remove_alert",
            description="Remove a specific price alert by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "alert_id": {
                        "type": "string",
                        "description": "Alert ID to remove"
                    }
                },
                "required": ["alert_id"]
            }
        ),
        types.Tool(
            name="check_alerts",
            description="Manually check all active alerts and return any triggered alerts.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="alert_status",
            description="Get alert monitoring status and statistics.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="configure_email",
            description="Configure email settings for alert notifications. Supports multiple recipients.",
            inputSchema={
                "type": "object",
                "properties": {
                    "smtp_server": {
                        "type": "string",
                        "description": "SMTP server address (e.g., 'smtp.gmail.com')"
                    },
                    "smtp_port": {
                        "type": "integer",
                        "description": "SMTP port (587 for TLS, 465 for SSL)"
                    },
                    "username": {
                        "type": "string",
                        "description": "SMTP username (usually your email address)"
                    },
                    "password": {
                        "type": "string",
                        "description": "SMTP password (use app password for Gmail)"
                    },
                    "from_email": {
                        "type": "string",
                        "description": "From email address with optional name"
                    },
                    "to_email": {
                        "type": "string",
                        "description": "Single recipient email address (for backward compatibility)"
                    },
                    "to_emails": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Array of recipient email addresses (supports multiple recipients)"
                    },
                    "use_tls": {
                        "type": "boolean",
                        "description": "Whether to use TLS encryption (default: true)"
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["gmail", "outlook", "custom"],
                        "description": "Email provider for preset configuration"
                    }
                }
            }
        ),
        types.Tool(
            name="test_email",
            description="Send a test email to verify email configuration.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="email_status",
            description="Get email configuration status and settings.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="disable_email",
            description="Disable email notifications for alerts.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="enable_email",
            description="Enable email notifications for alerts.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls."""
    try:
        # Validate configuration with detailed error messages
        if not config.validate():
            validation_errors = config.get_validation_errors()
            error_message = "❌ **Configuration Error**\n\nThe following issues need to be resolved:\n\n"
            for error in validation_errors:
                error_message += f"• {error}\n"
            error_message += "\n💡 **How to fix:**\n"
            error_message += "1. Set the GROWW_ACCESS_TOKEN environment variable\n"
            error_message += "2. Get your access token from Groww's developer portal\n"
            error_message += "3. Restart the MCP server after setting the token\n"

            return [types.TextContent(
                type="text",
                text=error_message
            )]

        if name == "buy_stock":
            return await handle_buy_stock(arguments)
        elif name == "sell_stock":
            return await handle_sell_stock(arguments)
        elif name == "get_stock_price":
            return await handle_get_stock_price(arguments)
        elif name == "get_portfolio":
            return await handle_get_portfolio(arguments)
        elif name == "get_holdings":
            return await handle_get_holdings(arguments)
        elif name == "get_orders":
            return await handle_get_orders(arguments)
        elif name == "cancel_order":
            return await handle_cancel_order(arguments)
        elif name == "search_stocks":
            return await handle_search_stocks(arguments)
        elif name == "get_market_status":
            return await handle_get_market_status(arguments)
        elif name == "parse_trade_command":
            return await handle_parse_trade_command(arguments)
        elif name == "set_price_alert":
            return await handle_set_price_alert(arguments)
        elif name == "list_alerts":
            return await handle_list_alerts(arguments)
        elif name == "remove_alert":
            return await handle_remove_alert(arguments)
        elif name == "check_alerts":
            return await handle_check_alerts(arguments)
        elif name == "alert_status":
            return await handle_alert_status(arguments)
        elif name == "configure_email":
            return await handle_configure_email(arguments)
        elif name == "test_email":
            return await handle_test_email(arguments)
        elif name == "email_status":
            return await handle_email_status(arguments)
        elif name == "disable_email":
            return await handle_disable_email(arguments)
        elif name == "enable_email":
            return await handle_enable_email(arguments)
        else:
            return [types.TextContent(
                type="text",
                text=f"❌ Unknown tool: {name}"
            )]

    except Exception as e:
        logger.error(f"Error in tool call {name}: {str(e)}")
        return [types.TextContent(
            type="text",
            text=f"❌ Error: {str(e)}"
        )]


async def handle_buy_stock(arguments: dict) -> list[types.TextContent]:
    """Handle buy stock command."""
    command = arguments.get("command", "")
    confirm = arguments.get("confirm", False)

    # Parse the command
    parsed_command = command_parser.parse_command(command)

    if not parsed_command:
        suggestions = command_parser.suggest_corrections(command)
        return [types.TextContent(
            type="text",
            text=f"❌ Could not parse command: '{command}'\n\nSuggestions:\n" + "\n".join(
                f"• {s}" for s in suggestions)
        )]

    if parsed_command.action != "buy":
        return [types.TextContent(
            type="text",
            text="❌ This is not a buy command. Use the sell_stock tool for selling."
        )]

    # Override with explicit parameters if provided
    symbol = arguments.get("symbol", parsed_command.symbol)
    quantity = arguments.get("quantity", parsed_command.quantity)
    amount = arguments.get("amount", parsed_command.amount)
    order_type = OrderType(arguments.get(
        "order_type", parsed_command.order_type.value))
    price = arguments.get("price", parsed_command.price)

    # Validate required fields
    if not symbol:
        return [types.TextContent(
            type="text",
            text="❌ Stock symbol is required"
        )]

    if not quantity and not amount:
        return [types.TextContent(
            type="text",
            text="❌ Either quantity or amount must be specified"
        )]

    if order_type == OrderType.LIMIT and not price:
        return [types.TextContent(
            type="text",
            text="❌ Price is required for limit orders"
        )]

    # Show order preview
    if not confirm:
        preview = f"""
📋 **Buy Order Preview**

**Stock:** {symbol}
**Action:** BUY
**Quantity:** {quantity if quantity else 'TBD (based on amount)'}
**Amount:** {f'₹{amount:,.2f}' if amount else 'TBD (based on quantity)'}
**Order Type:** {order_type.value}
**Price:** {f'₹{price:,.2f}' if price else 'Market Price'}

⚠️ **This is a preview only. To execute this order, add `"confirm": true` to your request.**

💡 **Example:**
"""
        preview += '```json\n{"command": "' + \
            command + '", "confirm": true}\n```'
        return [types.TextContent(type="text", text=preview)]

    # Execute the order
    async with GrowwClient() as client:
        try:
            # If amount is specified, get current price to calculate quantity
            if amount and not quantity:
                stock_price = await client.get_stock_price(symbol)
                quantity = int(amount / stock_price.ltp)
                if quantity == 0:
                    return [types.TextContent(
                        type="text",
                        text=f"❌ Amount ₹{amount:,.2f} is too small to buy even 1 share of {symbol} (current price: ₹{stock_price.ltp:,.2f})"
                    )]

            order_request = OrderRequest(
                symbol=symbol,
                quantity=quantity,
                order_type=order_type,
                order_side=OrderSide.BUY,
                product_type=ProductType.CNC,
                price=price,
                validity="DAY"
            )

            order = await client.place_order(order_request)

            success_msg = f"""
✅ **Buy Order Placed Successfully**

**Order ID:** {order.order_id}
**Stock:** {order.symbol}
**Quantity:** {order.quantity} shares
**Order Type:** {order.order_type.value}
**Status:** {order.status.value}
**Order Time:** {order.order_time.strftime('%Y-%m-%d %H:%M:%S')}
"""
            if order.price:
                success_msg += f"**Price:** ₹{order.price:,.2f}\n"

            return [types.TextContent(type="text", text=success_msg)]

        except GrowwAPIError as e:
            return [types.TextContent(
                type="text",
                text=f"❌ Failed to place buy order: {str(e)}"
            )]


async def handle_sell_stock(arguments: dict) -> list[types.TextContent]:
    """Handle sell stock command."""
    command = arguments.get("command", "")
    confirm = arguments.get("confirm", False)

    # Parse the command
    parsed_command = command_parser.parse_command(command)

    if not parsed_command:
        suggestions = command_parser.suggest_corrections(command)
        return [types.TextContent(
            type="text",
            text=f"❌ Could not parse command: '{command}'\n\nSuggestions:\n" + "\n".join(
                f"• {s}" for s in suggestions)
        )]

    if parsed_command.action != "sell":
        return [types.TextContent(
            type="text",
            text="❌ This is not a sell command. Use the buy_stock tool for buying."
        )]

    # Override with explicit parameters if provided
    symbol = arguments.get("symbol", parsed_command.symbol)
    quantity = arguments.get("quantity", parsed_command.quantity)
    amount = arguments.get("amount", parsed_command.amount)
    order_type = OrderType(arguments.get(
        "order_type", parsed_command.order_type.value))
    price = arguments.get("price", parsed_command.price)

    # Validate required fields
    if not symbol:
        return [types.TextContent(
            type="text",
            text="❌ Stock symbol is required"
        )]

    if not quantity and not amount:
        return [types.TextContent(
            type="text",
            text="❌ Either quantity or amount must be specified"
        )]

    if order_type == OrderType.LIMIT and not price:
        return [types.TextContent(
            type="text",
            text="❌ Price is required for limit orders"
        )]

    # Show order preview
    if not confirm:
        preview = f"""
📋 **Sell Order Preview**

**Stock:** {symbol}
**Action:** SELL
**Quantity:** {quantity if quantity else 'TBD (based on amount)'}
**Amount:** {f'₹{amount:,.2f}' if amount else 'TBD (based on quantity)'}
**Order Type:** {order_type.value}
**Price:** {f'₹{price:,.2f}' if price else 'Market Price'}

⚠️ **This is a preview only. To execute this order, add `"confirm": true` to your request.**

💡 **Example:**
"""
        preview += '```json\n{"command": "' + \
            command + '", "confirm": true}\n```'
        return [types.TextContent(type="text", text=preview)]

    # Execute the order
    async with GrowwClient() as client:
        try:
            # If amount is specified, get current price to calculate quantity
            if amount and not quantity:
                stock_price = await client.get_stock_price(symbol)
                quantity = int(amount / stock_price.ltp)
                if quantity == 0:
                    return [types.TextContent(
                        type="text",
                        text=f"❌ Amount ₹{amount:,.2f} is too small to sell even 1 share of {symbol} (current price: ₹{stock_price.ltp:,.2f})"
                    )]

            order_request = OrderRequest(
                symbol=symbol,
                quantity=quantity,
                order_type=order_type,
                order_side=OrderSide.SELL,
                product_type=ProductType.CNC,
                price=price,
                validity="DAY"
            )

            order = await client.place_order(order_request)

            success_msg = f"""
✅ **Sell Order Placed Successfully**

**Order ID:** {order.order_id}
**Stock:** {order.symbol}
**Quantity:** {order.quantity} shares
**Order Type:** {order.order_type.value}
**Status:** {order.status.value}
**Order Time:** {order.order_time.strftime('%Y-%m-%d %H:%M:%S')}
"""
            if order.price:
                success_msg += f"**Price:** ₹{order.price:,.2f}\n"

            return [types.TextContent(type="text", text=success_msg)]

        except GrowwAPIError as e:
            return [types.TextContent(
                type="text",
                text=f"❌ Failed to place sell order: {str(e)}"
            )]


async def handle_get_stock_price(arguments: dict) -> list[types.TextContent]:
    """Handle get stock price."""
    symbol = arguments.get("symbol", "").upper()

    if not symbol:
        return [types.TextContent(
            type="text",
            text="❌ Stock symbol is required"
        )]

    async with GrowwClient() as client:
        try:
            # Get live stock price data
            stock_price = await client.get_stock_price(symbol)

            # Format the price information
            price_change_indicator = "📈" if stock_price.change >= 0 else "📉"

            stock_msg = f"""
📊 **{symbol} - Live Stock Price**

**Current Price (LTP):** ₹{stock_price.ltp:,.2f}
**Open:** ₹{stock_price.open:,.2f}
**High:** ₹{stock_price.high:,.2f}
**Low:** ₹{stock_price.low:,.2f}
**Previous Close:** ₹{stock_price.close:,.2f}

**Day Change:** {price_change_indicator} ₹{stock_price.change:+.2f} ({stock_price.change_percent:+.2f}%)
**Volume:** {stock_price.volume:,} shares

**Last Updated:** {stock_price.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

💡 **Live data from Groww API**
"""

            return [types.TextContent(type="text", text=stock_msg)]

        except GrowwAPIError as e:
            # If direct price fetch fails, try to get basic stock info
            try:
                stock_results = await client.search_stocks(symbol)
                if stock_results:
                    stock = stock_results[0]
                    fallback_msg = f"""
📊 **{symbol} Stock Information**

**Company:** {stock.name}
**Exchange:** {stock.exchange}
**Trading Symbol:** {stock.symbol}
"""
                    if stock.isin:
                        fallback_msg += f"**ISIN:** {stock.isin}\n"
                    if stock.sector:
                        fallback_msg += f"**Sector:** {stock.sector}\n"
                    if stock.industry:
                        fallback_msg += f"**Industry:** {stock.industry}\n"

                    fallback_msg += f"""

⚠️ **Live price data temporarily unavailable**
Error: {str(e)}

💡 **To get live prices, try:**
• Using your Groww trading app
• Checking financial websites like NSE, BSE, or Moneycontrol
"""
                    return [types.TextContent(type="text", text=fallback_msg)]
                else:
                    return [types.TextContent(
                        type="text",
                        text=f"❌ Stock symbol '{symbol}' not found. Please check the symbol and try again."
                    )]
            except Exception as fallback_error:
                return [types.TextContent(
                    type="text",
                    text=f"❌ Failed to get information for {symbol}: {str(e)}"
                )]


async def handle_get_portfolio(arguments: dict) -> list[types.TextContent]:
    """Handle get portfolio."""
    async with GrowwClient() as client:
        try:
            portfolio = await client.get_portfolio()

            portfolio_msg = f"""
💼 **Portfolio Summary**

**Total Portfolio Value:** ₹{portfolio.total_value:,.2f}
**Total Invested:** ₹{portfolio.invested_value:,.2f}
**Cash Balance:** ₹{portfolio.cash_balance:,.2f}

**Holdings ({len(portfolio.holdings)} stocks):**
"""

            for holding in portfolio.holdings:
                invested_value = holding.quantity * holding.average_price
                portfolio_msg += f"""
• **{holding.symbol}**
  Quantity: {holding.quantity} shares
  Average Price: ₹{holding.average_price:.2f}
  Total Invested: ₹{invested_value:,.2f}
"""

            portfolio_msg += f"""

📝 **Note:** Real-time P&L calculations are limited by API permissions.
This shows your holdings with purchase prices. For current market prices,
use a trading platform or market data service.
"""

            return [types.TextContent(type="text", text=portfolio_msg)]

        except GrowwAPIError as e:
            return [types.TextContent(
                type="text",
                text=f"❌ Failed to get portfolio: {str(e)}"
            )]


async def handle_get_holdings(arguments: dict) -> list[types.TextContent]:
    """Handle get holdings."""
    async with GrowwClient() as client:
        try:
            holdings = await client.get_holdings()

            if not holdings:
                return [types.TextContent(
                    type="text",
                    text="📭 **No Holdings Found**\n\nYou don't have any stock holdings currently."
                )]

            holdings_msg = f"📊 **Current Holdings ({len(holdings)} stocks)**\n\n"

            for holding in holdings:
                pnl_indicator = "📈" if holding.pnl >= 0 else "📉"
                holdings_msg += f"""**{holding.symbol}**
• Quantity: {holding.quantity} shares
• Average Price: ₹{holding.average_price:.2f}
• Current Price: ₹{holding.current_price:.2f}
• Market Value: ₹{holding.market_value:,.2f}
• P&L: {pnl_indicator} ₹{holding.pnl:,.2f} ({holding.pnl_percent:+.2f}%)

"""

            return [types.TextContent(type="text", text=holdings_msg)]

        except GrowwAPIError as e:
            return [types.TextContent(
                type="text",
                text=f"❌ Failed to get holdings: {str(e)}"
            )]


async def handle_get_orders(arguments: dict) -> list[types.TextContent]:
    """Handle get orders."""
    status_filter = arguments.get("status", "ALL")
    start_date = arguments.get("start_date")
    end_date = arguments.get("end_date")

    # Parse and validate dates if provided
    start_date_obj = None
    end_date_obj = None

    try:
        if start_date:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()

        # Validate date range
        if start_date_obj and end_date_obj and start_date_obj > end_date_obj:
            return [types.TextContent(
                type="text",
                text="❌ **Invalid Date Range**\n\nStart date must be before or equal to end date."
            )]
    except ValueError as e:
        return [types.TextContent(
            type="text",
            text=f"❌ **Invalid Date Format**\n\nPlease use YYYY-MM-DD format for dates. Error: {str(e)}"
        )]

    async with GrowwClient() as client:
        try:
            orders = await client.get_orders()
            original_count = len(orders)

            # Filter orders by status
            if status_filter != "ALL":
                orders = [
                    order for order in orders if order.status.value == status_filter]

            # Filter orders by date range
            if start_date_obj or end_date_obj:
                filtered_orders = []
                for order in orders:
                    order_date = order.order_time.date()

                    # Check if order falls within the date range
                    if start_date_obj and order_date < start_date_obj:
                        continue
                    if end_date_obj and order_date > end_date_obj:
                        continue

                    filtered_orders.append(order)

                orders = filtered_orders

            if not orders:
                message = f"📭 **No Orders Found**\n\n"
                if start_date or end_date:
                    date_range = ""
                    if start_date and end_date:
                        date_range = f"between {start_date} and {end_date}"
                    elif start_date:
                        date_range = f"from {start_date} onwards"
                    elif end_date:
                        date_range = f"up to {end_date}"

                    message += f"No orders found {date_range}"
                    if status_filter != "ALL":
                        message += f" with status: {status_filter}"
                    message += f"\n\nTotal orders fetched: {original_count}"
                else:
                    if original_count == 0:
                        message += """📊 **Understanding Groww Order Data**

The Groww API has specific limitations:
• `get_order_list` only shows **orders placed today** (current trading day)
• Historical orders from previous days are not available through this endpoint
• However, we **reconstruct historical trade data** from your holdings and positions

**What we checked:**
• ✅ Current day orders: Available but none found today
• ✅ Historical trades: Reconstructed from holdings/positions data
• ✅ Holdings data: Shows your actual trading activity

**Your actual trading activity:**
• Use `get_holdings` to see your current stock positions
• Each holding shows the average price you paid (historical trade data)
• Positions data shows individual buy/sell transactions

💡 **To see your trading history:** Use `get_holdings` or `get_portfolio` commands."""
                    else:
                        message += f"No orders found with status: {status_filter}"

                return [types.TextContent(type="text", text=message)]

            # Create summary header with explanation
            orders_msg = f"📋 **Orders Found ({len(orders)} orders"
            if start_date or end_date:
                date_range = ""
                if start_date and end_date:
                    date_range = f"between {start_date} and {end_date}"
                elif start_date:
                    date_range = f"from {start_date}"
                elif end_date:
                    date_range = f"up to {end_date}"
                orders_msg += f" {date_range}"
            if status_filter != "ALL":
                orders_msg += f", status: {status_filter}"
            orders_msg += f")**\n\n"

            # Count order types
            current_day_orders = [
                o for o in orders if not o.order_id.startswith("HIST-")]
            historical_orders = [
                o for o in orders if o.order_id.startswith("HIST-")]

            if historical_orders:
                orders_msg += f"""📊 **Order Data Sources:**
• **Current Day Orders:** {len(current_day_orders)} (from Groww API)
• **Historical Trades:** {len(historical_orders)} (reconstructed from holdings/positions)

💡 **Note:** Groww's `get_order_list` API only shows current day orders. Historical trades are reconstructed from your portfolio data.

"""

            if original_count > len(orders):
                orders_msg += f"*Showing {len(orders)} of {original_count} total orders*\n\n"

            # Sort orders by date (newest first)
            orders.sort(key=lambda x: x.order_time, reverse=True)

            for order in orders:
                status_icon = {
                    "PENDING": "⏳",
                    "EXECUTED": "✅",
                    "CANCELLED": "❌",
                    "REJECTED": "🚫",
                    "PARTIAL": "🔄"
                }.get(order.status.value, "❓")

                orders_msg += f"""**{order.order_id}** {status_icon}
• Stock: {order.symbol}
• Action: {order.order_side.value}
• Quantity: {order.quantity} shares
• Type: {order.order_type.value}
• Status: {order.status.value}
• Order Time: {order.order_time.strftime('%Y-%m-%d %H:%M:%S')}
"""
                if order.price:
                    orders_msg += f"• Price: ₹{order.price:.2f}\n"
                if order.average_price:
                    orders_msg += f"• Avg Price: ₹{order.average_price:.2f}\n"

                orders_msg += "\n"

            return [types.TextContent(type="text", text=orders_msg)]

        except GrowwAPIError as e:
            error_message = str(e)

            # Detect authentication issues
            if "Authentication failed" in error_message or "expired or is invalid" in error_message:
                return [types.TextContent(
                    type="text",
                    text=f"""🔐 **Authentication Error**

❌ **Your Groww API token has expired or is invalid.**

**What this means:**
• Your API access token is no longer valid
• You need to get a fresh token from Groww
• This is a common issue as API tokens expire periodically

**🔧 How to fix this:**

1. **Get a new API token:**
   • Log into your Groww account
   • Go to the API/Developer section
   • Generate a new access token

2. **Update your environment:**
   • Set the new token: `GROWW_ACCESS_TOKEN=your_new_token`
   • Restart this MCP server

3. **Test the connection:**
   • Try fetching orders again after updating the token

**💡 Pro tip:** API tokens typically expire every 30-90 days for security reasons.

**Error details:** {error_message}"""
                )]

            # Other API errors
            return [types.TextContent(
                type="text",
                text=f"""❌ **API Connection Error**

Failed to retrieve orders from Groww API.

**Error details:** {error_message}

**Possible solutions:**
• Check your internet connection
• Verify your API token is valid
• Try again in a few moments
• Contact Groww support if the issue persists

**Need help?** Use the diagnostic script: `python debug_orders.py`"""
            )]


async def handle_cancel_order(arguments: dict) -> list[types.TextContent]:
    """Handle cancel order."""
    order_id = arguments.get("order_id", "")
    confirm = arguments.get("confirm", False)

    if not order_id:
        return [types.TextContent(
            type="text",
            text="❌ Order ID is required"
        )]

    if not confirm:
        return [types.TextContent(
            type="text",
            text=f"⚠️ **Order Cancellation Preview**\n\nYou are about to cancel order: {order_id}\n\nTo confirm, add `\"confirm\": true` to your request."
        )]

    async with GrowwClient() as client:
        try:
            success = await client.cancel_order(order_id)

            if success:
                return [types.TextContent(
                    type="text",
                    text=f"✅ **Order Cancelled Successfully**\n\nOrder {order_id} has been cancelled."
                )]
            else:
                return [types.TextContent(
                    type="text",
                    text=f"❌ **Failed to Cancel Order**\n\nOrder {order_id} could not be cancelled. It may already be executed or doesn't exist."
                )]

        except GrowwAPIError as e:
            return [types.TextContent(
                type="text",
                text=f"❌ Failed to cancel order {order_id}: {str(e)}"
            )]


async def handle_search_stocks(arguments: dict) -> list[types.TextContent]:
    """Handle search stocks."""
    query = arguments.get("query", "")

    if not query:
        return [types.TextContent(
            type="text",
            text="❌ Search query is required"
        )]

    async with GrowwClient() as client:
        try:
            stocks = await client.search_stocks(query)

            if not stocks:
                return [types.TextContent(
                    type="text",
                    text=f"❌ **No Results Found**\n\nNo stocks found for query: '{query}'"
                )]

            search_msg = f"🔍 **Search Results for '{query}' ({len(stocks)} results)**\n\n"

            for stock in stocks[:10]:  # Limit to top 10 results
                search_msg += f"""**{stock.symbol}** - {stock.name}
• Exchange: {stock.exchange}
"""
                if stock.sector:
                    search_msg += f"• Sector: {stock.sector}\n"
                if stock.industry:
                    search_msg += f"• Industry: {stock.industry}\n"

                search_msg += "\n"

            if len(stocks) > 10:
                search_msg += f"... and {len(stocks) - 10} more results"

            return [types.TextContent(type="text", text=search_msg)]

        except GrowwAPIError as e:
            return [types.TextContent(
                type="text",
                text=f"❌ Failed to search stocks: {str(e)}"
            )]


async def handle_get_market_status(arguments: dict) -> list[types.TextContent]:
    """Handle get market status."""
    async with GrowwClient() as client:
        try:
            market_status = await client.get_market_status()

            status_msg = f"""
🕐 **Market Status**

**Current Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Market Status:** {market_status.get('status', 'Unknown')}

**Trading Hours:**
• NSE: {market_status.get('nse_hours', 'N/A')}
• BSE: {market_status.get('bse_hours', 'N/A')}

**Next Session:** {market_status.get('next_session', 'N/A')}
"""

            return [types.TextContent(type="text", text=status_msg)]

        except GrowwAPIError as e:
            return [types.TextContent(
                type="text",
                text=f"❌ Failed to get market status: {str(e)}"
            )]


async def handle_parse_trade_command(arguments: dict) -> list[types.TextContent]:
    """Handle parse trade command."""
    command = arguments.get("command", "")

    if not command:
        return [types.TextContent(
            type="text",
            text="❌ Command is required"
        )]

    parsed_command = command_parser.parse_command(command)

    if not parsed_command:
        suggestions = command_parser.suggest_corrections(command)
        return [types.TextContent(
            type="text",
            text=f"❌ **Could not parse command:** '{command}'\n\n**Suggestions:**\n" + "\n".join(
                f"• {s}" for s in suggestions)
        )]

    parse_msg = f"""
✅ **Command Parsed Successfully**

**Original Command:** {command}

**Parsed Details:**
• Action: {parsed_command.action.upper()}
• Stock Symbol: {parsed_command.symbol}
• Quantity: {parsed_command.quantity if parsed_command.quantity else 'Not specified'}
• Amount: {f'₹{parsed_command.amount:,.2f}' if parsed_command.amount else 'Not specified'}
• Order Type: {parsed_command.order_type.value}
• Price: {f'₹{parsed_command.price:.2f}' if parsed_command.price else 'Market Price'}

💡 **Ready to execute:** Use the `{parsed_command.action}_stock` tool with this command to place the order.
"""

    return [types.TextContent(type="text", text=parse_msg)]


async def handle_set_price_alert(arguments: dict) -> list[types.TextContent]:
    """Handle set price alert."""
    global alert_manager

    if not alert_manager:
        return [types.TextContent(
            type="text",
            text="❌ Alert manager not initialized"
        )]

    command = arguments.get("command", "")

    if not command:
        return [types.TextContent(
            type="text",
            text="❌ Command is required"
        )]

    try:
        # Import market utils for status
        from .market_utils import get_market_status

        # Try to parse the natural language command (now async)
        parsed_alert = await alert_manager.parse_alert_command(command)

        # Check if parsing returned an error
        if "error" in parsed_alert:
            return [types.TextContent(
                type="text",
                text=f"""❌ **Alert Parsing Error**

{parsed_alert['error']}

💡 **{parsed_alert.get('suggestion', 'Please try again with a clearer command')}**

🤖 **For Advanced Users (LLM Integration):**
You can also provide structured data in JSON format:
```json
{{
  "stock_name": "RELIANCE",
  "alert_type_hint": "percentage_increase",
  "threshold_value": 5.0,
  "original_command": "Set alert for Reliance when it goes up by 5%"
}}
```

**Supported alert_type_hints:**
• `percentage_increase` / `percentage_decrease`
• `price_above` / `price_below`
• `volume_above`

**Example Commands:**
• 'Set alert for RELIANCE if it goes up by 2%'
• 'Alert me when TCS goes down by 5%'
• 'Set alert for HDFC Bank if it goes above ₹1600'
• 'Alert when Infosys goes below ₹1400'"""
            )]

        # Create the alert (this will validate the symbol)
        alert = await alert_manager.create_alert(
            symbol=parsed_alert["symbol"],
            alert_type=parsed_alert["alert_type"],
            threshold=parsed_alert["threshold"],
            # Use .get() since it might not be provided
            base_price=parsed_alert.get("base_price"),
            message=parsed_alert.get("message")
        )

        # Get market status for context
        market_status = get_market_status()

        alert_msg = f"""
✅ **Price Alert Set Successfully**

**Alert Details:**
• **Alert ID:** {alert.id}
• **Stock:** {alert.symbol}
• **Type:** {alert.alert_type.value.replace('_', ' ').title()}
• **Threshold:** {alert.threshold}{'%' if 'percentage' in alert.alert_type.value else ('₹' if 'price' in alert.alert_type.value else '')}
• **Base Price:** {f'₹{alert.base_price:.2f} (current price)' if alert.base_price is not None else 'N/A (price threshold alert)'}
• **Status:** {alert.status.value.title()}
• **Created:** {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}

**Market Context:**
• **Market Status:** {market_status.get('status', 'Unknown')}
• **Monitoring:** {'Active' if market_status.get('is_market_hours', False) or market_status.get('is_pre_market', False) else 'Paused (will resume when market opens)'}
• **Next Check:** {'Every 3 minutes' if market_status.get('is_market_hours', False) else f"When market reopens ({market_status.get('next_session', 'Unknown')})"}

💡 **The alert will be checked automatically during market hours (9:15 AM - 3:30 PM IST).**

🔍 **Dynamic Search Used:** Found '{alert.symbol}' by intelligently searching the stock database for your input.
"""

        return [types.TextContent(type="text", text=alert_msg)]

    except ValueError as e:
        error_msg = str(e)
        if "Could not find any stock matching" in error_msg:
            return [types.TextContent(
                type="text",
                text=f"""❌ **Stock Not Found**

{error_msg}

💡 **What happened:**
• The system intelligently searched for your stock using multiple strategies
• No matching stocks were found in the database
• This could be due to an incorrect name or an unlisted stock

🔍 **Suggestions:**
• Try using the `search_stocks` tool first to explore available stocks
• Check the spelling of the company name
• Try using the stock's trading symbol (e.g., 'RELIANCE', 'TCS')
• Try a shorter version of the name (e.g., 'Reliance' instead of 'Reliance Industries')

**Example Commands:**
• 'Set alert for Reliance if it goes up by 2%'
• 'Alert me when TCS goes down by 5%'
• 'Set alert for HDFC Bank if it goes above ₹1600'
• 'Alert when Infosys goes below ₹1400'"""
            )]
        elif "Could not identify any potential stock name" in error_msg:
            return [types.TextContent(
                type="text",
                text=f"""❌ **Could Not Parse Stock Name**

{error_msg}

💡 **Examples of valid commands:**
• 'Set alert for RELIANCE if it goes up by 2%'
• 'Alert me when TCS goes down by 5%'
• 'Set alert for Waaree Energies if it goes down by 3%'
• 'Alert when State Bank of India goes above ₹500'
• 'Set alert for HDFC Bank if it goes below ₹1500'

🤖 **How it works:**
• The system dynamically searches for ANY stock you mention
• No hardcoded lists - works with all available stocks
• Handles both company names and stock symbols
• Automatically finds the best match"""
            )]
        else:
            return [types.TextContent(
                type="text",
                text=f"❌ Could not parse alert command: {error_msg}\n\n💡 **Examples:**\n• 'Set alert for any stock name if it goes up by 2%'\n• 'Alert me when any company goes above ₹X'\n• 'Set alert for any stock if it goes down by 5%'"
            )]
    except Exception as e:
        logger.error(f"Error setting alert: {e}")
        return [types.TextContent(
            type="text",
            text=f"❌ Failed to set alert: {str(e)}"
        )]


async def handle_list_alerts(arguments: dict) -> list[types.TextContent]:
    """Handle list alerts."""
    global alert_manager

    if not alert_manager:
        return [types.TextContent(
            type="text",
            text="❌ Alert manager not initialized"
        )]

    symbol = arguments.get("symbol")
    status = arguments.get("status")
    status_filter = AlertStatus(status) if status else None

    try:
        alerts = alert_manager.get_alerts(symbol=symbol, status=status_filter)

        if not alerts:
            filter_text = ""
            if symbol:
                filter_text += f" for {symbol}"
            if status:
                filter_text += f" with status {status}"

            return [types.TextContent(
                type="text",
                text=f"📭 **No Alerts Found**\n\nYou don't have any alerts{filter_text}."
            )]

        alerts_msg = f"📋 **Price Alerts ({len(alerts)} alerts)**\n\n"

        for alert in alerts:
            status_emoji = {
                "active": "🟢",
                "triggered": "🔴",
                "cancelled": "❌",
                "expired": "⏰"
            }.get(alert.status.value, "❓")

            alert_type_text = alert.alert_type.value.replace('_', ' ').title()

            alerts_msg += f"""**{status_emoji} {alert.id[:8]}...** 
• **Stock:** {alert.symbol}
• **Type:** {alert_type_text}
• **Threshold:** {alert.threshold}{'%' if 'percentage' in alert.alert_type.value else ('₹' if 'price' in alert.alert_type.value else '')}
• **Base Price:** {f'₹{alert.base_price:.2f}' if alert.base_price is not None else 'N/A'}
• **Current Price:** {f'₹{alert.current_price:.2f}' if alert.current_price is not None else 'N/A'}
• **Status:** {alert.status.value.title()}
• **Created:** {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}
{f'• **Triggered:** {alert.triggered_at.strftime("%Y-%m-%d %H:%M:%S")}' if alert.triggered_at else ''}

"""

        return [types.TextContent(type="text", text=alerts_msg)]

    except Exception as e:
        logger.error(f"Error listing alerts: {e}")
        return [types.TextContent(
            type="text",
            text=f"❌ Failed to list alerts: {str(e)}"
        )]


async def handle_remove_alert(arguments: dict) -> list[types.TextContent]:
    """Handle remove alert."""
    global alert_manager

    if not alert_manager:
        return [types.TextContent(
            type="text",
            text="❌ Alert manager not initialized"
        )]

    alert_id = arguments.get("alert_id", "")

    if not alert_id:
        return [types.TextContent(
            type="text",
            text="❌ Alert ID is required"
        )]

    try:
        # Get all alerts to provide context
        all_alerts = alert_manager.get_alerts()

        success = alert_manager.remove_alert(alert_id)

        if success:
            return [types.TextContent(
                type="text",
                text=f"✅ **Alert Removed Successfully**\n\nAlert {alert_id} has been removed.\n\n📊 **Remaining alerts:** {len(alert_manager.get_alerts())}"
            )]
        else:
            # Provide helpful error message with context
            if not all_alerts:
                return [types.TextContent(
                    type="text",
                    text=f"""❌ **No Alerts Found**

You don't have any alerts to remove.

💡 **To create alerts:** Use `set_price_alert` with commands like:
• "Set alert for RELIANCE if it goes up by 5%"
• "Alert me when TCS goes above ₹3500"
"""
                )]

            # Find similar IDs for suggestions
            similar_alerts = []
            for alert in all_alerts:
                if alert_id.lower() in alert.id.lower() or alert.id.startswith(alert_id):
                    similar_alerts.append(alert)

            error_msg = f"""❌ **Alert Not Found**

Could not find alert with ID: `{alert_id}`

📋 **Available Alerts ({len(all_alerts)} total):**"""

            for i, alert in enumerate(all_alerts[:5], 1):  # Show first 5
                status_emoji = "🟢" if alert.status.value == "active" else "🔴"
                error_msg += f"\n{i}. {status_emoji} `{alert.id[:8]}...` - {alert.symbol} ({alert.alert_type.value.replace('_', ' ').title()})"

            if len(all_alerts) > 5:
                error_msg += f"\n... and {len(all_alerts) - 5} more"

            error_msg += f"""

💡 **How to remove alerts:**
• Use partial ID: `{all_alerts[0].id[:8]}`
• Use full ID: `{all_alerts[0].id}`
• Use `list_alerts` to see all alert IDs

🗑️ **Example:** `remove_alert` with alert_id: `{all_alerts[0].id[:8]}`"""

            return [types.TextContent(type="text", text=error_msg)]

    except Exception as e:
        logger.error(f"Error removing alert: {e}")
        return [types.TextContent(
            type="text",
            text=f"❌ Failed to remove alert {alert_id}: {str(e)}"
        )]


async def handle_check_alerts(arguments: dict) -> list[types.TextContent]:
    """Handle check alerts."""
    global alert_manager

    if not alert_manager:
        return [types.TextContent(
            type="text",
            text="❌ Alert manager not initialized"
        )]

    try:
        # Import market utils for status check
        from .market_utils import get_market_status, should_monitor_alerts

        market_status = get_market_status()

        # Show market status first
        market_info = f"🕐 **Market Status:** {market_status['status']} ({market_status['ist_time']})\n\n"

        if not should_monitor_alerts():
            return [types.TextContent(
                type="text",
                text=f"{market_info}💤 **Markets are closed** - Alert checking is paused for efficiency.\n\n⏰ **Next session:** {market_status['next_session']}\n\n💡 Alerts will automatically resume when markets reopen."
            )]

        triggered_messages = await alert_manager.check_all_alerts()

        if not triggered_messages:
            active_alerts = alert_manager.get_alerts(status=AlertStatus.ACTIVE)
            return [types.TextContent(
                type="text",
                text=f"{market_info}📭 **No Triggered Alerts**\n\nChecked {len(active_alerts)} active alerts - none are triggered right now."
            )]

        alerts_msg = f"{market_info}🚨 **Triggered Alerts ({len(triggered_messages)} alerts)**\n\n"

        for message in triggered_messages:
            alerts_msg += f"• {message}\n"

        alerts_msg += "\n💡 **These alerts have been marked as triggered and will no longer be monitored.**"

        return [types.TextContent(type="text", text=alerts_msg)]

    except Exception as e:
        logger.error(f"Error checking alerts: {e}")
        return [types.TextContent(
            type="text",
            text=f"❌ Failed to check alerts: {str(e)}"
        )]


async def handle_alert_status(arguments: dict) -> list[types.TextContent]:
    """Handle alert status."""
    global alert_manager

    if not alert_manager:
        return [types.TextContent(
            type="text",
            text="❌ Alert manager not initialized"
        )]

    try:
        status = alert_manager.get_monitoring_status()

        status_emoji = "🟢" if status["monitoring_active"] else "🔴"
        market_emoji = "📈" if status["market_hours"] else "🌙"
        monitoring_emoji = "✅" if status["should_monitor"] else "💤"

        status_msg = f"""
📊 **Alert Monitoring Status**

**System Status:** {status_emoji} {'Active' if status['monitoring_active'] else 'Inactive'}

**Market Information:** {market_emoji}
• **Market Status:** {status['market_status']}
• **IST Time:** {status['ist_time']}
• **Next Session:** {status['next_session']}

**Monitoring Behavior:** {monitoring_emoji}
• **Should Monitor:** {'Yes' if status['should_monitor'] else 'No (Market Closed)'}
• **Current Interval:** {status['monitoring_interval']} seconds
• **Efficiency:** {'Active monitoring' if status['should_monitor'] else 'Power-saving mode'}

📈 **Alert Statistics:**
• **Total Alerts:** {status['total_alerts']}
• **Active Alerts:** {status['active_alerts']}
• **Triggered Alerts:** {status['triggered_alerts']}
• **Cancelled Alerts:** {status['cancelled_alerts']}

💡 **Smart Features:**
• ✅ Monitors only during market hours (9:15 AM - 3:30 PM IST)
• ✅ Uses 3-minute intervals during trading hours
• ✅ Sleeps during market closure to save API calls
• ✅ Automatically resumes when markets reopen
"""

        return [types.TextContent(type="text", text=status_msg)]

    except Exception as e:
        logger.error(f"Error getting alert status: {e}")
        return [types.TextContent(
            type="text",
            text=f"❌ Failed to get alert status: {str(e)}"
        )]


async def handle_configure_email(arguments: dict) -> list[types.TextContent]:
    """Handle configure email."""
    try:
        from .email_config import email_config_manager, EmailConfigManager

        # Get provider for preset configurations
        provider = arguments.get("provider")

        if provider == "gmail":
            username = arguments.get("username")
            password = arguments.get("password")
            to_email = arguments.get("to_email")
            to_emails = arguments.get("to_emails", [])

            # Handle both single email and multiple emails
            if to_email and not to_emails:
                to_emails = [to_email]
            elif not to_emails:
                to_emails = []

            if not all([username, password]) or not to_emails:
                return [types.TextContent(
                    type="text",
                    text="""❌ **Gmail Configuration Error**

For Gmail setup, please provide:
• **username**: Your Gmail address
• **password**: Your Gmail App Password (NOT your regular password)
• **to_emails**: Array of email addresses to receive alerts (or single to_email)

📋 **Gmail App Password Setup:**
1. Go to Google Account settings
2. Enable 2-factor authentication
3. Go to Security → App Passwords
4. Generate a password for "Mail"
5. Use that 16-character password

💡 **Examples:**

Single recipient:
```json
{
  "provider": "gmail",
  "username": "your-email@gmail.com",
  "password": "your-16-char-app-password",
  "to_email": "your-email@gmail.com"
}
```

Multiple recipients:
```json
{
  "provider": "gmail",
  "username": "your-email@gmail.com",
  "password": "your-16-char-app-password",
  "to_emails": ["email1@gmail.com", "email2@gmail.com", "email3@gmail.com"]
}
```"""
                )]

            config = EmailConfigManager.get_gmail_config(
                # Use first email for compatibility
                username, password, to_emails[0])
            # Override with multiple emails
            config.to_emails = to_emails

        elif provider == "outlook":
            username = arguments.get("username")
            password = arguments.get("password")
            to_email = arguments.get("to_email")
            to_emails = arguments.get("to_emails", [])

            # Handle both single email and multiple emails
            if to_email and not to_emails:
                to_emails = [to_email]
            elif not to_emails:
                to_emails = []

            if not all([username, password]) or not to_emails:
                return [types.TextContent(
                    type="text",
                    text="""❌ **Outlook Configuration Error**

For Outlook setup, please provide:
• **username**: Your Outlook/Hotmail address
• **password**: Your account password
• **to_emails**: Array of email addresses to receive alerts (or single to_email)

💡 **Examples:**

Single recipient:
```json
{
  "provider": "outlook",
  "username": "your-email@outlook.com",
  "password": "your-password",
  "to_email": "your-email@outlook.com"
}
```

Multiple recipients:
```json
{
  "provider": "outlook",
  "username": "your-email@outlook.com",
  "password": "your-password",
  "to_emails": ["email1@outlook.com", "email2@gmail.com"]
}
```"""
                )]

            config = EmailConfigManager.get_outlook_config(
                # Use first email for compatibility
                username, password, to_emails[0])
            # Override with multiple emails
            config.to_emails = to_emails

        else:
            # Custom configuration
            smtp_server = arguments.get("smtp_server")
            smtp_port = arguments.get("smtp_port", 587)
            username = arguments.get("username")
            password = arguments.get("password")
            from_email = arguments.get("from_email")
            to_email = arguments.get("to_email")
            to_emails = arguments.get("to_emails", [])
            use_tls = arguments.get("use_tls", True)

            # Handle both single email and multiple emails
            if to_email and not to_emails:
                to_emails = [to_email]
            elif not to_emails:
                to_emails = []

            if not all([smtp_server, username, password, from_email]) or not to_emails:
                return [types.TextContent(
                    type="text",
                    text="""❌ **Custom Email Configuration Error**

Required fields:
• **smtp_server**: SMTP server address
• **username**: SMTP username
• **password**: SMTP password
• **from_email**: From email address
• **to_emails**: Array of recipient email addresses (or single to_email)

Optional fields:
• **smtp_port**: SMTP port (default: 587)
• **use_tls**: Use TLS encryption (default: true)

💡 **Examples:**

Single recipient:
```json
{
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "username": "your-email@gmail.com",
  "password": "your-app-password",
  "from_email": "Groww Alerts <your-email@gmail.com>",
  "to_email": "your-email@gmail.com",
  "use_tls": true
}
```

Multiple recipients:
```json
{
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "username": "your-email@gmail.com",
  "password": "your-app-password",
  "from_email": "Groww Alerts <your-email@gmail.com>",
  "to_emails": ["email1@gmail.com", "email2@yahoo.com", "email3@outlook.com"],
  "use_tls": true
}
```"""
                )]

            from .email_config import EmailConfig
            config = EmailConfig(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                username=username,
                password=password,
                from_email=from_email,
                to_emails=to_emails,  # Updated to use to_emails
                use_tls=use_tls,
                enabled=True
            )

        # Validate configuration
        if not config.validate():
            return [types.TextContent(
                type="text",
                text="❌ **Invalid Email Configuration**\n\nPlease check that all email fields are properly formatted and SMTP port is valid."
            )]

        # Save configuration
        success = email_config_manager.save_config(config)

        if success:
            # Reinitialize email service in alert manager
            global alert_manager
            if alert_manager:
                alert_manager._initialize_email_service()

            return [types.TextContent(
                type="text",
                text=f"""✅ **Email Configuration Saved Successfully**

**SMTP Server:** {config.smtp_server}:{config.smtp_port}
**From:** {config.from_email}
**To:** {', '.join(config.to_emails)}
**TLS:** {'Enabled' if config.use_tls else 'Disabled'}
**Status:** {'Enabled' if config.enabled else 'Disabled'}

🧪 **Next Step:** Use the `test_email` tool to verify your configuration works correctly.

📧 **Email notifications are now enabled for all triggered stock alerts.**"""
            )]
        else:
            return [types.TextContent(
                type="text",
                text="❌ **Failed to save email configuration**. Please check the error logs."
            )]

    except Exception as e:
        logger.error(f"Error configuring email: {e}")
        return [types.TextContent(
            type="text",
            text=f"❌ Failed to configure email: {str(e)}"
        )]


async def handle_test_email(arguments: dict) -> list[types.TextContent]:
    """Handle test email."""
    try:
        from .email_config import email_config_manager
        from .email_service import EmailService

        if not email_config_manager.is_configured():
            return [types.TextContent(
                type="text",
                text="""❌ **Email Not Configured**

Please configure your email settings first using the `configure_email` tool.

💡 **Quick Setup:**
```json
{
  "provider": "gmail",
  "username": "your-email@gmail.com",
  "password": "your-app-password",
  "to_email": "your-email@gmail.com"
}
```"""
            )]

        config = email_config_manager.get_config()
        email_service = EmailService(
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
            username=config.username,
            password=config.password,
            from_email=config.from_email,
            to_emails=config.to_emails,
            use_tls=config.use_tls
        )

        # Test SMTP connection first
        if not email_service.test_connection():
            return [types.TextContent(
                type="text",
                text="""❌ **SMTP Connection Failed**

Unable to connect to the email server. Please check:
• SMTP server address and port
• Username and password
• Internet connectivity
• Firewall settings

💡 **Common Issues:**
• Gmail: Make sure you're using an App Password, not your regular password
• Outlook: Verify your account credentials
• Corporate email: Check if SMTP is allowed"""
            )]

        # Send test email
        success = await email_service.send_test_email()

        if success:
            return [types.TextContent(
                type="text",
                text=f"""✅ **Test Email Sent Successfully!**

📧 **Check your inbox:** {', '.join(config.to_emails)}

The test email should arrive within a few minutes. If you don't see it, check your spam folder.

🚀 **Your email system is ready!** You'll now receive beautiful email notifications when your stock alerts are triggered.

📊 **Next Steps:**
• Set up stock price alerts using `set_price_alert`
• Alerts will automatically send emails when triggered
• Monitor status with `email_status` and `alert_status`"""
            )]
        else:
            return [types.TextContent(
                type="text",
                text="""❌ **Test Email Failed**

The email configuration appears correct, but sending failed. Please check:
• Email provider settings
• Rate limiting
• Account restrictions

💡 Try the test again in a few minutes."""
            )]

    except Exception as e:
        logger.error(f"Error testing email: {e}")
        return [types.TextContent(
            type="text",
            text=f"❌ Failed to test email: {str(e)}"
        )]


async def handle_email_status(arguments: dict) -> list[types.TextContent]:
    """Handle email status."""
    try:
        from .email_config import email_config_manager

        status = email_config_manager.get_status()

        if not status['configured']:
            return [types.TextContent(
                type="text",
                text="""📧 **Email Status: Not Configured**

Email notifications are not set up yet.

🚀 **Quick Setup:**
```json
{
  "provider": "gmail",
  "username": "your-email@gmail.com",
  "password": "your-app-password",
  "to_email": "your-email@gmail.com"
}
```

💡 **Available Providers:**
• `gmail` - Easy setup with App Password
• `outlook` - Outlook/Hotmail accounts
• `custom` - Any SMTP server

📋 **Use `configure_email` tool to get started!**"""
            )]

        status_emoji = "✅" if status['enabled'] and status['valid'] else "⚠️"
        config_emoji = "🟢" if status['valid'] else "🔴"

        status_msg = f"""📧 **Email Status: {status_emoji} {'Enabled' if status['enabled'] else 'Disabled'}**

**Configuration:** {config_emoji}
• **SMTP Server:** {status['smtp_server']}:{status['smtp_port']}
• **From Email:** {status['from_email']}
• **To Emails:** {', '.join(status['to_emails'])}
• **TLS Encryption:** {'Enabled' if status['use_tls'] else 'Disabled'}
• **Valid Config:** {'Yes' if status['valid'] else 'No'}
• **Notifications:** {'Active' if status['enabled'] else 'Paused'}

🔧 **Available Actions:**
• `test_email` - Send a test email
• `configure_email` - Update settings
• `{'disable' if status['enabled'] else 'enable'}_email` - {'Disable' if status['enabled'] else 'Enable'} notifications

📊 **Alert Integration:**
• Email notifications are automatically sent when stock alerts trigger
• Beautiful HTML emails with price charts and market context
• Rate limited to prevent spam (max 1 email per minute per alert type)
"""

        return [types.TextContent(type="text", text=status_msg)]

    except Exception as e:
        logger.error(f"Error getting email status: {e}")
        return [types.TextContent(
            type="text",
            text=f"❌ Failed to get email status: {str(e)}"
        )]


async def handle_disable_email(arguments: dict) -> list[types.TextContent]:
    """Handle disable email."""
    try:
        from .email_config import email_config_manager

        success = email_config_manager.disable_email()

        if success:
            # Reinitialize email service in alert manager
            global alert_manager
            if alert_manager:
                alert_manager._initialize_email_service()

            return [types.TextContent(
                type="text",
                text="""📧 **Email Notifications Disabled**

✅ Email notifications have been turned off.

**What happens now:**
• Stock alerts will still be monitored and logged
• No emails will be sent when alerts trigger
• Email configuration is preserved
• You can re-enable anytime with `enable_email`

💡 **Your alerts continue working** - they just won't send emails until you re-enable notifications."""
            )]
        else:
            return [types.TextContent(
                type="text",
                text="❌ **Failed to disable email notifications**. Email may not be configured."
            )]

    except Exception as e:
        logger.error(f"Error disabling email: {e}")
        return [types.TextContent(
            type="text",
            text=f"❌ Failed to disable email: {str(e)}"
        )]


async def handle_enable_email(arguments: dict) -> list[types.TextContent]:
    """Handle enable email."""
    try:
        from .email_config import email_config_manager

        if not email_config_manager.get_config():
            return [types.TextContent(
                type="text",
                text="""❌ **No Email Configuration Found**

Please configure your email settings first using the `configure_email` tool.

💡 **Quick Setup:**
```json
{
  "provider": "gmail",
  "username": "your-email@gmail.com",
  "password": "your-app-password",
  "to_email": "your-email@gmail.com"
}
```"""
            )]

        success = email_config_manager.enable_email()

        if success:
            # Reinitialize email service in alert manager
            global alert_manager
            if alert_manager:
                alert_manager._initialize_email_service()

            return [types.TextContent(
                type="text",
                text="""📧 **Email Notifications Enabled**

✅ Email notifications have been turned on.

**What happens now:**
• Stock alerts continue being monitored
• Beautiful email notifications will be sent when alerts trigger
• Emails include price charts and market context
• Rate limited to prevent spam

🧪 **Test it:** Use `test_email` to verify everything works correctly.

📈 **Set alerts:** Use `set_price_alert` to create stock price alerts that will trigger emails."""
            )]
        else:
            return [types.TextContent(
                type="text",
                text="❌ **Failed to enable email notifications**. Please check your email configuration is valid."
            )]

    except Exception as e:
        logger.error(f"Error enabling email: {e}")
        return [types.TextContent(
            type="text",
            text=f"❌ Failed to enable email: {str(e)}"
        )]


async def main():
    """Main entry point for the server."""
    global alert_manager

    # Initialize alert manager with a GrowwClient instance
    # Create a standalone client for the alert manager
    groww_client = GrowwClient()
    alert_manager = AlertManager(groww_client)

    # Start background monitoring with smart market-aware intervals
    alert_manager.start_monitoring()  # Will automatically use market-aware intervals

    logger.info("Alert manager initialized with market-aware monitoring")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
