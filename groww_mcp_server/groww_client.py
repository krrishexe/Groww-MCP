"""
Groww API client for stock trading operations.
Updated to use the official Groww API according to the documentation.
"""

import asyncio
import json
import logging
import sys
import io
import contextlib
import time
import hashlib
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
import pandas as pd

try:
    from growwapi import GrowwAPI
    GROWW_API_AVAILABLE = True
except ImportError:
    GROWW_API_AVAILABLE = False
    # Fallback to custom implementation if growwapi is not available

from .config import config
from .models import (
    StockInfo, StockPrice, OrderRequest, Order, Holding, Portfolio,
    APIResponse, OrderType, OrderSide, OrderStatus, ProductType
)

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def suppress_stdout():
    """Context manager to suppress stdout output."""
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old_stdout


class GrowwAPIError(Exception):
    """Custom exception for Groww API errors."""
    pass


class GrowwClient:
    """Groww API client for trading operations."""

    def __init__(self):
        self.api_auth_token = config.api_auth_token
        self.timeout = config.timeout
        self.groww_api = None
        # order_hash -> timestamp
        self._order_dedup_cache: Dict[str, float] = {}
        self._cache_timeout = 60  # 60 seconds to prevent duplicates

        if GROWW_API_AVAILABLE and self.api_auth_token:
            # Use official Groww API - suppress stdout to avoid MCP protocol interference
            try:
                with suppress_stdout():
                    self.groww_api = GrowwAPI(self.api_auth_token)
                self.use_official_api = True
                logger.info("Using official Groww API")
            except Exception as e:
                logger.error(f"Failed to initialize official Groww API: {e}")
                raise GrowwAPIError(f"Failed to initialize Groww API: {e}")
        else:
            if not GROWW_API_AVAILABLE:
                raise GrowwAPIError(
                    "GrowwAPI package not installed. Install with: pip install growwapi")
            if not self.api_auth_token:
                raise GrowwAPIError(
                    "Groww API token not configured. Set GROWW_ACCESS_TOKEN environment variable.")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass

    async def get_stock_price(self, symbol: str) -> StockPrice:
        """Get current stock price information using Groww API."""
        try:
            # Try to get quote data first
            quote_data = self.groww_api.get_quote(
                exchange="NSE",
                segment="CASH",
                trading_symbol=symbol
            )

            if quote_data and 'last_price' in quote_data:
                ohlc = quote_data.get('ohlc', {})
                return StockPrice(
                    symbol=symbol,
                    ltp=float(quote_data.get('last_price', 0)),
                    open=float(ohlc.get('open', 0)),
                    high=float(ohlc.get('high', 0)),
                    low=float(ohlc.get('low', 0)),
                    close=float(ohlc.get('close', 0)),
                    volume=int(quote_data.get('volume', 0)),
                    change=float(quote_data.get('day_change', 0)),
                    change_percent=float(quote_data.get('day_change_perc', 0)),
                    timestamp=datetime.now()
                )

            # Fallback to LTP if quote not available
            ltp_data = self.groww_api.get_ltp(
                segment="CASH",
                exchange_trading_symbols=(f"NSE_{symbol}",)
            )

            if ltp_data and f"NSE_{symbol}" in ltp_data:
                ltp_value = float(ltp_data[f"NSE_{symbol}"])

                # Try to get OHLC data as well
                try:
                    ohlc_data = self.groww_api.get_ohlc(
                        segment="CASH",
                        exchange_trading_symbols=(f"NSE_{symbol}",)
                    )
                    ohlc = ohlc_data.get(
                        f"NSE_{symbol}", {}) if ohlc_data else {}
                except:
                    ohlc = {}

                return StockPrice(
                    symbol=symbol,
                    ltp=ltp_value,
                    open=float(ohlc.get('open', ltp_value)),
                    high=float(ohlc.get('high', ltp_value)),
                    low=float(ohlc.get('low', ltp_value)),
                    close=float(ohlc.get('close', ltp_value)),
                    volume=0,  # Not available in LTP endpoint
                    change=0.0,  # Would need previous close to calculate
                    change_percent=0.0,  # Would need previous close to calculate
                    timestamp=datetime.now()
                )

            raise GrowwAPIError(f"No price data available for {symbol}")

        except Exception as e:
            raise GrowwAPIError(
                f"Failed to get stock price for {symbol}: {str(e)}")

    async def search_stocks(self, query: str) -> List[StockInfo]:
        """Search for stocks by name or symbol using Groww API."""
        try:
            # Get all instruments and filter by query
            instruments_df = self.groww_api.get_all_instruments()

            # Filter instruments based on query
            query_upper = query.upper()
            matching_instruments = instruments_df[
                (instruments_df['trading_symbol'].str.contains(query_upper, na=False)) |
                (instruments_df['name'].str.contains(
                    query, case=False, na=False))
            ].head(10)  # Limit to 10 results

            results = []
            for _, instrument in matching_instruments.iterrows():
                # Handle NaN values by converting to None or default values
                name = instrument.get('name')
                if pd.isna(name):
                    # Use symbol as fallback
                    name = instrument['trading_symbol']

                isin = instrument.get('isin')
                if pd.isna(isin):
                    isin = None

                sector = instrument.get('sector')
                if pd.isna(sector):
                    sector = None

                industry = instrument.get('industry')
                if pd.isna(industry):
                    industry = None

                results.append(StockInfo(
                    symbol=instrument['trading_symbol'],
                    name=str(name),  # Ensure it's a string
                    exchange=instrument['exchange'],
                    isin=str(isin) if isin is not None else None,
                    sector=str(sector) if sector is not None else None,
                    industry=str(industry) if industry is not None else None
                ))

            return results

        except Exception as e:
            raise GrowwAPIError(f"Failed to search stocks: {str(e)}")

    def _generate_order_hash(self, order_request: OrderRequest) -> str:
        """Generate a hash for order deduplication."""
        order_str = f"{order_request.symbol}_{order_request.quantity}_{order_request.order_side.value}_{order_request.order_type.value}_{order_request.price or 0}"
        return hashlib.md5(order_str.encode()).hexdigest()

    def _is_duplicate_order(self, order_request: OrderRequest) -> bool:
        """Check if this order is a duplicate within the cache timeout."""
        order_hash = self._generate_order_hash(order_request)
        current_time = time.time()

        # Clean old entries
        self._order_dedup_cache = {
            k: v for k, v in self._order_dedup_cache.items()
            if current_time - v < self._cache_timeout
        }

        # Check if this order was placed recently
        if order_hash in self._order_dedup_cache:
            time_since = current_time - self._order_dedup_cache[order_hash]
            return time_since < self._cache_timeout

        return False

    def _mark_order_placed(self, order_request: OrderRequest):
        """Mark an order as placed in the deduplication cache."""
        order_hash = self._generate_order_hash(order_request)
        self._order_dedup_cache[order_hash] = time.time()

    async def place_order(self, order_request: OrderRequest) -> Order:
        """Place a buy/sell order using Groww API with deduplication."""
        try:
            # Check for duplicate order
            if self._is_duplicate_order(order_request):
                raise GrowwAPIError(
                    f"🛡️ DUPLICATE ORDER PREVENTED: This exact order was placed within the last {self._cache_timeout} seconds. Please wait before placing the same order again.")

            # Mark this order as being placed
            self._mark_order_placed(order_request)

            # Map our order types to Groww API constants
            groww_order_type = self.groww_api.ORDER_TYPE_LIMIT if order_request.order_type == OrderType.LIMIT else self.groww_api.ORDER_TYPE_MARKET
            groww_transaction_type = self.groww_api.TRANSACTION_TYPE_BUY if order_request.order_side == OrderSide.BUY else self.groww_api.TRANSACTION_TYPE_SELL
            groww_product = self.groww_api.PRODUCT_CNC  # Default to CNC for cash segment

            order_response = self.groww_api.place_order(
                trading_symbol=order_request.symbol,
                quantity=order_request.quantity,
                validity=self.groww_api.VALIDITY_DAY,
                exchange=self.groww_api.EXCHANGE_NSE,
                segment=self.groww_api.SEGMENT_CASH,
                product=groww_product,
                order_type=groww_order_type,
                transaction_type=groww_transaction_type,
                price=order_request.price if order_request.order_type == OrderType.LIMIT else None,
                trigger_price=None,  # Not using stop loss for now
                order_reference_id=f"MCP-{int(time.time())}"
            )

            if order_response:
                return Order(
                    order_id=order_response.get('order_id', ''),
                    symbol=order_request.symbol,
                    quantity=order_request.quantity,
                    order_type=order_request.order_type,
                    order_side=order_request.order_side,
                    product_type=order_request.product_type,
                    price=order_request.price,
                    status=OrderStatus.NEW,  # Default status
                    order_time=datetime.now()
                )
            else:
                raise GrowwAPIError(
                    "Order placement failed - no response from API")

        except Exception as e:
            # If it's our duplicate prevention, re-raise as is
            if "DUPLICATE ORDER PREVENTED" in str(e):
                raise e
            raise GrowwAPIError(f"Failed to place order: {str(e)}")

    async def get_orders(self) -> List[Order]:
        """Get list of orders using Groww API (current day only) plus reconstructed historical trades."""
        try:
            all_orders = []

            # 1. Get current day orders (as per API documentation)
            logger.info("Fetching current day orders from API...")
            current_day_orders = await self._get_current_day_orders()
            all_orders.extend(current_day_orders)

            # 2. Get reconstructed historical orders from holdings/positions
            logger.info(
                "Reconstructing historical trades from holdings/positions...")
            historical_orders = await self._get_historical_orders_from_holdings()
            all_orders.extend(historical_orders)

            logger.info(
                f"Total orders: {len(current_day_orders)} current + {len(historical_orders)} historical = {len(all_orders)}")
            return all_orders

        except Exception as e:
            logger.error(f"Failed to get orders: {str(e)}")
            raise GrowwAPIError(f"Failed to get orders: {str(e)}")

    async def _get_current_day_orders(self) -> List[Order]:
        """Get current day orders using the correct API limitations."""
        try:
            current_orders = []
            page = 0
            max_page_size = 25  # API documentation limit

            while True:
                logger.info(f"Fetching current day orders page {page}")

                orders_response = self.groww_api.get_order_list(
                    page=page, page_size=max_page_size)

                if not orders_response or 'order_list' not in orders_response:
                    break

                order_list = orders_response['order_list']
                if not order_list:  # No more orders
                    break

                logger.info(
                    f"Processing {len(order_list)} current day orders from page {page}")

                for order_data in order_list:
                    try:
                        order = self._parse_order_data(
                            order_data, is_historical=False)
                        if order:
                            current_orders.append(order)
                    except Exception as order_error:
                        logger.error(
                            f"Error processing current day order: {order_error}")
                        continue

                # If we got fewer orders than max_page_size, we've reached the end
                if len(order_list) < max_page_size:
                    break

                page += 1

            return current_orders

        except Exception as e:
            logger.error(f"Failed to get current day orders: {e}")
            return []  # Return empty list instead of failing completely

    async def _get_historical_orders_from_holdings(self) -> List[Order]:
        """Reconstruct historical order information from holdings and positions."""
        try:
            historical_orders = []

            # Get holdings (shows what you currently own)
            holdings_response = self.groww_api.get_holdings_for_user(
                timeout=10)

            if holdings_response and 'holdings' in holdings_response:
                for holding in holdings_response['holdings']:
                    symbol = holding.get('trading_symbol', '')
                    quantity = float(holding.get('quantity', 0))
                    average_price = float(holding.get('average_price', 0))

                    if quantity > 0 and symbol:  # Only process actual holdings
                        # Create a reconstructed buy order
                        reconstructed_order = Order(
                            # Unique ID
                            order_id=f"HIST-{symbol}-{int(average_price*100)}",
                            symbol=symbol,
                            quantity=int(quantity),
                            order_type=OrderType.MARKET,  # Assume market order
                            order_side=OrderSide.BUY,
                            product_type=ProductType.CNC,
                            price=average_price,
                            average_price=average_price,
                            status=OrderStatus.EXECUTED,
                            order_time=datetime.now() - timedelta(days=1)  # Estimate as yesterday
                        )
                        historical_orders.append(reconstructed_order)

            # Get positions (shows additional trade details)
            positions_response = self.groww_api.get_positions_for_user(
                segment="CASH")

            if positions_response and 'positions' in positions_response:
                for position in positions_response['positions']:
                    symbol = position.get('trading_symbol', '')
                    credit_quantity = int(position.get('credit_quantity', 0))
                    credit_price = float(position.get('credit_price', 0))
                    debit_quantity = int(position.get('debit_quantity', 0))
                    debit_price = float(position.get('debit_price', 0))

                    # Skip if already added from holdings
                    existing_symbols = [
                        order.symbol for order in historical_orders]
                    if symbol in existing_symbols:
                        continue

                    # Add buy orders from credit transactions
                    if credit_quantity > 0:
                        buy_order = Order(
                            order_id=f"HIST-BUY-{symbol}-{int(credit_price*100)}",
                            symbol=symbol,
                            quantity=credit_quantity,
                            order_type=OrderType.MARKET,
                            order_side=OrderSide.BUY,
                            product_type=ProductType.CNC,
                            price=credit_price,
                            average_price=credit_price,
                            status=OrderStatus.EXECUTED,
                            order_time=datetime.now() - timedelta(days=2)
                        )
                        historical_orders.append(buy_order)

                    # Add sell orders from debit transactions
                    if debit_quantity > 0:
                        sell_order = Order(
                            order_id=f"HIST-SELL-{symbol}-{int(debit_price*100)}",
                            symbol=symbol,
                            quantity=debit_quantity,
                            order_type=OrderType.MARKET,
                            order_side=OrderSide.SELL,
                            product_type=ProductType.CNC,
                            price=debit_price,
                            average_price=debit_price,
                            status=OrderStatus.EXECUTED,
                            order_time=datetime.now() - timedelta(days=1)
                        )
                        historical_orders.append(sell_order)

            return historical_orders

        except Exception as e:
            logger.error(f"Failed to reconstruct historical orders: {e}")
            return []

    def _parse_order_data(self, order_data: dict, is_historical: bool = False) -> Optional[Order]:
        """Parse order data from API response into Order object."""
        try:
            # Map order status
            status_map = {
                'NEW': OrderStatus.NEW,
                'OPEN': OrderStatus.NEW,
                'PENDING': OrderStatus.NEW,
                'EXECUTED': OrderStatus.EXECUTED,
                'COMPLETE': OrderStatus.EXECUTED,
                'COMPLETED': OrderStatus.EXECUTED,
                'FILLED': OrderStatus.EXECUTED,
                'CANCELLED': OrderStatus.CANCELLED,
                'CANCELED': OrderStatus.CANCELLED,
                'REJECTED': OrderStatus.REJECTED
            }

            order_status_raw = order_data.get('order_status', 'NEW')
            order_status = status_map.get(
                order_status_raw.upper(), OrderStatus.NEW)

            # Handle order type
            order_type_raw = order_data.get('order_type', 'MARKET')
            order_type = OrderType.LIMIT if order_type_raw.upper() == 'LIMIT' else OrderType.MARKET

            # Handle transaction type
            transaction_type_raw = order_data.get('transaction_type', 'BUY')
            order_side = OrderSide.BUY if transaction_type_raw.upper() == 'BUY' else OrderSide.SELL

            # Parse order time
            order_time = datetime.now()  # Default fallback
            time_field = order_data.get('created_at') or order_data.get(
                'trade_date') or order_data.get('exchange_time')

            if time_field:
                try:
                    # Handle ISO format with Z
                    if isinstance(time_field, str) and 'T' in time_field:
                        time_field = time_field.replace('Z', '+00:00')
                        order_time = datetime.fromisoformat(
                            time_field.replace('Z', '+00:00'))
                    else:
                        # Try other formats
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d-%m-%Y %H:%M:%S']:
                            try:
                                order_time = datetime.strptime(
                                    str(time_field), fmt)
                                break
                            except ValueError:
                                continue
                except Exception as time_error:
                    logger.warning(
                        f"Could not parse order time '{time_field}': {time_error}")

            # Parse numeric fields safely
            price = None
            if order_data.get('price'):
                try:
                    price = float(order_data.get('price', 0))
                except (ValueError, TypeError):
                    price = None

            quantity = 0
            try:
                quantity = int(order_data.get('quantity', 0))
            except (ValueError, TypeError):
                quantity = 0

            average_price = None
            if order_data.get('average_fill_price'):
                try:
                    average_price = float(
                        order_data.get('average_fill_price', 0))
                except (ValueError, TypeError):
                    average_price = None

            return Order(
                order_id=str(order_data.get('groww_order_id',
                             order_data.get('order_id', ''))),
                symbol=str(order_data.get('trading_symbol',
                           order_data.get('symbol', ''))),
                quantity=quantity,
                order_type=order_type,
                order_side=order_side,
                product_type=ProductType.CNC,
                price=price,
                average_price=average_price,
                status=order_status,
                order_time=order_time
            )

        except Exception as e:
            logger.error(f"Error parsing order data {order_data}: {e}")
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order using Groww API."""
        try:
            # Cancel order using API
            cancel_response = self.groww_api.cancel_order(
                segment=self.groww_api.SEGMENT_CASH,
                groww_order_id=order_id
            )

            return cancel_response is not None

        except Exception as e:
            raise GrowwAPIError(f"Failed to cancel order: {str(e)}")

    async def get_holdings(self) -> List[Holding]:
        """Get current stock holdings and positions using Groww API."""
        try:
            holdings = []

            # 1. Get traditional holdings
            holdings_response = self.groww_api.get_holdings_for_user(
                timeout=10)
            if holdings_response and 'holdings' in holdings_response:
                for holding_data in holdings_response['holdings']:
                    symbol = holding_data.get('trading_symbol', '')
                    quantity = float(holding_data.get('quantity', 0))
                    average_price = float(holding_data.get('average_price', 0))

                    # Try to get current price for P&L calculation
                    try:
                        current_price_data = self.groww_api.get_ltp(
                            segment="CASH",
                            exchange_trading_symbols=(f"NSE_{symbol}",)
                        )
                        current_price = float(current_price_data.get(
                            symbol, {}).get('ltp', average_price))
                    except:
                        current_price = average_price  # Fallback to average price

                    market_value = quantity * current_price
                    invested_value = quantity * average_price
                    pnl = market_value - invested_value
                    pnl_percent = (pnl / invested_value *
                                   100) if invested_value > 0 else 0

                    holdings.append(Holding(
                        symbol=symbol,
                        quantity=int(quantity),
                        average_price=average_price,
                        current_price=current_price,
                        market_value=market_value,
                        pnl=pnl,
                        pnl_percent=pnl_percent,
                        product_type=ProductType.CNC
                    ))

            # 2. Get cash segment positions (where SUZLON appears)
            try:
                positions_response = self.groww_api.get_positions_for_user(
                    segment="CASH")
                if positions_response and 'positions' in positions_response:
                    for position_data in positions_response['positions']:
                        symbol = position_data.get('trading_symbol', '')
                        credit_quantity = float(
                            position_data.get('credit_quantity', 0))
                        credit_price = float(
                            position_data.get('credit_price', 0))

                        # Skip if already in holdings
                        if any(h.symbol == symbol for h in holdings):
                            continue

                        # Only include if we have actual shares
                        if credit_quantity > 0:
                            # Try to get current price
                            try:
                                current_price_data = self.groww_api.get_ltp(
                                    segment="CASH",
                                    exchange_trading_symbols=(f"NSE_{symbol}",)
                                )
                                current_price = float(current_price_data.get(
                                    symbol, {}).get('ltp', credit_price))
                            except:
                                current_price = credit_price

                            market_value = credit_quantity * current_price
                            invested_value = credit_quantity * credit_price
                            pnl = market_value - invested_value
                            pnl_percent = (pnl / invested_value *
                                           100) if invested_value > 0 else 0

                            holdings.append(Holding(
                                symbol=symbol,
                                quantity=int(credit_quantity),
                                average_price=credit_price,
                                current_price=current_price,
                                market_value=market_value,
                                pnl=pnl,
                                pnl_percent=pnl_percent,
                                product_type=ProductType.CNC
                            ))
            except Exception as e:
                print(f"Warning: Could not get positions: {e}")

            return holdings

        except Exception as e:
            raise GrowwAPIError(f"Failed to get holdings: {str(e)}")

    async def get_portfolio(self) -> Portfolio:
        """Get complete portfolio information using Groww API."""
        try:
            holdings = await self.get_holdings()

            # Calculate portfolio metrics
            total_invested = sum(
                h.quantity * h.average_price for h in holdings)
            total_current_value = sum(h.market_value for h in holdings)
            total_pnl = total_current_value - total_invested
            total_pnl_percent = (total_pnl / total_invested *
                                 100) if total_invested > 0 else 0

            # Get available margin for cash balance
            try:
                margin_data = self.groww_api.get_available_margin_details()
                cash_balance = float(margin_data.get('available_margin', 0))
            except:
                cash_balance = 0.0  # Fallback if margin API fails

            return Portfolio(
                total_value=total_current_value + cash_balance,
                invested_value=total_invested,
                current_value=total_current_value,
                total_pnl=total_pnl,
                total_pnl_percent=total_pnl_percent,
                day_pnl=0.0,  # Would need daily tracking for this
                holdings=holdings,
                cash_balance=cash_balance
            )

        except Exception as e:
            raise GrowwAPIError(f"Failed to get portfolio: {str(e)}")

    async def get_market_status(self) -> Dict[str, Any]:
        """Get current market status."""
        # Since market status API might not be available, provide basic info
        current_hour = datetime.now().hour
        current_minute = datetime.now().minute

        # NSE/BSE trading hours: 9:15 AM to 3:30 PM
        is_trading_time = (9 < current_hour < 15) or (
            current_hour == 9 and current_minute >= 15) or (current_hour == 15 and current_minute <= 30)

        return {
            "status": "OPEN" if is_trading_time else "CLOSED",
            "nse_hours": "9:15 AM - 3:30 PM (Monday to Friday)",
            "bse_hours": "9:15 AM - 3:30 PM (Monday to Friday)",
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "next_session": "Next trading day 9:15 AM" if not is_trading_time else "Currently trading"
        }
