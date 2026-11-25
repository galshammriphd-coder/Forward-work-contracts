"""Relational data model. Project.id is the isolation key for documents, chunks,
embeddings and conversations: every such row carries project_id as a real FK."""
from datetime import datetime, date

from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer,
                        LargeBinary, String, Table, Text, UniqueConstraint, Index)
from sqlalchemy.orm import relationship

from .db import Base


def now():
    return datetime.utcnow()


def FK(target, **kw):
    return Column(Integer, ForeignKey(target, ondelete=kw.pop("ondelete", "CASCADE")), **kw)


def OptFK(target):
    return Column(Integer, ForeignKey(target, ondelete="SET NULL"), nullable=True)


role_permissions = Table(
    "role_permissions", Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True))

risk_activities = Table(
    "risk_activities", Base.metadata,
    Column("risk_id", ForeignKey("risks.id", ondelete="CASCADE"), primary_key=True),
    Column("activity_id", ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True))

risk_deliverables = Table(
    "risk_deliverables", Base.metadata,
    Column("risk_id", ForeignKey("risks.id", ondelete="CASCADE"), primary_key=True),
    Column("deliverable_id", ForeignKey("deliverables.id", ondelete="CASCADE"), primary_key=True))


# ---------- organisation, identity, access ----------
class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True)
    name_ar = Column(String(200)); name_en = Column(String(200))
    currency = Column(String(8), default="SAR")


class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    organization_id = OptFK("organizations.id")
    name_ar = Column(String(200)); name_en = Column(String(200))


class Permission(Base):
    __tablename__ = "permissions"
    id = Column(Integer, primary_key=True)
    key = Column(String(80), unique=True, nullable=False)
    description = Column(String(300))


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    key = Column(String(60), unique=True, nullable=False)
    name_ar = Column(String(120)); name_en = Column(String(120))
    all_projects = Column(Boolean, default=False)  # platform-wide project visibility
    clearance = Column(Integer, default=1)  # 0 public,1 internal,2 confidential,3 restricted
    permissions = relationship("Permission", secondary=role_permissions, lazy="selectin")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True, nullable=False)
    name_ar = Column(String(200)); name_en = Column(String(200))
    password_hash = Column(String(300), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    department_id = OptFK("departments.id")
    is_active = Column(Boolean, default=True)
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(64))
    locale = Column(String(5), default="ar")
    token_version = Column(Integer, default=0)  # bump to revoke sessions
    created_at = Column(DateTime, default=now)
    role = relationship("Role", lazy="joined")


class ProjectMember(Base):
    __tablename__ = "project_members"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    user_id = FK("users.id", nullable=False)
    project_role = Column(String(60), default="member")
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)


# ---------- strategy, portfolio, programme, project ----------
class StrategicObjective(Base):
    __tablename__ = "strategic_objectives"
    id = Column(Integer, primary_key=True)
    code = Column(String(30)); name_ar = Column(String(300)); name_en = Column(String(300))
    description = Column(Text); target = Column(String(300)); weight = Column(Float, default=1)


class Portfolio(Base):
    __tablename__ = "portfolios"
    id = Column(Integer, primary_key=True)
    code = Column(String(30)); name_ar = Column(String(300)); name_en = Column(String(300))
    description = Column(Text); objectives = Column(Text)
    objective_id = OptFK("strategic_objectives.id")
    owner_id = OptFK("users.id")
    budget = Column(Float, default=0)


