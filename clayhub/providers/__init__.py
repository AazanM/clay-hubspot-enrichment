"""Provider registry."""
import os

from .apollo import ApolloProvider
from .base import Provider
from .hunter import HunterProvider
from .mock import MockProvider


def build_providers(names: list[str]) -> list[Provider]:
    providers = []
    for name in names:
        if name.startswith("mock_"):
            providers.append(MockProvider(name))
        elif name == "apollo" and os.getenv("APOLLO_API_KEY"):
            providers.append(ApolloProvider())
        elif name == "hunter" and os.getenv("HUNTER_API_KEY"):
            providers.append(HunterProvider())
    return providers
