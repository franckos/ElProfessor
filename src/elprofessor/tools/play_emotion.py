"""Tool pour jouer des émotions pré-enregistrées sur Reachy Mini."""

import logging
from typing import Dict, Optional

from elprofessor.tools.base import Tool

logger = logging.getLogger(__name__)

# Initialiser la bibliothèque d'émotions
try:
    from reachy_mini.motion.recorded_move import RecordedMoves

    # Note: huggingface_hub lit automatiquement HF_TOKEN depuis les variables d'environnement
    RECORDED_MOVES = RecordedMoves("pollen-robotics/reachy-mini-emotions-library")
    EMOTION_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Bibliothèque d'émotions non disponible: {e}")
    RECORDED_MOVES = None
    EMOTION_AVAILABLE = False


def get_available_emotions_and_descriptions() -> str:
    """Récupère la liste formatée des émotions disponibles avec leurs descriptions."""
    if not EMOTION_AVAILABLE:
        return "Émotions non disponibles"

    try:
        emotion_names = RECORDED_MOVES.list_moves()
        output = "Émotions disponibles:\n"
        for name in emotion_names:
            description = RECORDED_MOVES.get(name).description
            output += f" - {name}: {description}\n"
        return output
    except Exception as e:
        return f"Erreur lors de la récupération des émotions: {e}"


class PlayEmotionTool(Tool):
    """Tool qui permet de jouer une émotion pré-enregistrée sur Reachy Mini."""

    def __init__(self):
        """Initialise le tool play_emotion."""
        super().__init__(
            name="play_emotion",
            description="Joue une émotion pré-enregistrée sur le robot (ex: joyeuse pour une réponse correcte, triste pour une erreur)",
        )

    def start(self) -> bool:
        """
        Démarre le tool (pas nécessaire pour un tool stateless).

        Returns:
            True (tool toujours disponible)
        """
        if not EMOTION_AVAILABLE:
            print("⚠️  Bibliothèque d'émotions non disponible")
            print("   Le tool play_emotion sera désactivé.")
            return False
        return True

    def stop(self) -> None:
        """Arrête le tool (pas nécessaire pour un tool stateless)."""
        # Tool stateless, pas besoin d'arrêt
        pass

    def to_openai_function(self) -> Optional[Dict]:
        """
        Convertit le tool en définition de fonction OpenAI.

        Returns:
            Dictionnaire au format OpenAI Function Calling
        """
        if not EMOTION_AVAILABLE:
            return None

        return {
            "type": "function",
            "name": "play_emotion",
            "description": f"""Joue une émotion pré-enregistrée sur le robot.
Utilise ce tool pour exprimer des émotions en fonction des réponses de l'utilisateur:
- Si la phrase de l'utilisateur est incorrecte ou contient des erreurs, joue une émotion triste (ex: 'sad1', 'sad2', 'disappointed1')
- Si la phrase est parfaite et correcte, joue une émotion joyeuse (ex: 'cheerful1', 'enthusiastic1', 'happy1', 'excited1')

{get_available_emotions_and_descriptions()}""",
            "parameters": {
                "type": "object",
                "properties": {
                    "emotion": {
                        "type": "string",
                        "description": f"""Nom de l'émotion à jouer.
Voici la liste des émotions disponibles:
{get_available_emotions_and_descriptions()}
Pour une réponse incorrecte, utilisez une émotion triste.
Pour une réponse correcte, utilisez une émotion joyeuse.""",
                    },
                },
                "required": ["emotion"],
            },
        }

    def execute(self, **kwargs) -> Dict:
        """
        Exécute le tool pour jouer une émotion.

        Args:
            **kwargs: Paramètres contenant 'emotion' (nom de l'émotion à jouer)

        Returns:
            Dictionnaire contenant le résultat de l'exécution
        """
        if not EMOTION_AVAILABLE:
            return {
                "success": False,
                "error": "Système d'émotions non disponible. Vérifiez que reachy_mini.motion.recorded_move est installé.",
            }

        emotion_name = kwargs.get("emotion")
        if not emotion_name:
            return {"success": False, "error": "Le nom de l'émotion est requis"}

        logger.info("Appel du tool: play_emotion emotion=%s", emotion_name)

        # Vérifier si l'émotion existe
        try:
            emotion_names = RECORDED_MOVES.list_moves()
            if emotion_name not in emotion_names:
                return {
                    "success": False,
                    "error": f"Émotion '{emotion_name}' inconnue. Émotions disponibles: {emotion_names}",
                }

            # Récupérer le mouvement d'émotion
            emotion_move = RECORDED_MOVES.get(emotion_name)

            # Jouer le mouvement directement via l'API ReachyMini
            if self._reachy is None:
                return {"success": False, "error": "ReachyMini non disponible"}

            # Utiliser play_move si disponible (méthode standard de ReachyMini)
            if hasattr(self._reachy, "play_move"):
                self._reachy.play_move(emotion_move, initial_goto_duration=1.0)
            else:
                # Fallback: exécuter le mouvement manuellement
                self._play_emotion_manually(emotion_move)

            print(f"😊 Émotion '{emotion_name}' jouée")
            return {
                "success": True,
                "result": {
                    "emotion": emotion_name,
                    "message": f"Émotion '{emotion_name}' jouée avec succès",
                },
            }

        except Exception as e:
            logger.exception("Échec lors de la lecture de l'émotion")
            return {"success": False, "error": f"Échec lors de la lecture de l'émotion: {e!s}"}

    def _play_emotion_manually(self, emotion_move) -> None:
        """
        Joue une émotion manuellement en exécutant le mouvement frame par frame.

        Args:
            emotion_move: Mouvement d'émotion à jouer
        """
        try:
            import time

            duration = emotion_move.duration
            start_time = time.time()
            dt = 0.05  # 50ms entre chaque frame

            while time.time() - start_time < duration:
                t = time.time() - start_time
                head_pose, antennas, body_yaw = emotion_move.evaluate(t)

                # Appliquer les poses
                if head_pose is not None and self._reachy is not None:
                    if hasattr(self._reachy, "set_head_pose"):
                        self._reachy.set_head_pose(head_pose)
                    elif hasattr(self._reachy, "goto_head_pose"):
                        self._reachy.goto_head_pose(head_pose, duration=dt)

                if antennas is not None and self._reachy is not None:
                    if hasattr(self._reachy, "set_antennas"):
                        self._reachy.set_antennas(antennas)

                if body_yaw is not None and self._reachy is not None:
                    if hasattr(self._reachy, "set_body_yaw"):
                        self._reachy.set_body_yaw(body_yaw)

                time.sleep(dt)

        except Exception as e:
            logger.error(f"Erreur lors de la lecture manuelle de l'émotion: {e}")
