# Requirements Document

## Introduction

Part 7 adds Amazon Bedrock assistance and finishing touches to the existing DataWave Promo Audience Navigator (the Part 5 Streamlit webapp and the Part 5 personas page). It adds: a shared Bedrock client with a rule-based Demo Mode fallback; campaign file upload on New Promo; a campaign-focused Ask Assistant; plain-language decision cards; fixed-range threshold options; Bedrock-written persona names and descriptions; a clearer Expected Joiners By Persona section; an impact summary and Excel export on Results; tests and visual verification; and a smarter Past Promos tab.

Scope and constraints that apply to every requirement:

- The Part 1 model, Part 2 features, Part 3 segmentation, Part 4 card logic, and the persona clustering logic remain unchanged unless a requirement states otherwise. Part 7 adds presentation, orchestration, and AI-text layers on top of them.
- All numbers (joiners, savings, similarity scores, costs) are computed in Python. Bedrock is used only for text and structured extraction, never for numbers shown to the user.
- The app works fully without AWS. Every AI feature has a deterministic rule-based mock.
- All UI text uses Title Case for headings, labels, and buttons, and uses commas or periods instead of em dashes or double hyphens ("--").
- New UI elements reuse the existing look: the red gradient, rounded cards, and the typography already defined in `app/theme.py` and `app/styles.css`. The request names Poppins, but the repository currently defines Dax, Avenir Next, and Manrope in `app/theme.py`. Part 7 does not change the font stack unless the user confirms Poppins should replace it (open question, see Requirement 10).
- All files written are UTF-8 without a BOM.
- All Python commands run through `./.venv/bin/python` on macOS. No system Python and no global installs. Temporary files are written only under `scratch/`.
- `requirements.txt` gains `boto3`, `pdfplumber`, `python-docx`, and `openpyxl` (unpinned, matching the existing style of that file).

Repository facts these requirements build on (inspected before writing):

- `app/main.py` holds the tabs New Promo, Results, What-If, Personas, Past Promos, Ask Assistant. Ask Assistant is a placeholder. The form uses `MECHANIC_OPTIONS = TOP_UP, NEW_ACCOUNT, ADB_INCREASE, OTHER`, `PRODUCT_TYPE_OPTIONS`, and `CHANNEL_OPTIONS = In-app, Email, SMS`, with a single `threshold_php` number input.
- `src/webapp_core/` holds `run_promo.py` (`PromoSpec`, `RunResult`), `personas.py`, `past_promos.py`, `audience.py`, `model_io.py`, and `promo_id.py`. It must not import Streamlit.
- `outputs/cards.json` cards carry `top_drivers` (including `mechanic`), `excluded_by_reason`, `expected_joiners`, `joiners_90_low`, `joiners_90_high`, `expected_value`, `total_channel_cost`, `action`, and `dominant_channel`.
- `data/promo_history.csv` holds `promo_id, promo_name, product_type, mechanic, threshold_php, reward, start_date, end_date, channels`. `data/promo_leads.csv` holds `promo_id, client_id, control_group, channel_sent, joined, join_date`. `data/channel_costs.csv` holds per-message channel costs.
- `.gitignore` already lists `.env` and `scratch/`. No `.env` file or `scratch/` directory exists yet.
- Property tests for Part 7 are capped at 8 in total across the whole feature (see Requirement 10).

## Glossary

