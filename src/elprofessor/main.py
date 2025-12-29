"""Point d'entrée principal pour ElProfessor."""

import os
import signal
import sys
import time

import cv2
from dotenv import load_dotenv

from reachy_mini import ReachyMini

from elprofessor.managers import CameraManager
from elprofessor.tool_manager import ToolManager
from elprofessor.tools.camera_snapshot import CameraSnapshotTool
from elprofessor.tools.camera_view import CameraViewTool
from elprofessor.tools.conversation import ConversationTool
from elprofessor.tools.head_tracking import HeadTrackingTool
from elprofessor.tools.play_emotion import PlayEmotionTool


def main():
    """Fonction principale de l'application ElProfessor."""
    # Charger les variables d'environnement depuis .env
    load_dotenv()

    print("🤖 ElProfessor - Application pour Reachy Mini")
    print("=" * 50)

    # Connexion au robot avec context manager
    try:
        with ReachyMini(localhost_only=False, timeout=15.0) as reachy_mini:
            print("✅ Connecté à Reachy Mini")

            # Création du manager de caméra (gère l'accès unique à la caméra)
            camera_manager = CameraManager(reachy_mini)
            camera_manager.start()

            # Création du gestionnaire de tools
            tool_manager = ToolManager(reachy_mini, camera_manager)

            # Enregistrement des tools
            tool_manager.register_tool(CameraViewTool(x=100, y=100, width=854, height=480))
            tool_manager.register_tool(HeadTrackingTool())
            tool_manager.register_tool(CameraSnapshotTool())
            tool_manager.register_tool(PlayEmotionTool())

            # Enregistrement du tool de conversation (nécessite ToolManager)
            conversation_tool = ConversationTool(tool_manager)
            tool_manager.register_tool(conversation_tool)
            # Note: Le ConversationTool n'est pas activé automatiquement car il nécessite OPENAI_API_KEY

            # Gestion de l'arrêt propre
            def signal_handler(sig, frame):
                """Gère l'arrêt propre de l'application."""
                print("\n🛑 Arrêt de l'application...")
                tool_manager.stop_all_tools()
                camera_manager.stop()
                try:
                    cv2.destroyAllWindows()
                except:
                    pass
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)

            # Interface simple pour activer/désactiver les tools
            print("\n📋 Tools disponibles:")
            for tool_name in tool_manager.list_tools():
                print(f"  - {tool_name}")

            print("\n💡 Pour activer un tool, utilisez: tool_manager.activate_tool('nom_du_tool')")
            print("💡 Pour désactiver un tool, utilisez: tool_manager.deactivate_tool('nom_du_tool')")
            print("💡 Appuyez sur Ctrl+C pour arrêter l'application\n")

            # Activer les tools
            tool_manager.activate_tool("head_tracking")
            tool_manager.activate_tool("camera_view")
            tool_manager.activate_tool("camera_snapshot")  # Nécessaire pour les snapshots ChatGPT

            # Activer le tool de conversation si OPENAI_API_KEY est définie
            if os.getenv("OPENAI_API_KEY"):
                print("\n💬 Activation du tool de conversation...")
                tool_manager.activate_tool("conversation")
            else:
                print("\n⚠️  OPENAI_API_KEY non définie - Le tool de conversation n'est pas activé")
                print("   Pour l'activer, définissez la variable d'environnement OPENAI_API_KEY")

            # Boucle principale - maintient l'application en vie et gère la caméra
            try:
                while True:
                    # Récupérer et traiter une frame de la caméra (dans le thread principal)
                    frame = camera_manager.process_frame()

                    # Mettre à jour l'affichage de camera_view (seul tool qui affiche)
                    camera_view_tool = tool_manager.get_tool("camera_view")
                    if camera_view_tool and camera_view_tool.is_running():
                        camera_view_tool.update_display()

                    # Gérer les événements de la fenêtre (touche 'q' pour quitter)
                    key = cv2.waitKey(50) & 0xFF
                    if key == ord("q"):
                        print("🛑 Fermeture de l'application (touche 'q' pressée)")
                        signal_handler(None, None)

                    # Petite pause pour ne pas surcharger le CPU
                    if frame is None:
                        time.sleep(0.05)
            except KeyboardInterrupt:
                signal_handler(None, None)
            finally:
                # Nettoyage
                tool_manager.stop_all_tools()
                camera_manager.stop()
                try:
                    cv2.destroyAllWindows()
                except:
                    pass
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        print("Vérifiez que le robot est allumé et connecté au Wi-Fi")
        return


if __name__ == "__main__":
    main()
