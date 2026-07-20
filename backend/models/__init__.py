"""Model registry for the CarbonLab OPC migration scope.

Importing this package registers the selected SQLAlchemy models with
``Base.metadata`` for Alembic autogeneration and local test setup.
"""

from backend.models.activity_data import ActivityData
from backend.models.ai_os import ContextPackRecord, WorkflowInstance, WorkflowStep
from backend.models.cbam import CBAMReport, EmbeddedEmission, Product
from backend.models.cbam_ledger import (
    CBAMProduct,
    CarbonPricePaidEvidence,
    Installation,
    PrecursorConsumption,
    ProductionOutput,
    ProductionProcess,
    SEEResult,
    SourceStreamAttribution,
)
from backend.models.document import DocumentStore
from backend.models.emission_factor import EmissionFactor
from backend.models.emission_result import EmissionResult
from backend.models.emission_source import EmissionSource
from backend.models.enterprise import Enterprise
from backend.models.installation_passport import (
    DataSharingGrant,
    DataSharingRevocation,
    InstallationAccount,
    InstallationAccountMember,
    InstallationProfileVersion,
    MethodologyReview,
    ProfileDistributionEvent,
)
from backend.models.refresh_token_session import RefreshTokenSession
from backend.models.rule_record import RuleRecord
from backend.models.site import Site
from backend.models.tenant import Tenant
from backend.models.user import User

__all__ = [name for name in globals() if not name.startswith("_")]
