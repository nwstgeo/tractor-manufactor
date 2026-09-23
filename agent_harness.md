# Agent Harness - Tractor Supply Chain System Design

Use this file to restore context in a clean context window. Source files live in `C:/Users/Nwstg/Documents/Default Project/`.

## 1. Operating principles (highest priority)

- It is OK to not know the answer. Always be honest about what you are unsure of rather than fabricate something.
- Correctness and honesty are more important than providing a solution or answer.
- We are collaborating; ask the user for help when unsure. Use the `question` tool to clarify.
- Evidence before synthesis: inspect files yourself before stating facts. Cite `file_path:line_number` for code.
- Verify solutions via execution where reasonable (run code, tests, sanity checks).
- Prefer editing existing files over creating new ones. Keep responses short and factual. No emojis unless asked.
- Maintain context efficiency: for context-expensive operations (searching large files for bits of information or trends, profiling the 10k-row CSV, scanning the PDFs), use `subagent` workers (`explore` for searches, `general` for multi-step analysis) and bring back only the small useful subset.

When you hit an unknown: say what you know, what you don't know, and what you need.

## 2. Source files

- `SSE Job Guide.pdf` - interview prompt. Text-extractable. Summary in Section 3.
- `Information Sources.pdf` - 2-page image-only PDF (no embedded text). Proposed solution diagram + mock UI.
- `info_source_transcript.txt` - verified transcription of `Information Sources.pdf`. Read this instead of re-rendering the PDF.
- `Senior Agentic Engineer Technical Interview Synthetic_Supply_Chain_Dataset.csv` - example dataset. 10,000 rows, 0 missing values. Schema verified 2026-09-23 (see Section 5).
- Built layout: `data/` (reference CSV, synthetic outputs, `generator/` scripts), `src/sim/` + `src/controller/` (stepping engine, scoring, policy CLI), `ui/` (stdlib server + live six-box page), `tests/` (47 green). Details in `_temp_todo.txt`.

If starting fresh and doubting the transcript, re-render: the PDF has 2 pages, 0 text chars, 2 images/page. Render with PyMuPDF then `read` the PNGs.

## 3. Interview prompt (from `SSE Job Guide.pdf`)

Design and prototype an app using LLM/ML models to optimize a tractor manufacturer's supply chain by predicting demand fluctuations, supplier delays, component failures, and recommending cost-effective inventory strategies.

Optimize = right number/type of supplies to meet demand with no excess. Stage 1 output: System Design Diagram, API Definitions, UI Mockup, Identification of models + data sources + inputs/outputs.

## 4. System design (from `info_source_transcript.txt`)

Pipeline: Info Sources -> Topic-specific General LLM Agents -> Trained Models (H/O/S/F/R).

Trained models:
- H - Hardware Failure & Material Availability & Spare Reqs. Tracks inventory, current orders, production plan, needs-assuming-no-change, weak points/bottlenecks, low-supply alternatives.
- O - Overall Demand Prediction. Forecasting order trends.
- S - Supply Limitation Prediction. Forecasting material-availability issues, alternatives for scarce materials.
- F - Forecasting Overall Market. Potential markets for expansion, issues with current markets.
- R - Recommendation Synthesis. Combines H+O+S+F into H's demand requests; suggests new/changed markets or design based on H,S,F.

Mock UI (Page 2), each box labeled with contributing model(s):
- Customers Orders Table - H
- 3 month Forecast of Orders - O&F (R) [source spells "Forecastt"]
- Action Items to do - R
- Proposed Orders to Approve - R
- Supply Inventory Table - H
- Production Schedule - H

## 5. Example dataset schema (verified)

File: `Senior Agentic Engineer Technical Interview Synthetic_Supply_Chain_Dataset.csv`

Columns (10):
- Date (YYYY-MM-DD, 1459 distinct, ~2020-01-01 to ~2023-12-31 range, unordered in file)
- Tractor_Model (5: TX-100, TX-200, TX-300, TX-400, TX-500)
- Demand_Units (int-ish string, ~100-549 observed)
- Supplier (5: Supplier A-E)
- Supplier_Delay_Days (0-29)
- Component_Failure_Rate (0.0-0.1)
- Inventory_Levels (int-ish string)
- Warehouse_Location (5: CA, FL, IL, NY, TX)
- Inflation_Rate (~1.5-~6 observed)
- Market_Trend_Index (0.0-1.0)

First row: `2023-01-31,TX-500,225,Supplier C,3,0.035,4555,IL,3.89,0.39`. No empty cells.

## 6. Goals

1. Generate a synthetic dataset for use by the application, using the example CSV as the reference for schema/distributions. Must be regenerable via Python code (seeded), documented, and validated against the reference.
2. Implement the system design from `Information Sources.pdf` using the synthetic dataset: data ingestion, H/O/S/F/R models (may start as simple/statistical baselines before LLM agents), APIs, and UI-mockup backend (the 6 UI boxes).

Do not claim to have read a file you have not called `read` on in the current session.
