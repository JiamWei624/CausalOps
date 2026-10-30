"""Guarded structured-model integration.

The package deliberately separates model proposal from deterministic validation and
execution. A model can propose a :class:`CausalSpec`; it cannot run SQL, Python,
estimators, or reports directly.
"""

from causalops.llm.proposal import (
    DatasetSchema,
    ProposalRisk,
    ProposalStatus,
    SpecProposalResult,
    StaticStructuredModelClient,
    StructuredModelClient,
    propose_causal_spec,
)
from causalops.llm.deepseek import (
    DeepSeekConfigurationError,
    DeepSeekResponseError,
    DeepSeekStructuredModelClient,
)
from causalops.llm.schema_builder import build_dynamic_causal_spec_schema

__all__ = [
    "DatasetSchema",
    "ProposalRisk",
    "ProposalStatus",
    "SpecProposalResult",
    "StaticStructuredModelClient",
    "StructuredModelClient",
    "propose_causal_spec",
    "DeepSeekConfigurationError",
    "DeepSeekResponseError",
    "DeepSeekStructuredModelClient",
    "build_dynamic_causal_spec_schema",
]
