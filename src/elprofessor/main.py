"""Point d'entrée principal pour ElProfessor."""

import signal
import sys

from reachy_mini import ReachyMini

from elprofessor.tool_manager import ToolManager
from elprofessor.tools.head_tracking import HeadTrackingTool


def main():
    """Fonction principale de l'application ElProfessor."""
    print("🤖 ElProfessor - Application pour Reachy Mini")
    print("=" * 50)

    # Connexion au robot avec context manager
    try:
        with ReachyMini(localhost_only=False, timeout=15.0) as reachy_mini:
            print("✅ Connecté à Reachy Mini")

            # Création du gestionnaire de tools
            tool_manager = ToolManager(reachy_mini)

            # Enregistrement des tools
            tool_manager.register_tool(HeadTrackingTool())
            # Ajouter d'autres tools ici au fur et à mesure

            # Gestion de l'arrêt propre
            def signal_handler(sig, frame):
                """Gère l'arrêt propre de l'application."""
                print("\n🛑 Arrêt de l'application...")
                tool_manager.stop_all_tools()
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)

            # Interface simple pour activer/désactiver les tools
            print("\n📋 Tools disponibles:")
            for tool_name in tool_manager.list_tools():
                print(f"  - {tool_name}")

            print("\n💡 Pour activer un tool, utilisez: tool_manager.activate_tool('nom_du_tool')")
            print("💡 Pour désactiver un tool, utilisez: tool_manager.deactivate_tool('nom_du_tool')")
            print("💡 Appuyez sur Ctrl+C pour arrêter l'application\n")

            # Exemple: activer le head tracking
            # Décommentez la ligne suivante pour activer automatiquement le head tracking
            tool_manager.activate_tool("head_tracking")

            # Boucle principale - maintient l'application en vie
            try:
                while True:
                    import time

                    time.sleep(1)
            except KeyboardInterrupt:
                signal_handler(None, None)
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        print("Vérifiez que le robot est allumé et connecté au Wi-Fi")
        return


if __name__ == "__main__":
    main()
