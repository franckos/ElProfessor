"""Gestionnaire des tools pour ElProfessor."""

from typing import Dict, List, Optional

from elprofessor.tools.base import Tool


class ToolManager:
    """Gestionnaire central pour tous les tools."""

    def __init__(self, reachy):
        """
        Initialise le gestionnaire de tools.

        Args:
            reachy: Instance de ReachyMini
        """
        self._reachy = reachy
        self._tools: Dict[str, Tool] = {}
        self._active_tools: Dict[str, Tool] = {}

    def register_tool(self, tool: Tool) -> None:
        """
        Enregistre un tool.

        Args:
            tool: Instance du tool à enregistrer
        """
        tool.set_reachy(self._reachy)
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

