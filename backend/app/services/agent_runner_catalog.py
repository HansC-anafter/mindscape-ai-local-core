"""Agent catalog helpers for the agent runner facade."""

from typing import Any, Dict, List, Optional


def get_available_agents() -> List[Dict[str, Any]]:
    """Get list of available agent types."""
    return [
        {
            "type": "planner",
            "name": "Project Planner",
            "description": "Helps break down goals into actionable plans",
            "category": "planning",
        },
        {
            "type": "writer",
            "name": "Content Writer",
            "description": "Creates compelling written content and visual designs",
            "category": "content_creator",
        },
        {
            "type": "coach",
            "name": "Personal Coach",
            "description": "Provides guidance and motivation",
            "category": "coaching",
        },
        {
            "type": "coder",
            "name": "Code Assistant",
            "description": "Helps with programming tasks",
            "category": "development",
        },
        {
            "type": "visual_design_partner",
            "name": "視覺設計夥伴",
            "description": "幫你把想法變成視覺素材，從社群貼文到行銷海報，自動生成多尺寸設計",
            "category": "content_creator",
            "icon": "🎨",
            "subtitle": "從文案到設計，一鍵生成多平台視覺素材",
        },
    ]


def get_agent_detail(agent_type: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific agent type."""
    agents = get_available_agents()
    agent_info = next((agent for agent in agents if agent["type"] == agent_type), None)

    if not agent_info:
        return None

    if agent_type == "visual_design_partner":
        agent_info["ai_team"] = {
            "description": "這個成員背後有一支專業的 AI 小隊，協同完成從文案到設計的完整流程",
            "teams": [
                {
                    "name": "內容組",
                    "members": [
                        {
                            "role": "文案生成師",
                            "capability": "content_drafting.generate",
                            "description": "從 Campaign Brief 生成標題、副標、要點等文案內容",
                        },
                        {
                            "role": "內容結構化專家",
                            "description": "將文案解析為設計元素（標題、副標、CTA）",
                        },
                    ],
                },
                {
                    "name": "設計組",
                    "members": [
                        {
                            "role": "模板搜尋師",
                            "tool": "canva.list_templates",
                            "description": "根據需求推薦合適的 Canva 模板",
                        },
                        {
                            "role": "設計創建師",
                            "tool": "canva.create_design_from_template",
                            "description": "從模板創建設計",
                        },
                        {
                            "role": "文字更新師",
                            "tool": "canva.update_text_blocks",
                            "description": "將文案填入設計模板",
                        },
                        {
                            "role": "多尺寸生成師",
                            "description": "自動生成 Instagram、Facebook、Banner 等多種尺寸變體",
                        },
                        {
                            "role": "資產匯出師",
                            "tool": "canva.export_design",
                            "description": "匯出最終設計檔案",
                        },
                    ],
                },
            ],
            "workflow": [
                "讀取 Campaign Brief（從 Intent）",
                "生成文案內容（使用 content_drafting.generate）",
                "解析文案為設計元素",
                "搜尋並選擇 Canva 模板",
                "創建設計並更新文字",
                "生成多尺寸變體",
                "匯出設計資產",
            ],
            "use_cases": [
                "社群媒體貼文設計",
                "行銷活動海報",
                "產品宣傳素材",
                "簡報視覺化",
                "多平台素材批量生成",
            ],
            "related_playbooks": [
                {
                    "code": "campaign_asset_playbook",
                    "name": "Campaign Asset Generator",
                    "description": "從 Campaign Brief 生成設計資產",
                }
            ],
        }

    return agent_info
