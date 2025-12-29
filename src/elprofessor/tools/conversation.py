"""Tool de conversation avec OpenAI Realtime API pour ElProfessor."""

import asyncio
import base64
import json
import os
import random
import threading
from pathlib import Path
from queue import Queue
from typing import Dict, Optional

import numpy as np
import sounddevice as sd
from openai import AsyncOpenAI
from scipy.signal import resample
from websockets.exceptions import ConnectionClosedError

from elprofessor.tools.base import Tool
from elprofessor.audio.head_wobbler import HeadWobbler


class ConversationTool(Tool):
    """Tool qui permet de converser avec OpenAI Realtime API et d'exposer les tools à ChatGPT."""

    def __init__(
        self,
        tool_manager,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-realtime-preview-2024-12-17",
        prompt_path: Optional[str] = None,
    ):
        """
        Initialise le tool de conversation.

        Args:
            tool_manager: Instance de ToolManager pour appeler les tools
            api_key: Clé API OpenAI (si None, lit depuis OPENAI_API_KEY)
            model: Modèle OpenAI à utiliser
            prompt_path: Chemin vers le fichier de prompt (si None, utilise el_professor.md par défaut)
        """
        super().__init__(
            name="conversation",
            description="Conversation vocale avec OpenAI Realtime API - Permet de parler avec ChatGPT et d'utiliser les tools",
        )
        self._tool_manager = tool_manager
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._model = model
        self._client: Optional[AsyncOpenAI] = None
        self._connection = None
        self._audio_input_queue: Queue = Queue()
        self._audio_output_queue: Queue = Queue()
        self._stop_event = threading.Event()
        self._session_task: Optional[asyncio.Task] = None
        self._audio_input_task: Optional[asyncio.Task] = None
        self._audio_output_task: Optional[asyncio.Task] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

        # Gestion des transcripts partiels avec debouncing
        self._partial_transcript_task: Optional[asyncio.Task] = None
        self._partial_transcript_sequence: int = 0
        self._partial_debounce_delay = 0.5  # secondes

        # Flags de lifecycle
        self._shutdown_requested: bool = False
        self._connected_event: Optional[asyncio.Event] = None
        self._is_idle_tool_call: bool = False

        # Délai de réflexion pour rendre la conversation plus naturelle (en secondes)
        self._thinking_delay = 1.5  # Délai avant de répondre après que l'utilisateur ait fini de parler
        self._last_speech_stopped_time: Optional[float] = None
        self._response_pending: bool = False
        self._audio_delay_until: Optional[float] = None  # Timestamp jusqu'auquel retarder l'audio
        self._buffered_audio_chunks: list[bytes] = []  # Buffer pour accumuler l'audio pendant le délai
        self._audio_delay_task: Optional[asyncio.Task] = None  # Tâche pour gérer le délai audio

        # Chemin du prompt
        if prompt_path is None:
            # Chemin par défaut : src/elprofessor/prompts/el_professor.md
            base_dir = Path(__file__).parent.parent
            prompt_path = base_dir / "prompts" / "el_professor.md"
        self._prompt_path = Path(prompt_path)

        # Configuration audio
        self._sample_rate = 24000  # Taux d'échantillonnage pour OpenAI Realtime API
        self._channels = 1  # Mono
        self._chunk_size = 4096  # Taille des chunks audio

        # HeadWobbler pour les mouvements de tête synchronisés avec l'audio
        self._head_wobbler: Optional[HeadWobbler] = None
        # Flag pour suivre si le robot est en train de parler (pour notifier head_tracking)
        self._robot_speaking: bool = False

    def start(self) -> bool:
        """
        Démarre le tool de conversation.

        Returns:
            True si le démarrage a réussi, False sinon
        """
        if self._running:
            return False

        if self._api_key is None:
            print("❌ OPENAI_API_KEY non définie. Définissez la variable d'environnement OPENAI_API_KEY")
            return False

        if self._tool_manager is None:
            print("❌ ToolManager non défini pour le tool conversation")
            return False

        try:
            # Vérifier que des périphériques audio sont disponibles
            try:
                devices = sd.query_devices()
                if len(devices) == 0:
                    print("⚠️  Aucun périphérique audio détecté")
            except Exception as e:
                print(f"⚠️  Erreur lors de la vérification des périphériques audio: {e}")
                # On continue quand même, l'erreur se produira lors de l'ouverture du stream

            # Initialiser le client OpenAI asynchrone
            self._client = AsyncOpenAI(api_key=self._api_key)

            # Démarrer la boucle asyncio dans un thread séparé
            self._stop_event.clear()
            self._loop_thread = threading.Thread(target=self._run_event_loop, daemon=True)
            self._loop_thread.start()

            # Attendre que la boucle soit prête
            import time

            for _ in range(50):  # Attendre max 5 secondes
                if self._event_loop is not None:
                    break
                time.sleep(0.1)
            else:
                print("❌ Timeout lors du démarrage de la boucle asyncio")
                return False

            # La session sera démarrée automatiquement depuis _main_loop()
            # via _start_session_with_retry()

            # Initialiser le HeadWobbler si ReachyMini est disponible
            if self._reachy is not None:
                try:
                    self._head_wobbler = HeadWobbler(self._reachy)
                    self._head_wobbler.start()
                    print("✅ HeadWobbler activé - Mouvements de tête synchronisés avec l'audio")
                except Exception as e:
                    print(f"⚠️  Impossible d'initialiser le HeadWobbler: {e}")

            self._set_running(True)
            print("✅ ConversationTool démarré - Prêt à converser avec ChatGPT")
            return True
        except Exception as e:
            print(f"❌ Erreur lors du démarrage du ConversationTool: {e}")
            self._cleanup()
            return False

    def stop(self) -> None:
        """Arrête le tool de conversation."""
        if not self._running:
            return

        print("🛑 Arrêt du ConversationTool...")
        self._shutdown_requested = True
        self._stop_event.set()

        # Annuler les tâches asyncio si elles existent
        if self._event_loop and not self._event_loop.is_closed():
            if self._partial_transcript_task and not self._partial_transcript_task.done():
                asyncio.run_coroutine_threadsafe(self._cancel_partial_transcript(), self._event_loop)

            # Annuler la tâche de délai audio si elle existe
            if self._audio_delay_task and not self._audio_delay_task.done():
                self._audio_delay_task.cancel()
                # Vider le buffer audio immédiatement
                self._buffered_audio_chunks.clear()

            # Arrêter la session
            asyncio.run_coroutine_threadsafe(self._stop_session(), self._event_loop)

        # Arrêter le HeadWobbler
        if self._head_wobbler is not None:
            try:
                self._head_wobbler.stop()
            except Exception as e:
                print(f"⚠️  Erreur lors de l'arrêt du HeadWobbler: {e}")

        # Attendre que le thread se termine
        if self._loop_thread:
            self._loop_thread.join(timeout=5.0)

        self._cleanup()
        self._set_running(False)
        print("✅ ConversationTool arrêté")

    async def _cancel_partial_transcript(self) -> None:
        """Annule la tâche de transcript partiel."""
        if self._partial_transcript_task and not self._partial_transcript_task.done():
            self._partial_transcript_task.cancel()
            try:
                await self._partial_transcript_task
            except asyncio.CancelledError:
                pass

    def _run_event_loop(self) -> None:
        """Exécute la boucle asyncio dans un thread séparé."""
        self._event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._event_loop)
        self._event_loop.run_until_complete(self._main_loop())

    async def _main_loop(self) -> None:
        """Boucle principale asyncio."""
        # Initialiser l'event de connexion
        self._connected_event = asyncio.Event()

        # Démarrer les tâches audio
        self._audio_input_task = asyncio.create_task(self._audio_input_loop())
        self._audio_output_task = asyncio.create_task(self._audio_output_loop())

        # Démarrer la session avec retry
        await self._start_session_with_retry()

        # Attendre l'arrêt
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(0.1)
        finally:
            # Annuler les tâches
            if self._audio_input_task:
                self._audio_input_task.cancel()
            if self._audio_output_task:
                self._audio_output_task.cancel()
            # Annuler la tâche de transcript partiel si elle existe
            if self._partial_transcript_task and not self._partial_transcript_task.done():
                self._partial_transcript_task.cancel()
                try:
                    await self._partial_transcript_task
                except asyncio.CancelledError:
                    pass

    def _load_prompt(self) -> str:
        """
        Charge le prompt depuis le fichier markdown.

        Returns:
            Le contenu du prompt sous forme de chaîne de caractères
        """
        try:
            if not self._prompt_path.exists():
                print(f"⚠️  Fichier de prompt non trouvé: {self._prompt_path}")
                print("   Utilisation des instructions par défaut")
                return (
                    "Tu es un assistant vocal pour le robot Reachy Mini. "
                    "Tu peux utiliser les outils disponibles pour interagir avec le robot. "
                    "Sois naturel et conversationnel."
                )

            with open(self._prompt_path, "r", encoding="utf-8") as f:
                prompt_content = f.read().strip()

            print(f"✅ Prompt chargé depuis: {self._prompt_path}")
            return prompt_content

        except Exception as e:
            print(f"⚠️  Erreur lors du chargement du prompt: {e}")
            print("   Utilisation des instructions par défaut")
            return (
                "Tu es un assistant vocal pour le robot Reachy Mini. "
                "Tu peux utiliser les outils disponibles pour interagir avec le robot. "
                "Sois naturel et conversationnel."
            )

    async def _start_session_with_retry(self) -> None:
        """Démarre la session Realtime API avec retry et backoff exponentiel."""
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                await self._run_realtime_session()
                # Sortie normale de la session, arrêter les retries
                return
            except ConnectionClosedError as e:
                # Fermeture inattendue (ex: "no close frame received or sent") → retry
                if attempt < max_attempts and not self._stop_event.is_set():
                    base_delay = 2 ** (attempt - 1)  # 1s, 2s, 4s, etc.
                    jitter = random.uniform(0, 0.5)
                    delay = base_delay + jitter
                    print(f"⚠️  Connexion fermée inopinément (tentative {attempt}/{max_attempts}): {e}")
                    print(f"   Nouvelle tentative dans {delay:.1f} secondes...")
                    await asyncio.sleep(delay)
                    continue
                elif not self._stop_event.is_set():
                    print(f"❌ Échec de connexion après {max_attempts} tentatives")
                raise
            finally:
                # Ne jamais garder une référence obsolète
                self._connection = None
                if self._connected_event:
                    try:
                        self._connected_event.clear()
                    except Exception:
                        pass

    async def _run_realtime_session(self) -> None:
        """Établit et gère une session Realtime unique."""
        # Charger le prompt
        instructions = self._load_prompt()

        # Récupérer les tools au format OpenAI
        tools = self._tool_manager.get_tools_for_openai()

        # Connecter à l'API Realtime
        async with self._client.realtime.connect(model=self._model) as conn:
            try:
                self._connection = conn

                # Configurer la session
                # Ajouter des instructions pour un délai de réflexion naturel et éviter les réponses spontanées
                enhanced_instructions = (
                    f"{instructions}\n\n"
                    "CRITICAL RULES:\n"
                    "1. When the user finishes speaking, wait 1-2 seconds before responding. "
                    "This creates a more natural conversation flow. Take your time to think before speaking.\n"
                    "2. DO NOT speak spontaneously or initiate conversation. ONLY respond when the user speaks to you.\n"
                    "3. If the user doesn't speak after you finish your response, remain completely silent. "
                    "Do not try to fill silence, continue the conversation, or ask follow-up questions.\n"
                    "4. Wait passively for the user to speak. The conversation is user-driven, not robot-driven."
                )

                await conn.session.update(
                    session={
                        "type": "realtime",
                        "instructions": enhanced_instructions,
                        "audio": {
                            "input": {
                                "format": {"type": "audio/pcm", "rate": self._sample_rate},
                                "transcription": {"model": "gpt-4o-transcribe", "language": "fr"},
                                "turn_detection": {
                                    "type": "server_vad",
                                    "interrupt_response": True,
                                },
                            },
                            "output": {
                                "format": {"type": "audio/pcm", "rate": self._sample_rate},
                                "voice": "echo",
                            },
                        },
                        "tools": tools,
                        "tool_choice": "auto",
                    },
                )

                print("✅ Session Realtime API configurée")

                # Signaler que la connexion est prête
                if self._connected_event:
                    self._connected_event.set()

                # Gérer les événements
                async for event in conn:
                    if self._stop_event.is_set():
                        break

                    await self._handle_event(event)

            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"❌ Erreur dans la session Realtime API: {e}")
            finally:
                self._connection = None

    async def _emit_debounced_partial(self, transcript: str, sequence: int) -> None:
        """Émet un transcript partiel après le délai de debounce."""
        try:
            await asyncio.sleep(self._partial_debounce_delay)
            # N'émettre que si c'est toujours le dernier partial (par numéro de séquence)
            if self._partial_transcript_sequence == sequence:
                print(f"📝 Transcription partielle: {transcript}")
        except asyncio.CancelledError:
            pass

    async def _flush_buffered_audio(self, delay: float) -> None:
        """Attend le délai puis envoie tous les chunks audio accumulés."""
        try:
            await asyncio.sleep(delay)
            # Envoyer tous les chunks accumulés
            for audio_bytes in self._buffered_audio_chunks:
                self._audio_output_queue.put(audio_bytes)
            self._buffered_audio_chunks.clear()
            self._audio_delay_until = None
        except Exception as e:
            print(f"⚠️  Erreur lors de l'envoi différé de l'audio: {e}")
            # En cas d'erreur, vider le buffer quand même
            self._buffered_audio_chunks.clear()
            self._audio_delay_until = None

    async def _handle_event(self, event) -> None:
        """Gère un événement de la Realtime API."""
        event_type = event.type

        if event_type == "input_audio_buffer.speech_started":
            print("🎤 Début de la parole détecté")
            self._response_pending = False
            # Réinitialiser le délai si l'utilisateur recommence à parler
            self._audio_delay_until = None
            self._buffered_audio_chunks.clear()
            if self._audio_delay_task and not self._audio_delay_task.done():
                self._audio_delay_task.cancel()
            # Réinitialiser le HeadWobbler quand l'utilisateur commence à parler
            if self._head_wobbler is not None:
                self._head_wobbler.reset()
        elif event_type == "input_audio_buffer.speech_stopped":
            print("🔇 Fin de la parole détectée")
            # Enregistrer le moment où l'utilisateur a fini de parler
            loop_time = asyncio.get_event_loop().time()
            self._last_speech_stopped_time = loop_time
            self._response_pending = True
            # Calculer jusqu'à quand retarder l'audio de réponse
            self._audio_delay_until = loop_time + self._thinking_delay
            print(f"⏳ Délai de réflexion activé: {self._thinking_delay}s")
        elif event_type == "conversation.item.input_audio_transcription.partial":
            # Transcription partielle (utilisateur en train de parler)
            transcript = getattr(event, "transcript", "")

            # Incrémenter la séquence
            self._partial_transcript_sequence += 1
            current_sequence = self._partial_transcript_sequence

            # Annuler la tâche de debounce précédente si elle existe
            if self._partial_transcript_task and not self._partial_transcript_task.done():
                self._partial_transcript_task.cancel()
                try:
                    await self._partial_transcript_task
                except asyncio.CancelledError:
                    pass

            # Démarrer un nouveau timer de debounce avec le numéro de séquence
            self._partial_transcript_task = asyncio.create_task(
                self._emit_debounced_partial(transcript, current_sequence)
            )
        elif event_type == "conversation.item.input_audio_transcription.completed":
            # Transcription complète (utilisateur a fini de parler)
            transcript = getattr(event, "transcript", "")
            print(f"📝 Transcription: {transcript}")

            # Annuler toute émission partielle en attente
            if self._partial_transcript_task and not self._partial_transcript_task.done():
                self._partial_transcript_task.cancel()
                try:
                    await self._partial_transcript_task
                except asyncio.CancelledError:
                    pass
        elif event_type in (
            "response.audio.done",
            "response.output_audio.done",
            "response.audio.completed",
            "response.completed",
        ):
            # Réponse terminée - le robot a fini de parler
            self._robot_speaking = False
            self._notify_head_tracking_robot_speaking(False)

            # Réinitialiser le HeadWobbler
            if self._head_wobbler is not None:
                self._head_wobbler.reset()
        elif event_type == "response.created":
            # Réponse créée - le robot va commencer à parler
            self._robot_speaking = True
            self._notify_head_tracking_robot_speaking(True)

            # Enregistrer le temps pour calculer le délai de réflexion
            if self._response_pending and self._last_speech_stopped_time:
                elapsed = asyncio.get_event_loop().time() - self._last_speech_stopped_time
                if elapsed < self._thinking_delay:
                    # Le délai sera appliqué lors de la lecture de l'audio
                    remaining_delay = self._thinking_delay - elapsed
                    print(f"⏳ Délai de réflexion: {remaining_delay:.1f}s")
                self._response_pending = False
        elif event_type == "response.done":
            # Réponse terminée (ne signifie pas que l'audio a fini de jouer)
            pass
        elif event_type in ("response.audio_transcript.done", "response.output_audio_transcript.done"):
            # Transcription de la réponse de l'assistant
            transcript = getattr(event, "transcript", "")
            print(f"🤖 Assistant: {transcript}")
        elif event_type in ("response.audio.delta", "response.output_audio.delta"):
            # Audio de réponse - appliquer le délai de réflexion si nécessaire
            # Notifier le head_tracking que le robot parle (au premier chunk si pas déjà fait)
            if not self._robot_speaking:
                self._robot_speaking = True
                self._notify_head_tracking_robot_speaking(True)

            audio_delta = getattr(event, "delta", "")
            if audio_delta:
                try:
                    # IMPORTANT: Envoyer l'audio au HeadWobbler IMMÉDIATEMENT, même si on retarde la lecture
                    # Le HeadWobbler doit analyser l'audio en temps réel pour générer les mouvements synchronisés
                    # Le speech_tapper analyse l'audio et génère les offsets de mouvement
                    if self._head_wobbler is not None:
                        try:
                            self._head_wobbler.feed(audio_delta)
                        except Exception as e:
                            # Ne pas bloquer si le HeadWobbler a un problème
                            print(f"⚠️  Erreur lors de l'envoi de l'audio au HeadWobbler: {e}")
                            import traceback

                            traceback.print_exc()
                    else:
                        print("⚠️  HeadWobbler n'est pas initialisé")

                    audio_bytes = base64.b64decode(audio_delta)

                    # Vérifier si on doit retarder l'audio pour créer un délai de réflexion
                    if self._audio_delay_until:
                        loop_time = asyncio.get_event_loop().time()
                        if loop_time < self._audio_delay_until:
                            # Accumuler l'audio dans le buffer pendant le délai
                            self._buffered_audio_chunks.append(audio_bytes)

                            # Démarrer la tâche de délai si ce n'est pas déjà fait
                            if self._audio_delay_task is None or self._audio_delay_task.done():
                                remaining_delay = self._audio_delay_until - loop_time
                                self._audio_delay_task = asyncio.create_task(
                                    self._flush_buffered_audio(remaining_delay)
                                )
                            return
                        else:
                            # Le délai est écoulé, on peut continuer normalement
                            self._audio_delay_until = None
                            self._buffered_audio_chunks.clear()

                    # Envoyer l'audio immédiatement (pas de délai nécessaire)
                    self._audio_output_queue.put(audio_bytes)
                except Exception as e:
                    print(f"⚠️  Erreur lors du décodage de l'audio: {e}")
        elif event_type == "response.function_call_arguments.done":
            # Appel de fonction (tool)
            tool_name = getattr(event, "name", None)
            args_json_str = getattr(event, "arguments", None)
            call_id = getattr(event, "call_id", None)

            if not isinstance(tool_name, str) or not isinstance(args_json_str, str):
                print(f"❌ Appel de tool invalide: tool_name={tool_name}, args={args_json_str}")
                return

            try:
                # Parser les arguments
                args = json.loads(args_json_str) if args_json_str else {}

                # Appeler le tool via le ToolManager (synchrone, donc dans un thread)
                def call_tool():
                    return self._tool_manager.call_tool(tool_name, **args)

                # Exécuter dans un thread pool pour ne pas bloquer
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, call_tool)

                # Préparer le résultat du tool
                tool_result = (
                    result.get("result", {})
                    if result.get("success")
                    else {"error": result.get("error", "Erreur inconnue")}
                )

                # Envoyer le résultat
                if isinstance(call_id, str) and self._connection:
                    await self._connection.conversation.item.create(
                        item={
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(tool_result),
                        },
                    )

                # Si c'est un snapshot de caméra avec image, l'ajouter à la conversation
                if tool_name == "camera_snapshot" and result.get("success"):
                    if "image_base64" in tool_result and self._connection:
                        b64_im = tool_result["image_base64"]
                        # Vérifier le type (comme dans la référence)
                        if not isinstance(b64_im, str):
                            print(f"⚠️  Type inattendu pour image_base64: {type(b64_im)}")
                            b64_im = str(b64_im)

                        await self._connection.conversation.item.create(
                            item={
                                "type": "message",
                                "role": "user",
                                "content": [
                                    {
                                        "type": "input_image",
                                        "image_url": f"data:image/jpeg;base64,{b64_im}",
                                    },
                                ],
                            },
                        )
                        print("✅ Image de caméra ajoutée à la conversation")

                print(f"✅ Tool '{tool_name}' exécuté avec succès")

                # Si ce tool call a été déclenché par un signal idle, ne pas faire parler le robot
                # Pour les autres tool calls, demander explicitement une réponse vocale
                if self._is_idle_tool_call:
                    self._is_idle_tool_call = False
                else:
                    # Demander explicitement une réponse vocale après le tool call
                    # Ajouter un petit délai pour rendre la réponse plus naturelle
                    if self._connection:
                        await asyncio.sleep(0.8)  # Petit délai avant de répondre après un tool call
                        await self._connection.response.create(
                            response={
                                "instructions": (
                                    "Utilise le résultat du tool qui vient d'être retourné et réponds de manière concise à voix haute. "
                                    "Prends un moment pour réfléchir avant de répondre (1-2 secondes) pour rendre la conversation plus naturelle."
                                ),
                            },
                        )
            except Exception as e:
                print(f"❌ Erreur lors de l'exécution du tool {tool_name}: {e}")
                if isinstance(call_id, str) and self._connection:
                    await self._connection.conversation.item.create(
                        item={
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps({"error": str(e)}),
                        },
                    )
        elif event_type == "error":
            error = getattr(event, "error", None)
            error_msg = getattr(error, "message", str(error) if error else "Erreur inconnue")
            error_code = getattr(error, "code", "")

            # Ne montrer que les erreurs visibles par l'utilisateur, pas les erreurs d'état interne
            if error_code not in ("input_audio_buffer_commit_empty", "conversation_already_has_active_response"):
                print(f"❌ Erreur Realtime API [{error_code}]: {error_msg}")

    async def _audio_input_loop(self) -> None:
        """Boucle de capture audio depuis le microphone."""
        try:
            print("🎤 Microphone activé")

            # Utiliser un stream d'entrée avec sounddevice
            # Récupérer le sample rate du périphérique par défaut
            default_device = sd.query_devices(kind="input")
            device_sample_rate = int(default_device["default_samplerate"])

            with sd.InputStream(
                samplerate=device_sample_rate, channels=self._channels, dtype="int16", blocksize=self._chunk_size
            ) as stream:
                while not self._stop_event.is_set():
                    try:
                        # Lire un chunk audio
                        audio_data, overflowed = stream.read(self._chunk_size)

                        if overflowed:
                            print("⚠️  Overflow audio détecté")

                        # Reshape si nécessaire (gérer mono/stereo)
                        if audio_data.ndim == 2:
                            # Si stéréo, prendre seulement le premier canal
                            if audio_data.shape[1] > 1:
                                audio_data = audio_data[:, 0]
                            else:
                                audio_data = audio_data.flatten()

                        # Resample si nécessaire
                        if device_sample_rate != self._sample_rate:
                            num_samples = int(len(audio_data) * self._sample_rate / device_sample_rate)
                            audio_data = resample(audio_data, num_samples)

                        # S'assurer que c'est du int16
                        audio_data = audio_data.astype(np.int16)

                        # Convertir en bytes
                        audio_bytes = audio_data.tobytes()

                        # Encoder en base64 et envoyer à la session
                        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

                        # Envoyer à l'API Realtime (garder contre les races pendant la reconnexion)
                        if self._connection:
                            try:
                                await self._connection.input_audio_buffer.append(audio=audio_base64)
                            except Exception as e:
                                # Ignorer les erreurs de connexion (peut être en cours de reconnexion)
                                pass

                        await asyncio.sleep(0.01)  # Petite pause
                    except Exception as e:
                        if not self._stop_event.is_set():
                            print(f"⚠️  Erreur lors de la capture audio: {e}")
                        await asyncio.sleep(0.1)

        except Exception as e:
            print(f"❌ Erreur dans la boucle de capture audio: {e}")

    async def _audio_output_loop(self) -> None:
        """Boucle de lecture audio vers les haut-parleurs."""
        try:
            print("🔊 Haut-parleurs activés")

            # Utiliser un stream de sortie avec sounddevice
            with sd.OutputStream(
                samplerate=self._sample_rate, channels=self._channels, dtype="int16", blocksize=self._chunk_size
            ) as stream:
                while not self._stop_event.is_set():
                    try:
                        # Récupérer un chunk audio de la queue (avec timeout)
                        try:
                            audio_bytes = self._audio_output_queue.get_nowait()

                            # Convertir les bytes en numpy array
                            audio_array = np.frombuffer(audio_bytes, dtype="int16")
                            # Reshape pour correspondre au format attendu (samples, channels)
                            audio_array = audio_array.reshape(-1, self._channels)

                            # Jouer l'audio
                            stream.write(audio_array)
                        except:
                            # Queue vide - continuer la boucle
                            await asyncio.sleep(0.01)
                            continue
                    except Exception as e:
                        if not self._stop_event.is_set():
                            print(f"⚠️  Erreur lors de la lecture audio: {e}")
                        await asyncio.sleep(0.1)

        except Exception as e:
            print(f"❌ Erreur dans la boucle de lecture audio: {e}")

    async def _stop_session(self) -> None:
        """Arrête la session Realtime API."""
        if self._connection:
            try:
                await self._connection.close()
            except ConnectionClosedError:
                # Connexion déjà fermée, c'est OK
                pass
            except Exception as e:
                print(f"⚠️  Erreur lors de la fermeture de la connexion: {e}")
            finally:
                self._connection = None

        # Vider la queue de sortie audio
        while not self._audio_output_queue.empty():
            try:
                self._audio_output_queue.get_nowait()
            except Exception:
                break

    def _notify_head_tracking_robot_speaking(self, speaking: bool) -> None:
        """
        Notifie le HeadTrackingTool que le robot est en train de parler ou non.

        Args:
            speaking: True si le robot parle, False sinon
        """
        if self._tool_manager is None:
            return

        try:
            head_tracking_tool = self._tool_manager.get_tool("head_tracking")
            if head_tracking_tool is not None and hasattr(head_tracking_tool, "set_robot_speaking"):
                head_tracking_tool.set_robot_speaking(speaking)
        except Exception as e:
            # Ne pas bloquer si la notification échoue
            pass

    def _cleanup(self) -> None:
        """Nettoie les ressources."""
        self._connection = None
        self._client = None
        self._event_loop = None
        self._connected_event = None
        self._partial_transcript_task = None
        self._audio_delay_task = None
        self._buffered_audio_chunks.clear()
        self._audio_delay_until = None
        self._response_pending = False
        self._head_wobbler = None
        # Réinitialiser le flag de parole du robot
        self._robot_speaking = False
        self._notify_head_tracking_robot_speaking(False)

    def to_openai_function(self) -> Optional[Dict]:
        """
        Convertit le tool en définition de fonction OpenAI.

        Returns:
            None car ce tool n'est pas exposé à ChatGPT (c'est le tool de conversation lui-même)
        """
        return None

    def execute(self, **kwargs) -> Dict:
        """
        Exécute le tool (non applicable pour le tool de conversation).

        Args:
            **kwargs: Paramètres (non utilisés)

        Returns:
            Dictionnaire contenant un message d'erreur
        """
        return {"success": False, "error": "Le tool de conversation ne peut pas être exécuté directement"}
