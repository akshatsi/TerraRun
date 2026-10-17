"""Data types for the distance engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

ALGORITHM_VERSION = "gps-1.0.0"


@dataclass
class RawFix:
    lat: float
    lng: float
    t: float  # unix seconds
    accuracy_m: Optional[float] = None
    speed_mps: Optional[float] = None
    heading_deg: Optional[float] = None
    altitude_m: Optional[float] = None


@dataclass
class ProcessedFix:
    index: int
    lat: float
    lng: float
    t: float
    accepted: bool
    rejection_reason: Optional[str]
    segment_id: Optional[int]
    filtered_lat: Optional[float] = None
    filtered_lng: Optional[float] = None


@dataclass
class Segment:
    id: int
    fix_indices: list[int]
    distance_m: float
    start_t: float
    end_t: float


@dataclass
class TrackConfig:
    preferred_accuracy_m: float = 10.0
    max_accuracy_m: float = 20.0
    min_displacement_m: float = 4.0
    accuracy_displacement_factor: float = 0.5
    stationary_speed_mps: float = 0.5
    max_speed_mps: float = 12.0
    long_gap_s: float = 15.0
    use_kalman: bool = False
    # Extras beyond the shared contract (all have defaults).
    reanchor_after: int = 5  # consistent implausible fixes in a row before re-anchoring
    kalman_accel_std: float = 1.0  # process noise, m/s^2
    kalman_default_accuracy_m: float = 15.0  # measurement sigma when accuracy is unknown


@dataclass
class TrackResult:
    algorithm_version: str
    fixes: list[ProcessedFix]
    segments: list[Segment]
    distance_m: float
    raw_distance_m: float
    uncertain_distance_m: float
    moving_time_s: float
    accepted_count: int
    rejected_count: int
    gap_count: int
    quality: str
