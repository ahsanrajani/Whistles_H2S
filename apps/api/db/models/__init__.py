"""Import every model module so ``Base.metadata`` is fully populated for Alembic
and for ``create_all`` in tests."""
from ..base import Base
from .agent_activity import AgentActivity
from .ai_suggestion_cache import AiSuggestionCache
from .audit import AuditEvent
from .case import Case, CaseEvent, CaseMessage, CaseNote, Customer
from .collection import ApiKey, CallLog, Run, SurfaceStatus
from .content import ContentEvent, ContentItem
from .feature_flag import FeatureFlag
from .item import DupeEdge, Item
from .macro import CareMacroRule, CareMacroRun
from .llm_panel import LlmPanelResponse, LlmPrompt
from .item_author import ItemAuthor, TenantRetentionPolicy
from .knowledge import CareTemplate, KbArticle, KbAttachment
from .job import Job
from .location import Location
from .mention import GoldLabel, Mention, MentionClass, Sentiment
from .metric_fact import MetricFact
from .project import Project
from .outbound_action import OutboundAction
from .rbac import Permission, Role, RolePermission, UserRole
from .report_schedule import ReportSchedule
from .routing import CareAgent, RoutingPolicy
from .scheduled_task import ScheduledTask
from .seo_suggestion import SeoSuggestion
from .source_state import SourceState
from .survey import Survey, SurveyResponse
from .user import Identity, User
from .workspace import Brand, Workspace

__all__ = [
    "Base",
    "User", "Identity", "Workspace", "Brand", "Item", "DupeEdge", "Mention",
    "Sentiment", "MentionClass", "GoldLabel", "ApiKey", "CallLog",
    "SurfaceStatus", "Run", "AuditEvent",
    "Role", "Permission", "RolePermission", "UserRole", "Job", "ScheduledTask",
    "SourceState", "ItemAuthor", "TenantRetentionPolicy", "OutboundAction",
    "MetricFact",
    "Customer", "Case", "CaseMessage", "CaseNote", "CaseEvent",
    "CareAgent", "RoutingPolicy", "KbArticle", "KbAttachment", "CareTemplate",
    "CareMacroRule", "CareMacroRun",
    "AgentActivity", "ContentItem", "ContentEvent", "Survey", "SurveyResponse",
    "ReportSchedule", "Project", "FeatureFlag", "LlmPrompt", "LlmPanelResponse",
    "SeoSuggestion", "AiSuggestionCache",
]
