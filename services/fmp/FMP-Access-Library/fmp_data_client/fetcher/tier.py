"""Tier access control and validation."""

from typing import List

from ..config import Tier
from .endpoints import TIER_REQUIREMENTS, Endpoint


def can_access_endpoint(user_tier: Tier, endpoint: Endpoint) -> bool:
    """Check if a user tier can access an endpoint.

    Args:
        user_tier: User's subscription tier
        endpoint: Endpoint to check access for

    Returns:
        True if user can access the endpoint

    Example:
        >>> can_access_endpoint(Tier.STARTER, Endpoint.QUOTE)
        True
        >>> can_access_endpoint(Tier.STARTER, Endpoint.PRICE_TARGET)
        False
    """
    required_tier = TIER_REQUIREMENTS.get(endpoint)
    if required_tier is None:
        # If endpoint not in requirements, assume it's accessible
        return True

    # Tier hierarchy: STARTER < PREMIUM < ULTIMATE
    tier_hierarchy = {
        Tier.STARTER: 0,
        Tier.PREMIUM: 1,
        Tier.ULTIMATE: 2,
    }

    user_level = tier_hierarchy.get(user_tier, 0)
    required_level = tier_hierarchy.get(required_tier, 0)

    return user_level >= required_level


def get_accessible_endpoints(user_tier: Tier) -> List[Endpoint]:
    """Get list of endpoints accessible to a user tier.

    Args:
        user_tier: User's subscription tier

    Returns:
        List of accessible endpoints
    """
    return [
        endpoint
        for endpoint in Endpoint
        if can_access_endpoint(user_tier, endpoint)
    ]


def get_required_tier(endpoint: Endpoint) -> Tier:
    """Get the minimum required tier for an endpoint.

    Args:
        endpoint: Endpoint to check

    Returns:
        Minimum required tier (defaults to STARTER if not specified)
    """
    return TIER_REQUIREMENTS.get(endpoint, Tier.STARTER)


def get_rate_limit_for_tier(tier: Tier) -> int:
    """Get API calls per minute limit for a tier.

    Args:
        tier: Subscription tier

    Returns:
        Calls per minute limit
    """
    limits = {
        Tier.STARTER: 300,
        Tier.PREMIUM: 750,
        Tier.ULTIMATE: 3000,
    }
    return limits.get(tier, 300)
