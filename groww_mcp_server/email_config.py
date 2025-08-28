"""
Email configuration management for Groww MCP Server.
"""

import json
import os
import logging
from typing import Dict, Optional, Any, List, Union
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """Email configuration data structure."""
    smtp_server: str
    smtp_port: int
    username: str
    password: str
    from_email: str
    to_emails: List[str]
    use_tls: bool = True
    enabled: bool = True

    def validate(self) -> bool:
        """Validate email configuration."""
        if not all([self.smtp_server, self.username, self.password,
                   self.from_email, self.to_emails]):
            return False

        if not (1 <= self.smtp_port <= 65535):
            return False

        if '@' not in self.from_email:
            return False

        # Validate all recipient emails
        if not isinstance(self.to_emails, list) or len(self.to_emails) == 0:
            return False

        for email in self.to_emails:
            if '@' not in email:
                return False

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'smtp_server': self.smtp_server,
            'smtp_port': self.smtp_port,
            'username': self.username,
            'password': self.password,
            'from_email': self.from_email,
            'to_emails': self.to_emails,
            'use_tls': self.use_tls,
            'enabled': self.enabled
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmailConfig':
        """Create from dictionary."""
        # Handle backward compatibility with single to_email
        to_emails = data.get('to_emails', [])
        if not to_emails and data.get('to_email'):
            # Convert old single email to list
            to_emails = [data.get('to_email')]
        elif isinstance(to_emails, str):
            # Handle case where to_emails is accidentally a string
            to_emails = [to_emails]

        return cls(
            smtp_server=data.get('smtp_server', ''),
            smtp_port=data.get('smtp_port', 587),
            username=data.get('username', ''),
            password=data.get('password', ''),
            from_email=data.get('from_email', ''),
            to_emails=to_emails,
            use_tls=data.get('use_tls', True),
            enabled=data.get('enabled', True)
        )


class EmailConfigManager:
    """Manages email configuration with secure storage."""

    def __init__(self, config_file: str = "email_config.json"):
        # Try multiple locations for the config file
        possible_paths = [
            Path(config_file),  # Current directory
            Path("..") / config_file,  # Parent directory
            Path(__file__).parent.parent / config_file,  # Project root
        ]

        self.config_file = None
        for path in possible_paths:
            if path.exists():
                self.config_file = path
                break

        # If no existing file found, use the first path for new configs
        if self.config_file is None:
            self.config_file = possible_paths[0]

        self._config: Optional[EmailConfig] = None
        self._load_config()

    def _load_config(self) -> None:
        """Load email configuration from file or environment."""
        config_data = {}

        # Try to load from file first
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
                logger.info("Loaded email config from file")
            except Exception as e:
                logger.warning(f"Failed to load email config from file: {e}")

        # Override with environment variables if available
        env_config = self._load_from_env()
        if env_config:
            config_data.update(env_config)
            logger.info("Email config loaded from environment variables")

        if config_data:
            self._config = EmailConfig.from_dict(config_data)
            if not self._config.validate():
                logger.warning("Invalid email configuration")
                self._config = None
        else:
            logger.info("No email configuration found")

    def _load_from_env(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        env_vars = {
            'SMTP_SERVER': 'smtp_server',
            'SMTP_PORT': 'smtp_port',
            'SMTP_USERNAME': 'username',
            'SMTP_PASSWORD': 'password',
            'FROM_EMAIL': 'from_email',
            'TO_EMAIL': 'to_email',
            'USE_TLS': 'use_tls',
            'EMAIL_ENABLED': 'enabled'
        }

        config = {}
        for env_var, config_key in env_vars.items():
            value = os.getenv(env_var)
            if value is not None:
                if config_key in ['smtp_port']:
                    config[config_key] = int(value)
                elif config_key in ['use_tls', 'enabled']:
                    config[config_key] = value.lower() in (
                        'true', '1', 'yes', 'on')
                else:
                    config[config_key] = value

        return config

    def save_config(self, config: EmailConfig) -> bool:
        """Save email configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config.to_dict(), f, indent=2)
            self._config = config
            logger.info("Email configuration saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save email config: {e}")
            return False

    def get_config(self) -> Optional[EmailConfig]:
        """Get current email configuration."""
        return self._config

    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return self._config is not None and self._config.validate() and self._config.enabled

    def update_config(self, **kwargs) -> bool:
        """Update specific configuration values."""
        if not self._config:
            # Create new config with provided values
            config_data = {
                'smtp_server': kwargs.get('smtp_server', ''),
                'smtp_port': kwargs.get('smtp_port', 587),
                'username': kwargs.get('username', ''),
                'password': kwargs.get('password', ''),
                'from_email': kwargs.get('from_email', ''),
                'to_emails': kwargs.get('to_emails', []),
                'use_tls': kwargs.get('use_tls', True),
                'enabled': kwargs.get('enabled', True)
            }
            new_config = EmailConfig.from_dict(config_data)
        else:
            # Update existing config
            config_dict = self._config.to_dict()
            config_dict.update(kwargs)
            new_config = EmailConfig.from_dict(config_dict)

        return self.save_config(new_config)

    def disable_email(self) -> bool:
        """Disable email notifications."""
        if self._config:
            return self.update_config(enabled=False)
        return True

    def enable_email(self) -> bool:
        """Enable email notifications if properly configured."""
        if self._config and self._config.validate():
            return self.update_config(enabled=True)
        return False

    def get_status(self) -> Dict[str, Any]:
        """Get email configuration status."""
        if not self._config:
            return {
                'configured': False,
                'enabled': False,
                'valid': False,
                'smtp_server': None,
                'smtp_port': None,
                'from_email': None,
                'to_emails': None
            }

        return {
            'configured': True,
            'enabled': self._config.enabled,
            'valid': self._config.validate(),
            'smtp_server': self._config.smtp_server,
            'smtp_port': self._config.smtp_port,
            'from_email': self._config.from_email,
            'to_emails': self._config.to_emails,
            'use_tls': self._config.use_tls
        }

    @staticmethod
    def get_gmail_config(email: str, app_password: str, to_email: str) -> EmailConfig:
        """Create Gmail configuration with app password."""
        return EmailConfig(
            smtp_server='smtp.gmail.com',
            smtp_port=587,
            username=email,
            password=app_password,
            from_email=f"Groww Alert System <{email}>",
            to_emails=[to_email],
            use_tls=True,
            enabled=True
        )

    @staticmethod
    def get_outlook_config(email: str, password: str, to_email: str) -> EmailConfig:
        """Create Outlook/Hotmail configuration."""
        return EmailConfig(
            smtp_server='smtp.office365.com',
            smtp_port=587,
            username=email,
            password=password,
            from_email=f"Groww Alert System <{email}>",
            to_emails=[to_email],
            use_tls=True,
            enabled=True
        )

    @staticmethod
    def get_sample_env_config() -> str:
        """Get sample environment configuration."""
        return """
# Email Configuration Environment Variables
# Copy these to your .env file and fill in your details

# SMTP Server Settings
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Email Addresses  
FROM_EMAIL=Groww Alert System <your-email@gmail.com>
TO_EMAIL=your-email@gmail.com

# Optional Settings
USE_TLS=true
EMAIL_ENABLED=true

# Gmail App Password Setup:
# 1. Go to Google Account settings
# 2. Enable 2-factor authentication
# 3. Generate App Password for "Mail"
# 4. Use that app password, not your Gmail password
        """.strip()


# Global config manager instance
email_config_manager = EmailConfigManager()
