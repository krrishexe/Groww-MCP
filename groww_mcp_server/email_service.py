"""
Email service for sending alert notifications.
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications."""

    def __init__(self,
                 smtp_server: str,
                 smtp_port: int,
                 username: str,
                 password: str,
                 from_email: str,
                 to_emails: List[str],
                 use_tls: bool = True):
        """
        Initialize email service.

        Args:
            smtp_server: SMTP server address (e.g., 'smtp.gmail.com')
            smtp_port: SMTP port (587 for TLS, 465 for SSL, 25 for plain)
            username: SMTP username (usually email address)
            password: SMTP password (app password recommended)
            from_email: From email address with optional name
            to_emails: List of recipient email addresses
            use_tls: Whether to use TLS encryption
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.to_emails = to_emails if isinstance(
            to_emails, list) else [to_emails]
        self.use_tls = use_tls

        # Rate limiting
        self.last_email_time = {}
        self.rate_limit_seconds = 60  # Minimum 1 minute between emails for same alert type

    async def send_email(self,
                         subject: str,
                         body_text: str,
                         body_html: Optional[str] = None,
                         alert_type: str = "general") -> bool:
        """
        Send an email notification to all recipients.

        Args:
            subject: Email subject
            body_text: Plain text body
            body_html: HTML body (optional)
            alert_type: Type of alert for rate limiting

        Returns:
            True if email sent successfully to all recipients, False otherwise
        """
        try:
            # Check rate limiting
            if self._is_rate_limited(alert_type):
                logger.info(f"Email rate limited for alert type: {alert_type}")
                return False

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = ', '.join(self.to_emails)  # Join all recipients
            msg['Date'] = datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')

            # Add text part
            text_part = MIMEText(body_text, 'plain', 'utf-8')
            msg.attach(text_part)

            # Add HTML part if provided
            if body_html:
                html_part = MIMEText(body_html, 'html', 'utf-8')
                msg.attach(html_part)

            # Send email to all recipients
            await self._send_message(msg)

            # Update rate limiting
            self.last_email_time[alert_type] = datetime.now()

            logger.info(
                f"Email sent successfully to {len(self.to_emails)} recipients: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to recipients: {e}")
            return False

    async def send_alert_email(self,
                               alert_message: str,
                               symbol: str,
                               current_price: float,
                               base_price: Optional[float] = None,
                               percentage_change: Optional[float] = None) -> bool:
        """
        Send a formatted alert email.

        Args:
            alert_message: The triggered alert message
            symbol: Stock symbol
            current_price: Current stock price
            base_price: Base price for percentage alerts
            percentage_change: Percentage change if applicable

        Returns:
            True if email sent successfully
        """
        try:
            # Import here to avoid circular imports
            from .email_templates import create_alert_email_template

            # Generate email content
            email_content = create_alert_email_template(
                alert_message=alert_message,
                symbol=symbol,
                current_price=current_price,
                base_price=base_price,
                percentage_change=percentage_change
            )

            # Send email
            return await self.send_email(
                subject=email_content['subject'],
                body_text=email_content['text'],
                body_html=email_content['html'],
                alert_type=f"alert_{symbol.lower()}"
            )

        except Exception as e:
            logger.error(f"Failed to send alert email: {e}")
            return False

    async def send_test_email(self) -> bool:
        """Send a test email to verify configuration."""
        try:
            subject = "🧪 Groww MCP Alert System - Test Email"
            text_body = """
This is a test email from your Groww MCP Alert System.

If you're receiving this, your email configuration is working correctly!

System Information:
- SMTP Server: {smtp_server}
- Port: {smtp_port}
- From: {from_email}
- To: {to_emails}
- Time: {timestamp}

You can now set up stock price alerts and receive notifications via email.

Happy trading! 📈
            """.format(
                smtp_server=self.smtp_server,
                smtp_port=self.smtp_port,
                from_email=self.from_email,
                to_emails=', '.join(self.to_emails),
                timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )

            html_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px 10px 0 0;">
                        <h1 style="margin: 0;">🧪 Test Email</h1>
                        <p style="margin: 5px 0 0 0;">Groww MCP Alert System</p>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 0 0 10px 10px;">
                        <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            <h2 style="color: #2d3748; margin-top: 0;">✅ Configuration Test Successful!</h2>
                            
                            <p style="color: #4a5568;">If you're reading this, your email configuration is working correctly!</p>
                            
                            <div style="background: #e6fffa; border-left: 4px solid #38b2ac; padding: 15px; margin: 20px 0;">
                                <h3 style="color: #2d3748; margin: 0 0 10px 0;">📊 System Information</h3>
                                <p style="margin: 5px 0; color: #4a5568;"><strong>SMTP Server:</strong> {self.smtp_server}</p>
                                <p style="margin: 5px 0; color: #4a5568;"><strong>Port:</strong> {self.smtp_port}</p>
                                <p style="margin: 5px 0; color: #4a5568;"><strong>From:</strong> {self.from_email}</p>
                                <p style="margin: 5px 0; color: #4a5568;"><strong>To:</strong> {', '.join(self.to_emails)}</p>
                                <p style="margin: 5px 0; color: #4a5568;"><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                            </div>
                            
                            <p style="color: #4a5568;">You can now set up stock price alerts and receive notifications via email.</p>
                            
                            <div style="text-align: center; margin-top: 30px;">
                                <p style="font-size: 24px; margin: 0;">📈 Happy Trading!</p>
                            </div>
                        </div>
                    </div>
                    
                    <div style="text-align: center; margin-top: 20px; color: #a0aec0; font-size: 12px;">
                        <p>Groww MCP Alert System • Powered by Claude & Cursor</p>
                    </div>
                </body>
            </html>
            """

            return await self.send_email(
                subject=subject,
                body_text=text_body,
                body_html=html_body,
                alert_type="test"
            )

        except Exception as e:
            logger.error(f"Failed to send test email: {e}")
            return False

    async def _send_message(self, msg: MIMEMultipart) -> None:
        """Send the email message via SMTP."""
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._send_message_sync, msg)

    def _send_message_sync(self, msg: MIMEMultipart) -> None:
        """Synchronous email sending."""
        server = None
        try:
            # Create SMTP server
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)

            if self.use_tls:
                server.starttls()

            # Login
            server.login(self.username, self.password)

            # Send message
            text = msg.as_string()
            server.sendmail(self.from_email, self.to_emails, text)

        finally:
            if server:
                server.quit()

    def _is_rate_limited(self, alert_type: str) -> bool:
        """Check if this alert type is rate limited."""
        if alert_type not in self.last_email_time:
            return False

        time_diff = datetime.now() - self.last_email_time[alert_type]
        return time_diff.total_seconds() < self.rate_limit_seconds

    def test_connection(self) -> bool:
        """Test SMTP connection without sending email."""
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            if self.use_tls:
                server.starttls()
            server.login(self.username, self.password)
            server.quit()
            return True
        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False
