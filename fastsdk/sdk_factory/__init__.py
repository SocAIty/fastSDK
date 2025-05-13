"""
Client factory module for fastSDK.

This module provides tools to generate Python client code from service definitions.
"""

from .sdk_factory import create_sdk, normalize_class_name

__all__ = ['create_sdk', 'normalize_class_name']
