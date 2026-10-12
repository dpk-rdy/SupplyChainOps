"""Synthetic bid history for a structural-steel fabricator and erector.

The generator is seeded and deterministic. It plants structure a real shop would have, so the
analytic layer has something true to recover:

* some project types fit the shop (warehouse, industrial, K-12) and some do not (healthcare, podium);
* relationship general contractors award more often and price-shopping ones less;
* win odds fall with distance, markup, bidder count and very large tonnage;
* estimated gross margin slips on complex, far-away and change-order-heavy work.

None of this is Weibee Steel data. The point is to show the pipeline end to end; the schema in
``docs/data_dictionary.md`` is what the real intake would capture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from bid_intelligence import config as C

ESTIMATORS = ["M. Alvarez", "J. Whitfield", "D. Okafor"]
LEAD_SOURCES = ["GC invitation", "Repeat customer", "Lead service", "Architect / engineer", "Owner direct"]


@dataclass
class _GC:
    customer_id: str
    name: str
    city: str
    state: str
    tier: str
    relationship: float  # hidden 0..1: how much they like working with us
    price_sensitivity: float  # hidden 0..1
    co_friction: float  # hidden 0..1: how hard change orders are to get paid
    pay_days: int
    focus: list[str]
    first_contact: pd.Timestamp
    activity: float  # relative volume of opportunities


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-x))


def estimating_hours(tons: np.ndarray, complexity: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Hidden truth for hours an estimator spends on a bid (the decision layer re-fits this from data)."""
    base = 6.0 + 0.055 * tons * (0.7 + 0.15 * complexity)
    return np.clip(base * np.exp(rng.normal(0, 0.18, len(tons))), 4, 220)


