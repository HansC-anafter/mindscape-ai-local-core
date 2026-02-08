# Capture Brewing Session

Record weight and time data from your pour-over brewing session.

## Overview

This playbook captures the weight curve from your coffee scale during brewing. The data forms the foundation for all analysis and coaching features.

## How It Works

1. **Connect to Scale**
   - Select your scale type (Decent Scale or demo mode)
   - Ensure scale is powered on and in range

2. **Start Recording**
   - Tare the scale with your empty dripper
   - Begin your pour when ready
   - System records weight at 5Hz (200ms intervals)

3. **Complete Session**
   - Recording stops automatically when brewing appears complete
   - Or manually stop when finished

## Output

The captured session includes:
- Session ID for tracking
- Weight/time data points
- Total brewing time
- Total water weight

## Demo Mode

For practice without hardware, use the mock adapter with pre-defined curve types to simulate different brewing scenarios.

## Next Steps

After capture, run the **Analyze Session** playbook to get detailed metrics and stability scores.
