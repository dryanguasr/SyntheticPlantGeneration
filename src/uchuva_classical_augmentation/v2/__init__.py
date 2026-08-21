"""Classical Augmentation v2: reproducible, failure-oriented recipes."""

from .config import CampaignConfig, ScenarioConfig, default_campaign_config
from .labels import YoloBox
from .manifest import DerivedSampleRecord

__all__ = [
    "CampaignConfig",
    "DerivedSampleRecord",
    "ScenarioConfig",
    "YoloBox",
    "default_campaign_config",
]
