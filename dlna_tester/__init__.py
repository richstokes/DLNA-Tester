"""DLNA/UPnP Media Server Compliance Tester."""

from .tester import DLNATester
from .tests import TestResult, TestSuite

__version__ = "1.0.0"
__all__ = ["DLNATester", "TestResult", "TestSuite"]