- **Webapp**: The Streamlit application rooted at `app/main.py`, including the New Promo, Results, What-If, Personas, Past Promos, and Ask Assistant tabs.
- **Bedrock_Client**: The shared module at `src/ai/bedrock.py` that calls the Amazon Bedrock Converse API through boto3.
- **AI_Feature**: Any feature that uses the Bedrock_Client: Campaign_Extractor, Campaign_Assistant, and Persona_Narrator.
- **Demo_Mode**: The state in which an AI_Feature uses its rule-based mock because credentials are missing or the Bedrock call failed, timed out, or returned invalid output. The Webapp shows a small "Demo Mode" badge in this state.
- **Mock**: The deterministic rule-based fallback implementation of an AI_Feature.
- **Privacy_Boundary**: The rule that Bedrock receives only promo fields, uploaded document text, and segment-level or persona-level aggregates. It never receives a `client_id` or any individual client row.
- **Campaign_Extractor**: The component that reads an uploaded PDF or DOCX file and returns Campaign_Fields and Campaign_Context.
- **Campaign_Fields**: The New Promo form values: product_type, mechanic, threshold type and value, reward, eligible segments, minimum ADB, and channels.
- **Campaign_Context**: Extra extracted text: objective, target audience description, offer details, timeline, and key messages. It is stored in session state for the Campaign_Assistant.
- **Field_Tag**: A per-field label on the pre-filled form, either "Found in Document" or "Needs Input".
- **Campaign_Assistant**: The chat component in the Ask Assistant tab that answers questions about the current campaign proposal.
- **Assistant_Log**: The file `scratch/assistant_log.jsonl` that records each assistant question and answer.
- **Label_Map**: The single mapping module at `src/labels.py` from feature codes and exclusion codes to plain-English phrases.
- **Decision_Card**: One Part 4 action card for a segment, rendered on Results and in live New Promo cards.
- **Threshold_Type**: One of four selectable threshold kinds: Top-Up Amount, Minimum Balance To Maintain, Balance Increase, Opening Amount For A New Account.
- **Threshold_Php**: The single peso threshold value passed to model scoring (`PromoSpec.threshold_php`).
- **ADB**: Average daily balance. `latest_adb` is the client's current average balance feature.
- **Persona_Narrator**: The component that produces a persona's name, description, difference explanation, and recommended actions from persona aggregates.
- **Persona_Aggregate**: Persona-level statistics only: size, share, averages, top distinguishing features in plain labels, and response rate.
- **Impact_Summary**: The comparison of the Recommended_Plan against the Baseline_Plan.
- **Baseline_Plan**: Messaging all eligible, non-excluded clients on their best channel.
- **Recommended_Plan**: Messaging the sendable leads in segments whose action is not Skip.
- **Export_Workbook**: The Excel file `<promo_id>_campaign_summary.xlsx` produced with openpyxl.
- **Past_Promos_Tab**: The Webapp tab showing completed historical campaigns.
- **Similarity_Score**: A deterministic 0 to 100 score comparing a historical campaign to the current New Promo form, built from eight weighted components.
- **Similarity_Component**: One of eight parts of the Similarity_Score: audience and eligibility (30%), JTBD and customer need (20%), product and mechanic (15%), offer economics (10%), duration (10%), channels (5%), objective (5%), name and summary (5%).
- **Test_Suite**: The pytest and hypothesis tests under `tests/`.

## Requirements

### Requirement 1: Shared Bedrock Client With Demo Mode Fallback

**User Story:** As an analyst, I want every AI feature to share one safe Bedrock client that falls back to rules, so that the app works with or without AWS and never leaks client data.

#### Acceptance Criteria

1. THE Bedrock_Client SHALL expose one function, in `src/ai/bedrock.py`, that every AI_Feature calls to invoke the boto3 Converse API.
2. THE Bedrock_Client SHALL read `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `BEDROCK_MODEL_ID` from the `.env` file through python-dotenv.
3. THE Webapp repository SHALL list `.env` in `.gitignore`.
4. THE Bedrock_Client SHALL apply a request timeout of 30 seconds to every Converse call and SHALL make at most 1 attempt per call with no automatic retry.
5. IF any of `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, or `BEDROCK_MODEL_ID` is missing or an empty string after trimming whitespace, THEN THE Bedrock_Client SHALL report Demo_Mode without attempting a network call.
6. IF a Converse call raises an error, exceeds the 30-second timeout, or returns a response with no text content or text that is not valid JSON where JSON was requested, THEN THE Bedrock_Client SHALL report Demo_Mode and THE calling AI_Feature SHALL return its Mock result.
7. WHILE an AI_Feature result comes from its Mock, THE Webapp SHALL show a small "Demo Mode" badge next to that result.
8. WHEN a later Converse call succeeds after an earlier call reported Demo_Mode, THE Bedrock_Client SHALL report Bedrock for that later call, so that Demo_Mode applies per call and is not latched for the session.
9. WHEN no AWS credentials are configured, THE Webapp SHALL complete every existing and new user flow using Mock results, with no unhandled exception and no error shown to the user.
10. THE Bedrock_Client SHALL accept only promo fields, uploaded document text, and segment-level or persona-level aggregates in its payload.
11. IF a payload contains a `client_id` key or value, or any list of per-client rows (one record per client), THEN THE Bedrock_Client SHALL reject the payload before any network call, report Demo_Mode, and make zero calls to boto3.
12. THE Bedrock_Client SHALL contain no pricing, scoring, or other numeric business logic, and SHALL return model text or parsed JSON to the caller unchanged.
13. THE Bedrock_Client SHALL NOT write AWS credential values to the Assistant_Log, to Webapp output, or to any error text shown to the user.

### Requirement 2: Upload Campaign File On New Promo

**User Story:** As an analyst, I want to upload a campaign proposal and have the form pre-filled, so that I do not retype details that already exist in the document.

#### Acceptance Criteria