class Program(Base):
    __tablename__ = "programs"
    id = Column(Integer, primary_key=True)
    portfolio_id = OptFK("portfolios.id")
    code = Column(String(30)); name_ar = Column(String(300)); name_en = Column(String(300))
    description = Column(Text); objectives = Column(Text); outputs = Column(Text)
    manager_id = OptFK("users.id")
    budget = Column(Float, default=0)


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    code = Column(String(30), unique=True)
    name_ar = Column(String(300)); name_en = Column(String(300))
    description = Column(Text)
    portfolio_id = OptFK("portfolios.id"); program_id = OptFK("programs.id")
    department_id = OptFK("departments.id"); objective_id = OptFK("strategic_objectives.id")
    sponsor = Column(String(200)); business_owner = Column(String(200))
    manager_id = OptFK("users.id")
    status = Column(String(30), default="planned")  # planned|active|on_hold|completed|cancelled
    stage = Column(String(40), default="initiation")
    priority = Column(String(20), default="medium")
    start_date = Column(Date); end_date = Column(Date)
    budget = Column(Float, default=0)
    business_case = Column(Text); scope = Column(Text); out_of_scope = Column(Text)
    success_criteria = Column(Text); assumptions = Column(Text); constraints = Column(Text)
    dependencies_text = Column(Text)
    needs_intervention = Column(Boolean, default=False)
    intervention_reason = Column(Text)
    created_from = Column(String(30), default="manual")  # manual|charter
    last_update_at = Column(DateTime, default=now)
    created_at = Column(DateTime, default=now)
    manager = relationship("User", lazy="joined")


class ProjectCharter(Base):
    __tablename__ = "project_charters"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    content = Column(JSON, default=dict)  # field -> {value, tag, source}
    source_document_id = OptFK("documents.id")
    status = Column(String(20), default="draft")
    approved_by = OptFK("users.id"); approved_at = Column(DateTime)


class InitiationSession(Base):
    """Working draft of the AI initiation wizard. Nothing here is live project data
    until a user approves every section and activates the project."""
    __tablename__ = "initiation_sessions"
    id = Column(Integer, primary_key=True)
    user_id = FK("users.id", nullable=False)
    filename = Column(String(300)); storage_path = Column(String(500))
    language = Column(String(5))
    status = Column(String(20), default="analyzed")  # analyzed|generated|activated
    draft = Column(JSON, default=dict)
    approvals = Column(JSON, default=dict)
    project_id = OptFK("projects.id")
    created_at = Column(DateTime, default=now)


class ProjectPhase(Base):
    __tablename__ = "project_phases"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    name = Column(String(300)); order = Column(Integer, default=0)
    start_date = Column(Date); end_date = Column(Date)
    status = Column(String(20), default="not_started")
    gate_status = Column(String(20), default="pending")  # pending|requested|approved|rejected


class Deliverable(Base):
    __tablename__ = "deliverables"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    phase_id = OptFK("project_phases.id")
    name = Column(String(300)); description = Column(Text)
    due_date = Column(Date); status = Column(String(20), default="planned")
    acceptance_criteria = Column(Text); source_tag = Column(String(20), default="user")


class WBSElement(Base):
    __tablename__ = "wbs_elements"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    parent_id = Column(Integer, ForeignKey("wbs_elements.id", ondelete="CASCADE"))
    code = Column(String(40)); name = Column(String(300))
    kind = Column(String(20), default="work_package")  # phase|deliverable|work_package
    phase_id = OptFK("project_phases.id"); deliverable_id = OptFK("deliverables.id")
    order = Column(Integer, default=0); source_tag = Column(String(20), default="user")


class Activity(Base):
    __tablename__ = "activities"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    wbs_id = OptFK("wbs_elements.id"); phase_id = OptFK("project_phases.id")
    deliverable_id = OptFK("deliverables.id")
    parent_id = Column(Integer, ForeignKey("activities.id", ondelete="CASCADE"))
    code = Column(String(40)); wbs_code = Column(String(40))
    name = Column(String(300), nullable=False); description = Column(Text)
    responsible_id = OptFK("users.id"); responsible_name = Column(String(200))
    supporting_team = Column(String(300))
    planned_start = Column(Date); planned_end = Column(Date)
    duration_days = Column(Integer, default=1)  # working days; 0 = milestone
    constraint_start = Column(Date)  # "start no earlier than"
    actual_start = Column(Date); actual_end = Column(Date)
    priority = Column(String(20), default="medium")
    required_resources = Column(String(300))
    estimated_cost = Column(Float, default=0)
    completion_criteria = Column(Text)
    weight = Column(Float, default=0)
    risk_exposure = Column(Float, default=0)
    status = Column(String(20), default="not_started")
    progress = Column(Float, default=0)  # 0..100
    order = Column(Integer, default=0)
    # written by the scheduling engine
    early_start = Column(Date); early_finish = Column(Date)
    late_start = Column(Date); late_finish = Column(Date)
    total_float = Column(Integer); is_critical = Column(Boolean, default=False)
    source_tag = Column(String(20), default="user")


