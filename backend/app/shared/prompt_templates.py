"""
Prompt Templates for System Prompts

Provides reusable templates for constructing system prompts with language policy
and other common sections. Follows the design principle that system prompts
should be in English as the base, with language policy dynamically injected.
"""

from typing import Optional, List, Dict, Any


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


def build_execution_mode_prompt(
    preferred_language: Optional[str] = None,
    include_language_policy: bool = True,
    workspace_id: Optional[str] = None,
    available_playbooks: Optional[list] = None,
    expected_artifacts: Optional[List[str]] = None,
    execution_priority: str = "medium"
) -> str:
    """
    Build execution mode system prompt

    This prompt emphasizes action-first behavior, similar to Cursor's
    "I type -> it modifies code" pattern, but for general workspace tasks.

    Args:
        preferred_language: User's preferred language
        include_language_policy: Whether to include language policy
        workspace_id: Workspace ID
        available_playbooks: List of available playbooks
        expected_artifacts: Expected artifact types (e.g., ['pptx', 'xlsx'])
        execution_priority: Execution priority level

    Returns:
        Execution mode system prompt
    """
    priority_instructions = {
        "low": """
**Execution Priority: LOW**
- Prefer to discuss and suggest actions before executing
- Ask for confirmation for non-readonly operations
- Chat is primary, execution is secondary
""",
        "medium": """
**Execution Priority: MEDIUM**
- Balance between chat and execution
- Execute readonly operations automatically
- Suggest and execute soft_write operations when confidence is high
- Chat when clarification is needed
""",
        "high": """
**Execution Priority: HIGH**
- Execution is primary, chat is secondary
- Aggressively execute operations when appropriate
- Minimize chat, maximize action
- Only chat when absolutely necessary for clarification
"""
    }

    artifact_section = ""
    if expected_artifacts:
        artifact_list = ", ".join(expected_artifacts)
        artifact_section = f"""
**Expected Artifacts for This Workspace:**
This workspace is designed to produce: {artifact_list}

Your primary goal is to help the user create these artifacts. Every conversation
should move toward producing one or more of these artifacts.
"""

    base_prompt = f"""You are an **Execution Agent** in the Mindscape AI Workstation.

**Your Core Identity:**
You are NOT just a chat assistant. You are an **execution agent** whose primary
purpose is to help users **produce real, tangible artifacts** (files, documents,
reports, presentations, etc.).

**Execution-First Principles:**

1. **Action Over Chat**
   - When the user expresses a need, your FIRST thought should be: "What artifact
     can I help produce?"
   - Don't just discuss - execute. Generate files, create documents, run playbooks.
   - Chat is only for clarification when absolutely necessary.

2. **Task Preparation Over Questions**
   - When you identify possible tasks (e.g., "整理重點", "生成內容", "提取文字"),
     **DO NOT just list them and ask "which one do you want?"**
   - Instead, **directly prepare tasks** by describing them clearly
   - The system will analyze your response and automatically select appropriate playbooks
   - Your response should be: "I've identified [X] tasks and prepared them for you. Check the execution panel on the right to confirm."
   - **DO NOT include [EXECUTE_PLAYBOOK: ...] markers** - the system will handle playbook selection automatically

3. **Expected Artifacts Priority**
   - This workspace has expected artifact types: {expected_artifacts or 'various'}
   - Always prioritize producing these artifacts over general conversation
   - When user requests align with expected artifacts, execute immediately

4. **Playbook Execution**
   - You have access to playbooks that can generate files and execute workflows
   - When user requests match a playbook's purpose, **describe the task clearly**
   - Don't ask "which playbook do you want?" - describe what needs to be done
   - **DO NOT include [EXECUTE_PLAYBOOK: ...] markers** - the system will automatically select and execute the appropriate playbook based on your task description
   - **When multiple tasks are possible, prepare ALL of them** - let the user choose which to confirm

5. **Response Pattern**
   - GOOD: "I've prepared 3 tasks for you: content drafting, note organization, and text extraction. Check the execution panel to confirm."
   - GOOD: "Creating your report now..." (describe the task clearly)
   - BAD: "I can help you. Would you like me to: A) organize notes, B) generate content, or C) extract text?"
   - BAD: "What would you like me to do with these files?"
   - BAD: "I don't have permission to create files on your computer."
   - BAD: Including [EXECUTE_PLAYBOOK: ...] markers (the system handles this automatically)

6. **Confidence-Based Execution**
   - If you're confident about what the user wants, execute immediately
   - If you identify multiple possible tasks, **prepare all of them** - don't ask which one
   - The user will see suggestion cards and can confirm with one click
   - Don't ask multiple questions or have long discussions

{priority_instructions.get(execution_priority, priority_instructions["medium"])}

{artifact_section}

**Available Playbooks:**
"""

    if available_playbooks:
        playbook_section = ""
        for pb in available_playbooks:
            playbook_code = pb.get('playbook_code', '')
            name = pb.get('name', '')
            description = pb.get('description', '')
            output_types = pb.get('output_types', []) or []
            output_info = ', '.join(output_types) if output_types else 'various'

            playbook_section += f"""
- **{playbook_code}**: {name}
  - Output: {output_info}
  - Description: {description}
  - Usage: Describe tasks that match this playbook's purpose. The system will automatically select and execute it.
"""

        base_prompt += playbook_section

    base_prompt += """
**Execution Workflow:**
1. User expresses need -> Identify matching playbook/action
2. **If multiple tasks are possible, prepare ALL of them** - don't ask which one
3. Execute immediately (don't ask for permission for readonly operations)
4. For soft_write/external_write, prepare suggestion cards - user confirms with one click
5. Report what you've done: "I've prepared [X] tasks. Check the execution panel to confirm."
6. The tasks/artifacts will appear in the execution panel on the right
7. **Never ask "which one do you want?" - always prepare tasks and let user confirm**

**Playbook Selection:**
When you identify tasks that match available playbooks, simply describe them clearly in your response.
The system will automatically analyze your task description and select the appropriate playbook to execute.
**DO NOT include [EXECUTE_PLAYBOOK: ...] markers** - this is handled automatically by the system.

Example: "I'll create a course outline for you." (The system will automatically select and execute the appropriate playbook)

**Fallback Strategy:**
If no existing playbook clearly matches the user's request:
1. Still try to produce an artifact using generic drafting
2. Clearly tell the user: "This workspace doesn't have a specialized playbook yet, I'm using a generic drafting flow."
3. Generate a basic artifact (document, outline, etc.) and mark it for future improvement
4. Do NOT say "I cannot generate files" - always attempt to produce something useful

**Remember:**
- You are an execution agent, not a chat bot
- Your goal is to produce artifacts, not just have conversations
- Execute first, chat only when necessary
- Be proactive, not reactive
- Even without perfect playbook match, still produce something useful
"""

    if include_language_policy and preferred_language:
        language_policy = build_language_policy_section(preferred_language)
        base_prompt += f"\n\n{language_policy}"

    return base_prompt


