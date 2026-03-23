"""
Application bootstrap package.

Do not eagerly import lifecycle/route modules here. Submodule callers import the
exact bootstrap piece they need, and re-exporting them here forces heavyweight
startup dependencies to load much earlier than necessary.
"""