1. THE Webapp SHALL show two tabs on New Promo named "Upload Campaign File" and "Fill In Details".
2. WHEN a user uploads a PDF or DOCX file of 10 MB or less, THE Campaign_Extractor SHALL extract the document text locally using pdfplumber for PDF and python-docx for DOCX.
3. IF the uploaded file is not a PDF or DOCX, exceeds 10 MB, cannot be read, or contains no extractable text, THEN THE Webapp SHALL show an error message indicating which of these causes applies and SHALL leave every form field and the stored session state unchanged.
4. WHEN document text is extracted, THE Campaign_Extractor SHALL request strict JSON from the Bedrock_Client containing the Campaign_Fields and the Campaign_Context, and SHALL send at most the first 30,000 characters of the document text.
5. WHEN the Campaign_Extractor receives JSON, THE Campaign_Extractor SHALL validate each Campaign_Field against the allowed values of the New Promo form (mechanic, product type, channels, Threshold_Type, and the numeric ranges defined in Requirement 5) and SHALL drop each invalid value.
6. IF the Bedrock_Client returns text that is not parseable as JSON, THEN THE Campaign_Extractor SHALL use the Mock result for the whole document.
7. THE Campaign_Extractor SHALL map extracted channels to exactly "In-app", "Email", and "SMS" and drop any channel that matches none of them.
8. WHILE the Bedrock_Client reports Demo_Mode, THE Campaign_Extractor SHALL use Mock keyword rules and peso-amount rules to extract the Campaign_Fields and the Campaign_Context, and THE Webapp SHALL show the Demo Mode badge next to the extraction result.
9. WHEN extraction completes within 60 seconds of the upload, THE Webapp SHALL show the pre-filled form with a Field_Tag on every Campaign_Field.
10. IF extraction has not completed 60 seconds after the upload, THEN THE Webapp SHALL use the Mock result for the extraction.
11. THE Webapp SHALL tag a field "Found in Document" when a valid value was extracted and "Needs Input" otherwise, and SHALL leave a "Needs Input" field empty or at its form default.
12. THE Webapp SHALL wait for an explicit user click on the existing run button before starting any analysis, and SHALL NOT run the analysis automatically after extraction.
13. WHEN extraction completes, THE Webapp SHALL store the extracted document text and the Campaign_Context in session state for the Campaign_Assistant, replacing any text and context stored from a previous upload.

### Requirement 3: Ask Assistant About The Campaign

**User Story:** As an analyst, I want to chat about my campaign proposal, so that I can check clarity, find gaps, and draft copy.

#### Acceptance Criteria

1. WHEN a user submits a question of 1 to 500 characters, THE Campaign_Assistant SHALL ground the answer on the current form fields, the uploaded document text, and the Campaign_Context, and SHALL NOT use model scores, segments, or personas as grounding.
2. THE Campaign_Assistant SHALL answer questions about the offer, mechanic, eligibility, channels, timeline, messaging, copy suggestions, compliance and clarity checks, and gaps or inconsistencies in the proposal.
3. WHEN a user asks what is missing from the proposal, THE Campaign_Assistant SHALL list each of the following that applies: a channel listed without a budget, no control group stated, and any Campaign_Field tagged "Needs Input".
4. IF a question asks about model scores, segments, or personas, THEN THE Campaign_Assistant SHALL reply with a message directing the user to the Results page or the Personas page and SHALL NOT answer from model results.
5. IF a question is unrelated to the campaign, THEN THE Campaign_Assistant SHALL reply with a message stating that it only answers questions about the current campaign proposal.
6. IF a submitted question is empty, contains only whitespace, or exceeds 500 characters, THEN THE Webapp SHALL show a message asking for a question of 1 to 500 characters, SHALL NOT call the Bedrock_Client, and SHALL NOT write to the Assistant_Log.
7. THE Campaign_Assistant SHALL limit each answer to a maximum of 150 words.
8. THE Webapp SHALL show four suggested questions labeled "Summarize This Campaign", "What's Missing From This Proposal?", "Draft An SMS For This Offer", and "Is The Eligibility Clear?", and WHEN a user clicks one, THE Campaign_Assistant SHALL treat its label as the submitted question.
9. WHILE the Bedrock_Client reports Demo_Mode, THE Campaign_Assistant SHALL return templated answers built only from the form fields and the Campaign_Context, and THE Webapp SHALL show the Demo Mode badge next to each such answer.
10. WHEN the Campaign_Assistant returns an answer, THE Campaign_Assistant SHALL append one line of valid JSON containing the question, the answer, and a timestamp to the Assistant_Log, creating `scratch/` if absent.
11. IF writing to the Assistant_Log fails, THEN THE Webapp SHALL still display the answer and SHALL show a non-blocking notice that the log was not saved.
12. WHEN no campaign form values and no uploaded document exist, THE Webapp SHALL show a prompt asking the user to fill in or upload a campaign first, and SHALL NOT call the Bedrock_Client.
13. THE Campaign_Assistant SHALL satisfy the Privacy_Boundary.

