"""
Configuration management for Groww MCP Server.
Updated to work with real Groww API according to documentation.
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class GrowwConfig:
    """Configuration class for Groww API settings."""

    def __init__(self):
        # Groww API credentials - REQUIRED
        self.api_auth_token: str = os.getenv("GROWW_ACCESS_TOKEN", "")

        # API configuration
        self.base_url: str = os.getenv(
            "GROWW_BASE_URL", "https://api.groww.in")
        self.timeout: int = int(os.getenv("API_TIMEOUT", "30"))

        # Trading configuration
        self.max_order_value: float = float(
            os.getenv("MAX_ORDER_VALUE", "100000"))

        # Logging
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")

        # Rate limiting
        self.rate_limit_requests: int = int(
            os.getenv("RATE_LIMIT_REQUESTS", "100"))
        self.rate_limit_window: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

    def validate(self) -> bool:
        """Validate that required configuration is present."""
        if not self.api_auth_token:
            return False

        if len(self.api_auth_token.strip()) < 10:  # Basic validation
            return False

        return True

    def get_headers(self) -> dict:
        """Get standard headers for API requests."""
        return {
            "Authorization": f"Bearer {self.api_auth_token}",
            "Content-Type": "application/json",
            "User-Agent": "GrowwMCPServer/1.0.0"
        }

    def get_validation_errors(self) -> list[str]:
        """Get detailed validation errors for configuration."""
        errors = []

        if not self.api_auth_token:
            errors.append(
                "GROWW_ACCESS_TOKEN environment variable is required")
        elif len(self.api_auth_token.strip()) < 10:
            errors.append(
                "GROWW_ACCESS_TOKEN appears to be invalid (too short)")

        if self.timeout <= 0:
            errors.append("API_TIMEOUT must be positive")

        if self.max_order_value <= 0:
            errors.append("MAX_ORDER_VALUE must be positive")

        return errors


# Global configuration instance
config = GrowwConfig()
