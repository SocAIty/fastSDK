"""
Client factory module for fastSDK.

This module provides tools to generate Python client code from service definitions.
"""

from .sdk_factory import create_sdk

__all__ = ['create_sdk', 'normalize_name_for_python']
