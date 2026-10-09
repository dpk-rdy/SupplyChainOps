"""Assumptions that drive the synthetic data and the decision layer.

Every number here is a documented guess for a mid-size Oklahoma structural-steel fabricator and
erector. With real Weibee Steel data the synthetic generator goes away and these become the few
business parameters the scorecard still needs (capacity, rates, estimating cost, thresholds).
"""

from __future__ import annotations

from dataclasses import dataclass

HOME_BASE = {"city": "Washington", "state": "OK", "lat": 35.052, "lon": -97.492}

# ---------------------------------------------------------------- shop + rates
SHOP_CAPACITY_TONS_PER_WEEK = 140.0  # ~7,000 tons/yr at 100 % utilisation
SHOP_RATE_PER_HOUR = 78.0  # loaded shop labour $/hr
FIELD_RATE_PER_HOUR = 92.0  # loaded ironworker $/hr incl. equipment share
MATERIAL_COST_PER_TON = 1_450.0  # mill + supply, 2024-26 average
ESTIMATOR_RATE_PER_HOUR = 85.0  # loaded cost of an estimating hour
TARGET_MARKUP_PCT = 0.18  # default markup when scoring pipeline work (no estimate yet)

# ---------------------------------------------------------------- decision thresholds
CAPACITY_TIGHT_UTILISATION = 0.90  # projected shop load / capacity above this => "tight"
CAPACITY_OVER_UTILISATION = 1.05  # above this => hard flag
FAR_JOB_MILES = 250.0  # erection beyond this needs per-diem crews
MIN_WIN_PROBABILITY = 0.12  # below this a hard bid is a Pass unless strategic
# Expected-value thresholds are relative to what an estimating hour has historically returned in
# gross-margin dollars (won value x estimated margin / hours spent, trailing two years), so they
# re-scale automatically with the shop's own numbers.
PURSUE_EV_RATIO = 0.8  # Pursue when EV per estimating hour beats 80 % of the historical return
REVIEW_EV_RATIO = 0.35  # Review between 35 % and 80 %; Pass below that


@dataclass(frozen=True)
class ProjectType:
    key: str
    label: str
    median_tons: float
    tons_sigma: float  # log-normal sigma
    win_logit: float  # hidden fit with the shop (synthetic ground truth)
    margin_slip: float  # hidden mean (estimated - actual) gross margin, points
    complexity_mean: float  # 1 simple .. 5 AESS / long-span / heavy moment frames
    price_per_ton: float  # typical fab+erect sell price $/ton at complexity 3
    hard_bid_share: float  # share of opportunities that are hard bid (vs CMAR/negotiated/DB)


PROJECT_TYPES: list[ProjectType] = [
    ProjectType("warehouse", "Warehouse / distribution", 380, 0.55, 0.55, 0.004, 1.8, 3_900, 0.45),
    ProjectType("industrial", "Industrial / manufacturing", 420, 0.60, 0.45, 0.006, 2.6, 4_600, 0.40),
    ProjectType("k12", "K-12 school", 230, 0.45, 0.40, 0.008, 2.4, 4_800, 0.30),
    ProjectType("church", "Church / worship", 120, 0.50, 0.30, 0.010, 2.2, 4_900, 0.20),
    ProjectType("retail", "Retail / commercial", 85, 0.50, 0.20, 0.012, 1.9, 4_700, 0.65),
    ProjectType("municipal", "Municipal / civic", 210, 0.50, 0.05, 0.018, 2.9, 5_100, 0.80),
    ProjectType("higher_ed", "Higher education", 310, 0.50, 0.00, 0.022, 3.2, 5_300, 0.35),
    ProjectType("office", "Office", 290, 0.55, -0.10, 0.020, 2.9, 5_000, 0.50),
    ProjectType("sports", "Sports / recreation", 520, 0.55, -0.30, 0.045, 3.9, 5_600, 0.45),
    ProjectType("hospitality", "Hospitality", 260, 0.50, -0.40, 0.030, 3.1, 5_200, 0.55),
    ProjectType("multifamily", "Multifamily podium", 360, 0.50, -0.50, 0.038, 3.4, 5_100, 0.50),
    ProjectType("healthcare", "Healthcare", 470, 0.55, -0.70, 0.045, 4.1, 5_900, 0.30),
]
PROJECT_TYPE_BY_KEY = {p.key: p for p in PROJECT_TYPES}

