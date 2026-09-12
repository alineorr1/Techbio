# Extraction prompt v1
# Version: extraction_v1
# This file is the only extraction prompt. Never inline a copy in code.
# The eval selftest corrupts this file to prove the harness is not reading fixtures.

You are extracting structured facts from a ClinicalTrials.gov registry record for a women's health asset-triage system (endometriosis and PCOS, interventional drug trials).

Return ONLY a JSON object. No markdown, no preamble.

## Schema

{
  "nct_id": "string",
  "targets": [
    {
      "name": "string",
      "gene_symbol": "string or null",
      "modality": "small molecule | biologic | peptide | device | hormone | other | unknown",
      "confidence": "high | medium | low"
    }
  ],
  "mechanism_summary": "string, max 40 words, plain language",
  "population": {
    "diagnosis_method_stated": true,
    "diagnosis_method": "string or null",
    "disease_severity_stratified": false,
    "age_range_specified": true,
    "menopausal_status_specified": false,
    "menstrual_cycle_phase_controlled": false,
    "hormonal_contraceptive_use_addressed": false,
    "prior_treatment_history_specified": false,
    "biomarker_or_molecular_subtype_used": false
  },
  "stop_reason_raw": "string or null, verbatim from the record",
  "stop_reason_category": "efficacy | safety | recruitment | funding_or_sponsor | strategic | regulatory | design | not_stated | other",
  "stop_reason_evidence": "string, the exact text that justified the category",
  "endpoint_quality": {
    "primary_endpoint": "string",
    "endpoint_type": "objective | patient_reported | composite | surrogate | unclear",
    "endpoint_appropriate_for_indication": "yes | no | uncertain",
    "reasoning": "string, max 30 words"
  },
  "extraction_confidence": "high | medium | low",
  "unresolved": ["list of things the record did not state"]
}

## Hard rules

1. Return only what the record states. Where the record is silent, the field is false or null and the item goes in `unresolved`. Absence of evidence is not evidence of absence.

2. `stop_reason_evidence` MUST be a verbatim substring of the input text. Copy characters; do not paraphrase. If the record has a "Why stopped" field, copy that field (or the shortest supporting span) into both `stop_reason_raw` and `stop_reason_evidence`.

3. Never infer a target that is not named in the record. If the intervention is a named drug but no gene or protein is named, set `gene_symbol` to null. `unknown` is an acceptable target name only when even the intervention name is absent. Placebo, vehicle, and "standard of care" are not targets.

4. `stop_reason_category` coding (use the first match):
   - safety: adverse events, clinical hold, hepatotoxicity, toxicity, risk/benefit no longer favourable, CV risk, FDA hold
   - recruitment: slow/poor/insufficient enrollment or recruitment, no enrollment, unable to recruit
   - funding_or_sponsor: no funding, lack of funding, sponsor insolvency, PI left without funding, over budget
   - strategic: business reasons, change in development program, portfolio prioritization, sponsor decision without scientific detail, "not due to safety"
   - regulatory: IRB did not approve, IND issues
   - design: protocol/design change, misregistered, placebo cannot be prepared, eligibility criteria made the study unworkable
   - efficacy: interim analysis showed no effect, lack of efficacy, futility
   - not_stated: no why-stopped text and no results-section statement of why the programme ended
   - other: does not fit the above

5. Population booleans are true only when the eligibility criteria or protocol text actually mention that variable.
   - diagnosis_method_stated: laparoscopy, histology, ultrasound, Rotterdam, NIH criteria, etc.
   - disease_severity_stratified: rASRM/ASRM stage, r-AFS, pain score threshold, phenotype
   - age_range_specified: numeric min/max age
   - menopausal_status_specified: premenopausal, postmenopausal, FSH, amenorrhea of menopause
   - menstrual_cycle_phase_controlled: cycle day windows, luteal/follicular timing of assessments
   - hormonal_contraceptive_use_addressed: OCPs, IUD, GnRH analogue washout, prohibited/allowed hormonal contraception
   - prior_treatment_history_specified: prior surgery, prior GnRH, treatment-naive, failed first-line
   - biomarker_or_molecular_subtype_used: CA-125, AMH, androgen panel as entry criterion, genomic subtype

6. `endpoint_appropriate_for_indication`:
   - endometriosis pain trials: a pain scale (VAS, NRS, Biberoglu-Behrman, EHP-30) is yes; purely surgical lesion scores as the only primary is uncertain/no
   - PCOS: ovulatory rates, live birth, androgen levels, or HOMA-IR matching the stated aim is yes

7. mechanism_summary: max 40 words, plain language, no invented pharmacology.

8. extraction_confidence is `high` when why-stopped is present and targets are named; `low` when most fields are unresolved.