### Requirement 4: Plain-Language Decision Cards

**User Story:** As a marketer, I want decision cards in everyday words, so that I can understand each group without knowing feature codes.

#### Acceptance Criteria

1. THE Label_Map SHALL map every feature code and every exclusion code shown anywhere in the Webapp UI to a plain-English phrase, including `out_other_bank`, `ext_outflow_ratio`, `spend_share_retail`, `latest_adb`, `avg_contacts_per_month`, `digital_app_user`, `over_contacted`, `ndb`, and `no reachable channel`.
2. THE Webapp SHALL obtain every displayed feature or exclusion name from the Label_Map, and THE Part 5 personas page SHALL reuse the Label_Map for any code that it displays.
3. IF a code is missing from the Label_Map, THEN THE Label_Map SHALL return the code converted to Title Case with each underscore replaced by a single space, and THE Webapp SHALL NOT show the raw code with underscores.
4. THE Webapp SHALL omit `mechanic` and `threshold_php` from the displayed Top Drivers and show the next driver in their place, so that each Decision_Card shows up to 3 drivers when at least 3 non-omitted drivers exist.
5. THE Webapp SHALL show drivers under the heading "Why This Group:" as one phrase per driver, each phrase at most 60 characters long.
6. WHEN a Decision_Card has one or more exclusions, THE Webapp SHALL show them under the heading "Not Contacted:" with one line per reason in the form "<Plain Reason>: N", where N is a whole number of 1 or more, ordered from the highest count to the lowest and then alphabetically by plain reason.
7. IF a Decision_Card has no exclusions, THEN THE Webapp SHALL show the "Not Contacted:" heading with the text "None" or omit the heading, and SHALL show the same choice on every card.
8. THE Webapp SHALL replace the stat chips with "About N Likely To Join", "Likely Range: L To H", and "Expected Value: ₱V", where N, L, and H are whole numbers rounded to the nearest integer (halves rounded up), L is less than or equal to N, N is less than or equal to H, and V is a whole number of pesos formatted with thousands separators.
9. THE Webapp SHALL attach a tooltip of at most 120 characters to each of the three stats, explaining in plain language what the stat means.
10. THE Webapp SHALL title each card in the form "<promo_id> · <Segment Name>", for example "NEW-001 · Untapped Wealth", where Segment Name is one of Ready Toppers, Untapped Wealth, Willing but Stretched, or Not Now as defined by Part 3.
11. THE Part 4 card data in `outputs/cards.json` SHALL remain byte-for-byte unchanged by this requirement, and THE display layer SHALL perform all relabeling and filtering.
12. FOR ALL Decision_Cards on Results and in the live New Promo cards, THE Webapp SHALL show no feature code or exclusion code containing an underscore in the card text.

### Requirement 5: Threshold Options With Fixed Ranges

**User Story:** As an analyst, I want threshold types with sensible fixed ranges, so that I enter realistic values and the capacity check stays meaningful.

#### Acceptance Criteria

1. THE Webapp SHALL provide a Threshold_Type selector on New Promo and What-If with exactly four options and these fixed slider ranges and steps: Top-Up Amount (₱) from ₱50,000 to ₱2,000,000 in steps of ₱10,000; Minimum Balance To Maintain (₱) from ₱10,000 to ₱5,000,000 in steps of ₱10,000; Balance Increase (% Of Current ADB) from 5% to 100% in steps of 5%; Opening Amount For A New Account (₱) from ₱1,000 to ₱100,000 in steps of ₱1,000.
2. THE Webapp SHALL display peso values with a ₱ symbol and thousands separators, and SHALL display Balance Increase values as whole-number percentages.
3. WHEN the user changes the Threshold_Type, THE Webapp SHALL reset the slider to the range of the new type and set its value to the minimum of that range plus 25% of the range width, rounded down to the nearest step.
4. WHEN the Threshold_Type is Top-Up Amount, Minimum Balance To Maintain, or Opening Amount For A New Account, THE Webapp SHALL use the selected peso value as Threshold_Php.
5. WHEN the Threshold_Type is Balance Increase, THE Webapp SHALL compute each client's threshold amount as the selected percentage times that client's `latest_adb`, and SHALL use these per-client amounts for the capacity check.
6. WHEN the Threshold_Type is Balance Increase, THE Webapp SHALL set Threshold_Php to the median of the per-client threshold amounts for model scoring.
7. WHEN the Threshold_Type is Balance Increase, THE Webapp SHALL show one note of at most 200 characters explaining the per-client conversion and the median used for scoring.
8. THE Webapp SHALL apply the same Threshold_Type options, ranges, and steps on the What-If page, replacing the current slider bounds derived from the current threshold.
9. THE Webapp SHALL map each Threshold_Type to the existing `PromoSpec` fields without changing Part 1, Part 3, or Part 4 scoring and segmentation code.
10. IF the Threshold_Type is Balance Increase and a client's `latest_adb` is missing, THEN THE Webapp SHALL exclude that client from the median calculation, treat that client as failing the capacity check, and keep the remaining clients' results unchanged.
11. IF the Threshold_Type is Balance Increase and no client has a usable `latest_adb`, THEN THE Webapp SHALL show an error message indicating that the percentage threshold cannot be applied, and SHALL NOT start the analysis.

