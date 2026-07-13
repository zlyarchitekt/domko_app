"""Doradca struktury mieszkań (user 2026-07-11): proponuje korekty udziałów
procentowych typów tak, żeby program lepiej wpisywał się w dostępną
powierzchnię netto danego obrysu.

Model oceny kandydata (udziały % per typ):
- `utilization` = suma(count_t × środek_zakresu_t) / net_area — jak blisko
  100% powierzchni netto zagospodaruje program przy liczbie mieszkań
  wyprowadzonej z powierzchni (derive_total_units + allocate_counts,
  dokładnie ta sama para funkcji, której używa silnik podziału — doradca
  nie ma własnej, rozbieżnej arytmetyki).
- `rounding_dev` = suma |zrealizowany% − zadany%| po typach — zniekształcenie
  struktury przez zaokrąglanie do całkowitych mieszkań (np. 10% z 6 mieszkań
  to 0.6 → 1 szt. = faktycznie 16.7%).
Score = |1 − utilization| + ROUNDING_WEIGHT × rounding_dev/100. Niżej = lepiej.

Przeszukiwanie: baseline + przesunięcia PERCENT_STEPS punktów procentowych
między każdą uporządkowaną parą typów (małe, czytelne korekty zamiast
czarnej skrzynki). Zwracane są tylko kandydaci ściśle lepsi od baseline'u.
"""

from dataclasses import dataclass

from services.unit_mix import ProgramShare, allocate_counts, derive_total_units

PERCENT_STEPS = (5, 10)
ROUNDING_WEIGHT = 0.5
MAX_PROPOSALS = 3


@dataclass
class ProgramEvaluation:
    percentages: dict[str, float]
    total_units: int
    counts: dict[str, int]
    used_area_m2: float
    utilization: float
    rounding_dev: float
    score: float


@dataclass
class ProgramProposal(ProgramEvaluation):
    reason: str = ""


def _evaluate(shares: list[ProgramShare], net_area_m2: float) -> ProgramEvaluation | None:
    """None dla kandydata niepoliczalnego (suma udziałów 0, złe zakresy)."""
    try:
        total = derive_total_units(net_area_m2, shares)
        counts = allocate_counts(shares, total)
    except ValueError:
        return None
    used = sum(counts[s.type] * (s.area_min_m2 + s.area_max_m2) / 2.0 for s in shares)
    utilization = used / net_area_m2 if net_area_m2 > 0 else 0.0
    total_pct = sum(s.percentage for s in shares) or 1.0
    n = sum(counts.values()) or 1
    rounding_dev = sum(
        abs(100.0 * counts[s.type] / n - 100.0 * s.percentage / total_pct) for s in shares
    )
    score = abs(1.0 - utilization) + ROUNDING_WEIGHT * rounding_dev / 100.0
    return ProgramEvaluation(
        percentages={s.type: s.percentage for s in shares},
        total_units=total,
        counts=counts,
        used_area_m2=used,
        utilization=utilization,
        rounding_dev=rounding_dev,
        score=score,
    )


def suggest_program(
    shares: list[ProgramShare], net_area_m2: float
) -> tuple[ProgramEvaluation | None, list[ProgramProposal]]:
    """(ocena baseline'u, do MAX_PROPOSALS propozycji lepszych od niego).

    Propozycja = udziały po jednym przesunięciu X p.p. z typu A do typu B.
    Duplikaty (ten sam wektor udziałów) odrzucane, wynik posortowany po score.
    """
    baseline = _evaluate(shares, net_area_m2)
    if baseline is None:
        return None, []

    seen: set[tuple[float, ...]] = {tuple(s.percentage for s in shares)}
    candidates: list[ProgramProposal] = []
    for i, donor in enumerate(shares):
        for j, receiver in enumerate(shares):
            if i == j:
                continue
            for step in PERCENT_STEPS:
                if donor.percentage < step:
                    continue
                new_pcts = [s.percentage for s in shares]
                new_pcts[i] -= step
                new_pcts[j] += step
                key = tuple(new_pcts)
                if key in seen:
                    continue
                seen.add(key)
                variant = [
                    ProgramShare(
                        type=s.type,
                        percentage=new_pcts[k],
                        area_min_m2=s.area_min_m2,
                        area_max_m2=s.area_max_m2,
                        min_facade_m=s.min_facade_m,
                    )
                    for k, s in enumerate(shares)
                ]
                ev = _evaluate(variant, net_area_m2)
                if ev is None or ev.score >= baseline.score - 1e-9:
                    continue
                reason = (
                    f"{step} p.p. z {donor.type} do {receiver.type}: "
                    f"wykorzystanie {ev.utilization * 100:.1f}% "
                    f"(bazowo {baseline.utilization * 100:.1f}%), "
                    f"odchył struktury {ev.rounding_dev:.1f} p.p. "
                    f"(bazowo {baseline.rounding_dev:.1f})"
                )
                candidates.append(ProgramProposal(**ev.__dict__, reason=reason))

    candidates.sort(key=lambda p: p.score)
    return baseline, candidates[:MAX_PROPOSALS]
