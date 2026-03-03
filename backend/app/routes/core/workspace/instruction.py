import json
import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter
from fastapi import Body
from fastapi import HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel
from pydantic import Field
from pydantic import ValidationError

from ....capabilities.core_llm.services.structured import extract as structured_extract
from ....models.workspace_blueprint import WorkspaceInstruction
from ....services.mindscape_store import MindscapeStore
from ....services.workspace_instruction_chat_merge import INSTRUCTION_FIELDS
from ....services.workspace_instruction_chat_merge import merge_instruction_patch
from ....services.workspace_instruction_chat_merge import normalize_instruction
from ....shared.llm_provider_helper import create_llm_provider_manager
from ....shared.llm_provider_helper import get_llm_provider_from_settings

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()

class InstructionChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class WorkspaceInstructionInput(BaseModel):
    persona: Optional[str] = Field(None, max_length=500)
    goals: List[str] = Field(default_factory=list)
    anti_goals: List[str] = Field(default_factory=list)
    style_rules: List[str] = Field(default_factory=list)
    domain_context: Optional[str] = Field(None, max_length=2000)

    model_config = {"extra": "forbid"}


class WorkspaceInstructionPatch(BaseModel):
    # Optional + exclude_unset allows omitted=no-change semantics.
    persona: Optional[str] = Field(default=None, max_length=500)
    goals: Optional[List[str]] = Field(default=None)
    anti_goals: Optional[List[str]] = Field(default=None)
    style_rules: Optional[List[str]] = Field(default=None)
    domain_context: Optional[str] = Field(default=None, max_length=2000)

    model_config = {"extra": "forbid"}


class InstructionAssistantOutput(BaseModel):
    assistant_message: str = Field(..., min_length=1, max_length=4000)
    patch: WorkspaceInstructionPatch = Field(default_factory=WorkspaceInstructionPatch)

    model_config = {"extra": "ignore"}


class InstructionChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: List[InstructionChatMessage] = Field(default_factory=list)
    current_instruction: Optional[WorkspaceInstructionInput] = None


class InstructionChatResponse(BaseModel):
    assistant_message: str
    patch: Dict[str, Any]
    changed_fields: List[str]
    merged_instruction: WorkspaceInstruction
    confidence: Optional[float] = None


def _build_instruction_block(instruction: Dict[str, Any]) -> str:
    parts: List[str] = []
    if instruction.get("persona"):
        parts.append(f"Persona: {instruction['persona']}")
    if instruction.get("goals"):
        parts.append(
            "Goals:\n" + "\n".join(f"  - {goal}" for goal in instruction["goals"])
        )
    if instruction.get("anti_goals"):
        parts.append(
            "Anti-goals (DO NOT):\n"
            + "\n".join(f"  - {goal}" for goal in instruction["anti_goals"])
        )
    if instruction.get("style_rules"):
        parts.append(
            "Style:\n"
            + "\n".join(f"  - {rule}" for rule in instruction["style_rules"])
        )
    if instruction.get("domain_context"):
        parts.append(f"Domain context:\n{instruction['domain_context']}")

    if not parts:
        return "(empty)"

    return "=== Workspace Instruction ===\n" + "\n".join(parts) + "\n=== End Instruction ==="


def _build_history_block(history: List[InstructionChatMessage]) -> str:
    if not history:
        return "(none)"
    lines = []
    for msg in history[-8:]:
        role = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{role}: {msg.content}")
    return "\n".join(lines)


def _coerce_assistant_output(extracted_data: Any) -> InstructionAssistantOutput:
    if not isinstance(extracted_data, dict):
        return InstructionAssistantOutput(
            assistant_message="I analyzed your request but could not parse structured suggestions.",
            patch=WorkspaceInstructionPatch(),
        )

    candidate: Dict[str, Any] = dict(extracted_data)
    if "patch" not in candidate:
        fallback_patch = {
            key: candidate[key] for key in INSTRUCTION_FIELDS if key in candidate
        }
        candidate = {
            "assistant_message": candidate.get("assistant_message")
            or candidate.get("message")
            or "",
            "patch": fallback_patch,
        }

    if not candidate.get("assistant_message"):
        candidate["assistant_message"] = (
            "I analyzed your request and prepared editable instruction suggestions."
        )

    try:
        return InstructionAssistantOutput.model_validate(candidate)
    except ValidationError:
        logger.warning("Instruction chat: invalid structured output, falling back.")
        return InstructionAssistantOutput(
            assistant_message=str(candidate.get("assistant_message") or "")[:4000]
            or "I analyzed your request but could not parse structured suggestions.",
            patch=WorkspaceInstructionPatch(),
        )


@router.post(
    "/{workspace_id}/instruction/chat",
    response_model=InstructionChatResponse,
)
async def chat_workspace_instruction(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: InstructionChatRequest = Body(...),
):
    workspace = await store.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if request.current_instruction is not None:
        current_instruction = normalize_instruction(request.current_instruction)
    else:
        workspace_instruction = None
        if getattr(workspace, "workspace_blueprint", None):
            workspace_instruction = getattr(workspace.workspace_blueprint, "instruction", None)
        current_instruction = normalize_instruction(workspace_instruction)

    try:
        llm_manager = create_llm_provider_manager()
        llm_provider = get_llm_provider_from_settings(llm_manager)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    schema_json = json.dumps(
        InstructionAssistantOutput.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )
    schema_description = f"""Return JSON that matches this JSON Schema:
{schema_json}

Patch rules:
1. Put editable changes in "patch".
2. Omit a field in patch when you want no change.
3. Use null to clear scalar fields.
4. Use [] to clear list fields.
5. Keep assistant_message concise and actionable.
"""

    prompt_text = f"""You are an AI instruction assistant for workspace system prompts.
Your task is to suggest precise edits to the workspace instruction.

Current instruction:
{_build_instruction_block(current_instruction)}

Recent conversation:
{_build_history_block(request.history)}

Latest user request:
{request.message}

Generate a concise assistant message and a structured patch.
"""

    confidence: Optional[float] = None
    try:
        result = await structured_extract(
            text=prompt_text,
            schema_description=schema_description,
            llm_provider=llm_provider,
            target_language=getattr(workspace, "default_locale", None) or "zh-TW",
        )
        assistant_output = _coerce_assistant_output(result.get("extracted_data"))
        confidence_value = result.get("confidence")
        if isinstance(confidence_value, (int, float)):
            confidence = float(confidence_value)
    except Exception as exc:
        logger.error("Instruction chat generation failed: %s", exc, exc_info=True)
        assistant_output = InstructionAssistantOutput(
            assistant_message=(
                "I could not generate instruction suggestions right now. "
                "Please try again in a moment."
            ),
            patch=WorkspaceInstructionPatch(),
        )

    patch_dict = assistant_output.patch.model_dump(exclude_unset=True)
    merged_instruction_dict, changed_fields = merge_instruction_patch(
        current_instruction, patch_dict
    )
    merged_instruction = WorkspaceInstruction.model_validate(merged_instruction_dict)

    return InstructionChatResponse(
        assistant_message=assistant_output.assistant_message,
        patch=patch_dict,
        changed_fields=changed_fields,
        merged_instruction=merged_instruction,
        confidence=confidence,
    )
