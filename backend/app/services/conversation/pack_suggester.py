"""
Pack Suggester

Suggests relevant packs based on user message content using keyword matching.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class PackSuggester:
    """Suggests relevant packs based on user message content"""

    def __init__(self):
        """Initialize PackSuggester with keyword mappings"""
        self.keyword_mappings = {
            "storyboard": [
                "storyboard", "分鏡", "拍攝", "影片", "視頻", "video",
                "shot", "scene", "鏡頭", "cinematography", "film",
                "教學腳本", "教学脚本", "腳本", "脚本", "逐字稿", "講稿",
                "故事板", "畫面", "画面", "鏡頭", "镜头", "拍攝腳本", "拍摄脚本",
                "教學編劇", "教学编剧", "導演", "导演"
            ],
            "daily_planning": [
                "規劃", "計劃", "任務", "待辦", "plan", "task", "todo",
                "schedule", "planning", "長期", "long-term", "目標", "goal",
                "專案管理", "项目管理", "時間線", "时间线", "檢查清單", "检查清单",
                "準備清單", "准备清单", "任務列表", "任务列表", "pm", "pm團隊",
                "開課專案", "开课项目", "課程pm", "课程pm"
            ],
            "content_drafting": [
                "草稿", "總結", "文章", "draft", "summary", "article",
                "blog", "寫", "寫作", "writing", "content",
                "課程設計", "课程设计", "課程規劃", "课程规划", "課程流程", "课程流程",
                "教學設計", "教学设计", "課程企劃", "课程企划", "課程顧問", "课程顾问",
                "流程設計", "流程设计"
            ],
            "semantic_seeds": [
                "提取", "意圖", "主題", "extract", "intent", "theme",
                "seed", "文件", "document", "file"
            ],
            "habit_learning": [
                "習慣", "habit", "學習", "learn", "行為", "behavior",
                "執行教練", "执行教练", "習慣與執行", "习惯与执行",
                "持續推進", "持续推进", "長期經營", "长期经营",
                "行為教練", "行为教练", "最低可行版本", "檢視與調整", "检视与调整"
            ]
        }

    def suggest_packs(
        self,
        message: str,
        available_packs: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Suggest relevant packs based on message content

        Args:
            message: User message text
            available_packs: List of available pack IDs

        Returns:
            List of suggestion dictionaries containing pack_id, reason, confidence
        """
        message_lower = message.lower()
        suggestions = []

        for pack_id, keywords in self.keyword_mappings.items():
            if pack_id not in available_packs:
                continue

            matched_keywords = [
                kw for kw in keywords
                if kw.lower() in message_lower
            ]

            if matched_keywords:
                confidence = min(0.9, 0.5 + (len(matched_keywords) * 0.1))
                suggestions.append({
                    'pack_id': pack_id,
                    'reason': f"Message contains keywords: {', '.join(matched_keywords[:3])}",
                    'confidence': confidence,
                    'matched_keywords': matched_keywords
                })

        suggestions.sort(key=lambda x: x['confidence'], reverse=True)

        logger.info(f"Suggested {len(suggestions)} packs for message: {message[:50]}...")
        return suggestions

    def _keyword_based_suggestion(
        self,
        message: str,
        packs: List[str]
    ) -> List[str]:
        """
        Keyword-based pack suggestion

        Args:
            message: User message text
            packs: List of available pack IDs

        Returns:
            List of suggested pack IDs
        """
        suggestions = self.suggest_packs(message, packs)
        return [s['pack_id'] for s in suggestions]