class Dependency(Base):
    __tablename__ = "dependencies"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    predecessor_id = FK("activities.id", nullable=False)
    successor_id = FK("activities.id", nullable=False)
    type = Column(String(2), default="FS")  # FS|SS|FF|SF
    lag_days = Column(Integer, default=0)  # negative = lead
    __table_args__ = (UniqueConstraint("predecessor_id", "successor_id"),)


class Milestone(Base):
    __tablename__ = "milestones"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    name = Column(String(300)); description = Column(Text)
    target_date = Column(Date); actual_date = Column(Date)
    owner_name = Column(String(200)); acceptance_criteria = Column(Text)
    status = Column(String(20), default="pending")  # pending|achieved|missed
    activity_id = OptFK("activities.id"); deliverable_id = OptFK("deliverables.id")
    source_tag = Column(String(20), default="user")


class Baseline(Base):
    __tablename__ = "baselines"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    name = Column(String(200)); created_at = Column(DateTime, default=now)
    created_by = OptFK("users.id")
    is_current = Column(Boolean, default=True)
    snapshot = Column(JSON, default=dict)  # {activity_id: {start,end,duration,cost}}, finish, budget


# ---------- risk, issues, change ----------
class Risk(Base):
    __tablename__ = "risks"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id"); program_id = OptFK("programs.id"); portfolio_id = OptFK("portfolios.id")
    phase_id = OptFK("project_phases.id")
    scope_level = Column(String(20), default="project")  # project|program|portfolio|phase|deliverable|work_package|activity
    code = Column(String(30)); title = Column(String(300), nullable=False); description = Column(Text)
    category = Column(String(60))
    probability = Column(Integer, default=3); impact = Column(Integer, default=3)
    score = Column(Integer, default=9); level = Column(String(20), default="moderate")
    owner_name = Column(String(200)); owner_id = OptFK("users.id")
    mitigation = Column(Text); contingency = Column(Text); trigger = Column(Text)
    response_deadline = Column(Date)
    residual_probability = Column(Integer); residual_impact = Column(Integer)
    residual_score = Column(Integer)
    status = Column(String(20), default="open")  # open|mitigating|closed|occurred
    shared_key = Column(String(60))  # same key on several projects = one shared risk
    source_tag = Column(String(20), default="user")
    created_at = Column(DateTime, default=now); updated_at = Column(DateTime, default=now)
    activities = relationship("Activity", secondary=risk_activities, lazy="selectin")
    deliverables = relationship("Deliverable", secondary=risk_deliverables, lazy="selectin")
    responses = relationship("RiskResponse", cascade="all, delete-orphan", lazy="selectin")


class RiskResponse(Base):
    __tablename__ = "risk_responses"
    id = Column(Integer, primary_key=True)
    risk_id = FK("risks.id", nullable=False)
    type = Column(String(20), default="mitigation")  # mitigation|contingency
    description = Column(Text); action_owner = Column(String(200))
    target_date = Column(Date); progress = Column(Float, default=0)
    status = Column(String(20), default="planned")


class RiskSnapshot(Base):
    """Daily count per level, so the risk trend chart is history, not a guess."""
    __tablename__ = "risk_snapshots"
    id = Column(Integer, primary_key=True)
    snapshot_date = Column(Date, nullable=False)
    project_id = FK("projects.id")
    low = Column(Integer, default=0); moderate = Column(Integer, default=0)
    high = Column(Integer, default=0); critical = Column(Integer, default=0)


class Issue(Base):
    __tablename__ = "issues"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    title = Column(String(300), nullable=False); description = Column(Text)
    severity = Column(String(20), default="medium"); owner_name = Column(String(200))
    status = Column(String(20), default="open")
    raised_at = Column(Date, default=date.today); due_date = Column(Date); closed_at = Column(Date)


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    title = Column(String(300), nullable=False); description = Column(Text)
    change_type = Column(String(30), default="scope")
    impact_schedule_days = Column(Integer, default=0); impact_cost = Column(Float, default=0)
    status = Column(String(20), default="submitted")  # submitted|approved|rejected|implemented
    requested_by = Column(String(200)); requested_at = Column(Date, default=date.today)
    decided_at = Column(Date)


