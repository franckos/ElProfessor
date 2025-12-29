"""Tool pour bouger la tête de Reachy Mini dans différentes directions."""

from typing import Dict, Literal, Optional, Tuple

from elprofessor.tools.base import Tool

# Essayer d'importer create_head_pose depuis reachy_mini.utils
try:
    from reachy_mini.utils import create_head_pose

    CREATE_HEAD_POSE_AVAILABLE = True
except ImportError:
    CREATE_HEAD_POSE_AVAILABLE = False

Direction = Literal["left", "right", "up", "down", "front"]


class MoveHeadTool(Tool):
    """Tool qui permet de bouger la tête de Reachy Mini dans différentes directions."""

    # Mapping: direction -> (x_mm, y_mm, z_mm, roll_deg, pitch_deg, yaw_deg)
    DELTAS: Dict[str, Tuple[int, int, int, int, int, int]] = {
        "left": (0, 0, 0, 0, 0, 40),      # Yaw +40°
        "right": (0, 0, 0, 0, 0, -40),    # Yaw -40°
        "up": (0, 0, 0, 0, -30, 0),      # Pitch -30°
        "down": (0, 0, 0, 0, 30, 0),     # Pitch +30°
        "front": (0, 0, 0, 0, 0, 0),     # Position neutre
    }

    def __init__(self):
        """Initialise le tool move_head."""
        super().__init__(
            name="move_head",
            description="Bouge la tête du robot dans une direction donnée: left, right, up, down ou front."
        )

    def start(self) -> bool:
        """
        Démarre le tool (pas nécessaire pour un tool stateless).

        Returns:
            True (tool toujours disponible)
        """
        # Tool stateless, pas besoin de démarrage
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
        return {
            "type": "function",
            "name": "move_head",
            "description": "Bouge la tête du robot dans une direction donnée: left (gauche), right (droite), up (haut), down (bas) ou front (devant/neutre).",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["left", "right", "up", "down", "front"],
                        "description": "Direction dans laquelle bouger la tête: 'left' pour gauche, 'right' pour droite, 'up' pour haut, 'down' pour bas, 'front' pour position neutre devant."
                    }
                },
                "required": ["direction"]
            }
        }

    def execute(self, **kwargs) -> Dict:
        """
        Exécute le mouvement de tête.

        Args:
            **kwargs: Paramètres contenant 'direction' ('left', 'right', 'up', 'down', 'front')

        Returns:
            Dictionnaire contenant le résultat de l'exécution
        """
        if self._reachy is None:
            return {
                "success": False,
                "error": "ReachyMini non défini pour le tool move_head"
            }

        direction_raw = kwargs.get("direction")
        if not isinstance(direction_raw, str):
            return {
                "success": False,
                "error": "Le paramètre 'direction' doit être une chaîne de caractères"
            }

        direction: Direction = direction_raw  # type: ignore[assignment]

        if direction not in self.DELTAS:
            return {
                "success": False,
                "error": f"Direction '{direction}' non reconnue. Utilisez 'left', 'right', 'up', 'down' ou 'front'"
            }

        try:
            deltas = self.DELTAS[direction]
            print(f"🔄 Mouvement de tête: {direction}")

            # Essayer d'utiliser create_head_pose si disponible
            if CREATE_HEAD_POSE_AVAILABLE:
                target_head_pose = create_head_pose(*deltas, degrees=True)
                # Utiliser goto_head_pose si disponible
                if hasattr(self._reachy, 'goto_head_pose'):
                    self._reachy.goto_head_pose(target_head_pose, duration=1.0)
                elif hasattr(self._reachy, 'set_head_pose'):
                    self._reachy.set_head_pose(target_head_pose)
                else:
                    # Fallback: utiliser directement l'API ReachyMini
                    self._move_head_fallback(deltas)
            else:
                # Fallback: utiliser directement l'API ReachyMini
                self._move_head_fallback(deltas)

            return {
                "success": True,
                "result": {
                    "direction": direction,
                    "message": f"Tête bougée vers {direction}"
                }
            }

        except Exception as e:
            print(f"❌ Erreur lors du mouvement de tête: {e}")
            return {
                "success": False,
                "error": f"Erreur lors du mouvement de tête: {str(e)}"
            }

    def _move_head_fallback(self, deltas: Tuple[int, int, int, int, int, int]) -> None:
        """
        Méthode de fallback pour bouger la tête sans create_head_pose.

        Args:
            deltas: Tuple (x_mm, y_mm, z_mm, roll_deg, pitch_deg, yaw_deg)
        """
        x_mm, y_mm, z_mm, roll_deg, pitch_deg, yaw_deg = deltas

        # Essayer d'obtenir la pose actuelle et créer une nouvelle pose
        try:
            if hasattr(self._reachy, 'get_current_head_pose'):
                current_pose = self._reachy.get_current_head_pose()
                
                # Créer une nouvelle pose en ajoutant les deltas
                # La structure de la pose dépend de l'API, mais généralement c'est un dict ou un objet
                # avec des attributs comme x, y, z, roll, pitch, yaw
                if isinstance(current_pose, dict):
                    new_pose = current_pose.copy()
                    new_pose['x'] = new_pose.get('x', 0) + x_mm / 1000.0  # Convertir mm en m
                    new_pose['y'] = new_pose.get('y', 0) + y_mm / 1000.0
                    new_pose['z'] = new_pose.get('z', 0) + z_mm / 1000.0
                    new_pose['roll'] = new_pose.get('roll', 0) + roll_deg * 3.14159 / 180.0  # Convertir deg en rad
                    new_pose['pitch'] = new_pose.get('pitch', 0) + pitch_deg * 3.14159 / 180.0
                    new_pose['yaw'] = new_pose.get('yaw', 0) + yaw_deg * 3.14159 / 180.0
                else:
                    # Si c'est un objet avec des attributs
                    import math
                    new_pose = type(current_pose)(
                        x=getattr(current_pose, 'x', 0) + x_mm / 1000.0,
                        y=getattr(current_pose, 'y', 0) + y_mm / 1000.0,
                        z=getattr(current_pose, 'z', 0) + z_mm / 1000.0,
                        roll=getattr(current_pose, 'roll', 0) + roll_deg * math.pi / 180.0,
                        pitch=getattr(current_pose, 'pitch', 0) + pitch_deg * math.pi / 180.0,
                        yaw=getattr(current_pose, 'yaw', 0) + yaw_deg * math.pi / 180.0,
                    )

                # Appliquer la nouvelle pose
                if hasattr(self._reachy, 'goto_head_pose'):
                    self._reachy.goto_head_pose(new_pose, duration=1.0)
                elif hasattr(self._reachy, 'set_head_pose'):
                    self._reachy.set_head_pose(new_pose)
                else:
                    raise AttributeError("Aucune méthode pour définir la pose de la tête")
            else:
                # Si get_current_head_pose n'existe pas, utiliser les joints directement
                # Cette approche est plus bas niveau mais devrait fonctionner
                import math
                if hasattr(self._reachy, 'head'):
                    # Accéder aux joints de la tête
                    head = self._reachy.head
                    if hasattr(head, 'neck_roll'):
                        if roll_deg != 0:
                            head.neck_roll.goal_position = head.neck_roll.present_position + roll_deg * math.pi / 180.0
                    if hasattr(head, 'neck_pitch'):
                        if pitch_deg != 0:
                            head.neck_pitch.goal_position = head.neck_pitch.present_position + pitch_deg * math.pi / 180.0
                    if hasattr(head, 'neck_yaw'):
                        if yaw_deg != 0:
                            head.neck_yaw.goal_position = head.neck_yaw.present_position + yaw_deg * math.pi / 180.0
                else:
                    raise AttributeError("Impossible d'accéder à la tête du robot")
        except Exception as e:
            print(f"⚠️  Erreur dans la méthode de fallback: {e}")
            raise

