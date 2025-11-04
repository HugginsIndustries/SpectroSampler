"""Audio event detection modules."""

from samplepacker.detectors.base import BaseDetector, Segment
from samplepacker.detectors.energy import NonSilenceEnergyDetector
from samplepacker.detectors.flux import TransientFluxDetector
from samplepacker.detectors.spectral import SpectralInterestingnessDetector
from samplepacker.detectors.vad import VoiceVADDetector

__all__ = [
    "BaseDetector",
    "Segment",
    "VoiceVADDetector",
    "TransientFluxDetector",
    "NonSilenceEnergyDetector",
    "SpectralInterestingnessDetector",
]
