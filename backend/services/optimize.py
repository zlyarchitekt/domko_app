"""Kernel optymalizacji (plan 2026-07-14): generator / ewaluator / strategia.

Generator buduje kandydata z genomu i jest poprawny KONSTRUKCYJNIE (np. krajacz
traktowy: mieszkanie zawsze korytarz->elewacja). Ewaluator to czysta funkcja
(genome, payload) -> (score, components, hard_violations). Strategia decyduje,
które genomy próbować w ramach budżetu. Etap 1: RandomSearch (zachowanie 1:1 ze
starą pętlą `for seed in range(N)`); Etap 2 doda SimulatedAnnealing; Etap 3
NSGA-II. Determinizm: wyłącznie random.Random(seed) pochodne od indeksu."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass
class Candidate:
    genome: Any
    payload: Any
    score: float
    components: dict = field(default_factory=dict)
    hard_valid: bool = True
    hard_violations: list = field(default_factory=list)


@dataclass
class Budget:
    evaluations: int


class Generator(Protocol):
    def random_genome(self, rng: random.Random) -> Any: ...
    def mutate(self, genome: Any, rng: random.Random) -> Any: ...
    def build(self, genome: Any) -> Any: ...


Evaluator = Callable[[Any, Any], "tuple[float, dict, list]"]


def evaluate_genome(generator: Generator, evaluator: Evaluator, genome: Any) -> Candidate:
    payload = generator.build(genome)
    score, components, violations = evaluator(genome, payload)
    return Candidate(genome=genome, payload=payload, score=score, components=components,
                     hard_valid=not violations, hard_violations=list(violations))


def run_random_search(generator: Generator, evaluator: Evaluator, budget: Budget) -> list[Candidate]:
    out: list[Candidate] = []
    for i in range(budget.evaluations):
        rng = random.Random(i)
        out.append(evaluate_genome(generator, evaluator, generator.random_genome(rng)))
    return out


def pick_best(candidates: list[Candidate]) -> Candidate:
    """Najniższy score wśród spełniających zakazy; fallback najniższy w ogóle
    (ta sama reguła co unit_mix.pick_best_iteration)."""
    valid = [c for c in candidates if c.hard_valid]
    pool = valid or candidates
    return min(pool, key=lambda c: c.score)


def dedupe_and_rank(candidates: list[Candidate], limit: int) -> list[Candidate]:
    """Unikalne po genomie, ważne przed łamiącymi zakazy, w grupach po score."""
    seen: set = set()
    unique: list[Candidate] = []
    for c in candidates:
        key = c.genome if isinstance(c.genome, (int, float, str, tuple)) else repr(c.genome)
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    unique.sort(key=lambda c: (0 if c.hard_valid else 1, c.score))
    return unique[:limit]
