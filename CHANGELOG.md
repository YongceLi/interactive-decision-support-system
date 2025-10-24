# Changelog

All notable changes to the Interactive Decision Support System (IDSS) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## 2025-10-24

### Added

#### Interactive Elements Feature
- **Quick Replies**: 
  - Added support for clickable answer options when AI asks direct questions
- **Suggested Follow-ups**: 
  - Added contextual conversation starters (3-5 short phrases) representing user's potential next inputs
  - Examples: "Show me hybrids", "What about safety?", "Compare top 3"

#### State Management
- Added `quick_replies` field to `VehicleSearchState` (Optional[List[str]])
- Added `suggested_followups` field to `VehicleSearchState` (List[str])
- Added `AgentResponse` Pydantic model for unified structured output across modes

#### API Updates
- Updated `ChatResponse` model with `quick_replies` and `suggested_followups` fields
- Updated `/chat` endpoint to return interactive elements
- Updated `/chat/stream` endpoint to include interactive elements in complete event
- Both fields are now included in all API responses

#### Agent Improvements
- **Interview Mode**: Generates quick replies for interview questions and follow-ups for user guidance
- **Discovery Mode**: Generates both quick replies (for questions asked) and follow-ups (for exploration)
- **Analytical Mode**: Post-processes ReAct agent output to generate contextual suggestions
- **General Mode**: Generates follow-ups to guide users into productive conversation modes

#### Documentation
- Created `API_DOCUMENTATION.md` with full endpoint reference
- Added interactive elements section explaining implementation guidelines

#### Demo & Testing
- Updated `scripts/demo.py` to display quick replies and suggested follow-ups
- Updated `notebooks/test_api.ipynb` to showcase interactive elements

#### Configurations
- Added configuration and prompt templates in `idss_agent/config.py` and `config/` folder

### Changed

#### Agent Architecture Change
- Added intent classifier before entering any mode
- Detailed architecture illustration documented in README.md

#### Model Optimization
- Interview mode extraction now uses `gpt-4o-mini` instead of `gpt-4o` for cost efficiency
- Discovery mode uses `gpt-4o` for higher quality vehicle presentations
- Analytical mode uses `gpt-4o-mini` for tool execution and post-processing

#### Response Format
- All agent responses now consistently include interactive elements

#### Dependencies
- Added `PyYAML>=6.0.0` for YAML configuration parsing
- Added `Jinja2>=3.1.0` for prompt template rendering

