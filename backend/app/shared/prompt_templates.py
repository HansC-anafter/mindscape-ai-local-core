"""
Prompt Templates for System Prompts

Provides reusable templates for constructing system prompts with language policy
and other common sections. Follows the design principle that system prompts
should be in English as the base, with language policy dynamically injected.
"""

from typing import Optional


# Language name mapping for human-readable language names in prompts
_LANGUAGE_NAMES = {
    "en": "English",
    "zh-TW": "Traditional Chinese",
    "zh-CN": "Simplified Chinese",
    "ja": "Japanese",
    "ja-JP": "Japanese",
    "ko": "Korean",
    "de": "German",
    "de-DE": "German",
    "es": "Spanish",
    "es-ES": "Spanish",
    "fr": "French",
    "fr-FR": "French",
}


def get_language_name(locale: str) -> str:
    """
    Get human-readable language name for a locale code

    Args:
        locale: Locale code (e.g., "zh-TW", "en", "ja-JP")

    Returns:
        Human-readable language name (e.g., "Traditional Chinese", "English")
    """
    return _LANGUAGE_NAMES.get(locale, locale)


def build_language_policy_section(preferred_language: str) -> str:
    """
    Build language policy section for system prompt

    This section should be injected into system prompts to tell the LLM
    what language to use for responses. The policy is written in English
    (following the design principle that system prompts should be in English
    as the base), but instructs the LLM to respond in the user's preferred language.

    Args:
        preferred_language: User's preferred language (e.g., "zh-TW", "en", "ja")

    Returns:
        Language policy section string to be included in system prompt
    """
    language_name = get_language_name(preferred_language)

    return f"""[LANGUAGE_POLICY]
User's preferred language: {preferred_language} ({language_name}).

Rules:
1. By default, reply in the user's preferred language ({language_name}).
2. If the user explicitly asks to switch language (e.g., "請改用英文回答" or "Please respond in English"), obey the user's request.
3. For code, API names, and identifiers, keep them in English unless the user explicitly requests otherwise.
[/LANGUAGE_POLICY]"""


