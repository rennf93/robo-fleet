"""
RoboCo Data Models

This module contains all data models for the AI Agents Company system.
"""

from robofleet.models.agent import (
    Agent,
    AgentCreate,
    AgentUpdate,
    ModelConfig,
)
from robofleet.models.base import (
    AgentRole,
    AgentStatus,
    Complexity,
    HandoffStatus,
    JournalEntryType,
    MessageType,
    ModelProvider,
    NotificationPriority,
    NotificationType,
    # Base types
    RobocoBase,
    SubstituteReason,
    # Enums
    TaskNature,
    TaskStatus,
    Team,
)
from robofleet.models.handoff import (
    DocumenterHandoff,
    HandoffCreate,
)
from robofleet.models.journal import (
    Journal,
    JournalEntry,
    JournalEntryCreate,
)
from robofleet.models.kanban import (
    KanbanBoard,
    KanbanBoardType,
    KanbanCard,
    KanbanColumn,
    KanbanSwimlane,
    get_column_config,
)
from robofleet.models.message import (
    ExtractedMessage,
    RawStream,
)
from robofleet.models.notification import (
    Notification,
    NotificationCreate,
)
from robofleet.models.task import (
    Checkpoint,
    CommitRef,
    DocRef,
    ProgressUpdate,
    Task,
    TaskCreate,
    TaskPlan,
    TaskUpdate,
)

__all__ = [
    "Agent",
    "AgentCreate",
    "AgentRole",
    "AgentStatus",
    "AgentUpdate",
    "Checkpoint",
    "CommitRef",
    "Complexity",
    "DocRef",
    "DocumenterHandoff",
    "ExtractedMessage",
    "HandoffCreate",
    "HandoffStatus",
    "Journal",
    "JournalEntry",
    "JournalEntryCreate",
    "JournalEntryType",
    "KanbanBoard",
    "KanbanBoardType",
    "KanbanCard",
    "KanbanColumn",
    "KanbanSwimlane",
    "MessageType",
    "ModelConfig",
    "ModelProvider",
    "Notification",
    "NotificationCreate",
    "NotificationPriority",
    "NotificationType",
    "ProgressUpdate",
    "RawStream",
    "RobocoBase",
    "SubstituteReason",
    "Task",
    "TaskCreate",
    "TaskNature",
    "TaskPlan",
    "TaskStatus",
    "TaskUpdate",
    "Team",
    "get_column_config",
]
