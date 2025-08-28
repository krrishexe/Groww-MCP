"""
Email templates for stock price alerts.
"""

from typing import Dict, Optional
from datetime import datetime
from .market_utils import get_ist_now, get_market_status


def create_alert_email_template(alert_message: str,
                                symbol: str,
                                current_price: float,
                                base_price: Optional[float] = None,
                                percentage_change: Optional[float] = None) -> Dict[str, str]:
    """
    Create a formatted email template for stock price alerts.

    Args:
        alert_message: The triggered alert message
        symbol: Stock symbol
        current_price: Current stock price
        base_price: Base price for percentage alerts
        percentage_change: Percentage change if applicable

    Returns:
        Dictionary with 'subject', 'text', and 'html' content
    """
    # Get current market status
    market_status = get_market_status()
    timestamp = get_ist_now().strftime('%Y-%m-%d %H:%M:%S IST')

    # Determine alert type and styling
    is_positive = True
    if "down" in alert_message.lower() or "below" in alert_message.lower():
        is_positive = False

    # Create subject line
    subject = f"🚨 {symbol} Alert Triggered"
    if percentage_change:
        direction = "📈" if is_positive else "📉"
        subject = f"{direction} {symbol} Alert: {percentage_change:+.2f}%"

    # Create text version
    text_content = f"""
🚨 STOCK ALERT TRIGGERED

{alert_message}

Stock Details:
• Symbol: {symbol}
• Current Price: ₹{current_price:.2f}
• Time: {timestamp}
• Market Status: {market_status['status']}

Alert Information:
• This alert has been triggered and marked as complete
• No further notifications will be sent for this alert
• You can set up new alerts anytime

Market Context:
• Next Session: {market_status['next_session']}
• Alert triggered during: {market_status['status']}

View your portfolio: https://groww.in/

---
Groww MCP Alert System
Powered by Claude & Cursor
    """.strip()

    # Create HTML version
    alert_color = "#10b981" if is_positive else "#ef4444"  # Green or Red
    alert_icon = "📈" if is_positive else "📉"

    price_change_section = ""
    if base_price and percentage_change:
        price_change_section = f"""
        <div style="background: {'#ecfdf5' if is_positive else '#fef2f2'}; border-left: 4px solid {alert_color}; padding: 15px; margin: 20px 0; border-radius: 0 8px 8px 0;">
            <h3 style="color: #1f2937; margin: 0 0 10px 0; display: flex; align-items: center;">
                <span style="font-size: 24px; margin-right: 10px;">{alert_icon}</span>
                Price Movement
            </h3>
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <div style="flex: 1; min-width: 150px;">
                    <p style="margin: 5px 0; color: #6b7280;"><strong>From:</strong> ₹{base_price:.2f}</p>
                    <p style="margin: 5px 0; color: #6b7280;"><strong>To:</strong> ₹{current_price:.2f}</p>
                </div>
                <div style="text-align: right;">
                    <div style="background: {alert_color}; color: white; padding: 8px 16px; border-radius: 20px; font-weight: bold; font-size: 18px;">
                        {percentage_change:+.2f}%
                    </div>
                </div>
            </div>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
    </head>
    <body style="margin: 0; padding: 20px; background-color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
        
        <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            
            <!-- Header -->
            <div style="background: linear-gradient(135deg, {alert_color} 0%, {'#059669' if is_positive else '#dc2626'} 100%); color: white; padding: 30px 25px; text-align: center;">
                <div style="font-size: 48px; margin-bottom: 10px;">{alert_icon}</div>
                <h1 style="margin: 0; font-size: 28px; font-weight: 700;">Alert Triggered!</h1>
                <p style="margin: 10px 0 0 0; font-size: 18px; opacity: 0.9;">{symbol} Stock Alert</p>
            </div>
            
            <!-- Main Content -->
            <div style="padding: 30px 25px;">
                
                <!-- Alert Message -->
                <div style="background: #f9fafb; border-radius: 8px; padding: 20px; margin-bottom: 25px; border: 1px solid #e5e7eb;">
                    <h2 style="color: #1f2937; margin: 0 0 15px 0; font-size: 20px;">🚨 Alert Details</h2>
                    <p style="color: #374151; font-size: 16px; line-height: 1.6; margin: 0; font-weight: 500;">
                        {alert_message}
                    </p>
                </div>
                
                <!-- Price Change Section -->
                {price_change_section}
                
                <!-- Stock Information -->
                <div style="background: #f8fafc; border-radius: 8px; padding: 20px; margin: 25px 0;">
                    <h3 style="color: #1f2937; margin: 0 0 15px 0;">📊 Stock Information</h3>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                        <div>
                            <p style="margin: 0; color: #6b7280; font-size: 14px;">Symbol</p>
                            <p style="margin: 5px 0 15px 0; color: #1f2937; font-weight: 600; font-size: 16px;">{symbol}</p>
                        </div>
                        <div>
                            <p style="margin: 0; color: #6b7280; font-size: 14px;">Current Price</p>
                            <p style="margin: 5px 0 15px 0; color: #1f2937; font-weight: 600; font-size: 16px;">₹{current_price:.2f}</p>
                        </div>
                        <div>
                            <p style="margin: 0; color: #6b7280; font-size: 14px;">Alert Time</p>
                            <p style="margin: 5px 0 15px 0; color: #1f2937; font-weight: 600; font-size: 16px;">{timestamp}</p>
                        </div>
                        <div>
                            <p style="margin: 0; color: #6b7280; font-size: 14px;">Market Status</p>
                            <p style="margin: 5px 0 15px 0; color: #1f2937; font-weight: 600; font-size: 16px;">{market_status['status']}</p>
                        </div>
                    </div>
                </div>
                
                <!-- Important Notice -->
                <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; margin: 25px 0; border-radius: 0 8px 8px 0;">
                    <h3 style="color: #92400e; margin: 0 0 10px 0;">⚠️ Important Notice</h3>
                    <p style="color: #92400e; margin: 0; font-size: 14px; line-height: 1.5;">
                        This alert has been triggered and marked as complete. No further notifications will be sent for this specific alert condition. You can set up new alerts anytime through your Groww MCP system.
                    </p>
                </div>
                
                <!-- Action Button -->
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://groww.in/" style="display: inline-block; background: {alert_color}; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        📱 View Portfolio on Groww
                    </a>
                </div>
                
                <!-- Market Context -->
                <div style="background: #f1f5f9; border-radius: 8px; padding: 20px; margin: 25px 0 0 0;">
                    <h3 style="color: #1e293b; margin: 0 0 15px 0;">🕐 Market Context</h3>
                    <p style="color: #475569; margin: 0; font-size: 14px;">
                        <strong>Next Trading Session:</strong> {market_status['next_session']}<br>
                        <strong>Alert triggered during:</strong> {market_status['status']}
                    </p>
                </div>
                
            </div>
            
            <!-- Footer -->
            <div style="background: #f9fafb; padding: 20px 25px; text-align: center; border-top: 1px solid #e5e7eb;">
                <p style="margin: 0; color: #6b7280; font-size: 14px;">
                    📊 <strong>Groww MCP Alert System</strong><br>
                    Powered by Claude & Cursor • Real-time Stock Monitoring
                </p>
                <p style="margin: 10px 0 0 0; color: #9ca3af; font-size: 12px;">
                    This email was sent because you have active stock price alerts configured.
                </p>
            </div>
            
        </div>
        
        <!-- Mobile Optimization -->
        <style>
            @media only screen and (max-width: 600px) {{
                .container {{ margin: 10px !important; }}
                .header {{ padding: 20px 15px !important; }}
                .content {{ padding: 20px 15px !important; }}
                .grid {{ grid-template-columns: 1fr !important; }}
                .button {{ padding: 12px 24px !important; font-size: 14px !important; }}
            }}
        </style>
        
    </body>
    </html>
    """

    return {
        'subject': subject,
        'text': text_content,
        'html': html_content
    }


def create_daily_summary_template(triggered_alerts: list, date: str) -> Dict[str, str]:
    """
    Create a daily summary email template (for future use).

    Args:
        triggered_alerts: List of alerts triggered during the day
        date: Date for the summary

    Returns:
        Dictionary with email content
    """
    subject = f"📊 Daily Alert Summary - {date}"

    if not triggered_alerts:
        text_content = f"""
Daily Alert Summary - {date}

No alerts were triggered today.

Your monitoring system is running smoothly and watching your configured stock alerts.

Happy trading! 📈
        """.strip()

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>📊 Daily Alert Summary</h2>
                <p><strong>Date:</strong> {date}</p>
                <p>No alerts were triggered today.</p>
                <p>Your monitoring system is running smoothly and watching your configured stock alerts.</p>
                <p>Happy trading! 📈</p>
            </body>
        </html>
        """
    else:
        # TODO: Implement detailed summary for multiple alerts
        text_content = f"Daily summary with {len(triggered_alerts)} alerts"
        html_content = f"<p>Daily summary with {len(triggered_alerts)} alerts</p>"

    return {
        'subject': subject,
        'text': text_content,
        'html': html_content
    }
