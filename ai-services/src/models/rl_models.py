# ai-services/src/models/rl_models.py
"""Pydantic v2 models for the RL signal controller API."""

from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field


class TrafficStateRequest(BaseModel):
    intersection_id: str
    timestamp: int
    north_count: int = Field(ge=0)
    south_count: int = Field(ge=0)
    east_count:  int = Field(ge=0)
    west_count:  int = Field(ge=0)
    north_wait:  float = 0.0
    south_wait:  float = 0.0
    east_wait:   float = 0.0
    west_wait:   float = 0.0
    mode:   str = "RL"
    source: str = "sumo_simulation"


class SignalDecisionResponse(BaseModel):
    intersection_id: str
    timestamp: int
    green_arm:      str
    phase_duration: int
    action_id:      int
    confidence:     float
    all_q_values:   List[float]
    fallback_used:  bool
    reasoning:      str
