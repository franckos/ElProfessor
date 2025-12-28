"""Manager de caméra pour Reachy Mini.

Gère l'accès unique à la caméra et partage les frames avec les tools.
Tout l'affichage OpenCV se fait dans le thread principal (requis sur macOS).
"""

import time
from typing import Callable, List, Optional

import cv2
import numpy as np


class CameraManager:
    """Manager centralisé pour l'accès à la caméra de Reachy Mini."""

    def __init__(self, reachy):
        """
        Initialise le manager de caméra.

        Args:
            reachy: Instance de ReachyMini
        """
        self._reachy = reachy
        self._frame_callbacks: List[Callable[[np.ndarray], None]] = []
        self._windows: dict[str, bool] = {}  # Dictionnaire des fenêtres créées
        # Dictionnaire des propriétés des fenêtres : {nom: {"x": int, "y": int, "width": int, "height": int}}
        self._window_properties: dict[str, dict] = {}
        self._running = False
        self._frame_count = 0

    def register_frame_callback(self, callback: Callable[[np.ndarray], None]) -> None:
        """
        Enregistre un callback qui sera appelé à chaque nouvelle frame.

        Args:
            callback: Fonction qui prend une image (np.ndarray) en paramètre
        """
        if callback not in self._frame_callbacks:
            self._frame_callbacks.append(callback)
            print(f"✅ Callback enregistré pour les frames de la caméra")

    def unregister_frame_callback(self, callback: Callable[[np.ndarray], None]) -> None:
        """
        Désenregistre un callback.

        Args:
            callback: Fonction à désenregistrer
        """
        if callback in self._frame_callbacks:
            self._frame_callbacks.remove(callback)
            print(f"✅ Callback désenregistré pour les frames de la caméra")

    def create_display_window(
        self,
        window_name: str = "Reachy Mini Vision",
        x: Optional[int] = None,
        y: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> bool:
        """
        Crée une fenêtre OpenCV pour l'affichage. Doit être appelé depuis le thread principal.

        Args:
            window_name: Nom de la fenêtre
            x: Position X de la fenêtre (en pixels, optionnel)
            y: Position Y de la fenêtre (en pixels, optionnel)
            width: Largeur de la fenêtre (en pixels, optionnel)
            height: Hauteur de la fenêtre (en pixels, optionnel)

        Returns:
            True si la fenêtre a été créée, False sinon
        """
        if window_name in self._windows and self._windows[window_name]:
            return True

        # Debug: afficher les paramètres reçus
        if x is not None or y is not None or width is not None or height is not None:
            print(f"🔧 Configuration de la fenêtre '{window_name}':")
            if x is not None and y is not None:
                print(f"   Position: ({x}, {y})")
            if width is not None and height is not None:
                print(f"   Taille: {width}x{height}")

        try:
            # Créer la fenêtre avec cv2.namedWindow pour pouvoir la configurer
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

            # Stocker les propriétés de la fenêtre
            self._window_properties[window_name] = {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            }

            # Créer une image de test pour initialiser la fenêtre
            test_img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(
                test_img,
                "Waiting for camera feed...",
                (50, 240),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )
            cv2.imshow(window_name, test_img)
            cv2.waitKey(1)  # Forcer l'affichage initial

            # Sur macOS, il faut parfois réappliquer plusieurs fois les paramètres
            # Définir la taille si spécifiée (après l'affichage initial pour que ça fonctionne sur macOS)
            if width is not None and height is not None:
                try:
                    cv2.resizeWindow(window_name, int(width), int(height))
                    cv2.waitKey(10)  # Donner plus de temps à la fenêtre de se redimensionner
                    # Réappliquer une deuxième fois pour s'assurer que ça prend
                    cv2.resizeWindow(window_name, int(width), int(height))
                except Exception as e:
                    print(f"⚠️  Impossible de redimensionner la fenêtre '{window_name}': {e}")

            # Définir la position si spécifiée (après le redimensionnement)
            if x is not None and y is not None:
                try:
                    cv2.moveWindow(window_name, int(x), int(y))
                    cv2.waitKey(10)  # Donner plus de temps à la fenêtre de se déplacer
                    # Réappliquer une deuxième fois pour s'assurer que ça prend
                    cv2.moveWindow(window_name, int(x), int(y))
                except Exception as e:
                    print(f"⚠️  Impossible de déplacer la fenêtre '{window_name}': {e}")

            self._windows[window_name] = True
            print(f"✅ Fenêtre '{window_name}' créée")
            if x is not None and y is not None:
                print(f"   Position: ({x}, {y})")
            if width is not None and height is not None:
                print(f"   Taille: {width}x{height}")
            return True
        except Exception as e:
            print(f"❌ Impossible de créer la fenêtre OpenCV '{window_name}': {e}")
            return False

    def set_window_position(self, window_name: str, x: int, y: int) -> bool:
        """
        Définit la position d'une fenêtre existante.

        Args:
            window_name: Nom de la fenêtre
            x: Position X en pixels
            y: Position Y en pixels

        Returns:
            True si la position a été définie, False sinon
        """
        if window_name not in self._windows or not self._windows[window_name]:
            return False

        try:
            cv2.moveWindow(window_name, x, y)
            if window_name in self._window_properties:
                self._window_properties[window_name]["x"] = x
                self._window_properties[window_name]["y"] = y
            return True
        except Exception as e:
            print(f"⚠️  Impossible de déplacer la fenêtre '{window_name}': {e}")
            return False

    def set_window_size(self, window_name: str, width: int, height: int) -> bool:
        """
        Définit la taille d'une fenêtre existante.

        Args:
            window_name: Nom de la fenêtre
            width: Largeur en pixels
            height: Hauteur en pixels

        Returns:
            True si la taille a été définie, False sinon
        """
        if window_name not in self._windows or not self._windows[window_name]:
            return False

        try:
            cv2.resizeWindow(window_name, width, height)
            if window_name in self._window_properties:
                self._window_properties[window_name]["width"] = width
                self._window_properties[window_name]["height"] = height
            return True
        except Exception as e:
            print(f"⚠️  Impossible de redimensionner la fenêtre '{window_name}': {e}")
            return False

    def update_display(self, img: np.ndarray, window_name: str) -> None:
        """
        Met à jour l'affichage d'une fenêtre. Doit être appelé depuis le thread principal.

        Args:
            img: Image à afficher
            window_name: Nom de la fenêtre à mettre à jour
        """
        if window_name not in self._windows or not self._windows[window_name]:
            return

        try:
            cv2.imshow(window_name, img)
            cv2.waitKey(1)  # Traiter les événements de la fenêtre
        except Exception:
            # Ignorer les erreurs d'affichage
            pass

    def process_frame(self) -> Optional[np.ndarray]:
        """
        Récupère et traite une frame de la caméra.
        Distribue la frame à tous les callbacks enregistrés.

        Returns:
            L'image récupérée, ou None si aucune image n'est disponible
        """
        if self._reachy is None:
            return None

        try:
            img = self._reachy.media.get_frame()
            if img is not None and img.size > 0:
                # Faire une copie de l'image car elle est en lecture seule
                img_copy = img.copy()

                # Distribuer la frame à tous les callbacks enregistrés
                for callback in self._frame_callbacks:
                    try:
                        callback(img_copy)
                    except Exception as e:
                        print(f"⚠️  Erreur dans un callback de frame: {e}")

                self._frame_count += 1
                if self._frame_count == 1:
                    h, w = img_copy.shape[:2]
                    print(f"✅ Première frame de la caméra reçue ! Résolution: {w}x{h}")

                return img_copy
            return None
        except Exception as e:
            error_type = str(type(e).__name__)
            error_msg = str(e)
            if "OpenCV" not in error_type and "Unknown C++ exception" not in error_msg:
                print(f"⚠️  Erreur lors de la récupération de frame: {e}")
            return None

    def start(self) -> None:
        """Démarre le manager de caméra."""
        if self._running:
            return
        self._running = True
        print("📹 CameraManager démarré")

    def stop(self) -> None:
        """Arrête le manager de caméra."""
        if not self._running:
            return
        self._running = False
        self._frame_callbacks.clear()
        # Fermer toutes les fenêtres
        for window_name in list(self._windows.keys()):
            try:
                cv2.destroyWindow(window_name)
            except:
                pass
        self._windows.clear()
        self._window_properties.clear()
        print("🛑 CameraManager arrêté")

    def is_running(self) -> bool:
        """
        Vérifie si le manager est en cours d'exécution.

        Returns:
            True si le manager est actif, False sinon
        """
        return self._running