class Decision(Base):
    __tablename__ = "decisions"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id")
    title = Column(String(300), nullable=False); description = Column(Text)
    decided_by = Column(String(200)); meeting = Column(String(200))
    decided_at = Column(Date); due_date = Column(Date)
    status = Column(String(20), default="pending")  # pending|decided|implemented


# ---------- finance, resources, stakeholders ----------
class Budget(Base):
    __tablename__ = "budgets"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    phase_id = OptFK("project_phases.id")
    category = Column(String(100)); planned_amount = Column(Float, default=0)
    approved_amount = Column(Float, default=0); fiscal_year = Column(Integer)


class Cost(Base):
    __tablename__ = "costs"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    activity_id = OptFK("activities.id"); phase_id = OptFK("project_phases.id")
    budget_id = OptFK("budgets.id")
    kind = Column(String(20), default="actual")  # actual|commitment
    amount = Column(Float, default=0); cost_date = Column(Date, default=date.today)
    description = Column(String(300)); vendor = Column(String(200))


class Resource(Base):
    __tablename__ = "resources"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False); kind = Column(String(30), default="human")
    title = Column(String(200)); team = Column(String(120))
    department_id = OptFK("departments.id"); user_id = OptFK("users.id")
    capacity_pct = Column(Float, default=100); cost_rate = Column(Float, default=0)
    skills = Column(String(300))


class ResourceAssignment(Base):
    __tablename__ = "resource_assignments"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    resource_id = FK("resources.id", nullable=False)
    activity_id = OptFK("activities.id")
    role = Column(String(120)); allocation_pct = Column(Float, default=50)
    start_date = Column(Date); end_date = Column(Date)


class Stakeholder(Base):
    __tablename__ = "stakeholders"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    name = Column(String(200), nullable=False); organization = Column(String(200))
    role = Column(String(200)); power = Column(Integer, default=3); interest = Column(Integer, default=3)
    engagement = Column(String(30), default="neutral")
    communication = Column(String(300)); contact = Column(String(200))
    last_interaction = Column(Date); source_tag = Column(String(20), default="user")


class RACIAssignment(Base):
    __tablename__ = "raci_assignments"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    activity_id = FK("activities.id", nullable=False)
    party = Column(String(200), nullable=False)
    raci = Column(String(1), nullable=False)  # R|A|C|I
    __table_args__ = (UniqueConstraint("activity_id", "party"),)


class KPI(Base):
    __tablename__ = "kpis"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    name = Column(String(300), nullable=False); unit = Column(String(40))
    baseline = Column(Float); target = Column(Float); actual = Column(Float)
    direction = Column(String(10), default="up")  # up = higher is better
    frequency = Column(String(30), default="monthly"); owner_name = Column(String(200))
    source_tag = Column(String(20), default="user")


class Benefit(Base):
    __tablename__ = "benefits"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    objective_id = OptFK("strategic_objectives.id")
    name = Column(String(300), nullable=False); metric = Column(String(200)); unit = Column(String(40))
    owner_name = Column(String(200))
    baseline = Column(Float); target = Column(Float); actual = Column(Float)
    target_date = Column(Date); measured_at = Column(Date)
    monetary_value = Column(Float)  # realised financial value to date, when known
    status = Column(String(20), default="planned")  # planned|tracking|realized|at_risk


class LessonLearned(Base):
    __tablename__ = "lessons_learned"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id")
    category = Column(String(60)); kind = Column(String(20), default="improve")  # success|improve
    title = Column(String(300), nullable=False); description = Column(Text); recommendation = Column(Text)
    created_at = Column(DateTime, default=now)


