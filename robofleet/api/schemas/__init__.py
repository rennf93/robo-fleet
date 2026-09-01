"""
API Schemas

Pydantic models for request/response serialization.
"""

from robofleet.api.schemas.common import (
    ApiResponse,
    ErrorCode,
    ErrorDetail,
    error_response,
    list_response,
    success_response,
)
from robofleet.api.schemas.dashboard import (
    AuditorDashboard,
    AuditorFlag,
    AuditorReport,
    CEOOverview,
    CreateFlagRequest,
    CreateReportRequest,
    FlagSeverity,
    TeamHealth,
)
from robofleet.api.schemas.health import HealthResponse, ReadinessResponse
from robofleet.api.schemas.journals import (
    CreateEntryRequest,
    DecisionLogRequest,
    GeneralEntryRequest,
    GrowthMetricsResponse,
    JournalEntryResponse,
    JournalResponse,
    JournalStatsResponse,
    LearningRequest,
    ListEntriesParams,
    SearchEntriesRequest,
    StruggleRequest,
    TaskReflectionRequest,
)
from robofleet.api.schemas.notifications import (
    ListNotificationsParams,
    NotificationListResponse,
    NotificationResponse,
)
from robofleet.api.schemas.optimal import (
    ClearIndexResponse,
    IndexCodeRequest,
    IndexDocsRequest,
    IndexResponse,
    IndexStatsResponse,
    PromptTemplateRequest,
    PromptTemplateResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    RefreshIndexResponse,
    RefreshRequest,
    SearchRequest,
    SearchResponse,
    SearchResultResponse,
    TokenEstimateRequest,
    TokenEstimateResponse,
)
from robofleet.api.schemas.orchestrator import (
    AgentStatusResponse,
    OrchestratorStatusResponse,
    ResolveWaitRequest,
    SpawnAgentRequest,
    WaitingAgentResponse,
)
from robofleet.api.schemas.stream import (
    ExtractedMessageResponse,
    ExtractionResponse,
    ExtractRequest,
    StreamChunkRequest,
    StreamCompleteRequest,
    TranscriptionStatsResponse,
)
from robofleet.api.schemas.tasks import (
    CheckpointRequest,
    ClaimRequest,
    CommitRequest,
    ListTasksQuery,
    ProgressRequest,
    QANotes,
    TaskCountResponse,
    TaskResponse,
    TaskUpdate,
    TeamTasksQuery,
)

__all__ = [
    # Orchestrator
    "AgentStatusResponse",
    # Common
    "ApiResponse",
    # Dashboard
    "AuditorDashboard",
    "AuditorFlag",
    "AuditorReport",
    "CEOOverview",
    # Tasks
    "CheckpointRequest",
    "ClaimRequest",
    # Optimal
    "ClearIndexResponse",
    "CommitRequest",
    # Journals
    "CreateEntryRequest",
    "CreateFlagRequest",
    "CreateReportRequest",
    "DecisionLogRequest",
    "ErrorCode",
    "ErrorDetail",
    "ExtractRequest",
    # Stream
    "ExtractedMessageResponse",
    "ExtractionResponse",
    "FlagSeverity",
    "GeneralEntryRequest",
    "GrowthMetricsResponse",
    # Health
    "HealthResponse",
    "IndexCodeRequest",
    "IndexDocsRequest",
    "IndexResponse",
    "IndexStatsResponse",
    "JournalEntryResponse",
    "JournalResponse",
    "JournalStatsResponse",
    "LearningRequest",
    "ListEntriesParams",
    # Notifications
    "ListNotificationsParams",
    "ListTasksQuery",
    "NotificationListResponse",
    "NotificationResponse",
    "OrchestratorStatusResponse",
    "ProgressRequest",
    "PromptTemplateRequest",
    "PromptTemplateResponse",
    "QANotes",
    "RAGQueryRequest",
    "RAGQueryResponse",
    "ReadinessResponse",
    "RefreshIndexResponse",
    "RefreshRequest",
    "ResolveWaitRequest",
    "SearchEntriesRequest",
    "SearchRequest",
    "SearchResponse",
    "SearchResultResponse",
    "SpawnAgentRequest",
    "StreamChunkRequest",
    "StreamCompleteRequest",
    "StruggleRequest",
    "TaskCountResponse",
    "TaskReflectionRequest",
    "TaskResponse",
    "TaskUpdate",
    "TeamHealth",
    "TeamTasksQuery",
    "TokenEstimateRequest",
    "TokenEstimateResponse",
    "TranscriptionStatsResponse",
    "WaitingAgentResponse",
    "error_response",
    "list_response",
    "success_response",
]
