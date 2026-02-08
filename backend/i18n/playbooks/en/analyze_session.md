# Analyze Brewing Session

Get detailed stability metrics and performance scores for your brewing session.

## Overview

This playbook analyzes captured weight curve data to provide actionable insights about your pour-over technique.

## Analysis Includes

### Segment Detection
- **Bloom**: Initial wetting phase (typically 0-40s)
- **Main Pour**: Primary extraction (typically 40-95s)
- **Final Pour**: Finishing phase (typically 95-110s)

### Metrics Per Segment
- Average flow rate (g/s)
- Flow rate standard deviation (stability measure)
- Segment status: good / unstable / too_fast / too_slow

### Overall Score
- 0-100 score based on stability and consistency
- Letter grade: A (90+), B (80-89), C (70-79), D (60-69), F (<60)

### Deviation Detection
- Unstable flow (high stddev)
- Pauses during pour
- Flow rate outside target range

## Output

The analysis produces:
- Overall score and grade
- Per-segment metrics
- List of deviations found
- Key highlights (max 3)

## Next Steps

Run **Coach Feedback** to get friendly, actionable advice based on this analysis.
