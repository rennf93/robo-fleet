"""
RoboFleet Services

Phase 2: Communication, transcription, and permissions.
Phase 3: Intelligence - RAG, knowledge base, and journals.
Phase 5: Management - Tasks, kanban, metrics, dashboards.
"""

from robofleet.services.audit import (
    AuditEventType,
    AuditService,
    get_audit_service,
)
from robofleet.services.base import (
    BaseService,
    ConflictError,
    NotFoundError,
    ServiceError,
    ServiceUnavailableError,
    SingletonHolder,
    SingletonService,
    UnauthorizedError,
    ValidationError,
)
from robofleet.services.dashboard import (
    DashboardService,
    get_dashboard_service,
)
from robofleet.services.extraction import ExtractionResult, ExtractionService
from robofleet.services.journal import (
    GrowthMetrics,
    JournalService,
    JournalStats,
    get_journal_service,
)
from robofleet.services.kanban import (
    KanbanService,
    get_kanban_service,
)
from robofleet.services.metrics import (
    AgentMetrics,
    BlockerMetrics,
    MetricsService,
    TeamMetrics,
    VelocityMetrics,
    get_metrics_service,
)
from robofleet.services.notification import NotificationService
from robofleet.services.notification_delivery import (
    NotificationDeliveryService,
    get_notification_delivery_service,
)
from robofleet.services.optimal import (
    IndexType,
    OptimalService,
    QueryContext,
    RAGResponse,
    SearchResult,
    close_optimal_service,
    get_optimal_service,
)
from robofleet.services.permissions import PermissionService
from robofleet.services.task import (
    TaskService,
    get_task_service,
)
from robofleet.services.transcription import TranscriptionService

__all__ = [
    "AgentMetrics",
    "AuditEventType",
    "AuditService",
    "BaseService",
    "BlockerMetrics",
    "ConflictError",
    "DashboardService",
    "ExtractionResult",
    "ExtractionService",
    "GrowthMetrics",
    "IndexType",
    "JournalService",
    "JournalStats",
    "KanbanService",
    "MetricsService",
    "NotFoundError",
    "NotificationDeliveryService",
    "NotificationService",
    "OptimalService",
    "PermissionService",
    "QueryContext",
    "RAGResponse",
    "SearchResult",
    "ServiceError",
    "ServiceUnavailableError",
    "SingletonHolder",
    "SingletonService",
    "TaskService",
    "TeamMetrics",
    "TranscriptionService",
    "UnauthorizedError",
    "ValidationError",
    "VelocityMetrics",
    "close_optimal_service",
    "get_audit_service",
    "get_dashboard_service",
    "get_journal_service",
    "get_kanban_service",
    "get_metrics_service",
    "get_notification_delivery_service",
    "get_optimal_service",
    "get_task_service",
]
