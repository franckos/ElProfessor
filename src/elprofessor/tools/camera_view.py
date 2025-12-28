"""Tool d'affichage de la caméra pour Reachy Mini."""

from typing import Dict, Optional

import cv2
import numpy as np

from elprofessor.tools.base import Tool


class CameraViewTool(Tool):
    """Tool qui affiche la vue de la caméra de Reachy Mini dans une fenêtre."""

    def __init__(
        self,
        window_name: str = "Reachy Mini Vision",
        x: Optional[int] = None,
        y: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ):
        """
        Initialise le tool d'affichage de la caméra.

        Args:
            window_name: Nom de la fenêtre
            x: Position X de la fenêtre (en pixels, optionnel)
            y: Position Y de la fenêtre (en pixels, optionnel)
            width: Largeur de la fenêtre (en pixels, optionnel)
            height: Hauteur de la fenêtre (en pixels, optionnel)
        """
        super().__init__(
            name="camera_view", description="Affichage de la caméra - Affiche la vue de la caméra de Reachy Mini"
        )
        self._window_name = window_name
        self._window_x = x
        self._window_y = y
        self._window_width = width
        self._window_height = height
        self._current_frame: Optional[np.ndarray] = None

    def start(self) -> bool:
        """
        Démarre l'affichage de la caméra.

        Returns:
            True si le démarrage a réussi, False sinon
        """
        if self._camera_manager is None:
            print("❌ CameraManager non défini pour le tool camera_view")
            return False

        if self._running:
            return False

        # Enregistrer le callback pour recevoir les frames
        self._camera_manager.register_frame_callback(self._on_frame_received)

        # Créer la fenêtre d'affichage avec position et taille si spécifiées
        if not self._camera_manager.create_display_window(
            self._window_name,
            x=self._window_x,
            y=self._window_y,
            width=self._window_width,
            height=self._window_height,
        ):
            return False

        self._set_running(True)
        return True

    def stop(self) -> None:
        """Arrête l'affichage de la caméra."""
        if not self._running:
            return

        # Désenregistrer le callback
        if self._camera_manager is not None:
            self._camera_manager.unregister_frame_callback(self._on_frame_received)

        self._set_running(False)
        self._current_frame = None

    def _on_frame_received(self, img: np.ndarray) -> None:
        """
        Callback appelé lorsqu'une nouvelle frame est reçue du CameraManager.

        Args:
            img: Image reçue
        """
        self._current_frame = img.copy()

    def update_display(self) -> bool:
        """
        Met à jour l'affichage de la fenêtre. Doit être appelé depuis le thread principal.

        Returns:
            True si une image a été affichée, False sinon
        """
        if not self._running or self._current_frame is None:
            return False

        if self._camera_manager is not None:
            self._camera_manager.update_display(self._current_frame, self._window_name)
            return True
        return False

    def to_openai_function(self) -> Optional[Dict]:
        """
        Convertit le tool en définition de fonction OpenAI.

        Returns:
            Dictionnaire au format OpenAI Function Calling (format Realtime API)
        """
        return {
            "type": "function",
            "name": "camera_view",
            "description": "Active ou désactive l'affichage de la caméra dans une fenêtre. "
                           "Permet de voir ce que voit le robot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get_status", "activate", "deactivate"],
                        "description": "Action à effectuer: 'get_status' pour obtenir l'état, "
                                     "'activate' pour activer l'affichage, 'deactivate' pour le désactiver"
                    }
                },
                "required": ["action"]
            }
        }

    def execute(self, **kwargs) -> Dict:
        """
        Exécute le tool pour gérer l'affichage de la caméra.

        Args:
            **kwargs: Paramètres contenant 'action' ('get_status', 'activate', 'deactivate')

        Returns:
            Dictionnaire contenant le résultat de l'exécution
        """
        action = kwargs.get("action", "get_status")

        if action == "get_status":
            return {
                "success": True,
                "result": {
                    "running": self._running,
                    "window_name": self._window_name
                }
            }
        elif action == "activate":
            if self._running:
                return {
                    "success": True,
                    "result": {"message": "L'affichage de la caméra est déjà actif"}
                }
            if self.start():
                return {
                    "success": True,
                    "result": {"message": "Affichage de la caméra activé"}
                }
            else:
                return {
                    "success": False,
                    "error": "Impossible d'activer l'affichage de la caméra"
                }
        elif action == "deactivate":
            if not self._running:
                return {
                    "success": True,
                    "result": {"message": "L'affichage de la caméra est déjà désactivé"}
                }
            self.stop()
            return {
                "success": True,
                "result": {"message": "Affichage de la caméra désactivé"}
            }
        else:
            return {
                "success": False,
                "error": f"Action '{action}' non reconnue. Utilisez 'get_status', 'activate' ou 'deactivate'"
            }
