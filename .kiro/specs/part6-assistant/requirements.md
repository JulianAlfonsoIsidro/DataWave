# Requirements Document

## Introduction

Part 6 Assistant adds a conversational AI assistant to the existing Part 5 Streamlit webapp, wired into the already-present "Ask Assistant" tab (which is currently a static placeholder). The assistant answers an analyst's natural-language questions about the current promo run and past promos by calling a small set of tools that wrap the existing Python functions; it never computes campaign numbers itself. Every number it reports comes from a tool output, and it cites which tool produced it.

The assistant uses Amazon Bedrock (via the boto3 Converse API with tool use) when AWS credentials are configured, and falls back to a fully offline Mock Mode when they are missing or the call fails, so the demo works end to end without AWS. It keeps chat history in Streamlit session state, offers clickable suggested questions, enforces data-privacy and scope guardrails, and logs each turn to `scratch/assistant_log.jsonl`. It also lets an analyst upload a campaign brief (PDF or DOCX) on the New Promo tab and pre-fills the promo form from the extracted text for review before any run. All assistant code lives in a new `src/assistant/` package; the existing app visual style (Poppins, red gradient, rounded cards, Title Case) is preserved.

All code runs under the project virtualenv (`.\.venv\Scripts\python.exe`) with `PYTHONPATH=src`; the app launches with `streamlit run app/main.py`. New Python files are saved as UTF-8 without a BOM. Any temporary output is written only under `scratch/`.

## Glossary

- **Assistant**: The system under specification. A Python package at `src/assistant/` plus the chat UI wired into the "Ask Assistant" tab of `app/main.py`.
- **Ask_Assistant_Tab**: The existing Title Case tab in `app/main.py` whose placeholder body this spec replaces with the chat UI.
- **Chat_UI**: The in-tab conversation surface built with `st.chat_message` and `st.chat_input`, with clickable suggested questions and history in session state.
- **Suggested_Question**: One of four preset, clickable example questions shown in the Chat_UI (e.g. "Why is Ready Toppers prioritized?", "What if the threshold is P300,000?", "Which segment should we skip?", "How accurate was P001?").
- **Chat_History**: The ordered list of user and assistant messages for the session, held in `st.session_state`.
- **Run_Result**: The current in-memory `RunResult` (`webapp_core.run_promo.RunResult`) stored in session state under `run_result`, carrying the current run's cards and sendable leads.
- **Tool**: One of the four functions the model may call; each wraps existing Python and reads the current Run_Result (or `outputs/` for past promos) and returns segment-level data only.
- **Get_Card_Tool**: `get_card(segment)` -- returns the decision card for one Segment_Label of the current Run_Result.
- **Compare_Segments_Tool**: `compare_segments()` -- returns all four current-run decision cards side by side.
- **What_If_Tool**: `what_if(threshold_php)` -- reruns `webapp_core.run_promo.run_promo` for the current eligible audience with a new threshold and returns the changed per-segment totals.
- **Past_Promo_Accuracy_Tool**: `past_promo_accuracy(promo_id)` -- returns predicted vs actual join rate per segment for a past promo, from `outputs/cards.json` and `data/promo_leads.csv` via `webapp_core.past_promos.predicted_vs_actual`.
- **Tool_Result**: The structured, segment-level data a Tool returns, tagged with the Tool's name so the answer can cite its source.
- **Bedrock_Mode**: The live path where the Assistant calls Amazon Bedrock via the boto3 Converse API with tool use.
- **Mock_Mode**: The offline fallback that matches a question to a Tool with keyword rules, runs it, and returns a templated answer without any AWS call.
- **Demo_Mode_Badge**: A small UI badge shown when the Assistant is answering in Mock_Mode.
- **Model_Config**: The Bedrock settings read from a `.env` file via python-dotenv: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `BEDROCK_MODEL_ID`.
- **Assistant_Log**: The append-only JSON Lines file at `scratch/assistant_log.jsonl`, one record per answered turn.
- **Segment_Label**: One of the four Part 3 labels: "Ready Toppers", "Willing but Stretched", "Untapped Wealth", "Not Now".
- **New_Promo_Tab**: The existing Title Case "New Promo" tab of `app/main.py` that holds the promo design form and its Run Analysis button.
- **Fill_In_Details_Tab**: The sub-tab of the New_Promo_Tab carrying the manual promo form (the current form body).
- **Upload_Campaign_File_Tab**: A new sub-tab beside Fill_In_Details_Tab that accepts a Campaign_File and pre-fills the promo form from it.
- **Campaign_File**: An uploaded campaign brief, either a PDF or a DOCX, from which promo form fields are extracted.
- **Campaign_Text**: The plain text extracted locally from a Campaign_File (pdfplumber for PDF, python-docx for DOCX).
- **Promo_Form_Fields**: The seven form fields the upload fills: product_type, mechanic, threshold_php, reward, eligible segments, min ADB, and channels.
- **Extracted_Fields**: The subset of Promo_Form_Fields the Assistant could read from Campaign_Text, each either Found or Needs_Input.
- **Allowed_Channel_Label**: One of the exact channel labels the app uses: "In-app", "Email", "SMS".

