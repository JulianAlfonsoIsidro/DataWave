import numpy as np, pandas as pd

rng = np.random.default_rng(42)
N = 2000

def sig(x):
    return 1 / (1 + np.exp(-x))

# ---------------- Customer DNA ----------------
ids = [f"C{100000 + i}" for i in range(N)]
segment = rng.choice(["Mass", "Mid-Market", "Affluent-Preferred", "Affluent-Gold"], N, p=[0.40, 0.35, 0.17, 0.08])
seg_income = {"Mass": 25_000, "Mid-Market": 60_000, "Affluent-Preferred": 180_000, "Affluent-Gold": 400_000}
base_income = np.array([seg_income[s] for s in segment]) * rng.lognormal(0, 0.35, N)

age_band = rng.choice(["18-24", "25-34", "35-44", "45-54", "55+"], N, p=[0.10, 0.30, 0.28, 0.20, 0.12])
tenure = np.clip(rng.gamma(2.2, 3.0, N), 0.2, 40).round(1)
region = rng.choice(["NCR", "Luzon", "Visayas", "Mindanao"], N, p=[0.45, 0.25, 0.17, 0.13])
sec_map = {"Mass": ["D", "C2", "C1"], "Mid-Market": ["C2", "C1", "B2"], "Affluent-Preferred": ["C1", "B2", "B1"], "Affluent-Gold": ["B2", "B1", "A"]}
sec = np.array([rng.choice(sec_map[s]) for s in segment])
young = np.isin(age_band, ["18-24", "25-34"])
digital_score = sig(rng.normal(0.3 + 0.9 * young, 1.0, N))
digital_user = (digital_score > 0.5).astype(int)
online_shopper = pd.cut(digital_score + rng.normal(0, 0.1, N), [-1, 0.3, 0.5, 0.7, 0.85, 2],
                        labels=["Low", "Medium", "High", "Very High", "Ultra High"]).astype(str)
inflow_type = rng.choice(["Salary", "Remittance", "Business", "Mixed"], N, p=[0.50, 0.15, 0.20, 0.15])
frugal = (rng.random(N) < 0.35).astype(int)
email_valid = (rng.random(N) < 0.80).astype(int)
mobile_valid = (rng.random(N) < 0.90).astype(int)

# Latent (hidden) variables: money held outside BPI, investment appetite
external_funds = base_income * rng.lognormal(1.2, 0.9, N) * (rng.random(N) < 0.55)
invest_appetite = rng.normal(0, 1, N) + 0.6 * (segment != "Mass") + 0.4 * frugal
inv_decile = pd.qcut(invest_appetite + rng.normal(0, 0.6, N), 10, labels=False) + 1  # noisy observed proxy

dna = pd.DataFrame({
    "client_id": ids, "segment": segment, "age_band": age_band, "tenure_years": tenure,
    "region": region, "sec_class": sec, "inflow_type": inflow_type,
    "digital_app_user": digital_user, "online_shopper": online_shopper, "frugal_flag": frugal,
    "investment_propensity_decile": inv_decile, "email_valid": email_valid, "mobile_valid": mobile_valid,
})

# ---------------- Product ownership ----------------
prod_catalog = {
    "Deposit": ["SA-REG", "SA-PLUS", "CA-REG", "TD-90D"],
    "Investment": ["UITF-EQ", "UITF-BOND", "WB-STD"],
    "Insurance": ["LIFE-VUL", "HEALTH-HMO"],
    "Loan": ["AUTO-LN", "HOUSE-LN", "PERS-LN"],
    "Credit Card": ["CC-CLASSIC", "CC-GOLD", "CC-PLAT"],
}
po_rows = []
for i, cid in enumerate(ids):
    po_rows.append((cid, "SA-REG", "Deposit"))
    rich = segment[i] != "Mass"
    for ptype, p in [("Deposit", 0.35 + 0.2 * rich), ("Investment", 0.04 + 0.08 * (inv_decile[i] >= 8)),
                     ("Insurance", 0.10 + 0.1 * rich), ("Loan", 0.12), ("Credit Card", 0.25 + 0.25 * rich)]:
        if rng.random() < p:
            code = rng.choice([c for c in prod_catalog[ptype] if c != "SA-REG"])
            po_rows.append((cid, code, ptype))
po = pd.DataFrame(po_rows, columns=["client_id", "product_code", "product_type"]).drop_duplicates()
start = pd.Timestamp("2026-09-30") - pd.to_timedelta((rng.random(len(po)) * 3650).astype(int), unit="D")
po["open_date"] = start.strftime("%Y-%m-%d")
po["status"] = np.where(rng.random(len(po)) < 0.93, "Active", "Closed")
n_products = po[po.status == "Active"].groupby("client_id").size().reindex(ids).fillna(0).values

# ---------------- Monthly ADB (Jan to Sep 2026) ----------------
months = pd.period_range("2026-01", "2026-09", freq="M")
adb_base = base_income * rng.lognormal(0.9, 0.6, N)
trend = rng.normal(0.0, 0.03, N)
adb_rows = []
for m_i, m in enumerate(months):
    vals = adb_base * (1 + trend) ** m_i * rng.lognormal(0, 0.08, N)
    for cid, v in zip(ids, vals):
        adb_rows.append((cid, str(m), round(float(v), 2)))
