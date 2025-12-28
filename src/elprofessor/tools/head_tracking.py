"""Tool de suivi de visage pour Reachy Mini."""

import threading
import time
from typing import Optional

import cv2
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
        self._head_tracker = HeadTracker()  # Version standard sans vertical_offset
        self._vertical_offset = vertical_offset
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._show_preview = True
        # Seuil de différence pour déclencher un mouvement (5%)
        self._movement_threshold = 0.05

    def start(self) -> bool:
        """
        Démarre le suivi de visage.

        Returns:
            True si le démarrage a réussi, False sinon
        """
        if self._reachy is None:
            print("❌ ReachyMini non défini pour le tool head_tracking")
            return False

        if not self._reachy:
            print("❌ ReachyMini non connecté")
            return False

        if self._running:
            return False

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self._thread.start()
        self._set_running(True)
        return True

    def stop(self) -> None:
        """Arrête le suivi de visage."""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._set_running(False)
        cv2.destroyAllWindows()

    def _tracking_loop(self) -> None:
        """Boucle principale de suivi de visage."""
        last_target = None  # Stocker la dernière position cible
        try:
            while not self._stop_event.is_set():
                try:
                    img = self._reachy.media.get_frame()
                    if img is not None:
                        # Faire une copie de l'image car elle est en lecture seule
                        img_copy = img.copy()

                        eye_center, roll = self._head_tracker.get_head_position(img)
                        if eye_center is not None:
                            # Appliquer l'offset vertical pour incliner la tête vers le bas
                            # (dans l'espace normalisé [-1, 1])
                            eye_center[1] += self._vertical_offset

                            h, w, _ = img_copy.shape
                            # Convertir de [-1, 1] à [0, 1] puis en pixels
                            eye_center = (eye_center + 1) / 2
                            eye_center[0] *= w
                            eye_center[1] *= h
                            # Borner les valeurs dans les limites de la résolution de la caméra
                            eye_center[0] = np.clip(eye_center[0], 0, w - 1)
                            eye_center[1] = np.clip(eye_center[1], 0, h - 1)

                            # Dessine un cercle sur la position détectée
                            cv2.circle(
                                img_copy,
                                center=(int(eye_center[0]), int(eye_center[1])),
                                radius=5,
                                color=(0, 255, 0),
                                thickness=2,
                            )

                            # Vérifier si on doit ajuster la position
                            should_move = False
                            if last_target is None:
                                # Première détection, on bouge toujours
                                should_move = True
                            else:
                                # Calculer la différence relative
                                diff_x = abs(eye_center[0] - last_target[0]) / w
                                diff_y = abs(eye_center[1] - last_target[1]) / h
                                # Si la différence est supérieure au seuil, on bouge
                                if diff_x > self._movement_threshold or diff_y > self._movement_threshold:
                                    should_move = True

                            if should_move:
                                self._reachy.look_at_image(*eye_center, perform_movement=True)
                                last_target = eye_center.copy()

                        if self._show_preview and img_copy is not None:
                            try:
                                cv2.imshow("Head Tracking", img_copy)
                                if cv2.waitKey(50) & 0xFF == ord("q"):
                                    self._stop_event.set()
                            except cv2.error as e:
                                # Ignorer les erreurs d'affichage OpenCV (fenêtre fermée, etc.)
                                pass
                    else:
                        # Pas d'image, petite pause pour ne pas surcharger le CPU
                        time.sleep(0.05)
                except Exception as e:
                    # Erreur dans une itération, continuer la boucle
                    print(f"⚠️  Erreur dans une itération de suivi: {e}")
                    time.sleep(0.1)
        except Exception as e:
            print(f"❌ Erreur dans la boucle de suivi: {e}")
        finally:
            try:
                cv2.destroyAllWindows()
            except:
                pass

    def set_show_preview(self, show: bool) -> None:
        """
        Active ou désactive l'affichage de la prévisualisation.

        Args:
            show: True pour afficher, False pour masquer
        """
        self._show_preview = show