### Requirement 6: Better Personas With Bedrock

**User Story:** As a marketer, I want friendly persona names and clear recommendations, so that I can brief a campaign team without reading statistics.

#### Acceptance Criteria

1. THE Persona_Narrator SHALL leave the existing clustering, preprocessing, and persona assignment unchanged, so that for the same input and seed 42 the persona membership and sizes are identical before and after Part 7.
2. WHEN personas are generated, THE Persona_Narrator SHALL send to the Bedrock_Client one request per persona containing only that persona's Persona_Aggregate, using plain-language feature labels from the Label_Map and no raw feature codes.
3. WHEN the Bedrock_Client returns JSON, THE Persona_Narrator SHALL read these fields: a friendly name of 2 to 4 words and at most 40 characters, a description of 1 to 2 sentences and at most 300 characters, a statement of why the persona differs from the other personas of at most 200 characters, and 2 to 3 recommended actions each naming a channel, an offer angle, and a message of at most 160 characters.
4. IF a returned recommended action names a channel other than exactly "In-app", "Email", or "SMS", THEN THE Persona_Narrator SHALL use the Mock result for that persona.
5. IF the name, description, or difference statement contains a number that is not present in the supplied Persona_Aggregate, THEN THE Persona_Narrator SHALL reject the Bedrock result for that persona and use its Mock result.
6. IF the returned JSON cannot be parsed, is missing a field, has an empty field, exceeds a length limit in criterion 3, or has fewer than 2 or more than 3 recommended actions, THEN THE Persona_Narrator SHALL use the Mock result for that persona.
7. IF two personas in the same persona set receive the same name, THEN THE Persona_Narrator SHALL use the Mock result for the later persona so that all names in the set are unique.
8. IF the Bedrock_Client fails or times out for one persona, THEN THE Persona_Narrator SHALL use the Mock result for that persona only, and SHALL keep the Bedrock results already accepted for the other personas.
9. WHILE the Bedrock_Client reports Demo_Mode, THE Persona_Narrator SHALL build rule-based names, descriptions, difference statements, and recommended actions from the same Persona_Aggregate in plain English without feature codes, meeting the same length limits and the same channel and action-count rules as criteria 3, 4, and 6.
10. THE Persona_Narrator SHALL NOT emit raw feature codes, text containing underscores from feature codes, or phrases such as "Highlight total outflows as the campaign hook" or "led by payroll income (avg 14%)", in either Bedrock or Mock output.
11. WHILE any persona text on the Personas page comes from the Mock, THE Webapp SHALL show the Demo Mode badge on the Personas page.
12. WHEN the same Persona_Aggregate and the same mode (Bedrock or Demo_Mode) are used in one session, THE Persona_Narrator SHALL return the same Mock text for each persona on repeated runs.
13. THE Persona_Narrator SHALL satisfy the Privacy_Boundary by sending no `client_id` and no per-client row in any request.

### Requirement 7: Easier Expected Joiners By Persona

**User Story:** As a marketer, I want each persona's likely joiners as a sentence and a bar, so that I can see where joiners come from at a glance.

#### Acceptance Criteria

1. WHEN a Decision_Card with persona data is rendered, THE Webapp SHALL show one row per listed persona in the form "<Persona Name>: about N of M likely to join (P%)", where N is the persona's expected joiners, M is the persona's lead count in that segment, and P is N divided by M times 100, together with a horizontal bar whose filled width equals P% of the bar's full width.
2. THE Webapp SHALL round N to a whole number and P to a whole percent, and SHALL display P within the range 0% to 100%.
3. IF M is 0 for a persona, THEN THE Webapp SHALL show that row as "<Persona Name>: no leads in this group" with an empty bar and SHALL NOT divide by zero.
4. THE Webapp SHALL label the total row "Total For <Segment Name>", for example "Total For Untapped Wealth", and SHALL NOT show a group index such as "Total for 0".
5. THE Webapp SHALL replace the note "(0 is 7.3 of it)" with wording that names the segment, in the form "<Persona Name> is N of the <Segment Name> total", with N rounded to a whole number.
6. THE Webapp SHALL show an "Other Personas" row whose expected joiners value equals the card's expected joiners minus the sum of the listed personas' expected joiners, and SHALL show the row only when that value is greater than 0.
7. THE Webapp SHALL end each card breakdown with one takeaway sentence in the form "Most likely joiners are in <Persona Name>; lead the message with them.", naming the persona, among the listed personas and "Other Personas", with the highest expected joiners.
8. IF two or more personas tie for the highest expected joiners, THEN THE Webapp SHALL name the tied persona that appears first in the displayed row order.
9. IF every persona has zero expected joiners, THEN THE Webapp SHALL show a takeaway stating that no persona stands out, in place of the persona-naming takeaway.
10. IF persona data is unavailable for a card, THEN THE Webapp SHALL omit the persona breakdown for that card and show one line stating that personas were not generated for this run, and SHALL leave the rest of the card unchanged.
11. FOR ALL cards, THE sum of the persona rows including "Other Personas" SHALL equal the card's expected joiners within a tolerance of 0.5.
12. THE Webapp SHALL use persona names and segment names as displayed elsewhere in the Webapp, with no feature codes or group indexes, and SHALL contain no em dash or "--" in the text introduced by this requirement.