adb = pd.DataFrame(adb_rows, columns=["client_id", "month", "adb_php"])
adb_sep = adb[adb.month == "2026-09"].set_index("client_id").adb_php.reindex(ids).values

# ---------------- NDB (negative data bank) ----------------
ndb_mask = rng.random(N) < 0.04
ndb = pd.DataFrame({
    "client_id": np.array(ids)[ndb_mask],
    "flag_type": rng.choice(["Loan delinquency", "Card delinquency", "Returned check"], ndb_mask.sum()),
    "flag_date": (pd.Timestamp("2026-09-30") - pd.to_timedelta(rng.integers(0, 700, ndb_mask.sum()), unit="D")).strftime("%Y-%m-%d"),
})

# ---------------- Transactions (Jul to Sep 2026) ----------------
industries = ["Grocery", "Restaurants", "Utilities", "Telco", "Retail", "Fuel", "Health", "Education", "Travel", "E-commerce"]
billers = ["Utilities", "Telco", "Education", "Insurance premium"]
ext_share = np.clip(sig((np.log1p(external_funds) - 11) * 0.9) * 0.7 + rng.normal(0, 0.04, N), 0, 0.8)
txn = []
tid = 0
days = pd.date_range("2026-07-01", "2026-09-30")
for i, cid in enumerate(ids):
    inc = base_income[i]
    for m in [7, 8, 9]:
        mdays = days[days.month == m]
        mstr = [d.strftime("%Y-%m-%d") for d in mdays]
        # inflows
        it = inflow_type[i]
        if it in ("Salary", "Mixed"):
            for d in [15, 30]:
                txn.append((cid, f"2026-{m:02d}-{min(d, len(mdays)):02d}", "IN", round(inc / 2 * rng.uniform(0.98, 1.02), 2), "EMP" + str(i % 97).zfill(4), "Employer", "Payroll", "Payroll"))
        if it in ("Remittance", "Mixed"):
            txn.append((cid, str(rng.choice(mstr)), "IN", round(inc * rng.uniform(0.6, 1.4), 2), "REM" + str(i % 53).zfill(4), "Remittance", "Remittance", "Remittance"))
        if it == "Business":
            for _ in range(rng.integers(8, 16)):
                txn.append((cid, str(rng.choice(mstr)), "IN", round(inc / 10 * rng.lognormal(0, 0.5), 2), "P" + str(rng.integers(0, 3000)).zfill(5), "BPI client", "Business receipts", "InstaPay"))
        # outflows: spending
        spend = inc * rng.uniform(0.45, 0.75)
        for _ in range(rng.integers(4, 9)):
            ind = rng.choice(industries)
            txn.append((cid, str(rng.choice(mstr)), "OUT", round(spend / 8 * rng.lognormal(0, 0.4), 2), "M" + str(rng.integers(0, 800)).zfill(4), "Merchant", ind, "Debit/QR"))
        b = rng.choice(billers)
        txn.append((cid, str(rng.choice(mstr)), "OUT", round(inc * 0.06 * rng.uniform(0.7, 1.3), 2), "B" + str(rng.integers(0, 60)).zfill(3), "Biller", b, "BillsPay"))
        # outflows: transfers to other banks (planted signal)
        if rng.random() < 0.15 + ext_share[i]:
            amt = inc * (0.05 + ext_share[i]) * rng.uniform(0.8, 1.2)
            txn.append((cid, str(rng.choice(mstr)), "OUT", round(amt, 2), "XB" + str(i % 211).zfill(4), "Other bank", "Bank transfer", rng.choice(["InstaPay", "PESONet"])))
        # p2p to other BPI clients
        if rng.random() < 0.4:
            txn.append((cid, str(rng.choice(mstr)), "OUT", round(inc * 0.05 * rng.lognormal(0, 0.5), 2), rng.choice(ids), "BPI client", "P2P transfer", "InstaPay"))
tx = pd.DataFrame(txn, columns=["client_id", "txn_date", "direction", "amount_php", "counterparty_id", "counterparty_type", "counterparty_category", "channel"])
tx = tx.sort_values(["txn_date", "client_id"]).reset_index(drop=True)
tx.insert(0, "txn_id", [f"T{1000000 + k}" for k in range(len(tx))])

# ---------------- Promo history ----------------
promos = pd.DataFrame([
    ("P001", "Preferred Status Top-Up", "Deposit", "TOP_UP", 500000, "Keep Preferred status + gift", "2026-02-01", "2026-03-31", "Email, In-app"),
    ("P002", "Wealth Builder Starter", "Investment", "NEW_ACCOUNT", 1000, "Bonus 500 points", "2026-04-01", "2026-05-31", "Email, In-app, SMS"),
    ("P003", "Save-Up Challenge", "Deposit", "ADB_INCREASE", 50000, "Raffle entry per 10K", "2026-06-01", "2026-07-31", "Email, SMS"),
], columns=["promo_id", "promo_name", "product_type", "mechanic", "threshold_php", "reward", "start_date", "end_date", "channels"])