# ---------- documents & knowledge ----------
class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False, index=True)
    name = Column(String(300), nullable=False); doc_type = Column(String(60), default="other")
    folder = Column(String(200), default="/"); tags = Column(JSON, default=list)
    language = Column(String(5)); confidentiality = Column(Integer, default=1)
    access_roles = Column(JSON, default=list)  # non-empty = only these role keys (+ uploader)
    current_version = Column(Integer, default=1)
    approval_status = Column(String(20), default="draft")  # draft|approved|superseded
    doc_date = Column(Date)  # date of the content, not of the upload
    processing_status = Column(String(20), default="pending")
    processing_error = Column(Text)
    pages = Column(Integer, default=0)
    uploaded_by = OptFK("users.id"); upload_date = Column(DateTime, default=now)
    embedding_model = Column(String(60)); last_indexed = Column(DateTime)
    source_tag = Column(String(20), default="user")
    versions = relationship("DocumentVersion", cascade="all, delete-orphan", lazy="selectin",
                            order_by="DocumentVersion.version")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id = Column(Integer, primary_key=True)
    document_id = FK("documents.id", nullable=False)
    version = Column(Integer, nullable=False)
    filename = Column(String(300)); storage_path = Column(String(500))
    sha256 = Column(String(64)); size = Column(Integer)
    uploaded_by = OptFK("users.id"); uploaded_at = Column(DateTime, default=now)
    note = Column(String(300))


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    document_id = FK("documents.id", nullable=False)
    version = Column(Integer, nullable=False)
    ordinal = Column(Integer); page = Column(Integer); section = Column(String(300))
    kind = Column(String(20), default="text")  # text|table
    text = Column(Text, nullable=False)
    context = Column(String(400))  # contextual-retrieval prefix (doc + section)
    flagged = Column(Boolean, default=False)  # prompt-injection suspicion
    __table_args__ = (Index("ix_chunk_project_doc", "project_id", "document_id", "version"),)


class Embedding(Base):
    __tablename__ = "embeddings"
    id = Column(Integer, primary_key=True)
    chunk_id = FK("document_chunks.id", nullable=False, unique=True)
    project_id = FK("projects.id", nullable=False, index=True)
    model = Column(String(60)); vector = Column(LargeBinary)


class DocumentConflict(Base):
    __tablename__ = "document_conflicts"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id", nullable=False)
    conflict_type = Column(String(40))
    doc_a_id = FK("documents.id"); doc_b_id = FK("documents.id")
    value_a = Column(String(400)); value_b = Column(String(400))
    source_a = Column(JSON); source_b = Column(JSON)
    severity = Column(String(20)); recommendation = Column(Text)
    review_status = Column(String(20), default="open")  # open|accepted_a|accepted_b|dismissed
    created_at = Column(DateTime, default=now)


class ProjectConversation(Base):
    __tablename__ = "project_conversations"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id")  # NULL = platform Copilot conversation
    user_id = FK("users.id", nullable=False)
    title = Column(String(300), default="")
    scope = Column(JSON, default=dict)
    created_at = Column(DateTime, default=now)
    messages = relationship("ConversationMessage", cascade="all, delete-orphan",
                            order_by="ConversationMessage.id", lazy="selectin")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id = Column(Integer, primary_key=True)
    conversation_id = FK("project_conversations.id", nullable=False)
    role = Column(String(12)); content = Column(Text)
    blocks = Column(JSON, default=list); citations = Column(JSON, default=list)
    created_at = Column(DateTime, default=now)


# ---------- governance, workflow, automation ----------
class GovernanceItem(Base):
    __tablename__ = "governance_items"
    id = Column(Integer, primary_key=True)
    kind = Column(String(30), nullable=False)  # policy|methodology|template|committee|exception|quality_review
    title = Column(String(300), nullable=False); body = Column(Text)
    owner_name = Column(String(200)); status = Column(String(20), default="active")
    project_id = FK("projects.id")
    updated_at = Column(DateTime, default=now)


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    id = Column(Integer, primary_key=True)
    key = Column(String(60), unique=True); name_ar = Column(String(200)); name_en = Column(String(200))
    steps = Column(JSON, default=list)  # [{name_ar,name_en,approver_role,sets_stage,sla_days}]
    is_active = Column(Boolean, default=True)


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"
    id = Column(Integer, primary_key=True)
    definition_id = FK("workflow_definitions.id", nullable=False)
    project_id = FK("projects.id")
    current_step = Column(Integer, default=0)
    status = Column(String(20), default="running")  # running|completed|rejected
    started_by = OptFK("users.id"); started_at = Column(DateTime, default=now)
    completed_at = Column(DateTime); history = Column(JSON, default=list)


