"""CRM-style persona archetype names (Demo Mode namer).

Every trait a persona can stand out on has an archetype entry: an adjective,
a role noun and a "people with ..." phrase. A persona is named from its top
one or two traits:

- one trait:  "<adjective> <noun>" of that trait      -> "Disciplined Saver"
- two traits: "<adjective of the 2nd> <noun of the 1st>" -> "Digital-First Saver"

so every trait, and every combination of two traits, has a name. When a name
is already taken in the set (or the two words repeat each other) the roles
swap, then the third trait steps in, then a classic/modern qualifier; never a
letter or a number. Names stay 2-4 words, at most 40 characters, with no
digits or underscores (the Bedrock validation limits).

Keys are ``(raw column, value)`` where value is ``"high"``/``"low"`` for a
numeric attribute, ``"more"``/``"fewer"`` for a yes/no flag, and the category
itself for a text attribute (``("age_band", "25-34")``). Pure data and pure
functions: no Streamlit, no I/O, deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Archetype:
    adjective: str      # one hyphenated word: "Digital-First"
    noun: str           # one or two words: "App Native"
    phrase: str         # fits after "people with": "confidence using digital financial products"


A = Archetype

ARCHETYPES: dict[tuple[str, str], Archetype] = {
    # ---- relationship and propensity -------------------------------------------
    ("tenure_years", "high"): A("Loyal", "Long-Timer", "a long relationship with the bank"),
    ("tenure_years", "low"): A("Fresh", "Newcomer", "a new relationship with the bank"),
    ("investment_propensity_decile", "high"): A(
        "Wealth-Minded", "Investor", "the highest likelihood to make a first investment"),
    ("investment_propensity_decile", "low"): A(
        "Cautious", "Safekeeper", "little appetite for investing"),
    # ---- money out ---------------------------------------------------------------
    ("total_out", "high"): A("Big-Spending", "Spender", "heavy monthly spending"),
    ("total_out", "low"): A("Light-Spending", "Minimalist", "light monthly spending"),
    ("out_other_bank", "high"): A("Multi-Bank", "Money Mover", "a lot of money sent to other banks"),
    ("out_other_bank", "low"): A("Bank-Loyal", "Loyalist", "money kept within the bank"),
    ("ext_outflow_ratio", "high"): A(
        "Outward-Flowing", "Fund Shifter", "a large share of money flowing to other banks"),
    ("ext_outflow_ratio", "low"): A("Home-Banked", "Anchor", "most of their money staying with us"),
    ("months_with_ext_transfer", "high"): A(
        "Habitual", "Transferrer", "a steady habit of transfers to other banks"),
    ("months_with_ext_transfer", "low"): A("Steady", "Stayer", "rare transfers to other banks"),
    # ---- money in ----------------------------------------------------------------
    ("inflow_share_payroll", "high"): A("Salaried", "Salary Earner", "a salary-led income"),
    ("inflow_share_payroll", "low"): A("Self-Directed", "Free Agent", "income mostly outside payroll"),
    ("inflow_share_remittance", "high"): A(
        "Family-Backed", "Remittance Receiver", "income supported by remittances"),
    ("inflow_share_remittance", "low"): A("Self-Funded", "Self-Starter", "little reliance on remittances"),
    ("inflow_share_business_receipts", "high"): A(
        "Enterprising", "Entrepreneur", "income from their own business"),
    ("inflow_share_business_receipts", "low"): A("Employed", "Employee", "little business income"),
    # ---- spending mix -------------------------------------------------------------
    ("spend_share_bank_transfer", "high"): A(
        "Transfer-Heavy", "Money Sender", "a big share of spending on bank transfers"),
    ("spend_share_bank_transfer", "low"): A("Direct-Paying", "Direct Spender", "few bank transfers"),
    ("spend_share_e_commerce", "high"): A("Online-Savvy", "Online Shopper", "a big share of spending online"),
    ("spend_share_e_commerce", "low"): A("In-Store", "Store Shopper", "little online shopping"),
    ("spend_share_education", "high"): A(
        "Education-Minded", "Parent Planner", "a big share of spending on education"),
    ("spend_share_education", "low"): A("Unburdened", "Free Spender", "little spending on education"),
    ("spend_share_fuel", "high"): A("On-the-Go", "Commuter", "a big share of spending on fuel"),
    ("spend_share_fuel", "low"): A("Car-Free", "City Walker", "little spending on fuel"),
    ("spend_share_grocery", "high"): A(
        "Home-Centered", "Household Manager", "a big share of spending on groceries"),
    ("spend_share_grocery", "low"): A("Eat-Out", "Diner", "little spending on groceries"),
    ("spend_share_health", "high"): A(
        "Health-Conscious", "Wellness Seeker", "a big share of spending on health"),
    ("spend_share_health", "low"): A("Carefree", "Free Spirit", "little spending on health"),
    ("spend_share_insurance_premium", "high"): A(
        "Protected", "Planner", "a big share of spending on insurance premiums"),
    ("spend_share_insurance_premium", "low"): A("Risk-Taking", "Risk Taker", "little spending on insurance"),
    ("spend_share_p2p_transfer", "high"): A("Social", "Peer Payer", "frequent person-to-person payments"),
    ("spend_share_p2p_transfer", "low"): A("Private", "Solo Spender", "few person-to-person payments"),
    ("spend_share_restaurants", "high"): A("Foodie", "Food Lover", "a big share of spending at restaurants"),
    ("spend_share_restaurants", "low"): A("Home-Cooking", "Home Cook", "little spending at restaurants"),
    ("spend_share_retail", "high"): A("Retail-Loving", "Shopper", "a big share of spending on retail"),
    ("spend_share_retail", "low"): A("Essentials-Only", "Essentialist", "little retail spending"),
    ("spend_share_telco", "high"): A(
        "Always-Connected", "Connector", "a big share of spending on mobile and internet"),
    ("spend_share_telco", "low"): A("Unplugged", "Unplugger", "little spending on mobile and internet"),
    ("spend_share_travel", "high"): A("Jet-Setting", "Traveler", "a big share of spending on travel"),
    ("spend_share_travel", "low"): A("Homebound", "Homebody", "little travel spending"),
    ("spend_share_utilities", "high"): A(
        "Household-Running", "Homeowner", "a big share of spending on household bills"),
    ("spend_share_utilities", "low"): A("Lean-Living", "Lodger", "little spending on household bills"),
    # ---- yes / no flags ------------------------------------------------------------
    ("digital_app_user", "more"): A("Digital-First", "App Native", "confidence using digital financial products"),
    ("digital_app_user", "fewer"): A("Traditional", "Branch Banker", "a preference for branch banking"),
    ("frugal_flag", "more"): A(
        "Disciplined", "Saver", "a strong savings habit with spare cash flow from frugality"),
    ("frugal_flag", "fewer"): A("Free-Spending", "Splurger", "a relaxed attitude to spending"),
    ("email_valid", "more"): A("Inbox-Ready", "Email Reader", "an email address we can reach"),
    ("email_valid", "fewer"): A("Off-Grid", "Offliner", "no email address we can reach"),
    ("mobile_valid", "more"): A("Mobile-Ready", "Texter", "a mobile number we can reach"),
    ("mobile_valid", "fewer"): A("Phone-Shy", "Quiet One", "no mobile number we can reach"),
    ("owns_Credit Card", "more"): A("Card-Carrying", "Cardholder", "a credit card with us"),
    ("owns_Credit Card", "fewer"): A("Cash-Paying", "Cash User", "no credit card with us yet"),
    ("owns_Deposit", "more"): A("Deposit-Holding", "Depositor", "a deposit account with us"),
    ("owns_Deposit", "fewer"): A("Liquid", "Cash Keeper", "no deposit account with us yet"),
    ("owns_Insurance", "more"): A("Insured", "Protector", "insurance cover with us"),
    ("owns_Insurance", "fewer"): A("Unprotected", "Self-Insurer", "no insurance cover with us yet"),
    ("owns_Investment", "more"): A("Invested", "Portfolio Builder", "investments with us"),
    ("owns_Investment", "fewer"): A("Untapped", "Future Investor", "no investments with us yet"),
    ("owns_Loan", "more"): A("Credit-Using", "Borrower", "a loan with us"),
    ("owns_Loan", "fewer"): A("Debt-Free", "Clean Slate", "no loans with us"),
    # The label rules treat online_shopper as a flag, so it can arrive as more/fewer.
    ("online_shopper", "more"): A("Click-Happy", "Online Shopper", "a strong online shopping habit"),
    ("online_shopper", "fewer"): A("Offline", "Store Shopper", "little online shopping"),
    # ---- categories ---------------------------------------------------------------
    ("segment", "Mass"): A("Everyday", "Earner", "an everyday mass-market relationship"),
    ("segment", "Mid-Market"): A("Rising", "Climber", "a growing mid-market relationship"),
    ("segment", "Affluent-Preferred"): A("Affluent", "Achiever", "an affluent preferred relationship"),
    ("segment", "Affluent-Gold"): A("Premium", "Elite", "a premium gold relationship"),
    ("age_band", "18-24"): A("Young", "Starter", "a life just starting out"),
    ("age_band", "25-34"): A("Up-and-Coming", "Young Professional", "an early-career life stage"),
    ("age_band", "35-44"): A("Established", "Family Builder", "a mid-career family-building life stage"),
    ("age_band", "45-54"): A("Seasoned", "Peak Earner", "their peak earning years"),
    ("age_band", "55+"): A("Golden", "Pre-Retiree", "retirement on the horizon"),
    ("region", "Luzon"): A("Luzon-Based", "Luzon Local", "a home in Luzon"),
    ("region", "Visayas"): A("Island-Based", "Visayan", "a home in the Visayas"),
    ("region", "Mindanao"): A("Southern", "Mindanaoan", "a home in Mindanao"),
    ("region", "NCR"): A("Metro", "Metro Local", "a home in Metro Manila"),
    ("sec_class", "A"): A("Upscale", "Top Earner", "a top socio-economic class lifestyle"),
    ("sec_class", "B1"): A("Upper-Middle", "Professional", "an upper-middle-class lifestyle"),
    ("sec_class", "B2"): A("Comfortable", "Middle Earner", "a comfortable middle-class lifestyle"),
    ("sec_class", "C1"): A("Working", "Go-Getter", "a working-class lifestyle"),
    ("sec_class", "C2"): A("Budget-Minded", "Striver", "a budget-minded lifestyle"),
    ("sec_class", "D"): A("Resourceful", "Hustler", "a tight and resourceful budget"),
    ("inflow_type", "Business"): A("Enterprising", "Business Owner", "income from a business"),
    ("inflow_type", "Mixed"): A("Multi-Income", "Juggler", "a mix of income sources"),
    ("inflow_type", "Remittance"): A("Overseas-Funded", "Remittance Receiver", "remittances as their main income"),
    ("inflow_type", "Salary"): A("Salaried", "Salary Earner", "a salary as their main income"),
    ("online_shopper", "Low"): A("Offline", "Store Shopper", "little online shopping"),
    ("online_shopper", "Medium"): A("Casual", "Browser", "a casual online shopping habit"),
    ("online_shopper", "High"): A("Click-Happy", "Online Shopper", "a strong online shopping habit"),
    ("online_shopper", "Very High"): A("Cart-Loving", "E-Shopper", "a very strong online shopping habit"),
    ("online_shopper", "Ultra High"): A("Shop-Obsessed", "Power Shopper", "an intense online shopping habit"),
}

# Last-resort qualifiers (no letters, no numbers) for a set that still collides.
_QUALIFIERS = ("Classic", "Modern", "Core", "True", "Prime", "Bold", "Quiet", "Keen")
NAME_MAX_CHARS = 40


def trait_key(attr: str, direction: str | None, focus: str | None,
              is_flag: bool) -> tuple[str, str] | None:
    """The archetype key for one distinguishing trait, or None if unusable.

    A text category reads its focus category (a rare "fewer" focus has no
    archetype); a flag maps high/low to more/fewer; a numeric uses high/low.
    """
    direction = (direction or "").lower()
    if focus is not None:
        return None if direction == "fewer" else (attr, str(focus))
    if is_flag:
        direction = {"high": "more", "low": "fewer"}.get(direction, direction)
        return (attr, direction) if direction in ("more", "fewer") else None
    return (attr, direction) if direction in ("high", "low") else None


def archetypes_for(keys: Iterable[tuple[str, str] | None]) -> list[Archetype]:
    """The archetypes for ``keys`` in order, skipping unknown ones."""
    return [ARCHETYPES[k] for k in keys if k is not None and k in ARCHETYPES]


def _ok(adjective: str, noun: str) -> bool:
    """A usable pairing: the two words don't repeat each other."""
    a, n = adjective.lower(), noun.lower()
    stem = a.split("-")[0][:5]
    return stem not in n and n.split()[0][:5] not in a


