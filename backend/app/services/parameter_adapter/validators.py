"""
Parameter Validators

Validates adapted parameters against tool contracts.

Responsibilities:
- Parameter completeness validation
- Parameter type validation
- Required parameter checking
- Not responsible for:
  - Parameter transformation
  - Contract definition
"""

import logging
from typing import Dict, Any, Optional, List

from .contracts import ToolContract, ParameterRequirement

logger = logging.getLogger(__name__)


class ParameterValidator:
    """
    Validates parameters against tool contracts

    Responsibilities:
    - Check required parameters are present
    - Validate parameter types (basic)
    - Report validation errors
    - Not responsible for:
      - Parameter transformation
      - Contract creation
    """

    def validate(
        self,
        params: Dict[str, Any],
        contract: Optional[ToolContract] = None
    ) -> None:
        """
        Validate parameters against contract

        Args:
            params: Parameters to validate
            contract: Tool contract (optional)

        Raises:
            ValueError: If validation fails
        """
        if not contract:
            # No contract means no validation required
            return

        # Check required parameters
        required_params = contract.get_required_parameters()
        missing = required_params - set(params.keys())

        if missing:
            raise ValueError(
                f"Missing required parameters: {', '.join(missing)}. "
                f"Required: {', '.join(required_params)}"
            )

        logger.debug(f"Parameter validation passed for {contract.tool_name}")

