# novelty

The local skill registry cache, alias normalisation and the novelty filter from ADR-011. Given a candidate card it emits a card (new skill, higher depth, new measurable result, or a non-code `work` item) or increments `counters.json`. It also computes canonical card IDs (ADR-002). The same code is reused by the hub to re-check novelty at merge.
