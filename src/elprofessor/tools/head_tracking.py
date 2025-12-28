"""Tool de suivi de visage pour Reachy Mini."""

from typing import Optional

import numpy as np
from reachy_mini_toolbox.vision import HeadTracker

from elprofessor.tools.base import Tool


class HeadTrackingTool(Tool):
    """Tool qui permet à Reachy Mini de suivre le visage de l'utilisateur."""

    def __init__(self, vertical_offset=0.35):
        """
        Initialise le tool de suivi de visage.

        Args:
            vertical_offset: Offset vertical pour incliner la tête vers le bas (dans l'espace normalisé [-1, 1])
        """
        super().__init__(name="head_tracking", description="Suivi de visage - Reachy suit les mouvements de votre tête")
        self._head_tracker = HeadTracker()
        self._vertical_offset = vertical_offset
        # Seuil de différence pour déclencher un mouvement (5%)
        self._movement_threshold = 0.05
        self._last_target: Optional[np.ndarray] = None

    def start(self) -> bool:
        """
        Démarre le suivi de visage.

        Returns:
            True si le démarrage a réussi, False sinon
        """
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

    def _on_frame_received(self, img: np.ndarray) -> None:
        """
        Callback appelé lorsqu'une nouvelle frame est reçue du CameraManager.

        Args:
            img: Image reçue
        """
        if not self._running or self._reachy is None:
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
