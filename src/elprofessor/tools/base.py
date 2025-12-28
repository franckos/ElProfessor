"""Classe de base pour tous les tools."""

from abc import ABC, abstractmethod
from typing import Dict, Optional


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
        self._camera_manager = None

    def set_reachy(self, reachy):
        """
        Définit l'instance ReachyMini à utiliser.

        Args:
            reachy: Instance de ReachyMini
        """
        self._reachy = reachy

    def set_camera_manager(self, camera_manager):
        """
        Définit le CameraManager à utiliser.

        Args:
            camera_manager: Instance de CameraManager
        """
        self._camera_manager = camera_manager

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

    def to_openai_function(self) -> Optional[Dict]:
        """
        Convertit le tool en définition de fonction OpenAI.

        Returns:
            Dictionnaire au format OpenAI Function Calling, ou None si le tool
            ne doit pas être exposé à ChatGPT
        """
        return None

    def execute(self, **kwargs) -> Dict:
        """
        Exécute le tool avec des paramètres.

        Args:
            **kwargs: Paramètres pour l'exécution du tool

        Returns:
            Dictionnaire contenant le résultat de l'exécution avec les clés:
            - 'success': bool indiquant si l'exécution a réussi
            - 'result': résultat de l'exécution (si success=True)
            - 'error': message d'erreur (si success=False)
        """
        return {"success": False, "error": f"Tool '{self.name}' ne supporte pas l'exécution avec paramètres"}
