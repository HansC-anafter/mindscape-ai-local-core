"""
Compile Target Plugins for Mind-Lens unified implementation.

Different compile targets for different output interfaces:
- COPY: Text/copy writing
- VISUAL: Visual design
- LAYOUT: Layout/structure
- NARRATIVE: Storytelling
- CODE: Code generation
"""
from .base import CompileTargetPlugin, CompileTarget
from .copy import CopyCompileTarget
from .visual import VisualCompileTarget

__all__ = [
    'CompileTargetPlugin',
    'CompileTarget',
    'CopyCompileTarget',
    'VisualCompileTarget',
]