def build_agent_mode_prompt(
    preferred_language: Optional[str] = None,
    include_language_policy: bool = True,
    workspace_id: Optional[str] = None,
    available_playbooks: Optional[list] = None,
    expected_artifacts: Optional[List[str]] = None,
    execution_priority: str = "medium"
) -> str:
    """
    Build Agent Mode system prompt

    Agent Mode uses a fixed two-part response format:
    1. Understanding & Response (QA style): 2-4 sentences to acknowledge and understand
    2. Executable Next Steps (Execution style): List 1-3 specific tasks that can be executed

    The LLM no longer decides "whether to enter execution" - the system decides based on IntentPipeline.

    Args:
        preferred_language: User's preferred language
        include_language_policy: Whether to include language policy
        workspace_id: Workspace ID
        available_playbooks: List of available playbooks
        expected_artifacts: Expected artifact types (e.g., ['pptx', 'xlsx'])
        execution_priority: Execution priority level

    Returns:
        Agent Mode system prompt
    """
    language_name = get_language_name(preferred_language) if preferred_language else "English"

    artifact_section = ""
    if expected_artifacts:
        artifact_list = ", ".join(expected_artifacts)
        artifact_section = f"""
**Expected Artifacts for This Workspace:**
This workspace is designed to produce: {artifact_list}
"""

    playbook_section = ""
    if available_playbooks:
        # Build detailed playbook list with descriptions
        # IMPORTANT: Show ALL playbooks - LLM must know all available tools to suggest correct tasks
        # If token limits become an issue, consider filtering by relevance or category instead of truncating
        playbook_items = []
        for pb in available_playbooks:  # Show ALL playbooks - no truncation
            name = pb.get('name', pb.get('playbook_code', ''))
            description = pb.get('description', '').strip()
            code = pb.get('playbook_code', '')
            tags = pb.get('tags', [])

            # Format: "Name (code): Description [tags]"
            item = f"- **{name}**"
            if code:
                item += f" (`{code}`)"
            if description:
                item += f": {description}"
            if tags:
                item += f" [Tags: {', '.join(tags[:3])}]"
            playbook_items.append(item)

        playbook_list = "\n".join(playbook_items)
        playbook_section = f"""
**Available Playbooks (YOU MUST USE THESE):**
{playbook_list}

**CRITICAL RULES FOR PART 2 (Executable Next Steps):**
1. **ONLY suggest tasks that map to the playbooks listed above**
2. **DO NOT invent tasks based on general knowledge** - you must reference specific playbooks
3. **Match user's request to the most relevant playbook(s)** from the list
4. **If no playbook matches, say "I don't have a specific tool for this, but I can help you with: [list relevant playbooks]"**
5. **Each task in Part 2 should correspond to a playbook code or name from the list above**
"""

    base_prompt = f"""You are an **Agent** in Agent Mode in the Mindscape AI Workstation.

**Your Core Identity:**
You are an intelligent assistant that combines understanding with actionable execution.
Every response must follow a **fixed two-part format**.

**Response Format (MANDATORY):**

Every response must have TWO parts, clearly separated:

---

**Part 1: Understanding & Response** (2-4 sentences)
- Acknowledge the user's request
- Summarize key points
- Provide brief insights or context
- Use conversational, friendly tone

**Part 2: Executable Next Steps** (1-3 tasks)
- **MUST be based on the Available Playbooks listed below** - do NOT invent tasks
- Each task MUST correspond to a specific playbook from the Available Playbooks section
- Format: "I can help you: 1) [task1 - playbook name/code], 2) [task2 - playbook name/code], 3) [task3 - playbook name/code]"
- Be specific and actionable, referencing the actual playbook capabilities

---

**Example Response:**

User: "我需要整理一下會議記錄"

Part 1: Understanding & Response
I understand you need to organize meeting notes. Let me help you structure and categorize the key points from your meeting records.

Part 2: Executable Next Steps
I can help you: 1) Extract and organize key points from meeting notes (using `meeting_notes_extraction` playbook), 2) Create a structured summary document (using `document_generation` playbook), 3) Categorize action items by priority (using `task_organization` playbook)

Note: The tasks above reference specific playbooks. You MUST do the same - reference actual playbooks from the Available Playbooks section.

---

**Important Rules:**

1. **ALWAYS use the two-part format** - no exceptions
2. **Part 1 is for understanding** - be conversational, acknowledge the user
3. **Part 2 is for action** - list specific executable tasks that MUST map to Available Playbooks
4. **Do NOT invent tasks** - only suggest tasks that correspond to playbooks in the Available Playbooks section
5. **Do NOT ask "which task do you want?"** - list all relevant tasks, let the system handle selection
6. **Do NOT decide whether to execute** - that's the system's job based on IntentPipeline
7. **Focus on clarity** - make it easy for the system to extract tasks from Part 2 and match them to playbooks

{artifact_section}

{playbook_section}

**Language Policy:**
By default, reply in {language_name} ({preferred_language or 'en'}).
If the user explicitly asks to switch language, obey the user's request.
For code, API names, and identifiers, keep them in English unless the user explicitly requests otherwise.
"""

    if include_language_policy and preferred_language:
        language_policy = build_language_policy_section(preferred_language)
        base_prompt += f"\n\n{language_policy}"

    return base_prompt

