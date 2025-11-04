"""
Prompt template loader using Jinja2.

This module provides functionality to load and render Jinja2 templates
for agent prompts with configuration variables.
"""
import os
from typing import Dict, Any, Optional
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound
from idss_agent.utils.config import get_config


class PromptLoader:
    """
    Jinja2 template loader for agent prompts.

    Loads templates from config/prompts/ directory and renders them
    with configuration variables (terminology, limits, etc.).
    """

    _instance: Optional['PromptLoader'] = None
    _env: Optional[Environment] = None
    _template_cache: Dict[str, Template] = {}

    def __new__(cls):
        """Singleton pattern - only one instance exists."""
        if cls._instance is None:
            cls._instance = super(PromptLoader, cls).__new__(cls)
            cls._instance._setup_environment()
        return cls._instance

    def _setup_environment(self) -> None:
        """Setup Jinja2 environment with template directory."""
        # Get project root (parent of idss_agent directory)
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent
        template_dir = project_root / "config" / "prompts"

        # Create prompts directory if it doesn't exist
        template_dir.mkdir(parents=True, exist_ok=True)

        # Setup Jinja2 environment
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,  
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True
        )

        # Initialize cache
        self._template_cache = {}

    def load_template(self, template_name: str) -> Template:
        """
        Load a Jinja2 template by name.

        Args:
            template_name: Template filename (e.g., 'interview_system.j2')

        Returns:
            Jinja2 Template object

        Raises:
            TemplateNotFound: If template file doesn't exist
        """
        # Check cache first
        if template_name in self._template_cache:
            return self._template_cache[template_name]

        # Load template
        try:
            template = self._env.get_template(template_name)
            self._template_cache[template_name] = template
            return template
        except TemplateNotFound:
            raise FileNotFoundError(
                f"Template not found: {template_name}\n"
                f"Expected location: config/prompts/{template_name}"
            )

    def render(
        self,
        template_name: str,
        extra_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Load and render a template with configuration variables.

        Automatically includes terminology from config as context variables.
        Additional context can be provided via extra_context parameter.

        Args:
            template_name: Template filename (e.g., 'interview_system.j2')
            extra_context: Additional variables to pass to template

        Returns:
            Rendered prompt string

        Example:
            loader = PromptLoader()
            prompt = loader.render('interview_system.j2', {
                'max_questions': 8,
                'current_stage': 'budget'
            })
        """
        template = self.load_template(template_name)

        # Build context with terminology from config
        config = get_config()
        context = config.get_terminology_context()

        # Add limits to context
        context.update({
            'max_interview_questions': config.limits.get('max_interview_questions', 8),
            'max_recommended_items': config.limits.get('max_recommended_items', 20),
            'top_vehicles_to_show': config.limits.get('top_vehicles_to_show', 3),
            'max_conversation_history': config.limits.get('max_conversation_history', 10),
        })

        # Add interactive element limits
        context.update({
            'quick_replies_min': config.interactive.get('quick_replies', {}).get('min_options', 2),
            'quick_replies_max': config.interactive.get('quick_replies', {}).get('max_options', 4),
            'quick_replies_max_words': config.interactive.get('quick_replies', {}).get('max_words_per_option', 5),
            'followups_min': config.interactive.get('suggested_followups', {}).get('min_options', 3),
            'followups_max': config.interactive.get('suggested_followups', {}).get('max_options', 5),
            'followups_max_words': config.interactive.get('suggested_followups', {}).get('max_words_per_phrase', 8),
        })

        # Merge extra context (overrides config values if keys conflict)
        if extra_context:
            context.update(extra_context)

        # Render template
        return template.render(**context)

    def clear_cache(self) -> None:
        """Clear the template cache. Useful when templates are updated."""
        self._template_cache.clear()


# Global singleton instance
_loader_instance: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """
    Get the global PromptLoader instance.

    Returns:
        PromptLoader singleton instance
    """
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = PromptLoader()
    return _loader_instance


def render_prompt(
    template_name: str,
    extra_context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Convenience function to render a prompt template.

    Args:
        template_name: Template filename (e.g., 'interview_system.j2')
        extra_context: Additional variables to pass to template

    Returns:
        Rendered prompt string

    Example:
        from idss_agent.utils.prompts import render_prompt

        prompt = render_prompt('interview_system.j2')
        # or with extra context:
        prompt = render_prompt('discovery.j2', {'current_stage': 'recommendation'})
    """
    loader = get_prompt_loader()
    return loader.render(template_name, extra_context)