## Requirements

### Requirement 1: Chat UI in the Ask Assistant tab

**User Story:** As an analyst, I want a chat panel in the Ask Assistant tab with example questions, so that I can ask about the campaign in natural language and see the conversation.

#### Acceptance Criteria

1. WHEN the Ask_Assistant_Tab renders THEN the Assistant SHALL present a Chat_UI built with `st.chat_message` and `st.chat_input` that preserves the existing app style (Poppins, red gradient, rounded cards, Title Case) and shows a title and one-line description.
2. WHEN the Ask_Assistant_Tab renders THEN the Chat_UI SHALL show four clickable Suggested_Questions (including threshold, segment-priority, segment-skip, and past-promo-accuracy examples), and clicking one SHALL submit it as the next user message.
3. WHEN the user submits a question via `st.chat_input` or a Suggested_Question THEN the Assistant SHALL append the user message and the assistant's reply to Chat_History in `st.session_state` and render the full history in order on rerun.
4. WHILE no promo run exists in session state AND the question needs the current run THEN the Assistant SHALL reply that the user should run a promo first, rather than erroring.

### Requirement 2: Tools over existing functions and the current run

**User Story:** As an analyst, I want the assistant to pull real numbers from the app's own functions, so that its answers reflect the actual run and past promos rather than invented figures.

#### Acceptance Criteria

1. WHERE the Assistant answers a question THEN it SHALL obtain every campaign number from a Tool_Result and SHALL NOT compute or estimate any campaign number itself.
2. WHEN the Get_Card_Tool is called with a Segment_Label THEN it SHALL return that segment's decision card from the current Run_Result (action, dominant channel, message angle, expected joiners with its 90% range, expected value, top drivers, exclusions by reason), or a not-available result if that segment has no card.
3. WHEN the Compare_Segments_Tool is called THEN it SHALL return all four current-run decision cards together.
4. WHEN the What_If_Tool is called with a threshold THEN it SHALL rerun `webapp_core.run_promo.run_promo` for the current eligible audience with only `threshold_php` changed (no retraining) and return the resulting per-segment totals and how they changed from the current run.
5. WHEN the Past_Promo_Accuracy_Tool is called with a promo id THEN it SHALL return the predicted vs actual join rate per segment from `outputs/cards.json` and `data/promo_leads.csv` via `webapp_core.past_promos.predicted_vs_actual`.
6. WHEN the Assistant states a number in its reply THEN it SHALL cite which Tool the number came from.

### Requirement 3: Amazon Bedrock via the Converse API with tool use

**User Story:** As a developer, I want the assistant to use Amazon Bedrock with tool calling when credentials exist, so that a real model drives the conversation when configured.

#### Acceptance Criteria

