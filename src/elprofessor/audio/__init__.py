"""Module audio pour ElProfessor - Mouvements de tête synchronisés avec la parole."""

from elprofessor.audio.head_wobbler import HeadWobbler
from elprofessor.audio.speech_tapper import SwayRollRT, HOP_MS

__all__ = [
    "HeadWobbler",
    "SwayRollRT",
    "HOP_MS",
]