DELIVERY_METHODS = {
    # key: (label, mean bidders, win logit bump, share of non-hard-bid opportunities)
    "hard_bid": ("Hard bid", 5.5, -0.35, None),
    "cmar": ("CM at risk", 3.5, 0.15, 0.55),
    "negotiated": ("Negotiated", 1.8, 0.75, 0.25),
    "design_build": ("Design-build", 2.5, 0.30, 0.20),
}

LOST_REASONS = ["price", "relationship", "schedule", "capacity", "scope", "cancelled", "unknown"]

SIZE_BANDS = [
    (0, 100, "< 100 t"),
    (100, 250, "100-250 t"),
    (250, 500, "250-500 t"),
    (500, 1_000, "500-1,000 t"),
    (1_000, 10**9, "1,000 t +"),
]
DISTANCE_BANDS = [
    (0, 60, "< 60 mi"),
    (60, 150, "60-150 mi"),
    (150, 250, "150-250 mi"),
    (250, 10**9, "250 mi +"),
]

# city, state, lat, lon, weight (how often work shows up there)
CITIES = [
    ("Oklahoma City", "OK", 35.468, -97.516, 18),
    ("Norman", "OK", 35.222, -97.439, 8),
    ("Edmond", "OK", 35.653, -97.478, 6),
    ("Moore", "OK", 35.339, -97.487, 4),
    ("Tulsa", "OK", 36.154, -95.993, 12),
    ("Broken Arrow", "OK", 36.061, -95.797, 3),
    ("Stillwater", "OK", 36.116, -97.059, 3),
    ("Lawton", "OK", 34.609, -98.390, 3),
    ("Ardmore", "OK", 34.174, -97.144, 2),
    ("Enid", "OK", 36.396, -97.878, 2),
    ("Shawnee", "OK", 35.327, -96.925, 2),
    ("Muskogee", "OK", 35.748, -95.370, 2),
    ("Durant", "OK", 33.994, -96.371, 2),
    ("Dallas", "TX", 32.777, -96.797, 7),
    ("Fort Worth", "TX", 32.755, -97.331, 6),
    ("Denton", "TX", 33.215, -97.133, 3),
    ("Sherman", "TX", 33.636, -96.609, 2),
    ("Wichita Falls", "TX", 33.914, -98.493, 2),
    ("Amarillo", "TX", 35.222, -101.831, 2),
    ("Lubbock", "TX", 33.578, -101.855, 1),
    ("Austin", "TX", 30.267, -97.743, 2),
    ("Wichita", "KS", 37.687, -97.330, 4),
    ("Topeka", "KS", 39.048, -95.678, 1),
    ("Kansas City", "KS", 39.114, -94.627, 2),
    ("Fort Smith", "AR", 35.386, -94.399, 3),
    ("Fayetteville", "AR", 36.062, -94.157, 3),
    ("Little Rock", "AR", 34.746, -92.290, 2),
    ("Joplin", "MO", 37.084, -94.513, 2),
    ("Springfield", "MO", 37.209, -93.292, 2),
    ("Albuquerque", "NM", 35.085, -106.650, 1),
    ("Denver", "CO", 39.739, -104.990, 1),
]

GC_NAMES = [
    "Crossroads Construction",
    "Red River Builders",
    "Sooner State Contractors",
    "Prairie Wind General",
    "Flint Hills Construction",
    "Arbuckle Builders",
    "Canadian River Construction",
    "Timberline GC",
    "Cimarron Commercial",
    "Ouachita Building Group",
    "Great Plains Constructors",
    "Heartland Build Co",
    "Washita Valley Builders",
    "Blue Stem Contracting",
    "Tallgrass Construction",
    "Keystone Commercial Builders",
    "North Fork General Contractors",
    "Boomer Construction Group",
    "Wagon Trail Builders",
    "Caddo Construction",
    "Ironhorse Contractors",
    "Sandstone General",
    "Summit Ridge Construction",
    "Meridian Build Partners",
    "Longhorn Commercial",
    "Trinity Basin Builders",
    "Panhandle Constructors",
    "Cross Timbers Contracting",
    "Verdigris Construction",
    "Osage Builders",
    "Cedar Creek Commercial",
    "Mesa Vista Construction",
    "Pioneer Civic Builders",
    "Lone Elm Construction",
    "Cottonwood General Contractors",
    "Granite Peak Builders",
]
