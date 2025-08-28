# Groww MCP Server

A Model Context Protocol (MCP) server for integrating with Groww's stock trading API. This server allows you to execute real stock trades using natural language commands through Claude Desktop or Cursor IDE.

## Features

- **Natural Language Trading**: Execute real trades with simple commands like "buy 5 stocks of RELIANCE" or "sell 10 stocks of TCS"
- **Real Groww API Integration**: Direct integration with Groww's official API for authentic trading
- **Portfolio Management**: View your real holdings, portfolio status, and P&L
- **Real-time Stock Data**: Get current stock prices and market information
- **Order Management**: Place, cancel, and track real orders with confirmation workflow
- **Comprehensive Search**: Search and discover stocks by name or symbol
- **Multiple IDE Support**: Works with both Claude Desktop and Cursor IDE

## Setup

### Prerequisites

- Python 3.10 or higher
- Groww trading account with API access
- **One of the following MCP clients:**
  - Claude Desktop
  - Cursor IDE (version 0.47.x or above)
- Groww API access token (get from Groww's developer portal)

### Installation

1. Clone this repository:

```bash
git clone <repository-url>
cd groww-mcp-server
```

2. Install dependencies:

```bash
pip install -e .
```

3. Install the Groww API package:

```bash
pip install growwapi
```

4. Create a `.env` file with your Groww API credentials:

```env
# REQUIRED: Groww API Access Token
GROWW_ACCESS_TOKEN=your_groww_access_token_here

# Optional Configuration
GROWW_BASE_URL=https://api.groww.in
API_TIMEOUT=30
MAX_ORDER_VALUE=100000
LOG_LEVEL=INFO
```

### Getting Your Groww API Token

1. Visit [Groww Developer Portal](https://groww.in/developers)
2. Create a developer account or log in
3. Generate an API access token
4. Copy the token to your `.env` file

### Configuration

#### For Claude Desktop

Add this server to your Claude Desktop configuration (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "groww": {
      "command": "python",
      "args": ["-m", "groww_mcp_server.server"],
      "env": {
        "GROWW_ACCESS_TOKEN": "your_groww_access_token_here",
        "GROWW_BASE_URL": "https://api.groww.in",
        "API_TIMEOUT": "30",
        "MAX_ORDER_VALUE": "100000",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

#### For Cursor IDE

**Option 1: Project-specific configuration**
Create `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "groww": {
      "command": "python",
      "args": ["-m", "groww_mcp_server.server"],
      "env": {
        "GROWW_ACCESS_TOKEN": "your_groww_access_token_here",
        "GROWW_BASE_URL": "https://api.groww.in",
        "API_TIMEOUT": "30",
        "MAX_ORDER_VALUE": "100000",
        "LOG_LEVEL": "INFO",
        "PAPER_TRADING": "true"
      }
    }
  }
}
```

**Option 2: Global configuration**
Create `~/.cursor/mcp.json` in your home directory with the same content.

**For detailed Cursor setup instructions, see [CURSOR_SETUP.md](./CURSOR_SETUP.md)**

## Usage

Once configured, you can use natural language commands in Claude/Cursor to manage your real Groww trading account:

### Trading Commands

- `"Buy 5 stocks of RELIANCE"` - Place a buy order for 5 shares
- `"Sell 10 shares of TCS"` - Place a sell order for 10 shares
- `"Purchase ₹1000 worth of INFY"` - Buy stocks worth ₹1000
- `"Sell all my HDFC Bank stocks"` - Sell your entire HDFC Bank position

⚠️ **All trading commands require explicit confirmation before execution**

### Information Commands

- `"Show my portfolio"` - View your real portfolio with current P&L
- `"What's the current price of RELIANCE?"` - Get live stock price
- `"Show my holdings"` - View your actual stock holdings
- `"Get market status"` - Check if markets are open/closed

## Available Functions

### Trading Functions

- `buy_stock`: Execute real buy orders with natural language parsing
- `sell_stock`: Execute real sell orders with natural language parsing
- `cancel_order`: Cancel pending orders
- `get_orders`: View your actual order history

### Information Functions

- `get_portfolio`: View your real portfolio with live P&L calculations
- `get_stock_price`: Get real-time stock prices from Groww
- `get_holdings`: View your actual stock holdings with current values
- `search_stocks`: Search Groww's stock database by name or symbol
- `get_market_status`: Check market status and trading hours
- `parse_trade_command`: Parse trading commands without executing

## Authentication

The server uses Groww's official API with your access token:

```python
from growwapi import GrowwAPI

# Initialize with your access token from environment
GROWW_ACCESS_TOKEN = os.getenv("GROWW_ACCESS_TOKEN")
groww = GrowwAPI(GROWW_ACCESS_TOKEN)
```

**To get your Groww API token:**

1. Visit [Groww Developer Portal](https://groww.in/developers)
2. Create a developer account or log in to your existing account
3. Generate an API access token
4. Copy the token to your `.env` file as `GROWW_ACCESS_TOKEN`

## Security & Safety

- ✅ All API credentials are stored securely in environment variables
- ✅ All orders require explicit confirmation before execution
- ✅ Maximum order value limits configurable to prevent large mistakes
- ✅ Rate limiting implemented to prevent API abuse
- ✅ All transactions are executed through Groww's secure API
- ✅ Real-time validation of orders before execution

⚠️ **Important Safety Notes:**

- This system executes **REAL TRADES** on your Groww account
- Always verify order details before confirming
- Start with small amounts to test the system
- Monitor your account regularly when using automated trading

## Testing

Run the test suite to verify your setup:

```bash
python test_server.py
```

This will test:

- API token validation
- Connection to Groww API
- Basic functionality (portfolio, holdings, search)
- Market data access

## Legal Disclaimer

This software executes real trades on your behalf. Please ensure you:

- Understand the risks of automated trading
- Comply with all applicable securities regulations
- Monitor your account activity regularly
- Use appropriate position sizing and risk management

The authors are not responsible for any financial losses incurred through the use of this software. Trade responsibly.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