def build_workspace_context_prompt(
    preferred_language: Optional[str] = None,
    include_language_policy: bool = True,
    workspace_id: Optional[str] = None,
    available_playbooks: Optional[list] = None
) -> str:
    """
    Build workspace context system prompt

    This is the base workspace context prompt in English, with optional
    language policy injection. This replaces the hardcoded Chinese prompt
    in core_llm/services/generate.py.

    Args:
        preferred_language: User's preferred language (optional)
        include_language_policy: Whether to include language policy section
        workspace_id: Workspace ID (optional, for playbook context)
        available_playbooks: List of available playbooks with file export capabilities (optional)

    Returns:
        Complete workspace context system prompt
    """
    base_prompt = """You are an intelligent workspace assistant in the Mindscape AI Workstation that helps users manage workspaces, analyze files, and execute tasks.

**Strictly follow these principles:**

1. **Never use generic greetings**, including but not limited to:
   - "請問有什麼可以幫助您的嗎？" (How can I help you?)
   - "您好！有什麼問題我可以幫忙解答嗎？" (Hello! What questions can I help answer?)
   - "請問您需要什麼幫助嗎？" (Do you need any help?)
   - "有什麼可以幫助您的嗎？" (Is there anything I can help you with?)
   Unless the user explicitly asks you to greet them, **never** use these greetings.

2. **Must respond based on context**:
   - If the user has uploaded files, the prompt will contain file information, and you **must** respond based on the file content
   - If the user's question is unclear (e.g., just "?"), directly ask what specific help is needed, without using generic greetings
   - Responses should be specific, practical, and targeted

3. **Response format**:
   - Answer questions directly, without greeting first
   - If you see file context, briefly explain what files you see, then answer the question
   - Keep responses concise and professional

4. **File generation capabilities - Two distinct scenarios**:

   **Scenario A: User asks for a LIST of available tools**
   - Examples: "What tools can you use to generate files?" / "What file export capabilities do you have?"
   - Your response: List all available file export Playbooks from the workspace (if listed below)
   - Explain what each Playbook can generate
   - Do NOT execute any Playbook, just inform the user about available options

   **Scenario B: User wants you to ACTUALLY generate a file**
   - Examples: "Generate a file for me!" / "Output a file" / "Create a report file" / "Give me an export file"
   - Your response:
     1. Based on the conversation context, determine the most appropriate Playbook
     2. DO NOT just list options (A/B/C) or ask "which one do you want?"
     3. Instead, directly trigger the Playbook execution by including the playbook code in your response
     4. The system will automatically execute the Playbook and generate the file
     5. Reply: "I've started generating the file using [playbook_name]. The file will appear in the execution panel on the right."

   **Important rules**:
   - ❌ NEVER say: "I don't have permission to generate .pptx / .xlsx / .docx files on your computer."
   - ❌ NEVER say: "I can only provide text, I cannot actually generate files."
   - ❌ When user requests file generation, NEVER respond with "A. content_drafting B. storyboard C. core_export - which one do you want?"
   - ✅ For action requests (user wants you to generate a file), directly suggest the most appropriate Playbook and let the system execute it
   - ✅ If no file export Playbook is available, say: "This workspace currently doesn't have file export Playbooks installed, but I can help you format content that you can paste directly into Excel/PPT/Word."
"""

    # Add workspace playbook capabilities section
    playbook_capabilities_section = ""
    if available_playbooks and len(available_playbooks) > 0:
        # Filter playbooks that have file export capabilities
        file_export_playbooks = []
        for pb in available_playbooks:
            # Check if playbook has file export output types
            # Support both 'output_type' (singular) and 'output_types' (plural)
            output_type = pb.get('output_type') or ''
            output_types = pb.get('output_types', []) or []
            # Combine both into a list for checking
            all_outputs = []
            if output_type:
                all_outputs.append(output_type)
            if output_types:
                all_outputs.extend(output_types if isinstance(output_types, list) else [output_types])

            tags = pb.get('tags', []) or []
            description = pb.get('description', '') or ''
            name = pb.get('name', '') or ''

            # Check for file export indicators
            has_file_export = (
                any(ext in str(all_outputs) for ext in ['.xlsx', '.pptx', '.docx', '.pdf', '.csv']) or
                any(tag in ['file-export', 'excel', 'powerpoint', 'word', 'document'] for tag in tags) or
                any(keyword in description.lower() or keyword in name.lower()
                    for keyword in ['excel', 'powerpoint', 'ppt', 'word', 'doc', 'spreadsheet', 'presentation', 'document', 'file', 'export'])
            )

            if has_file_export:
                playbook_code = pb.get('playbook_code', '')
                # Format output info from all_outputs
                output_info_parts = [ot for ot in all_outputs if isinstance(ot, str) and (ot.startswith('.') or ot in ['.xlsx', '.pptx', '.docx', '.pdf', '.csv'])]
                output_info = ', '.join(output_info_parts) if output_info_parts else 'file'
                file_export_playbooks.append({
                    'code': playbook_code,
                    'name': name,
                    'description': description,
                    'output': output_info
                })

        if file_export_playbooks:
            playbook_capabilities_section = "\n\n### Workspace File Export Capabilities\n\n"
            playbook_capabilities_section += "You are in a Mindscape AI Workstation. This workspace has the following **file export Playbooks** installed that can directly generate files:\n\n"

            for idx, pb in enumerate(file_export_playbooks, 1):
                playbook_capabilities_section += f"{idx}. **{pb['code']}** (Output: {pb['output']})\n"
                playbook_capabilities_section += f"   - {pb['name']}: {pb['description']}\n\n"

            playbook_capabilities_section += """**Two distinct scenarios for handling file generation requests:**

**Scenario A: User asks for a LIST** (e.g., "What tools can you use to generate files?")
1. List the available file export Playbooks from the list above
2. Explain what each Playbook can generate
3. Do NOT execute any Playbook, just inform the user about available options

**Scenario B: User wants ACTION** (e.g., "Generate a file for me!" / "Output a file" / "Create a report")
1. Based on conversation context, determine the most appropriate Playbook from the list above
2. DO NOT list options (A/B/C) or ask "which one do you want?"
3. Directly suggest the most suitable Playbook (e.g., "I'll use content_drafting to generate a document for you")
4. The system will automatically execute the Playbook when you mention it in your response
5. Reply: "I've started generating the file using [playbook_name]. The file will appear in the execution panel on the right."

**Important**:
- Do NOT say you cannot generate files. You CAN generate files through these Playbooks.
- For action requests, be proactive - choose the best Playbook and execute it, don't just list options."""

    # Combine all sections
    full_prompt = base_prompt
    if playbook_capabilities_section:
        full_prompt += playbook_capabilities_section

    if include_language_policy and preferred_language:
        language_policy = build_language_policy_section(preferred_language)
        full_prompt += f"\n\n{language_policy}"

    return full_prompt


