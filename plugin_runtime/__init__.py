"""AI-Love's plugin kernel. Business implementations are discovered, never imported here."""

from .contracts import Plugin, PluginContext, PluginError, PluginManifest
from .manager import PluginManager

__all__ = ["Plugin", "PluginContext", "PluginError", "PluginManager", "PluginManifest"]