### Requirement 8: Impact Summary On The Results Page

**User Story:** As a campaign owner, I want to see how the recommended plan compares with messaging everyone, so that I can justify targeting fewer clients.

#### Acceptance Criteria

1. WHEN a run result is available, THE Webapp SHALL compute the Baseline_Plan as the count of messages, the sum of expected joiners, and the sum of channel cost for all eligible, non-excluded clients, each messaged on their best channel, where channel cost per message is read from `data/channel_costs.csv`.
2. WHEN a run result is available, THE Webapp SHALL compute the Recommended_Plan as the count of messages, the sum of expected joiners, and the sum of channel cost for the sendable leads in segments whose action is not Skip, using the same per-message channel costs as the Baseline_Plan.
3. WHEN the Results tab is displayed with a run result, THE Webapp SHALL show a highlighted banner above the Decision_Cards reading "Messaging X% Fewer Clients Keeps Y% Of Expected Joiners And Saves ₱Z In Channel Costs", where X is (Baseline_Plan messages minus Recommended_Plan messages) divided by Baseline_Plan messages, Y is Recommended_Plan expected joiners divided by Baseline_Plan expected joiners, and Z is Baseline_Plan channel cost minus Recommended_Plan channel cost.
4. THE Webapp SHALL display X and Y as whole percentages rounded to the nearest integer, with values from 0 to 100, and Z as pesos rounded to the nearest whole peso with thousands separators.
5. WHEN the banner is shown, THE Webapp SHALL show three stat tiles beneath it named "Messages Saved", "Joiners Kept (%)", and "Cost Saved (₱)", where Messages Saved is the Baseline_Plan messages minus the Recommended_Plan messages as a whole number, and each tile has a tooltip of at most 200 characters stating its formula.
6. WHEN the What-If threshold changes and the audience is rescored, THE Webapp SHALL recompute the Impact_Summary from the rescored result and update the What-If banner and tiles before the next user interaction.
7. IF the Baseline_Plan has zero messages or zero expected joiners, THEN THE Webapp SHALL show a neutral message stating that no comparison is available, SHALL NOT show the percentage banner, and SHALL NOT raise a division error.
8. IF `data/channel_costs.csv` is missing, unreadable, or has no cost for a channel used in either plan, THEN THE Webapp SHALL show a message indicating that cost savings are unavailable, SHALL still show the Messages Saved and Joiners Kept (%) tiles, and SHALL leave the Decision_Cards and run result unchanged.
9. THE Webapp SHALL compute every Impact_Summary number in Python from the run result and `data/channel_costs.csv`, and SHALL NOT ask Bedrock for any number.
10. FOR ALL runs, THE Recommended_Plan messages SHALL be less than or equal to the Baseline_Plan messages, and THE Recommended_Plan expected joiners SHALL be less than or equal to the Baseline_Plan expected joiners.

### Requirement 9: Export Summary Button On The Results Page

**User Story:** As a campaign owner, I want to download one Excel workbook, so that I can share the plan and the send lists with my team.

#### Acceptance Criteria

