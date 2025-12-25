"""
Base source classes for paper and blog sources.
"""

from abc import ABC, abstractmethod
from typing import List

from models import Paper


class BaseSource(ABC):
    """Abstract base class for all paper sources."""

    @abstractmethod
    async def fetch(self, **kwargs) -> List[Paper]:
        """Fetch papers from this source."""
        pass
