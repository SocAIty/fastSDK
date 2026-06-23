"""
Stub factory module for fastSDK.

This module provides tools to generate Python client stub code from service definitions.
"""

from ..fastStub import FastStub
from .sdk_factory import generate_stub


__all__ = ['generate_stub', 'FastStub']
