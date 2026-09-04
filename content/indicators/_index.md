---
title: "Indicators"
---

Indicator families and weights driving the Bubble Risk Score.

| Indicator | Code | Category | Weight | Unit | Active | Bubble Direction | Description |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Accelerator Inventory & Lead Times | CHIP_INVENTORY | Semiconductor Supply | 8 | USD / weeks | ✓ | Higher = Riskier | Finished-goods inventory, work-in-process, lead times and channel conditions for AI accelerators. |
| Private AI Valuation & Funding | PRIVATE_VALUATION | Private Markets | 6 | USD / multiple | ✓ | Higher = Riskier | Private-company valuation multiples, funding pace and financing terms relative to revenue and economics. |
| Power & Project Constraints | POWER_PROJECTS | Power & Construction | 8 | GW / project count | ✓ | Contextual | Interconnection queues, project delays/cancellations and power availability affecting AI data-center buildout. |
| Frontier Model Revenue Growth | MODEL_REVENUE | Model Economics | 10 | USD / growth % | ✓ | Lower = Riskier | Revenue and annualized run-rate growth of leading frontier model providers relative to compute commitments. |
| Hyperscaler AI Capex | HYPER_CAPEX | Hyperscaler Capex | 12 | USD / growth % | ✓ | Contextual | Aggregate and company-level capital expenditure by major cloud hyperscalers, with emphasis on AI infrastructure guidance. |
| H100/B200 Rental Pricing | GPU_RENTAL | GPU Market | 12 | USD/GPU-hour | ✓ | Lower = Riskier | Observable cloud and specialty-provider accelerator rental pricing as a proxy for scarcity, utilization and commoditization. |
| Enterprise AI Scaling & ROI | ENTERPRISE_ROI | Enterprise ROI | 14 | % adoption / ROI | ✓ | Lower = Riskier | Share of enterprises scaling AI and evidence of measurable returns from deployments. |
| Neocloud Credit Stress | NEOCLOUD_CREDIT | Credit | 18 | bps / leverage | ✓ | Higher = Riskier | Credit spreads, CDS, debt terms, refinancing conditions and maturity mismatch for GPU clouds and AI infrastructure borrowers. |
| Nvidia Data Center Revenue Growth | NVDA_DC_YOY | Accelerators | 12 | % YoY | ✓ | Lower = Riskier | Year-over-year growth in Nvidia Data Center revenue; rapid deceleration can indicate weakening accelerator demand. |