class Approval(Base):
    __tablename__ = "approvals"
    id = Column(Integer, primary_key=True)
    instance_id = FK("workflow_instances.id")
    project_id = FK("projects.id")
    step_index = Column(Integer, default=0); title = Column(String(300))
    approver_role = Column(String(60)); decided_by = OptFK("users.id")
    status = Column(String(20), default="pending")  # pending|approved|rejected
    note = Column(Text); requested_at = Column(DateTime, default=now)
    due_date = Column(Date); decided_at = Column(DateTime)


class AlertRule(Base):
    __tablename__ = "alert_rules"
    id = Column(Integer, primary_key=True)
    key = Column(String(60), unique=True); category = Column(String(20))
    name_ar = Column(String(200)); name_en = Column(String(200))
    severity = Column(String(20), default="warning")
    threshold = Column(Float); enabled = Column(Boolean, default=True)
    recipient_roles = Column(JSON, default=list); channels = Column(JSON, default=list)
    escalate_after_days = Column(Integer, default=0); escalate_to_role = Column(String(60))


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    project_id = FK("projects.id")
    rule_key = Column(String(60)); category = Column(String(20)); severity = Column(String(20))
    title_ar = Column(String(400)); title_en = Column(String(400))
    recommendation_ar = Column(Text); recommendation_en = Column(Text)
    entity_type = Column(String(40)); entity_id = Column(Integer)
    dedupe_key = Column(String(200), index=True)
    status = Column(String(20), default="open")  # open|acknowledged|resolved
    escalated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now); resolved_at = Column(DateTime)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = FK("users.id", nullable=False)
    project_id = FK("projects.id"); alert_id = FK("alerts.id")
    title = Column(String(400)); body = Column(Text); severity = Column(String(20), default="informational")
    channel = Column(String(20), default="in_app"); is_read = Column(Boolean, default=False)
    link = Column(String(300)); created_at = Column(DateTime, default=now)


class AutomationRule(Base):
    __tablename__ = "automation_rules"
    id = Column(Integer, primary_key=True)
    name_ar = Column(String(300)); name_en = Column(String(300))
    trigger_type = Column(String(20), default="event")  # event|schedule|rule|ai|manual
    event = Column(String(60)); schedule = Column(String(20))  # hourly|daily|weekly
    conditions = Column(JSON, default=list)  # [{field, op, value}]
    actions = Column(JSON, default=list)  # [{type, ...params}]
    enabled = Column(Boolean, default=True); last_run_at = Column(DateTime)


class AutomationRun(Base):
    __tablename__ = "automation_runs"
    id = Column(Integer, primary_key=True)
    rule_id = FK("automation_rules.id", nullable=False)
    project_id = FK("projects.id")
    trigger = Column(String(80)); status = Column(String(20))  # success|failed|skipped
    result = Column(Text); error = Column(Text)
    started_at = Column(DateTime, default=now); finished_at = Column(DateTime)


class ReportSchedule(Base):
    __tablename__ = "report_schedules"
    id = Column(Integer, primary_key=True)
    report_type = Column(String(40)); project_id = FK("projects.id"); portfolio_id = OptFK("portfolios.id")
    frequency = Column(String(20), default="weekly"); fmt = Column(String(10), default="pdf")
    lang = Column(String(5), default="ar"); recipient_roles = Column(JSON, default=list)
    enabled = Column(Boolean, default=True); last_run_at = Column(DateTime)
    created_by = OptFK("users.id")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = OptFK("users.id"); user_email = Column(String(200))
    action = Column(String(60), nullable=False); entity_type = Column(String(60)); entity_id = Column(Integer)
    project_id = Column(Integer, index=True)
    detail = Column(JSON, default=dict); ip = Column(String(60))
    created_at = Column(DateTime, default=now, index=True)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(60), primary_key=True)
    value = Column(JSON)
