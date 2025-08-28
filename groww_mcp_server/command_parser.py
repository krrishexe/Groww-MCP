"""
Natural language command parser for trading commands.
"""

import re
from typing import Optional, List, Union
from .models import TradeCommand, OrderType, OrderSide


class CommandParser:
    """Parser for natural language trading commands."""

    # Common stock symbol patterns
    STOCK_PATTERNS = [
        # Stock symbols after "of"
        r'(?:stocks? of |shares? of |worth of )\s*([A-Z][A-Z0-9&\.]{2,15})',
        # Company names after "of"
        r'(?:stocks? of |shares? of |worth of )\s*([A-Z][a-z]+(?: [A-Z][a-z]+)*)',
        # Stock symbols before "stocks/shares"
        r'([A-Z][A-Z0-9&\.]{2,15})(?:\s+stocks?|\s+shares?|$)',
    ]

    # Quantity patterns
    QUANTITY_PATTERNS = [
        r'(\d+)\s*(?:stocks?|shares?)',
        r'(\d+)\s*(?:units?)?',
        r'(?:buy|sell|purchase)\s+(\d+)',
    ]

    # Amount patterns (for rupee-based orders)
    AMOUNT_PATTERNS = [
        r'(?:₹|Rs\.?|INR)\s*(\d+(?:,\d+)*(?:\.\d+)?)',
        r'(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:rupees?|rs)',
        r'worth\s+(?:₹|Rs\.?|INR)?\s*(\d+(?:,\d+)*(?:\.\d+)?)',
    ]

    # Action patterns
    BUY_PATTERNS = [
        r'\b(?:buy|purchase|get|acquire)\b',
    ]

    SELL_PATTERNS = [
        r'\b(?:sell|dispose|exit)\b',
    ]

    # Order type patterns
    MARKET_PATTERNS = [
        r'\b(?:market|immediate|now)\b',
    ]

    LIMIT_PATTERNS = [
        r'\blimit\b',
        r'at\s+(?:₹|Rs\.?)?\s*(\d+(?:\.\d+)?)',
        r'price\s+(?:₹|Rs\.?)?\s*(\d+(?:\.\d+)?)',
    ]

    def __init__(self):
        self.compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> dict:
        """Compile regex patterns for better performance."""
        return {
            'stock': [re.compile(pattern, re.IGNORECASE) for pattern in self.STOCK_PATTERNS],
            'quantity': [re.compile(pattern, re.IGNORECASE) for pattern in self.QUANTITY_PATTERNS],
            'amount': [re.compile(pattern, re.IGNORECASE) for pattern in self.AMOUNT_PATTERNS],
            'buy': [re.compile(pattern, re.IGNORECASE) for pattern in self.BUY_PATTERNS],
            'sell': [re.compile(pattern, re.IGNORECASE) for pattern in self.SELL_PATTERNS],
            'market': [re.compile(pattern, re.IGNORECASE) for pattern in self.MARKET_PATTERNS],
            'limit': [re.compile(pattern, re.IGNORECASE) for pattern in self.LIMIT_PATTERNS],
        }

    def _extract_with_patterns(self, text: str, patterns: List[re.Pattern]) -> Optional[str]:
        """Extract information using compiled patterns."""
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(1) if match.groups() else match.group(0)
        return None

    def _normalize_stock_symbol(self, symbol: str) -> str:
        """Normalize stock symbol to standard format."""
        # Convert common company names to stock symbols
        name_to_symbol = {
            'reliance': 'RELIANCE',
            'tcs': 'TCS',
            'infosys': 'INFY',
            'hdfc bank': 'HDFCBANK',
            'hdfc': 'HDFCBANK',
            'icici bank': 'ICICIBANK',
            'icici': 'ICICIBANK',
            'sbi': 'SBIN',
            'state bank': 'SBIN',
            'wipro': 'WIPRO',
            'bharti airtel': 'BHARTIARTL',
            'airtel': 'BHARTIARTL',
            'itc': 'ITC',
            'axis bank': 'AXISBANK',
            'axis': 'AXISBANK',
            'maruti': 'MARUTI',
            'maruti suzuki': 'MARUTI',
            'asian paints': 'ASIANPAINT',
            'bajaj finance': 'BAJFINANCE',
            'bajaj': 'BAJFINANCE',
            'nestlé': 'NESTLEIND',
            'nestle': 'NESTLEIND',
            'ultratech': 'ULTRACEMCO',
            'ultra tech': 'ULTRACEMCO',
            'titan': 'TITAN',
            'power grid': 'POWERGRID',
            'powergrid': 'POWERGRID',
            'ntpc': 'NTPC',
            'ongc': 'ONGC',
            'kotak bank': 'KOTAKBANK',
            'kotak': 'KOTAKBANK',
            'larsen': 'LT',
            'l&t': 'LT',
            'mahindra': 'M&M',
            'sun pharma': 'SUNPHARMA',
            'sunpharma': 'SUNPHARMA',
            'dr reddy': 'DRREDDY',
            'dr reddys': 'DRREDDY',
            'tech mahindra': 'TECHM',
            'techm': 'TECHM',
            'grasim': 'GRASIM',
            'adani ports': 'ADANIPORTS',
            'adaniports': 'ADANIPORTS',
            'britannia': 'BRITANNIA',
            'cipla': 'CIPLA',
            'eicher': 'EICHERMOT',
            'eicher motors': 'EICHERMOT',
            'hero motocorp': 'HEROMOTOCO',
            'hero': 'HEROMOTOCO',
            'hindalco': 'HINDALCO',
            'hul': 'HINDUNILVR',
            'hindustan unilever': 'HINDUNILVR',
            'jswsteel': 'JSWSTEEL',
            'jsw steel': 'JSWSTEEL',
            'shree cement': 'SHREECEM',
            'shreecem': 'SHREECEM',
            'tata steel': 'TATASTEEL',
            'tatasteel': 'TATASTEEL',
            'upl': 'UPL',
            'vedanta': 'VEDL',
            'vedl': 'VEDL',
        }

        symbol_lower = symbol.lower().strip()

        # Check if it's a known company name
        if symbol_lower in name_to_symbol:
            return name_to_symbol[symbol_lower]

        # If it's already a symbol format, return uppercase
        if symbol.isupper() and len(symbol) >= 3:
            return symbol

        # Try to convert to uppercase (assuming it's already a symbol)
        return symbol.upper()

    def _parse_numeric_value(self, value_str: str) -> float:
        """Parse numeric value from string, handling commas."""
        if not value_str:
            return 0.0

        # Remove commas and convert to float
        clean_value = value_str.replace(',', '')
        try:
            return float(clean_value)
        except ValueError:
            return 0.0

    def parse_command(self, command: str) -> Optional[TradeCommand]:
        """Parse natural language trading command."""
        command = command.strip()

        # Determine action (buy/sell)
        action = None
        if self._extract_with_patterns(command, self.compiled_patterns['buy']):
            action = "buy"
        elif self._extract_with_patterns(command, self.compiled_patterns['sell']):
            action = "sell"

        if not action:
            return None

        # Extract stock symbol
        stock_symbol = self._extract_with_patterns(
            command, self.compiled_patterns['stock'])
        if not stock_symbol:
            return None

        stock_symbol = self._normalize_stock_symbol(stock_symbol)

        # Extract quantity
        quantity_str = self._extract_with_patterns(
            command, self.compiled_patterns['quantity'])
        quantity = int(self._parse_numeric_value(
            quantity_str)) if quantity_str else None

        # Extract amount (for rupee-based orders)
        amount_str = self._extract_with_patterns(
            command, self.compiled_patterns['amount'])
        amount = self._parse_numeric_value(amount_str) if amount_str else None

        # Determine order type and price
        order_type = OrderType.MARKET
        price = None

        # Check for limit order
        limit_match = self._extract_with_patterns(
            command, self.compiled_patterns['limit'])
        if limit_match:
            order_type = OrderType.LIMIT
            # Try to extract price from limit pattern
            for pattern in self.compiled_patterns['limit']:
                match = pattern.search(command)
                if match and match.groups():
                    price = self._parse_numeric_value(match.group(1))
                    break

        # Check for market order indicators
        if self._extract_with_patterns(command, self.compiled_patterns['market']):
            order_type = OrderType.MARKET
            price = None

        return TradeCommand(
            action=action,
            symbol=stock_symbol,
            quantity=quantity,
            amount=amount,
            order_type=order_type,
            price=price
        )

    def suggest_corrections(self, command: str) -> List[str]:
        """Suggest corrections for malformed commands."""
        suggestions = []

        # Check if action is missing
        if not (self._extract_with_patterns(command, self.compiled_patterns['buy']) or
                self._extract_with_patterns(command, self.compiled_patterns['sell'])):
            suggestions.append(
                "Please specify whether you want to 'buy' or 'sell'")

        # Check if stock symbol is missing
        if not self._extract_with_patterns(command, self.compiled_patterns['stock']):
            suggestions.append(
                "Please specify the stock symbol or company name")

        # Check if quantity or amount is missing
        quantity = self._extract_with_patterns(
            command, self.compiled_patterns['quantity'])
        amount = self._extract_with_patterns(
            command, self.compiled_patterns['amount'])

        if not quantity and not amount:
            suggestions.append(
                "Please specify either the number of shares or the amount in rupees")

        return suggestions


# Global parser instance
command_parser = CommandParser()