# ---------------- Contact history (Jan to Sep 2026) ----------------
contacts = []
fatigue = rng.poisson(1.5, N)  # campaigns received in a typical month
for i, cid in enumerate(ids):
    for m in range(1, 10):
        for _ in range(rng.poisson(fatigue[i] * 0.8)):
            contacts.append((cid, f"2026-{m:02d}-{rng.integers(1, 28):02d}", "CMP" + str(rng.integers(100, 160)), rng.choice(["Email", "SMS", "In-app"], p=[0.5, 0.25, 0.25])))
ch = pd.DataFrame(contacts, columns=["client_id", "contact_date", "campaign_id", "channel"]).sort_values(["contact_date", "client_id"])

# ---------------- Promo leads (targeted lists with outcomes) ----------------
true_rows = []
lead_rows = []
ndb_set = set(ndb.client_id)
for _, p in promos.iterrows():
    if p.mechanic == "TOP_UP":
        elig = np.isin(segment, ["Mid-Market", "Affluent-Preferred", "Affluent-Gold"]) & (adb_sep > 100000)
    elif p.mechanic == "NEW_ACCOUNT":
        has_inv = po[(po.product_type == "Investment")].client_id.unique()
        elig = ~np.isin(ids, has_inv)
    else:
        elig = np.ones(N, bool)
    idx = np.where(elig)[0]
    for i in idx:
        control = rng.random() < 0.10
        chans = [c.strip() for c in p.channels.split(",")]
        if digital_user[i] and "In-app" in chans:
            channel = "In-app"
        elif email_valid[i] and "Email" in chans:
            channel = "Email"
        elif "SMS" in chans and mobile_valid[i]:
            channel = "SMS"
        else:
            channel = chans[0]
        # planted logic
        capacity = np.log1p(adb_sep[i] + external_funds[i])
        logit = -4.2
        if p.mechanic == "TOP_UP":
            logit += 1.6 * (external_funds[i] + adb_sep[i] > 500000) + 1.8 * ext_share[i] + 0.3 * (segment[i] == "Affluent-Preferred")
        elif p.mechanic == "NEW_ACCOUNT":
            logit += 0.45 * invest_appetite[i] + 0.5 * digital_user[i] + 0.4 * frugal[i]
        else:
            logit += 0.25 * (capacity - 12) + 0.5 * frugal[i] + 0.3 * (inflow_type[i] in ("Salary", "Remittance"))
        logit += 0.15 * n_products[i] - 0.35 * max(fatigue[i] - 2, 0)
        logit += 0.5 if (channel == "In-app" and digital_user[i]) else 0
        if cid_in := (ids[i] in ndb_set):
            logit -= 2.0
        organic = sig(logit - 1.3)  # baseline without message
        treated = sig(logit)
        prob = organic if control else treated
        joined = int(rng.random() < prob)
        jd = ""
        if joined:
            jd = str((pd.Timestamp(p.start_date) + pd.Timedelta(days=int(rng.integers(1, 55)))).date())
        lead_rows.append((p.promo_id, ids[i], int(control), "None (control)" if control else channel, joined, jd))
        true_rows.append((p.promo_id, ids[i], round(float(organic), 4), round(float(treated), 4)))
leads = pd.DataFrame(lead_rows, columns=["promo_id", "client_id", "control_group", "channel_sent", "joined", "join_date"])

# ---------------- Channel costs ----------------
costs = pd.DataFrame([
    ("Email", 0.053, "Per email. From the sample CRM campaign proposal (Project FORWARD)."),
    ("SMS", 0.264, "Per 1-part SMS. From the sample CRM campaign proposal."),
    ("In-app", 1.17, "Midpoint of the 0.57 to 1.77 range in the sample CRM campaign proposal."),
], columns=["channel", "cost_php_per_message", "source"])

# ---------------- Answer key (hidden truth, for validation only) ----------------
key = pd.DataFrame({"client_id": ids, "external_funds_php_TRUE": external_funds.round(2),
                    "external_outflow_share_TRUE": ext_share.round(4), "invest_appetite_TRUE": invest_appetite.round(3),
                    "typical_monthly_contacts_TRUE": fatigue})
true_probs = pd.DataFrame(true_rows, columns=["promo_id", "client_id", "p_join_if_not_sent_TRUE", "p_join_if_sent_TRUE"])

tables = {"customer_dna": dna, "product_ownership": po, "adb_monthly": adb, "ndb": ndb, "transactions": tx,
          "promo_history": promos, "promo_leads": leads, "contact_history": ch, "channel_costs": costs,
          "_answer_key_clients": key, "_answer_key_promos": true_probs}
for k, v in tables.items():
    v.to_pickle(f"{k}.pkl")
    print(k, v.shape)
print(leads.groupby(["promo_id", "control_group"]).joined.agg(["count", "mean"]))
