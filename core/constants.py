"""Settings and constants for FoodBridge Smart Match, proposals, and inventory."""
from decimal import Decimal

# Smart match weighting constants (sum to 100)
MATCH_WEIGHTS = {
    "item_compatibility": 25,
    "quantity_coverage": 25,
    "distance": 15,
    "pickup_feasibility": 10,
    "safety_deadline": 10,
    "recipient_capacity": 5,
    "reliability": 10,
}

# Proposal expiry in hours
PROPOSAL_EXPIRY_HOURS = 12

# Messaging rate limits
MAX_MESSAGES_PER_MINUTE = 20
MAX_MESSAGE_LENGTH = 2000
