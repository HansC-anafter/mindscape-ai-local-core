"""Shared dependencies for habit learning routes."""

from backend.app.services.habit_store import HabitStore
from backend.app.services.mindscape_store import MindscapeStore

habit_store = HabitStore()
mindscape_store = MindscapeStore()
