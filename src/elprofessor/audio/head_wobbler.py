"""Mouvements de tête synchronisés avec l'audio de la parole."""

import time
import queue
import base64
import logging
import threading
from typing import Tuple, Optional

import numpy as np
from numpy.typing import NDArray

from elprofessor.audio.speech_tapper import HOP_MS, SwayRollRT


SAMPLE_RATE = 24000
MOVEMENT_LATENCY_S = 0.08  # secondes entre l'audio et le mouvement du robot
logger = logging.getLogger(__name__)


class HeadWobbler:
    """Convertit les chunks audio (base64) en offsets de mouvement de tête."""

    def __init__(self, reachy_mini):
        """
        Initialise le HeadWobbler.

        Args:
            reachy_mini: Instance de ReachyMini pour appliquer les mouvements
        """
        self._reachy = reachy_mini
        self._base_ts: Optional[float] = None
        self._hops_done: int = 0

        self.audio_queue: "queue.Queue[Tuple[int, int, NDArray[np.int16]]]" = queue.Queue()
        self.sway = SwayRollRT()

        # Primitives de synchronisation
        self._state_lock = threading.Lock()
        self._sway_lock = threading.Lock()
        self._generation = 0

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Pose de base de la tête (sans offsets)
        self._base_head_pose: Optional[dict] = None
        self._base_pose_lock = threading.Lock()

    def feed(self, delta_b64: str) -> None:
        """Thread-safe: ajoute l'audio dans la queue de consommation."""
        try:
            buf = np.frombuffer(base64.b64decode(delta_b64), dtype=np.int16).reshape(1, -1)
            with self._state_lock:
                generation = self._generation
            self.audio_queue.put((generation, SAMPLE_RATE, buf))
        except Exception as e:
            print(f"⚠️  HeadWobbler: Erreur lors de l'ajout de l'audio à la queue: {e}")

    def start(self) -> None:
        """Démarre la boucle du HeadWobbler dans un thread."""
        self._stop_event.clear()
        # Capturer la pose de base de la tête au démarrage
        self._capture_base_pose()
        self._thread = threading.Thread(target=self.working_loop, daemon=True)
        self._thread.start()
        logger.debug("Head wobbler démarré")

    def stop(self) -> None:
        """Arrête la boucle du HeadWobbler."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
        # Réinitialiser la tête à la pose de base
        self._reset_to_base_pose()
        logger.debug("Head wobbler arrêté")

    def _capture_base_pose(self) -> None:
        """Capture la pose de base de la tête (sans offsets)."""
        if self._reachy is None:
            print("⚠️  HeadWobbler: ReachyMini est None")
            return
        try:
            if hasattr(self._reachy, "get_current_head_pose"):
                pose = self._reachy.get_current_head_pose()
                with self._base_pose_lock:
                    self._base_head_pose = pose
                print(f"✅ HeadWobbler: Pose de base capturée: {type(pose)}")
            else:
                print("⚠️  HeadWobbler: get_current_head_pose n'existe pas, utilisation des joints directement")
                # Si on ne peut pas obtenir la pose, on utilisera les joints directement
                with self._base_pose_lock:
                    self._base_head_pose = None
        except Exception as e:
            print(f"❌ HeadWobbler: Erreur lors de la capture de la pose de base: {e}")
            import traceback

            traceback.print_exc()

    def _reset_to_base_pose(self) -> None:
        """Réinitialise la tête à la pose de base."""
        if self._reachy is None:
            return
        with self._base_pose_lock:
            base_pose = self._base_head_pose
        if base_pose is None:
            return
        try:
            if hasattr(self._reachy, "goto_head_pose"):
                self._reachy.goto_head_pose(base_pose, duration=0.5)
            elif hasattr(self._reachy, "set_head_pose"):
                self._reachy.set_head_pose(base_pose)
        except Exception as e:
            logger.warning(f"Impossible de réinitialiser la pose de base: {e}")

    def _apply_offsets(self, offsets: Tuple[float, float, float, float, float, float]) -> None:
        """
        Applique les offsets directement à la tête du robot.

        Args:
            offsets: Tuple (x_m, y_m, z_m, roll_rad, pitch_rad, yaw_rad)
        """
        if self._reachy is None:
            return

        x_m, y_m, z_m, roll_rad, pitch_rad, yaw_rad = offsets

        # Utiliser directement les joints de la tête (approche plus fiable)
        try:
            if hasattr(self._reachy, "head"):
                head = self._reachy.head

                # Obtenir les positions actuelles et ajouter les offsets
                if hasattr(head, "neck_roll"):
                    current_roll = head.neck_roll.present_position
                    head.neck_roll.goal_position = current_roll + roll_rad

                if hasattr(head, "neck_pitch"):
                    current_pitch = head.neck_pitch.present_position
                    head.neck_pitch.goal_position = current_pitch + pitch_rad

                if hasattr(head, "neck_yaw"):
                    current_yaw = head.neck_yaw.present_position
                    head.neck_yaw.goal_position = current_yaw + yaw_rad
            else:
                # Fallback: essayer avec la pose de base
                with self._base_pose_lock:
                    base_pose = self._base_head_pose

                # Si on n'a pas de pose de base, essayer de l'obtenir maintenant
                if base_pose is None:
                    if hasattr(self._reachy, "get_current_head_pose"):
                        try:
                            base_pose = self._reachy.get_current_head_pose()
                            with self._base_pose_lock:
                                self._base_head_pose = base_pose
                        except Exception as e:
                            print(f"⚠️  HeadWobbler: Impossible d'obtenir la pose actuelle: {e}")
                            return
                    else:
                        return

                # Calculer la nouvelle pose en ajoutant les offsets
                if isinstance(base_pose, dict):
                    new_pose = base_pose.copy()
                    new_pose["x"] = new_pose.get("x", 0) + x_m
                    new_pose["y"] = new_pose.get("y", 0) + y_m
                    new_pose["z"] = new_pose.get("z", 0) + z_m
                    new_pose["roll"] = new_pose.get("roll", 0) + roll_rad
                    new_pose["pitch"] = new_pose.get("pitch", 0) + pitch_rad
                    new_pose["yaw"] = new_pose.get("yaw", 0) + yaw_rad
                else:
                    # Si c'est un objet avec des attributs
                    import copy

                    new_pose = copy.deepcopy(base_pose)
                    if hasattr(new_pose, "x"):
                        new_pose.x = getattr(new_pose, "x", 0) + x_m
                    if hasattr(new_pose, "y"):
                        new_pose.y = getattr(new_pose, "y", 0) + y_m
                    if hasattr(new_pose, "z"):
                        new_pose.z = getattr(new_pose, "z", 0) + z_m
                    if hasattr(new_pose, "roll"):
                        new_pose.roll = getattr(new_pose, "roll", 0) + roll_rad
                    if hasattr(new_pose, "pitch"):
                        new_pose.pitch = getattr(new_pose, "pitch", 0) + pitch_rad
                    if hasattr(new_pose, "yaw"):
                        new_pose.yaw = getattr(new_pose, "yaw", 0) + yaw_rad

                # Appliquer la nouvelle pose
                if hasattr(self._reachy, "goto_head_pose"):
                    self._reachy.goto_head_pose(new_pose, duration=HOP_MS / 1000.0)
                elif hasattr(self._reachy, "set_head_pose"):
                    self._reachy.set_head_pose(new_pose)

        except Exception as e:
            print(f"❌ HeadWobbler: Erreur lors de l'application des offsets: {e}")
            import traceback

            traceback.print_exc()

    def working_loop(self) -> None:
        """Convertit les chunks audio en offsets de mouvement de tête."""
        hop_dt = HOP_MS / 1000.0

        print("🔄 HeadWobbler: Thread de traitement démarré")
        chunks_processed = 0
        while not self._stop_event.is_set():
            queue_ref = self.audio_queue
            try:
                chunk_generation, sr, chunk = queue_ref.get_nowait()  # (gen, sr, data)
                chunks_processed += 1
                if chunks_processed == 1:
                    print(f"✅ HeadWobbler: Premier chunk audio reçu (taille: {chunk.shape})")
            except queue.Empty:
                # éviter que la boucle ne sorte jamais
                time.sleep(MOVEMENT_LATENCY_S)
                continue

            try:
                with self._state_lock:
                    current_generation = self._generation
                if chunk_generation != current_generation:
                    continue

                if self._base_ts is None:
                    with self._state_lock:
                        if self._base_ts is None:
                            self._base_ts = time.monotonic()

                pcm = np.asarray(chunk).squeeze(0)
                with self._sway_lock:
                    results = self.sway.feed(pcm, sr)
                    if len(results) > 0 and chunks_processed <= 3:
                        print(f"✅ HeadWobbler: {len(results)} offsets générés par speech_tapper")

                i = 0
                while i < len(results):
                    with self._state_lock:
                        if self._generation != current_generation:
                            break
                        base_ts = self._base_ts
                        hops_done = self._hops_done

                    if base_ts is None:
                        base_ts = time.monotonic()
                        with self._state_lock:
                            if self._base_ts is None:
                                self._base_ts = base_ts
                                hops_done = self._hops_done

                    target = base_ts + MOVEMENT_LATENCY_S + hops_done * hop_dt
                    now = time.monotonic()

                    if now - target >= hop_dt:
                        lag_hops = int((now - target) / hop_dt)
                        drop = min(lag_hops, len(results) - i - 1)
                        if drop > 0:
                            with self._state_lock:
                                self._hops_done += drop
                                hops_done = self._hops_done
                            i += drop
                            continue

                    if target > now:
                        time.sleep(target - now)
                        with self._state_lock:
                            if self._generation != current_generation:
                                break

                    r = results[i]
                    offsets = (
                        r["x_mm"] / 1000.0,
                        r["y_mm"] / 1000.0,
                        r["z_mm"] / 1000.0,
                        r["roll_rad"],
                        r["pitch_rad"],
                        r["yaw_rad"],
                    )

                    with self._state_lock:
                        if self._generation != current_generation:
                            break

                    # Appliquer les offsets seulement si ils sont significatifs
                    if abs(r["roll_rad"]) > 0.001 or abs(r["pitch_rad"]) > 0.001 or abs(r["yaw_rad"]) > 0.001:
                        self._apply_offsets(offsets)

                    with self._state_lock:
                        self._hops_done += 1
                    i += 1
            finally:
                queue_ref.task_done()
        logger.debug("Thread Head wobbler terminé")

    def reset(self) -> None:
        """Réinitialise l'état interne."""
        with self._state_lock:
            self._generation += 1
            self._base_ts = None
            self._hops_done = 0

        # Vider les chunks audio en attente des générations précédentes
        drained_any = False
        while True:
            try:
                _, _, _ = self.audio_queue.get_nowait()
            except queue.Empty:
                break
            else:
                drained_any = True
                self.audio_queue.task_done()

        with self._sway_lock:
            self.sway.reset()

        # Réinitialiser la tête à la pose de base
        self._reset_to_base_pose()

        if drained_any:
            logger.debug("Queue Head wobbler vidée lors du reset")