def _fits(name: str) -> bool:
    return 2 <= len(name.split()) <= 4 and len(name) <= NAME_MAX_CHARS


def archetype_name(traits: Sequence[Archetype], taken: Iterable[str]) -> str | None:
    """A unique archetype name from the persona's ordered traits, or None.

    ``traits`` are the persona's distinguishing traits, strongest first.
    ``taken`` (compared case-insensitively) is not mutated.
    """
    if not traits:
        return None
    used = {t.casefold() for t in taken}
    p = traits[0]
    s = traits[1] if len(traits) > 1 else None
    t = traits[2] if len(traits) > 2 else None
    candidates: list[tuple[str, str]] = []
    if s is not None:
        candidates += [(s.adjective, p.noun), (p.adjective, s.noun)]
    candidates.append((p.adjective, p.noun))
    if t is not None:
        candidates += [(t.adjective, p.noun), (p.adjective, t.noun)]
        if s is not None:
            candidates += [(t.adjective, s.noun), (s.adjective, t.noun)]
    if s is not None:
        candidates.append((s.adjective, s.noun))
    for adjective, noun in candidates:
        name = f"{adjective} {noun}"
        if _ok(adjective, noun) and _fits(name) and name.casefold() not in used:
            return name
    for q in _QUALIFIERS:
        name = f"{q} {p.adjective} {p.noun}"
        if _fits(name) and name.casefold() not in used:
            return name
    return None


def people_with(traits: Sequence[Archetype], limit: int = 3) -> str:
    """ "a strong savings habit, comfort with ... and ..." for the description."""
    phrases = [a.phrase for a in traits[:limit]]
    if not phrases:
        return ""
    if len(phrases) == 1:
        return phrases[0]
    return f"{', '.join(phrases[:-1])} and {phrases[-1]}"


__all__ = ["Archetype", "ARCHETYPES", "trait_key", "archetypes_for", "archetype_name", "people_with"]
