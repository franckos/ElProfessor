"""Module des tools pour ElProfessor."""

from elprofessor.tools.base import Tool
from elprofessor.tools.camera_snapshot import CameraSnapshotTool
from elprofessor.tools.camera_view import CameraViewTool
from elprofessor.tools.conversation import ConversationTool
from elprofessor.tools.head_tracking import HeadTrackingTool
from elprofessor.tools.move_head import MoveHeadTool

__all__ = [
    "Tool",
    "CameraSnapshotTool",
    "CameraViewTool",
    "ConversationTool",
    "HeadTrackingTool",
    "MoveHeadTool",
]