class Generator:
    def __init__(self, seed: int = 42, start: str = "2022-01-03", end: str = "2026-09-28") -> None:
        self.rng = np.random.default_rng(seed)
        self.start = pd.Timestamp(start)
        self.end = pd.Timestamp(end)
        self._city_weights = np.array([c[4] for c in C.CITIES], dtype=float)
        self._city_weights /= self._city_weights.sum()

    # ------------------------------------------------------------------ customers
    def customers(self, n: int = len(C.GC_NAMES)) -> list[_GC]:
        rng = self.rng
        gcs: list[_GC] = []
        type_keys = [p.key for p in C.PROJECT_TYPES]
        for i, name in enumerate(C.GC_NAMES[:n]):
            ci = rng.choice(len(C.CITIES), p=self._city_weights)
            city, state = C.CITIES[ci][0], C.CITIES[ci][1]
            tier = rng.choice(["local", "regional", "national"], p=[0.45, 0.40, 0.15])
            relationship = float(np.clip(rng.beta(2.2, 2.2), 0.03, 0.97))
            if tier == "national":
                relationship *= 0.8
            price_sens = float(np.clip(rng.beta(2, 2) + (0.2 if tier == "national" else 0), 0.02, 0.98))
            co_friction = float(np.clip(rng.beta(1.8, 3.0) + 0.25 * price_sens, 0.02, 0.98))
            pay_days = int(np.clip(rng.normal(42 + 25 * price_sens, 8), 25, 95))
            focus = list(rng.choice(type_keys, size=int(rng.integers(2, 5)), replace=False))
            first_contact = self.start - pd.Timedelta(days=int(rng.integers(0, 365 * 6)))
            activity = float(rng.gamma(2.0, 1.0)) * (1.6 if tier != "local" else 1.0)
            gcs.append(
                _GC(
                    f"GC-{i + 1:03d}",
                    name,
                    city,
                    state,
                    tier,
                    relationship,
                    price_sens,
                    co_friction,
                    pay_days,
                    focus,
                    first_contact,
                    activity,
                )
            )
        return gcs

    # ------------------------------------------------------------------ opportunities
    def _city(self, gc: _GC) -> tuple[str, str, float]:
        rng = self.rng
        if rng.random() < 0.55:
            matches = [c for c in C.CITIES if c[1] == gc.state]
            w = np.array([c[4] for c in matches], dtype=float)
            c = matches[rng.choice(len(matches), p=w / w.sum())]
        else:
            c = C.CITIES[rng.choice(len(C.CITIES), p=self._city_weights)]
        dist = haversine_miles(C.HOME_BASE["lat"], C.HOME_BASE["lon"], c[2], c[3])
        return c[0], c[1], round(dist * (1 + 0.12 * rng.random()), 0)  # road factor

    def _project_type(self, gc: _GC) -> C.ProjectType:
        rng = self.rng
        if rng.random() < 0.65:
            return C.PROJECT_TYPE_BY_KEY[rng.choice(gc.focus)]
        return C.PROJECT_TYPES[rng.integers(len(C.PROJECT_TYPES))]

    def _delivery_method(self, pt: C.ProjectType, gc: _GC) -> str:
        rng = self.rng
        hard = pt.hard_bid_share * (0.8 if gc.relationship > 0.7 else 1.0)
        if rng.random() < hard:
            return "hard_bid"
        keys = ["cmar", "negotiated", "design_build"]
        w = np.array([C.DELIVERY_METHODS[k][3] for k in keys])
        if gc.relationship > 0.7:
            w = w * np.array([1.0, 1.8, 1.0])
        return str(rng.choice(keys, p=w / w.sum()))

    def _opportunity(self, idx: int, gc: _GC, due: pd.Timestamp, pipeline: bool) -> dict:
        rng = self.rng
        pt = self._project_type(gc)
        city, state, dist = self._city(gc)
        tons = float(np.round(np.exp(rng.normal(np.log(pt.median_tons * 0.85), pt.tons_sigma)), 0))
        tons = max(15.0, tons)
        complexity = int(np.clip(np.round(rng.normal(pt.complexity_mean, 0.8)), 1, 5))
        method = self._delivery_method(pt, gc)
        scope = "fab_erect" if rng.random() < 0.82 else "fab_only"
        lead_weeks = int(rng.integers(10, 27))
        fab_rate = float(rng.uniform(32, 58))  # tons/week this job can absorb in the shop
        fab_weeks = max(2, int(math.ceil(tons / fab_rate)))
        fab_start = (due + pd.Timedelta(weeks=lead_weeks)).normalize()
        fab_start = fab_start - pd.Timedelta(days=fab_start.weekday())
        erection_weeks = max(1, int(math.ceil(fab_weeks * rng.uniform(0.6, 1.1))))
        prefix = "P" if pipeline else "O"
        return {
            "opportunity_id": f"{prefix}-{idx:04d}",
            "project_name": f"{pt.label.split(' /')[0]} - {city} #{idx}",
            "customer_id": gc.customer_id,
            "project_type": pt.key,
            "city": city,
            "state": state,
            "distance_miles": dist,
            "est_tons": tons,
            "complexity": complexity,
            "delivery_method": method,
            "scope": scope,
            "bid_due_date": due,
            "fab_start_week": fab_start,
            "fab_weeks": fab_weeks,
            "erection_weeks": erection_weeks,
            "lead_source": str(rng.choice(LEAD_SOURCES, p=[0.45, 0.2, 0.2, 0.1, 0.05])),
            "_pt": pt,
            "_gc": gc,
        }

    # ------------------------------------------------------------------ bids + outcomes
    def _win_logit(self, o: dict, markup: float, bidders: int, intercept: float) -> float:
        pt, gc = o["_pt"], o["_gc"]
        x = intercept + pt.win_logit + C.DELIVERY_METHODS[o["delivery_method"]][2]
        x += 1.7 * (gc.relationship - 0.5)
        x -= 0.0035 * max(0.0, o["distance_miles"] - 80)
        x -= 0.22 * max(0, bidders - 3)
        x -= 9.0 * (markup - 0.17) * (0.6 + 0.8 * gc.price_sensitivity)
        x -= 0.55 * max(0.0, math.log(o["est_tons"] / 700))
        x -= 0.18 * max(0, o["complexity"] - 3)
        return x

    def _bid(self, o: dict, intercept: float) -> dict:
        rng = self.rng
        gc = o["_gc"]
        tons, cx = o["est_tons"], o["complexity"]
        shop_hpt = 13.0 + 3.6 * (cx - 3) + rng.normal(0, 1.2)
        shop_hours = max(4.0, tons * shop_hpt)
        field_hours = (
            max(0.0, tons * (8.5 + 2.2 * (cx - 3) + rng.normal(0, 1.0))) if o["scope"] == "fab_erect" else 0.0
        )
        material = tons * C.MATERIAL_COST_PER_TON * (1 + 0.06 * (cx - 3)) * np.exp(rng.normal(0, 0.05))
        direct = material + shop_hours * C.SHOP_RATE_PER_HOUR + field_hours * C.FIELD_RATE_PER_HOUR
        overhead = 0.12 * direct
        markup = float(
            np.clip(
                rng.normal(0.175, 0.035) - 0.03 * gc.price_sensitivity * (o["delivery_method"] == "hard_bid"),
                0.06,
                0.32,
            )
        )
        price = (direct + overhead) * (1 + markup)
        bidders = int(max(1, rng.poisson(C.DELIVERY_METHODS[o["delivery_method"]][1] - 1) + 1))
        est_hours = float(estimating_hours(np.array([tons]), np.array([cx]), rng)[0])
        p_win = float(_sigmoid(self._win_logit(o, markup, bidders, intercept)))
        u = rng.random()
        cancelled = rng.random() < 0.05
        if cancelled:
            result, reason = "cancelled", "cancelled"
        elif u < p_win:
            result, reason = "won", None
        else:
            result = "lost"
            reason = str(
                rng.choice(
                    ["price", "relationship", "schedule", "scope", "unknown"],
                    p=[0.56, 0.17, 0.10, 0.07, 0.10],
                )
            )
        comp_low = None
        if result == "lost" and reason == "price" and rng.random() < 0.65:
            gap = float(
                np.clip(
                    rng.normal(
                        0.055 + 0.05 * gc.price_sensitivity + 0.02 * (o["delivery_method"] == "hard_bid"),
                        0.035,
                    ),
                    0.005,
                    0.25,
                )
            )
            comp_low = price * (1 - gap)
        elif result == "won" and rng.random() < 0.40:
            comp_low = price * (1 + float(np.clip(rng.normal(0.04, 0.03), 0.002, 0.2)))  # next-lowest bid
        award = o["bid_due_date"] + pd.Timedelta(weeks=int(rng.integers(2, 9)))
        if award > self.end:  # not decided yet as of the snapshot date
            result, reason, comp_low = "pending", None, None
        return {
            "opportunity_id": o["opportunity_id"],
            "bid_id": o["opportunity_id"].replace("O-", "B-"),
            "estimator": str(rng.choice(ESTIMATORS, p=[0.45, 0.35, 0.20])),
            "bid_date": o["bid_due_date"],
            "estimating_hours": round(est_hours, 1),
            "est_shop_hours": round(shop_hours, 0),
            "est_field_hours": round(field_hours, 0),
            "est_material_cost": round(float(material), 0),
            "est_direct_cost": round(float(direct), 0),
            "est_overhead": round(float(overhead), 0),
            "markup_pct": round(markup, 4),
            "bid_price": round(float(price), 0),
            "num_bidders": bidders,
            "result": result,
            "result_date": None
            if result == "pending"
            else (award if result != "cancelled" else award + pd.Timedelta(weeks=4)),
            "lost_reason": reason,
            "competitor_low_price": None if comp_low is None else round(float(comp_low), 0),
            "_p_win_true": p_win,
        }

    def _job(self, o: dict, b: dict) -> dict:
        rng = self.rng
        pt, gc = o["_pt"], o["_gc"]
        cx, dist = o["complexity"], o["distance_miles"]
        fab_start = max(o["fab_start_week"], b["result_date"] + pd.Timedelta(weeks=6))
        fab_start = fab_start - pd.Timedelta(days=fab_start.weekday())
        fab_end = fab_start + pd.Timedelta(weeks=o["fab_weeks"])
        erect_end = fab_end + pd.Timedelta(weeks=o["erection_weeks"])
        complete = erect_end <= self.end
        slip_core = pt.margin_slip * 2.6 + 0.045 * (cx - 3) + 0.10 * gc.co_friction
        shop_var = rng.normal(slip_core, 0.07)
        field_var = rng.normal(slip_core + (0.10 if dist > C.FAR_JOB_MILES else 0.0), 0.10)
        mat_var = rng.normal(0.01, 0.025)
        actual_tons = o["est_tons"] * (1 + rng.normal(0.01, 0.03))
        shop_act = b["est_shop_hours"] * (1 + shop_var)
        field_act = b["est_field_hours"] * (1 + field_var)
        mat_act = b["est_material_cost"] * (1 + mat_var)
        co_requested = b["bid_price"] * float(np.clip(rng.gamma(1.6, 0.025), 0, 0.25))
        co_approved = co_requested * float(np.clip(1 - gc.co_friction * rng.uniform(0.3, 1.0), 0.1, 1.0))
        actual_direct = mat_act + shop_act * C.SHOP_RATE_PER_HOUR + field_act * C.FIELD_RATE_PER_HOUR
        actual_direct += co_requested * 0.62  # change-order work costs money whether or not it gets approved
        revenue = b["bid_price"] + co_approved
        sched_var = rng.normal(2 + 25 * max(0.0, field_var), 9)
        ncr = int(rng.poisson(0.6 + 0.9 * max(0, cx - 2)))
        out = {
            "job_id": o["opportunity_id"].replace("O-", "J-"),
            "opportunity_id": o["opportunity_id"],
            "fab_start_week": fab_start,
            "fab_end_week": fab_end,
            "erection_end_week": erect_end,
            "status": "complete" if complete else "in_progress",
            "contract_value": b["bid_price"],
        }
        if complete:
            out.update(
                {
                    "actual_tons": round(actual_tons, 0),
                    "actual_shop_hours": round(shop_act, 0),
                    "actual_field_hours": round(field_act, 0),
                    "actual_material_cost": round(mat_act, 0),
                    "change_orders_requested": round(co_requested, 0),
                    "change_orders_approved": round(co_approved, 0),
                    "final_revenue": round(revenue, 0),
                    "actual_direct_cost": round(actual_direct, 0),
                    "schedule_variance_days": int(round(sched_var)),
                    "ncr_count": ncr,
                    "days_to_final_payment": int(np.clip(rng.normal(gc.pay_days, 10), 15, 150)),
                }
            )
        return out

    # ------------------------------------------------------------------ orchestration
    def _calibrate_intercept(self, opps: list[dict], target_rate: float = 0.29) -> float:
        """Choose the hidden intercept so that the average true win probability hits the target."""
        rng_state = self.rng.bit_generator.state
        lo, hi = -4.0, 4.0
        for _ in range(40):
            mid = (lo + hi) / 2
            ps = [
                _sigmoid(
                    self._win_logit(o, 0.17, int(round(C.DELIVERY_METHODS[o["delivery_method"]][1])), mid)
                )
                for o in opps
            ]
            if float(np.mean(ps)) < target_rate:
                lo = mid
            else:
                hi = mid
        self.rng.bit_generator.state = rng_state
        return (lo + hi) / 2

    def generate(self, n_opportunities: int = 440, n_pipeline: int = 90) -> dict[str, pd.DataFrame]:
        rng = self.rng
        gcs = self.customers()
        act = np.array([g.activity for g in gcs])
        act /= act.sum()
        span_days = (self.end - self.start).days

        opps: list[dict] = []
        for i in range(1, n_opportunities + 1):
            gc = gcs[rng.choice(len(gcs), p=act)]
            due = self.start + pd.Timedelta(days=int(rng.integers(0, span_days)))
            opps.append(self._opportunity(i, gc, due, pipeline=False))
        opps.sort(key=lambda o: o["bid_due_date"])
        for i, o in enumerate(opps, start=1):  # renumber chronologically
            o["opportunity_id"] = f"O-{i:04d}"
            o["project_name"] = o["project_name"].rsplit("#", 1)[0] + f"#{i}"

        intercept = self._calibrate_intercept(opps)
        bids: list[dict] = []
        jobs: list[dict] = []
        for o in opps:
            # bid / no-bid decision made historically by gut feel: skip some far / huge / bad-fit work
            p_nobid = (
                0.06
                + 0.18 * (o["distance_miles"] > 300)
                + 0.15 * (o["est_tons"] > 1400)
                + 0.06 * (o["_pt"].key == "healthcare")
            )
            if rng.random() < p_nobid:
                o["decision"] = "no_bid"
                o["no_bid_reason"] = str(
                    rng.choice(["capacity", "geography", "scope_fit", "schedule", "bandwidth"])
                )
                continue
            o["decision"] = "bid"
            o["no_bid_reason"] = None
            b = self._bid(o, intercept)
            bids.append(b)
            if b["result"] == "won":
                jobs.append(self._job(o, b))

        pipeline: list[dict] = []
        for i in range(1, n_pipeline + 1):
            gc = gcs[rng.choice(len(gcs), p=act)]
            due = self.end + pd.Timedelta(days=int(rng.integers(14, 24 * 30)))
            p = self._opportunity(i, gc, due, pipeline=True)
            p["status"] = str(rng.choice(["lead", "invited", "bidding"], p=[0.55, 0.35, 0.10]))
            pipeline.append(p)
        pipeline.sort(key=lambda o: o["bid_due_date"])

        cust_df = pd.DataFrame(
            [
                {
                    "customer_id": g.customer_id,
                    "customer_name": g.name,
                    "hq_city": g.city,
                    "hq_state": g.state,
                    "tier": g.tier,
                    "first_contact_date": g.first_contact,
                    "primary_contact": f"{g.name.split()[0]} preconstruction",
                }
                for g in gcs
            ]
        )
        drop = ["_pt", "_gc"]
        opp_df = pd.DataFrame([{k: v for k, v in o.items() if k not in drop} for o in opps])
        pipe_df = pd.DataFrame([{k: v for k, v in o.items() if k not in drop} for o in pipeline])
        bid_df = pd.DataFrame([{k: v for k, v in b.items() if not k.startswith("_")} for b in bids])
        job_df = pd.DataFrame(jobs)
        cap_df = self.capacity(opp_df["fab_start_week"].min(), self.end + pd.Timedelta(weeks=130))
        truth = pd.DataFrame(
            {"bid_id": [b["bid_id"] for b in bids], "p_win_true": [b["_p_win_true"] for b in bids]}
        )
        return {
            "customers": cust_df,
            "opportunities": opp_df,
            "bids": bid_df,
            "jobs": job_df,
            "pipeline": pipe_df,
            "capacity": cap_df,
            "_truth": truth,  # not loaded into the warehouse; used by tests only
        }

    def capacity(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        weeks = pd.date_range(start - pd.Timedelta(days=start.weekday()), end, freq="W-MON")
        tons = np.where(weeks < pd.Timestamp("2024-07-01"), 120.0, C.SHOP_CAPACITY_TONS_PER_WEEK)
        return pd.DataFrame({"week_start": weeks, "capacity_tons": tons})


def generate(seed: int = 42, **kwargs) -> dict[str, pd.DataFrame]:
    return Generator(seed=seed).generate(**kwargs)
