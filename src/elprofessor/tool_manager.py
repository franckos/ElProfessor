"""Gestionnaire des tools pour ElProfessor."""

from typing import Dict, List, Optional

from elprofessor.tools.base import Tool


class ToolManager:
    """Gestionnaire central pour tous les tools."""

    def __init__(self, reachy, camera_manager=None):
        """
        Initialise le gestionnaire de tools.

        Args:
            reachy: Instance de ReachyMini
            camera_manager: Instance de CameraManager (optionnel)
        """
        self._reachy = reachy
        self._camera_manager = camera_manager
        self._tools: Dict[str, Tool] = {}
        self._active_tools: Dict[str, Tool] = {}

    def register_tool(self, tool: Tool) -> None:
        """
        Enregistre un tool.

        Args:
            tool: Instance du tool à enregistrer
        """
        tool.set_reachy(self._reachy)
        if self._camera_manager is not None:
            tool.set_camera_manager(self._camera_manager)
        self._tools[tool.name] = tool
        print(f"✅ Tool '{tool.name}' enregistré: {tool.description}")

    def get_tool(self, name: str) -> Optional[Tool]:
        """
        Récupère un tool par son nom.

        Args:
            name: Nom du tool

        Returns:
            Le tool si trouvé, None sinon
        """
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """
        Liste tous les tools enregistrés.

        Returns:
            Liste des noms des tools
        """
        return list(self._tools.keys())

    def list_active_tools(self) -> List[str]:
        """
        Liste tous les tools actifs.

        Returns:
            Liste des noms des tools actifs
        """
        return list(self._active_tools.keys())

    def activate_tool(self, name: str) -> bool:
        """
        Active un tool.

        Args:
            name: Nom du tool à activer

        Returns:
            True si l'activation a réussi, False sinon
        """
        tool = self._tools.get(name)
        if tool is None:
            print(f"❌ Tool '{name}' non trouvé")
            return False

        if tool.is_running():
            print(f"⚠️  Tool '{name}' est déjà actif")
            return False

        if tool.start():
            self._active_tools[name] = tool
            print(f"✅ Tool '{name}' activé")
            return True
        else:
            print(f"❌ Échec de l'activation du tool '{name}'")
            return False

    def deactivate_tool(self, name: str) -> bool:
        """
        Désactive un tool.

        Args:
            name: Nom du tool à désactiver

        Returns:
            True si la désactivation a réussi, False sinon
        """
        tool = self._active_tools.get(name)
        if tool is None:
            print(f"⚠️  Tool '{name}' n'est pas actif")
            return False

        tool.stop()
        del self._active_tools[name]
        print(f"✅ Tool '{name}' désactivé")
        return True

    def stop_all_tools(self) -> None:
        """Arrête tous les tools actifs."""
        for name in list(self._active_tools.keys()):
            self.deactivate_tool(name)

    def call_tool(self, name: str, **kwargs) -> Dict:
        """
        Exécute un tool avec des paramètres.

        Args:
            name: Nom du tool à exécuter
            **kwargs: Paramètres à passer au tool

        Returns:
            Dictionnaire contenant le résultat de l'exécution avec les clés:
            - 'success': bool indiquant si l'exécution a réussi
            - 'result': résultat de l'exécution (si success=True)
            - 'error': message d'erreur (si success=False)
        """
        tool = self._tools.get(name)
        if tool is None:
            return {
                "success": False,
                "error": f"Tool '{name}' non trouvé"
            }

        try:
            return tool.execute(**kwargs)
        except Exception as e:
            return {
                "success": False,
                "error": f"Erreur lors de l'exécution du tool '{name}': {str(e)}"
            }

    def get_tools_for_openai(self) -> List[Dict]:
        """
        Récupère la liste des tools au format OpenAI Function Calling.

        Returns:
            Liste de dictionnaires au format OpenAI Function Calling
        """
        tools = []
        for tool in self._tools.values():
            openai_function = tool.to_openai_function()
            if openai_function is not None:
                tools.append(openai_function)
        return tools

