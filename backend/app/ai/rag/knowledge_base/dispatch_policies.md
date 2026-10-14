# Operational Policy: Ambulance Tiering and Dispatch Fail-Safes (POL-DISPATCH-01)
Category: DISPATCH_POLICY
Source: SahayAI Central Operations & Emergency Governance Manual 2026

## Basic Life Support (BLS) vs Advanced Life Support (ALS) Policy
- BLS Tier Deployment:
  - Indicated for hemodynamically stable patients with non-life-threatening conditions.
  - Examples: isolated closed extremity fractures without shock, minor soft-tissue lacerations, stable fever, mild abdominal discomfort, non-urgent scheduled hospital transfers.
  - Equipment: Stretcher, portable oxygen cylinder, basic splints, automated external defibrillator (AED), sterile bandages.
- ALS Tier Deployment:
  - Indicated for any potential airway, breathing, circulation, or neurological compromise.
  - Examples: active chest pain, unconsciousness, severe respiratory distress, major trauma, status epilepticus, severe burns >10% TBSA, stroke signs within 4.5 hours.
  - Equipment: Multiparameter monitor, manual defibrillator, mechanical ventilator, IV infusion pumps, intubation kit, resuscitation pharmacopeia.

## Dispatch Fail-Safe & Human-in-the-Loop Policies
1. Conflicting Clinical Evidence:
   If caller symptoms and triage findings contradict (e.g. caller states patient is walking normally but report states cardiac arrest), dispatch status MUST be flagged as CONFLICTING and routed to human review immediately.
2. Low Confidence Rule:
   If end-to-end composite confidence is below 0.50, mandatory dispatcher review is triggered before final dispatch.
3. Fail-Safe Principle:
   In cases of doubt between BLS and ALS, always dispatch the higher tier (ALS) to preserve life.
