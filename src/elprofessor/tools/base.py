"""Classe de base pour tous les tools."""

from abc import ABC, abstractmethod
from typing import Optional


class Tool(ABC):
    """Classe abstraite de base pour tous les tools."""

    def __init__(self, name: str, description: str):
        """
        Initialise un tool.

        Args:
            name: Nom du tool
            description: Description du tool
        """
        self.name = name
        self.description = description
        self._running = False
        self._reachy = None

    def set_reachy(self, reachy):
        """
        Définit l'instance ReachyMini à utiliser.

        Args:
            reachy: Instance de ReachyMini
        """
        self._reachy = reachy

    @abstractmethod
    def start(self) -> bool:
        """
        Démarre le tool.

        Returns:
            True si le démarrage a réussi, False sinon
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Arrête le tool."""
        pass

    def is_running(self) -> bool:
        """
        Vérifie si le tool est en cours d'exécution.

        Returns:
            True si le tool est actif, False sinon
        """
        return self._running

    def _set_running(self, running: bool) -> None:
        """
        Définit l'état d'exécution du tool.

        Args:
            running: État d'exécution
        """
        self._running = running

