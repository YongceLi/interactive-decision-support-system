"""
Configuration loader for IDSS agent system.

This module loads and validates the agent configuration from YAML file.
Uses singleton pattern to ensure config is loaded only once.
"""
import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path


class AgentConfig:
    """
    Singleton configuration loader for IDSS agent.

    Loads configuration from config/agent_config.yaml and provides
    convenient access methods for different configuration sections.
    """

    _instance: Optional['AgentConfig'] = None
    _config: Optional[Dict[str, Any]] = None

    def __new__(cls):
        """Singleton pattern - only one instance exists."""
        if cls._instance is None:
            cls._instance = super(AgentConfig, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        # Get project root (parent of idss_agent directory)
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent
        config_path = project_root / "config" / "agent_config.yaml"

        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}\n"
                f"Please ensure config/agent_config.yaml exists in the project root."
            )

        with open(config_path, 'r') as f:
            self._config = yaml.safe_load(f)

        # Validate required sections
        required_sections = ['terminology', 'models', 'limits', 'interactive']
        for section in required_sections:
            if section not in self._config:
                raise ValueError(f"Missing required configuration section: {section}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key path (dot notation).

        Examples:
            config.get('models.interview.name') -> 'gpt-4o-mini'
            config.get('limits.max_recommended_items') -> 20
            config.get('terminology.product_name') -> 'product'

        Args:
            key: Configuration key in dot notation
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    @property
    def terminology(self) -> Dict[str, str]:
        """Get product terminology configuration."""
        return self._config.get('terminology', {})

    @property
    def models(self) -> Dict[str, Dict[str, Any]]:
        """Get model configuration for all components."""
        return self._config.get('models', {})

    @property
    def limits(self) -> Dict[str, int]:
        """Get system limits configuration."""
        return self._config.get('limits', {})

    @property
    def interactive(self) -> Dict[str, Dict[str, int]]:
        """Get interactive elements configuration."""
        return self._config.get('interactive', {})

    @property
    def features(self) -> Dict[str, bool]:
        """Get feature flags configuration."""
        return self._config.get('features', {})

    @property
    def api(self) -> Dict[str, Any]:
        """Get API configuration."""
        return self._config.get('api', {})

    @property
    def logging(self) -> Dict[str, str]:
        """Get logging configuration."""
        return self._config.get('logging', {})

    def get_model_config(self, component: str) -> Dict[str, Any]:
        """
        Get model configuration for a specific component.

        Args:
            component: Component name (e.g., 'interview', 'discovery', 'analytical')

        Returns:
            Dictionary with 'name', 'temperature', 'max_tokens'

        Raises:
            ValueError: If component not found in configuration
        """
        if component not in self.models:
            raise ValueError(
                f"Unknown component: {component}. "
                f"Available components: {list(self.models.keys())}"
            )

        return self.models[component]

    def get_terminology_context(self) -> Dict[str, str]:
        """
        Get terminology as a context dictionary for template rendering.

        Returns:
            Dictionary with all terminology variables for Jinja2 templates
        """
        return self.terminology.copy()


# Global singleton instance
_config_instance: Optional[AgentConfig] = None


def get_config() -> AgentConfig:
    """
    Get the global configuration instance.

    Returns:
        AgentConfig singleton instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = AgentConfig()
    return _config_instance


def reload_config() -> AgentConfig:
    """
    Force reload configuration from file.

    Useful for testing or when configuration file is updated.

    Returns:
        Fresh AgentConfig instance
    """
    global _config_instance
    AgentConfig._instance = None
    AgentConfig._config = None
    _config_instance = None
    return get_config()
