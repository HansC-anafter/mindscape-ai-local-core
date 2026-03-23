"""
Core routes package.

Keep this module import-light. Importing concrete route modules here eagerly
pulls large parts of the backend service graph into any caller that only needs
one submodule, which can block app startup.
"""