1. WHEN a run result exists, THE Webapp SHALL show an "Export Summary" button on Results that downloads the Export_Workbook named `<promo_id>_campaign_summary.xlsx`.
2. WHILE no run result exists, THE Webapp SHALL hide the "Export Summary" button or show it disabled with a short message asking the user to run an analysis first.
3. THE Export_Workbook SHALL contain a "Summary" sheet with the promo details (promo_id, product type, mechanic, Threshold_Type, Threshold_Php, reward, channels), the Impact_Summary values (messages saved, joiners kept as a percentage, cost saved in pesos), the run date in YYYY-MM-DD format, and the text "Demo Mode" or "Bedrock" naming the AI source.
4. THE Export_Workbook SHALL contain a "Decision Cards" sheet with one row per segment (four rows) showing plain-language drivers and plain-language exclusions with a count for each reason, using phrases from the Label_Map and no raw feature codes.
5. THE Export_Workbook SHALL contain a "Personas" sheet with one row per persona showing the persona name, description, size, likely joiners rounded to a whole number, and recommended actions.
6. WHEN no persona result exists for the run, THE Export_Workbook SHALL include the Personas sheet with a single row stating that personas were not generated.
7. THE Export_Workbook SHALL contain one Send List sheet per segment whose action is not Skip, named after the segment in at most 31 characters, with the columns "client_id", "Best Channel", "Join Chance", and "Control Flag".
8. IF a segment's action is Skip or a segment has zero sendable leads, THEN THE Export_Workbook SHALL omit the Send List sheet for that segment, and SHALL still contain the Summary, Decision Cards, and Personas sheets.
9. THE Export_Workbook SHALL use Title Case headers, a bold header row, frozen panes on the row directly below the header row of every sheet, column widths of 10 to 60 characters, percentage formatting for join chance and shares, and peso formatting with thousands separators for money values.
10. THE Export_Workbook SHALL be built with openpyxl from the run result and persona result already in memory, without calling Bedrock for numbers and without reading data files other than `data/channel_costs.csv` if needed for the Impact_Summary.
11. THE Export_Workbook SHALL be encoded as a valid .xlsx file that opens with openpyxl without error, and all text cells SHALL be UTF-8 without em dashes or "--".
12. IF building the Export_Workbook fails, THEN THE Webapp SHALL show a plain-language error message, SHALL NOT start a download, and SHALL keep the Results page and run result unchanged.
13. THE Webapp SHALL keep `client_id` out of every Bedrock payload, and the Send List sheets SHALL contain `client_id` because the Export_Workbook is a local file.

### Requirement 10: Quality, Tests, And Visual Verification

**User Story:** As a developer, I want focused tests and visual checks, so that the new features are trustworthy and render correctly.

#### Acceptance Criteria

1. THE Test_Suite SHALL contain at most 8 property tests (hypothesis tests) across all of Part 7, including the tests for Requirements 1 through 11, and SHALL cover all other behavior with unit, integration, or example tests.
2. THE Test_Suite SHALL verify that the Label_Map returns a plain-English phrase, not a Title Case fallback, for every feature code and every exclusion code that the Webapp UI can show, and that no returned phrase contains an underscore.
3. THE Test_Suite SHALL verify, for each of the four Threshold_Type options, the minimum, maximum, and step defined in Requirement 5, that the default value lies inside the range, and that a Balance Increase conversion of percentage times `latest_adb` per client yields a Threshold_Php equal to the median of those per-client amounts.
4. THE Test_Suite SHALL verify that the Campaign_Extractor and the Persona_Narrator accept valid JSON and reject JSON with a missing field, a wrong type, or an invalid value, using mocked boto3 calls and no network access.
5. THE Test_Suite SHALL verify that each AI_Feature returns its Mock result and reports Demo_Mode in each of four cases: missing credentials, a failed call, a timed-out call, and invalid JSON, using mocked boto3 calls and no network access.
6. THE Test_Suite SHALL verify that the payload sent to the Bedrock_Client by each AI_Feature contains no `client_id` value and no per-client row, and that the Bedrock_Client rejects a payload that does.
7. THE Test_Suite SHALL verify the Impact_Summary math for X, Y, and Z from Requirement 8 on at least one example with known values, and SHALL verify the zero-message and zero-expected-joiners baseline cases return the neutral message without a division error.
8. THE Test_Suite SHALL verify that the Export_Workbook opens with openpyxl and contains the sheets required by Requirement 9, a bold header row on each sheet, and frozen panes directly below the header row on each sheet.
9. THE Test_Suite SHALL verify that no UI text string introduced by Part 7 contains an em dash or the sequence "--".
10. WHEN the implementation is complete, THE developer SHALL run the Webapp with `PYTHONPATH=src ./.venv/bin/python -m streamlit run app/main.py` and SHALL save one screenshot each of New Promo (the "Upload Campaign File" tab and the "Fill In Details" tab), Results, Personas, What-If, and Ask Assistant into `scratch/`, for 6 screenshots in total.
11. IF a screen does not render or shows an uncaught error in its screenshot, THEN THE developer SHALL fix the cause and recapture that screenshot before reporting completion.
12. WHEN the implementation is complete, THE developer SHALL deliver a report listing the modified files, the assumptions made, the known limitations, and the test commands run with their pass and fail counts.
13. THE Test_Suite SHALL leave the six existing Part 1 Hypothesis timeout failures unchanged and SHALL set `deadline=None` on every new hypothesis test that fits a model.
14. WHERE the user confirms that Poppins should replace the current font stack, THE Webapp SHALL load Poppins through `app/theme.py` and `.streamlit/config.toml` and SHALL keep the existing layout and colors unchanged.
15. WHILE the user has not confirmed that Poppins should replace the current font stack, THE Webapp SHALL keep the existing font stack unchanged.

