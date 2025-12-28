"""Tool de snapshot de caméra pour Reachy Mini."""

import base64
from io import BytesIO
from typing import Dict, Optional

import cv2
import numpy as np

from elprofessor.tools.base import Tool


class CameraSnapshotTool(Tool):
    """Tool qui permet de prendre un snapshot de la caméra et de le retourner en base64."""

    def __init__(self, quality: int = 85):
        """
        Initialise le tool de snapshot de caméra.

        Args:
            quality: Qualité JPEG (1-100, par défaut 85)
        """
        super().__init__(
            name="camera_snapshot",
            description="Prend un snapshot de la caméra et le retourne en base64 pour analyse par ChatGPT"
        )
        self._quality = quality
        self._last_frame: Optional[np.ndarray] = None

    def start(self) -> bool:
        """
        Démarre le tool de snapshot.

        Returns:
            True si le démarrage a réussi, False sinon
        """
        if self._camera_manager is None:
            print("❌ CameraManager non défini pour le tool camera_snapshot")
            return False

        if self._running:
            return False

        # Enregistrer le callback pour recevoir les frames
        self._camera_manager.register_frame_callback(self._on_frame_received)

        self._set_running(True)
        return True

    def stop(self) -> None:
        """Arrête le tool de snapshot."""
        if not self._running:
            return

        # Désenregistrer le callback
        if self._camera_manager is not None:
            self._camera_manager.unregister_frame_callback(self._on_frame_received)

        self._set_running(False)
        self._last_frame = None

    def _on_frame_received(self, img: np.ndarray) -> None:
        """
        Callback appelé lorsqu'une nouvelle frame est reçue du CameraManager.

        Args:
            img: Image reçue
        """
        self._last_frame = img.copy()

    def to_openai_function(self) -> Optional[Dict]:
        """
        Convertit le tool en définition de fonction OpenAI.

        Returns:
            Dictionnaire au format OpenAI Function Calling (format Realtime API)
        """
        return {
            "type": "function",
            "name": "camera_snapshot",
            "description": "Prend un snapshot de la caméra de Reachy Mini et le retourne en base64. "
                           "Utilisez cette fonction pour obtenir du contexte visuel de ce que voit le robot.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }

    def execute(self, **kwargs) -> Dict:
        """
        Exécute le tool pour prendre un snapshot.

        Args:
            **kwargs: Paramètres (non utilisés pour ce tool)

        Returns:
            Dictionnaire contenant le résultat avec l'image en base64
        """
        if not self._running:
            return {
                "success": False,
                "error": "Tool camera_snapshot n'est pas démarré"
            }

        if self._last_frame is None:
            return {
                "success": False,
                "error": "Aucune frame disponible de la caméra"
            }

        try:
            # Convertir l'image en JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self._quality]
            _, buffer = cv2.imencode('.jpg', self._last_frame, encode_param)
            
            # Convertir en base64
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            
            return {
                "success": True,
                "result": {
                    "image_base64": image_base64,
                    "format": "jpeg",
                    "quality": self._quality
                }
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Erreur lors de la conversion de l'image: {str(e)}"
            }

