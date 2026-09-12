# Women's Health Failed Asset Triage Engine

A pipeline and dashboard that finds **clinical-stage endometriosis and PCOS drug programmes that stopped for reasons other than the biology being wrong**, and ranks them as re-acquisition / re-development candidates.

The motivating problem: capital in women's health has clustered in academia and in late-stage de-risked commercial assets. A large number of clinically advanced programmes were shelved because a sponsor ran out of money, a trial under-recruited, a corporate strategy shifted, or a study was designed with a population so poorly defined that a real effect could not have been detected. Those failures are separable from "the mechanism does not work," and they are separable in public data.

The counterexample the scoring rules exist to catch: Organon acquired Forendo Pharma for an endometriosis HSD17B1 programme; that asset, **OG-6219, failed Phase 2 and was discontinued in 2025**. Acquiring overlooked science does not automatically create value. Rule B (the Organon guard) refuses to score an asset above 60 unless independent mechanism evidence **predates** the trial start date.

**Success criterion.** A domain expert opens the dashboard, clicks the top-ranked asset, and can trace every input that produced the score back to a primary source in under thirty seconds.

See the Origin repository `alineorrantia/techbioC` for the full pipeline, dashboard, and workflows.