### Requirement 11: Smarter Past Promos Tab

**User Story:** As an analyst, I want past campaigns sorted and filtered by how similar they are to my new promo, so that I can learn from the most relevant history.

#### Acceptance Criteria

1. THE Past_Promos_Tab SHALL read campaign metadata from `data/promo_history.csv`, lead outcomes from `data/promo_leads.csv`, and existing artifacts under `outputs/`, and SHALL NOT generate dummy data or retrain or rescore historical campaigns.
2. THE Past_Promos_Tab SHALL offer exactly three sort options: "Newest" (descending `start_date`), "Oldest" (ascending `start_date`), and "Most Similar" (descending Similarity_Score against the current New Promo form).
3. WHILE no New Promo proposal exists in session state, THE Past_Promos_Tab SHALL select "Newest" by default, SHALL show "Most Similar" as disabled with a visible label stating it is unavailable until a New Promo is filled in or uploaded, and SHALL NOT compute any Similarity_Score.
4. THE Past_Promos_Tab SHALL offer optional Product Type and Target Audience filters, each defaulting to "All", and SHALL apply the filters before sorting.
5. IF the selected filters match zero campaigns, THEN THE Past_Promos_Tab SHALL show a message stating that no campaigns match the filters, SHALL hide the "View More" control, and SHALL keep the filter selections unchanged.
6. THE Past_Promos_Tab SHALL initially show 5 campaigns, and WHEN the user clicks "View More", THE Past_Promos_Tab SHALL reveal the next 5 campaigns, and SHALL hide "View More" once all matching campaigns are shown.
7. WHEN the user changes the sort option or a filter, THE Past_Promos_Tab SHALL reset the visible count to 5.
8. THE Similarity_Score SHALL be a deterministic value from 0 to 100, rounded to a whole number for display, equal to the sum of the weighted points of the eight Similarity_Components with maximum weights: audience and eligibility 30, JTBD and customer need 20, product and mechanic 15, offer economics 10, duration 10, channels 5, objective 5, name and summary 5.
9. THE Similarity_Score SHALL compute each Similarity_Component as a fraction from 0 to 1 multiplied by its weight, so that identical inputs always yield identical scores.
10. THE Similarity_Score SHALL compare duration using the inclusive day count from start date to end date (same start and end date equals 1 day).
11. IF metadata for a Similarity_Component is missing or empty for either campaign, THEN THE Similarity_Score SHALL mark that component "Unavailable", exclude its weight, and rescale the remaining weights so they sum to 100, without inventing values.
12. IF every Similarity_Component is unavailable for a campaign, THEN THE Past_Promos_Tab SHALL show "Not Enough Data" instead of a score and SHALL sort that campaign after all scored campaigns under "Most Similar".
13. WHEN two campaigns have equal Similarity_Score under "Most Similar", THE Past_Promos_Tab SHALL order them by newest `start_date`, then by ascending `promo_id`, so the order is deterministic.
14. WHEN a campaign detail is opened, THE Past_Promos_Tab SHALL show a horizontal bar chart of all eight Similarity_Components with weighted points and maximum points for each, and SHALL label each unavailable component "Unavailable".
15. WHEN a campaign detail is opened, THE Past_Promos_Tab SHALL show the campaign dates, inclusive duration in days, product, audience, channels, actual opt-in rate computed as joined count divided by treated leads (`control_group == 0`) from `data/promo_leads.csv` and shown as a percentage with one decimal place, and available segment responses.
16. IF a campaign has zero treated leads in `data/promo_leads.csv`, THEN THE Past_Promos_Tab SHALL show the actual opt-in rate as "Not Available" and SHALL NOT divide by zero.
17. WHERE valid historical prediction artifacts exist for a campaign, THE Past_Promos_Tab SHALL show predicted versus actual join rate using the existing Past Promos accuracy logic, and OTHERWISE THE Past_Promos_Tab SHALL omit the prediction comparison.
18. IF `data/promo_history.csv` or `data/promo_leads.csv` is missing or unreadable, THEN THE Past_Promos_Tab SHALL show an error message naming the missing file and SHALL NOT show partial campaign data.
19. THE Past_Promos_Tab SHALL use only local calculations, cached summaries, and existing dependencies, and SHALL NOT call Bedrock, any LLM, embeddings, external APIs, or any token-metered service.
20. THE Past_Promos_Tab SHALL preserve all existing Past Promos features and the existing historical accuracy logic.
