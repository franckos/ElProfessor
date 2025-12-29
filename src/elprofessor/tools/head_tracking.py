"""Tool de suivi de visage pour Reachy Mini."""

from typing import Dict, Optional

import numpy as np

from elprofessor.tools.base import Tool

# Importer HeadTracker avec gestion d'erreur si mediapipe n'est pas disponible
try:
    from reachy_mini_toolbox.vision import HeadTracker

    _HEAD_TRACKER_AVAILABLE = True
    _HEAD_TRACKER_ERROR = None
except (ImportError, ModuleNotFoundError, Exception) as e:
    # Capturer toutes les exceptions car reachy-mini-toolbox peut lever différentes erreurs
    # si mediapipe n'est pas disponible
    _HEAD_TRACKER_AVAILABLE = False
    _HEAD_TRACKER_ERROR = str(e)
    HeadTracker = None  # Pour éviter les erreurs de référence


class HeadTrackingTool(Tool):
    """Tool qui permet à Reachy Mini de suivre le visage de l'utilisateur."""

    def __init__(self, vertical_offset=0.35):
        """
        Initialise le tool de suivi de visage.

        Args:
            vertical_offset: Offset vertical pour incliner la tête vers le bas (dans l'espace normalisé [-1, 1])
        """
        super().__init__(name="head_tracking", description="Suivi de visage - Reachy suit les mouvements de votre tête")

        if not _HEAD_TRACKER_AVAILABLE:
            print(f"⚠️  HeadTracker non disponible: {_HEAD_TRACKER_ERROR}")
            print("   Le tool head_tracking sera désactivé. MediaPipe n'est pas disponible pour cette architecture.")
            self._head_tracker = None
        else:
            try:
                self._head_tracker = HeadTracker()
            except Exception as e:
                print(f"⚠️  Erreur lors de l'initialisation de HeadTracker: {e}")
                print("   Le tool head_tracking sera désactivé.")
                self._head_tracker = None

        self._vertical_offset = vertical_offset
        # Seuil de différence pour déclencher un mouvement (5%)
        self._movement_threshold = 0.05
        self._last_target: Optional[np.ndarray] = None
        # Flag pour indiquer si le robot est en train de parler (pour éviter les conflits avec HeadWobbler)
        self._robot_speaking: bool = False

    def start(self) -> bool:
        """
        Démarre le suivi de visage.

        Returns:
            True si le démarrage a réussi, False sinon
        """
        if self._head_tracker is None:
            print("❌ HeadTracker non disponible - le tool head_tracking ne peut pas démarrer")
            return False

        if self._camera_manager is None:
            print("❌ CameraManager non défini pour le tool head_tracking")
            return False

        if self._reachy is None:
            print("❌ ReachyMini non défini pour le tool head_tracking")
            return False

        if self._running:
            return False

        # Enregistrer le callback pour recevoir les frames
        self._camera_manager.register_frame_callback(self._on_frame_received)

        self._last_target = None
        self._set_running(True)
        return True

    def stop(self) -> None:
        """Arrête le suivi de visage."""
        if not self._running:
            return

        # Désenregistrer le callback
        if self._camera_manager is not None:
            self._camera_manager.unregister_frame_callback(self._on_frame_received)

        self._set_running(False)
        self._last_target = None

    def set_robot_speaking(self, speaking: bool) -> None:
        """
        Définit si le robot est en train de parler.

        Quand le robot parle, le head_tracking est temporairement désactivé
        pour éviter les conflits avec le HeadWobbler.

        Args:
            speaking: True si le robot parle, False sinon
        """
        self._robot_speaking = speaking

    def _on_frame_received(self, img: np.ndarray) -> None:
        """
        Callback appelé lorsqu'une nouvelle frame est reçue du CameraManager.

        Args:
            img: Image reçue
        """
        if not self._running or self._reachy is None:
            return

        # Ne pas bouger la tête si le robot est en train de parler (HeadWobbler gère les mouvements)
        if self._robot_speaking:
            # Log seulement occasionnellement pour éviter le spam
            if hasattr(self, "_last_skip_log_time"):
                import time
                if time.time() - self._last_skip_log_time > 2.0:  # Log toutes les 2 secondes max
                    print("⏸️  HeadTracking: Ignoré (robot parle)")
                    self._last_skip_log_time = time.time()
            else:
                import time
                self._last_skip_log_time = time.time()
                print("⏸️  HeadTracking: Ignoré (robot parle)")
            return

        if self._head_tracker is None:
            return

        try:
            eye_center, roll = self._head_tracker.get_head_position(img)
            if eye_center is not None:
                # Appliquer l'offset vertical pour incliner la tête vers le bas
                # (dans l'espace normalisé [-1, 1])
                eye_center[1] += self._vertical_offset

                h, w = img.shape[:2]
                # Convertir de [-1, 1] à [0, 1] puis en pixels
                eye_center = (eye_center + 1) / 2
                eye_center[0] *= w
                eye_center[1] *= h
                # Borner les valeurs dans les limites de la résolution de la caméra
                eye_center[0] = np.clip(eye_center[0], 0, w - 1)
                eye_center[1] = np.clip(eye_center[1], 0, h - 1)

                # Vérifier si on doit ajuster la position
                should_move = False
                if self._last_target is None:
                    # Première détection, on bouge toujours
                    should_move = True
                else:
                    # Calculer la différence relative
                    diff_x = abs(eye_center[0] - self._last_target[0]) / w
                    diff_y = abs(eye_center[1] - self._last_target[1]) / h
                    # Si la différence est supérieure au seuil, on bouge
                    if diff_x > self._movement_threshold or diff_y > self._movement_threshold:
                        should_move = True

                if should_move:
                    self._reachy.look_at_image(*eye_center, perform_movement=True)
                    self._last_target = eye_center.copy()
        except Exception as e:
            print(f"⚠️  Erreur dans le traitement de frame head_tracking: {e}")

    def to_openai_function(self) -> Optional[Dict]:
        """
        Convertit le tool en définition de fonction OpenAI.

        Returns:
            Dictionnaire au format OpenAI Function Calling (format Realtime API)
        """
        return {
            "type": "function",
            "name": "head_tracking",
            "description": "Active ou désactive le suivi de visage. "
            "Quand activé, le robot suit automatiquement les mouvements de la tête de l'utilisateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get_status", "activate", "deactivate"],
                        "description": "Action à effectuer: 'get_status' pour obtenir l'état, "
                        "'activate' pour activer le suivi, 'deactivate' pour le désactiver",
                    }
                },
                "required": ["action"],
            },
        }

    def execute(self, **kwargs) -> Dict:
        """
        Exécute le tool pour gérer le suivi de visage.

        Args:
            **kwargs: Paramètres contenant 'action' ('get_status', 'activate', 'deactivate')

        Returns:
            Dictionnaire contenant le résultat de l'exécution
        """
        action = kwargs.get("action", "get_status")

        if action == "get_status":
            return {"success": True, "result": {"running": self._running, "vertical_offset": self._vertical_offset}}
        elif action == "activate":
            if self._running:
                return {"success": True, "result": {"message": "Le suivi de visage est déjà actif"}}
            if self.start():
                return {"success": True, "result": {"message": "Suivi de visage activé"}}
            else:
                return {"success": False, "error": "Impossible d'activer le suivi de visage"}
        elif action == "deactivate":
            if not self._running:
                return {"success": True, "result": {"message": "Le suivi de visage est déjà désactivé"}}
            self.stop()
            return {"success": True, "result": {"message": "Suivi de visage désactivé"}}
        else:
            return {
                "success": False,
                "error": f"Action '{action}' non reconnue. Utilisez 'get_status', 'activate' ou 'deactivate'",
            }
