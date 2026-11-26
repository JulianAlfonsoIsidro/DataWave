# Input Data Dictionary

Describes the CSV files in `data/` used as pipeline inputs. Row counts and value sets come from the files as they stand now. Descriptions of meaning are inferred from column names and values, so confirm them against the data owner where it matters.

## Files at a glance

| File | Rows | Grain (one row per) | Key |
|---|---:|---|---|
| `customer_dna.csv` | 2,000 | client | `client_id` |
| `adb_monthly.csv` | 18,000 | client and month | `client_id`, `month` |
| `transactions.csv` | 70,555 | transaction | `txn_id` |
| `product_ownership.csv` | 4,437 | client and product | `client_id`, `product_code` |
| `contact_history.csv` | 21,578 | contact sent | none (`client_id`, `contact_date`, `campaign_id`) |
| `ndb.csv` | 79 | client flag | none (`client_id`, `flag_type`, `flag_date`) |
| `promo_history.csv` | 3 | past promo | `promo_id` |
| `promo_leads.csv` | 4,864 | promo and client | `promo_id`, `client_id` |
| `channel_costs.csv` | 3 | channel | `channel` |

`client_id` (format `C100000`) joins all client-level files to `customer_dna`. `promo_id` (`P001` to `P003`) joins `promo_leads` to `promo_history`.

## customer_dna.csv

Client profile.

| Column | Type | Description | Values |
|---|---|---|---|
| `client_id` | string | Unique client identifier. | `C100000` and up |
| `segment` | category | Bank customer tier. | Affluent-Gold, Affluent-Preferred, Mass, Mid-Market |
| `age_band` | category | Age range. | 18-24, 25-34, 35-44, 45-54, 55+ |
| `tenure_years` | float | Years as a client. | numeric |
| `region` | category | Home region. | NCR, Luzon, Visayas, Mindanao |
| `sec_class` | category | Socio-economic class. | A, B1, B2, C1, C2, D |
| `inflow_type` | category | Main source of incoming money. | Salary, Business, Remittance, Mixed |
| `digital_app_user` | 0/1 | 1 if the client uses the mobile app. | 0, 1 |
| `online_shopper` | category | Online shopping intensity. | Low, Medium, High, Very High, Ultra High |
| `frugal_flag` | 0/1 | 1 if flagged as frugal. | 0, 1 |
| `investment_propensity_decile` | int | Investment propensity rank, as a decile. | 1 to 10 |
| `email_valid` | 0/1 | 1 if the email address is usable. | 0, 1 |
| `mobile_valid` | 0/1 | 1 if the mobile number is usable. | 0, 1 |

## adb_monthly.csv

Average daily balance (ADB) per client per month.

| Column | Type | Description | Values |
|---|---|---|---|
| `client_id` | string | Client. | FK to `customer_dna` |
| `month` | string `YYYY-MM` | Month of the balance. | 2026-01 to 2026-09 |
| `adb_php` | float | Average daily balance in pesos. | numeric |

## transactions.csv

Money movements, 2026-07-01 to 2026-09-30.

| Column | Type | Description | Values |
|---|---|---|---|
| `txn_id` | string | Unique transaction id. | `T1000000` and up |
| `client_id` | string | Client. | FK to `customer_dna` |
| `txn_date` | date | Transaction date. | 2026-07-01 to 2026-09-30 |
| `direction` | category | Money in or out for the client. | IN, OUT |
| `amount_php` | float | Amount in pesos. | numeric |
| `counterparty_id` | string | Other party, such as a merchant (`M0414`) or biller (`B045`). | identifier |
| `counterparty_type` | category | Kind of other party. | BPI client, Biller, Employer, Merchant, Other bank, Remittance |
| `counterparty_category` | category | Spend or income category of the other party. | Bank transfer, Business receipts, E-commerce, Education, Fuel, Grocery, Health, Insurance premium, P2P transfer, Payroll, Remittance, Restaurants, Retail, Telco, Travel, Utilities |
| `channel` | category | Payment rail used. | BillsPay, Debit/QR, InstaPay, PESONet, Payroll, Remittance |