1. WHERE valid Model_Config credentials are present THEN the Assistant SHALL call Amazon Bedrock through the boto3 Converse API, advertising the four Tools for tool use and executing a Tool when the model requests it.
2. WHEN the Assistant starts THEN it SHALL read `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `BEDROCK_MODEL_ID` from a `.env` file via python-dotenv, and SHALL NOT hardcode credentials in source.
3. WHEN the model returns a tool-use request THEN the Assistant SHALL run the named Tool, return its Tool_Result to the model, and let the model produce the final natural-language answer grounded in that result.
4. WHERE the `.env` file is used THEN `.env` SHALL be listed in `.gitignore` so credentials are never committed.

### Requirement 4: Mock Mode fallback that works fully offline

**User Story:** As a presenter, I want the assistant to work without AWS, so that the demo is reliable even when no credentials are configured or Bedrock is unreachable.

#### Acceptance Criteria

1. IF the Model_Config credentials are missing OR a Bedrock call raises an error THEN the Assistant SHALL answer in Mock_Mode instead of surfacing an exception.
2. WHEN answering in Mock_Mode THEN the Assistant SHALL match the question to one of the four Tools using simple keyword rules, run that Tool, and return a clear templated answer built from the Tool_Result that still cites the Tool.
3. WHILE the Assistant is answering in Mock_Mode THEN the Chat_UI SHALL show a small Demo_Mode_Badge.
4. WHEN no credentials are configured at all THEN the Assistant SHALL still answer every Suggested_Question end to end using Mock_Mode, with no AWS call attempted.

### Requirement 5: Privacy, scope, and length guardrails

**User Story:** As a compliance-minded analyst, I want the assistant to protect individual data and stay on topic, so that it is safe to use in front of stakeholders.

#### Acceptance Criteria

1. WHERE the Assistant produces any reply THEN it SHALL NOT output any `client_id` or any individual client's data, reporting only segment-level numbers.
2. IF a Tool_Result or question would expose individual client data THEN the Assistant SHALL reduce it to segment-level figures before replying.
3. IF a question is unrelated to the campaign data THEN the Assistant SHALL politely refuse and redirect to what it can answer, in both Bedrock_Mode and Mock_Mode.
4. WHEN the Assistant produces any reply THEN it SHALL keep the answer to roughly 120 words or fewer.

### Requirement 6: Per-turn logging to a JSON Lines file

**User Story:** As a developer, I want each answered turn logged, so that I can audit what was asked, which tool ran, and what was answered.

#### Acceptance Criteria

1. WHEN the Assistant answers a turn THEN it SHALL append one JSON object to `scratch/assistant_log.jsonl` recording at least the question, the Tool called (if any), the answer, and whether the turn used Bedrock_Mode or Mock_Mode.
2. WHEN a log record is written THEN it SHALL be a single line of valid JSON (JSON Lines), appended without rewriting earlier records.
3. WHERE a log record is written THEN it SHALL NOT contain any `client_id` or individual client data, consistent with the privacy guardrail.
4. WHERE the `scratch/` directory does not yet exist THEN the Assistant SHALL create it before writing, and SHALL write the log only under `scratch/`.

### Requirement 7: Campaign document upload that pre-fills the promo form

**User Story:** As an analyst, I want to upload a campaign brief and have the promo form filled in from it, so that I can set up a run quickly and still review every field before analysis.

#### Acceptance Criteria

1. WHEN the New_Promo_Tab renders THEN it SHALL present two sub-tabs, a Fill_In_Details_Tab carrying the current manual promo form and an Upload_Campaign_File_Tab beside it, preserving the existing app style (Poppins, red gradient, rounded cards, Title Case).
2. WHEN the user opens the Upload_Campaign_File_Tab THEN it SHALL accept a single Campaign_File whose type is PDF or DOCX and SHALL reject any other file type with a clear message.
3. WHEN a Campaign_File is uploaded THEN the Assistant SHALL extract Campaign_Text locally, using pdfplumber for a PDF and python-docx for a DOCX, without sending the file to any external service for extraction.
4. WHERE valid Model_Config credentials are present THEN the Assistant SHALL ask Amazon Bedrock to return strict JSON matching the Promo_Form_Fields, SHALL validate the returned JSON against the allowed field types and values, and SHALL drop any invalid or unrecognized value rather than filling it.
5. IF the Model_Config credentials are missing OR the Bedrock extraction call raises an error THEN the Assistant SHALL derive the Promo_Form_Fields from Campaign_Text in Mock_Mode using simple keyword and peso-amount rules.
6. WHEN the Assistant fills channels from a Campaign_File THEN it SHALL map each recognized channel name to exactly one Allowed_Channel_Label ("In-app", "Email", "SMS") and SHALL drop any channel name it cannot map.
7. WHEN extraction completes THEN the Assistant SHALL show the pre-filled promo form for review and editing, marking each field in Extracted_Fields as Found or Needs_Input, and the user SHALL be able to edit any field before running.
8. WHERE the promo form was pre-filled from a Campaign_File THEN the Assistant SHALL NOT start a run automatically and SHALL run only when the user presses Run Analysis.
9. WHERE the Assistant processes a Campaign_File THEN it SHALL write any temporary output only under `scratch/` and SHALL NOT output or log any individual client data from the file, consistent with the privacy guardrail.
