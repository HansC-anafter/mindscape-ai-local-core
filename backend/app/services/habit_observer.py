"""
Habit Observer Service
DEPRECATED: This file has been migrated to app.capabilities.habit_learning.services.habit_observer

Please use: from app.capabilities.habit_learning.services.habit_observer import HabitObserver
"""

# Re-export for backward compatibility
from backend.app.capabilities.habit_learning.services.habit_observer import HabitObserver

__all__ = ["HabitObserver"]