## product_ownership.csv

Products a client holds or held.

| Column | Type | Description | Values |
|---|---|---|---|
| `client_id` | string | Client. | FK to `customer_dna` |
| `product_code` | category | Specific product. | AUTO-LN, CA-REG, CC-CLASSIC, CC-GOLD, CC-PLAT, HEALTH-HMO, HOUSE-LN, LIFE-VUL, PERS-LN, SA-PLUS, SA-REG, TD-90D, UITF-BOND, UITF-EQ, WB-STD |
| `product_type` | category | Product family. | Credit Card, Deposit, Insurance, Investment, Loan |
| `open_date` | date | Date the product was opened. | date |
| `status` | category | Current state. | Active, Closed |

## contact_history.csv

Past marketing contacts, 2026-01-01 to 2026-09-27. Used for contact-fatigue and do-not-contact logic.

| Column | Type | Description | Values |
|---|---|---|---|
| `client_id` | string | Client contacted. | FK to `customer_dna` |
| `contact_date` | date | Date of contact. | date |
| `campaign_id` | string | Campaign that sent the message (for example `CMP151`). | identifier |
| `channel` | category | Channel used. | Email, In-app, SMS |

## ndb.csv

Negative-data flags on clients (delinquency or returned checks).

| Column | Type | Description | Values |
|---|---|---|---|
| `client_id` | string | Flagged client. | FK to `customer_dna` |
| `flag_type` | category | Type of flag. | Card delinquency, Loan delinquency, Returned check |
| `flag_date` | date | Date the flag was raised. | date |

## promo_history.csv

Past promos. Only `P001`, `P002` and `P003` are used for training.

| Column | Type | Description | Values |
|---|---|---|---|
| `promo_id` | string | Promo identifier. | P001, P002, P003 |
| `promo_name` | string | Promo name. | Preferred Status Top-Up, Wealth Builder Starter, Save-Up Challenge |
| `product_type` | category | Product family promoted. | Deposit, Investment |
| `mechanic` | category | How a client qualifies. | TOP_UP, NEW_ACCOUNT, ADB_INCREASE |
| `threshold_php` | int | Qualifying amount in pesos. | 500000, 1000, 50000 |
| `reward` | string | Reward offered. | free text |
| `start_date` | date | Promo start. | date |
| `end_date` | date | Promo end. | date |
| `channels` | string | Comma-separated channels allowed. | Email, In-app, SMS |

## promo_leads.csv

Who was targeted in each past promo and the outcome.

| Column | Type | Description | Values |
|---|---|---|---|
| `promo_id` | string | Promo. | FK to `promo_history` |
| `client_id` | string | Client. | FK to `customer_dna` |
| `control_group` | 0/1 | 1 if held out and not contacted. A lead is "treated" when this is 0. | 0, 1 |
| `channel_sent` | category | Channel used. | Email, In-app, SMS, None (control) |
| `joined` | 0/1 | 1 if the client joined the promo. This is the training label. | 0, 1 |
| `join_date` | date | Date joined. Empty when `joined` is 0. | date or blank |

## channel_costs.csv

Cost per message by channel.

| Column | Type | Description | Values |
|---|---|---|---|
| `channel` | category | Channel. | Email, SMS, In-app |
| `cost_php_per_message` | float | Pesos per message. | 0.053, 0.264, 1.170 |
| `source` | string | Where the figure comes from. | free text |

## Other files in `data/`

| File | Status |
|---|---|
| `_answer_key_clients.csv` | Forbidden as a model input. Never train or score on it. Not documented here. |
| `_answer_key_promos.csv` | Forbidden as a model input. Never train or score on it. Not documented here. |
| `gen_data.py` | Synthetic data generator. Not data. |
| `theme_reference.png` | UI reference image. Not data. |

## Conventions and cautions

- Channel labels must match exactly (`In-app`, `Email`, `SMS`). A mismatch makes leads unreachable.
- Amounts are in Philippine pesos (PHP).
- All data is synthetic.
