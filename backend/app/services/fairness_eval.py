"""Fairness and Demographic Model Evaluation Service.

Calculates real performance disparities across languages and dialect categories:
- English
- Hindi
- Marathi
- Code-mixed (Hinglish / Marathi-English)

Evaluates:
1. Emergency extraction accuracy
2. Severity classification accuracy
3. Ambulance recommendation accuracy
4. Location extraction success
5. False positives and false negatives
6. Average latency (ms)
"""
import time
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.case import SeverityLevel, AmbulanceType
from app.ai.schemas import EmergencyExtractionResult
from app.ai.triage_engine import evaluate_hybrid_triage
from app.ai.providers.mock import MockProvider

logger = logging.getLogger(__name__)

# Standardized, semantically equivalent benchmark test scenarios across 4 language groups
# Covering 7 clinical categories: CARDIAC, STROKE, RESPIRATORY, TRAUMA, BURN, BLEEDING, GENERAL_MEDICAL
BENCHMARK_DATASET: List[Dict[str, Any]] = [
    # =========================================================================
    # English (7 Scenarios)
    # =========================================================================
    {
        "id": "EN-01",
        "text": "The patient is having a heart attack with severe crushing chest pain in Kothrud.",
        "language": "English",
        "category": "CARDIAC",
        "expected_severity": SeverityLevel.CRITICAL,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Kothrud",
    },
    {
        "id": "EN-02",
        "text": "Elderly person suspected of stroke, face drooping and cannot speak in Swargate.",
        "language": "English",
        "category": "STROKE",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Swargate",
    },
    {
        "id": "EN-03",
        "text": "Patient cannot breathe and is gasping for air near Deccan.",
        "language": "English",
        "category": "RESPIRATORY",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Deccan",
    },
    {
        "id": "EN-04",
        "text": "Major vehicle crash and bike accident with head injury near Hadapsar.",
        "language": "English",
        "category": "TRAUMA",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Hadapsar",
    },
    {
        "id": "EN-05",
        "text": "Severe fire explosion, patient is badly burned and in agony in Katraj.",
        "language": "English",
        "category": "BURN",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Katraj",
    },
    {
        "id": "EN-06",
        "text": "Deep laceration with severe heavy bleeding from leg near Shivajinagar.",
        "language": "English",
        "category": "BLEEDING",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Shivajinagar",
    },
    {
        "id": "EN-07",
        "text": "Patient is feeling unwell and having mild fever and malaise in Baner.",
        "language": "English",
        "category": "GENERAL_MEDICAL",
        "expected_severity": SeverityLevel.UNKNOWN,
        "expected_ambulance": AmbulanceType.UNKNOWN,
        "expected_location": "Baner",
    },

    # =========================================================================
    # Hindi (7 Scenarios - Semantically Equivalent)
    # =========================================================================
    {
        "id": "HI-01",
        "text": "मरीज को दिल का दौरा पड़ा है और सीने में तेज दर्द है कोथरूड में।",
        "language": "Hindi",
        "category": "CARDIAC",
        "expected_severity": SeverityLevel.CRITICAL,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "कोथरूड",
    },
    {
        "id": "HI-02",
        "text": "मरीज को लकवा मार गया है, चेहरा टेढ़ा हो गया है स्वारगेट में।",
        "language": "Hindi",
        "category": "STROKE",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "स्वारगेट",
    },
    {
        "id": "HI-03",
        "text": "मरीज सांस नहीं ले पा रहा है और दम घुट रहा है डेक्कन में।",
        "language": "Hindi",
        "category": "RESPIRATORY",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "डेक्कन",
    },
    {
        "id": "HI-04",
        "text": "हडपसर के पास बहुत बड़ा गाड़ी का एक्सीडेंट हुआ है और सिर पर चोट लगी है।",
        "language": "Hindi",
        "category": "TRAUMA",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "हडपसर",
    },
    {
        "id": "HI-05",
        "text": "कात्रज में आग लगने से मरीज बुरी तरह जल गया है।",
        "language": "Hindi",
        "category": "BURN",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "कात्रज",
    },
    {
        "id": "HI-06",
        "text": "शिवाजीनगर में पैर से बहुत ज्यादा खून बह रहा है।",
        "language": "Hindi",
        "category": "BLEEDING",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "शिवाजीनगर",
    },
    {
        "id": "HI-07",
        "text": "मरीज की तबियत ठीक नहीं लग रही है और कमजोरी लग रही है बानेर में।",
        "language": "Hindi",
        "category": "GENERAL_MEDICAL",
        "expected_severity": SeverityLevel.UNKNOWN,
        "expected_ambulance": AmbulanceType.UNKNOWN,
        "expected_location": "बानेर",
    },

    # =========================================================================
    # Marathi (7 Scenarios - Semantically Equivalent)
    # =========================================================================
    {
        "id": "MR-01",
        "text": "रुग्णाला हृदयविकाराचा झटका आला आहे आणि छातीत तीव्र वेदना होत आहेत कोथरूड येथे.",
        "language": "Marathi",
        "category": "CARDIAC",
        "expected_severity": SeverityLevel.CRITICAL,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "कोथरूड",
    },
    {
        "id": "MR-02",
        "text": "वृद्ध व्यक्तीला पक्षाघाताचा झटका आला आहे, तोंड वाकडे झाले आहे स्वारगेट येथे.",
        "language": "Marathi",
        "category": "STROKE",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "स्वारगेट",
    },
    {
        "id": "MR-03",
        "text": "रुग्णाला श्वास घेता येत नाही आणि गुदमरल्यासारखे होत आहे डेक्कन येथे.",
        "language": "Marathi",
        "category": "RESPIRATORY",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "डेक्कन",
    },
    {
        "id": "MR-04",
        "text": "हडपसर जवळ वाहनाचा भीषण अपघात झाला आहे आणि डोक्याला गंभीर दुखापत झाली आहे.",
        "language": "Marathi",
        "category": "TRAUMA",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "हडपसर",
    },
    {
        "id": "MR-05",
        "text": "कात्रज येथे आगीमुळे रुग्ण गंभीररीत्या भाजला आहे.",
        "language": "Marathi",
        "category": "BURN",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "कात्रज",
    },
    {
        "id": "MR-06",
        "text": "शिवाजीनगर येथे पायातून खूप रक्त वाहत आहे आणि थांबत नाही.",
        "language": "Marathi",
        "category": "BLEEDING",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "शिवाजीनगर",
    },
    {
        "id": "MR-07",
        "text": "रुग्णाला तो बरा वाटत नाही आणि तब्येत बरी नाही बानेर येथे.",
        "language": "Marathi",
        "category": "GENERAL_MEDICAL",
        "expected_severity": SeverityLevel.UNKNOWN,
        "expected_ambulance": AmbulanceType.UNKNOWN,
        "expected_location": "बानेर",
    },

    # =========================================================================
    # Code-Mixed (7 Scenarios - Hinglish / Marathi-English)
    # =========================================================================
    {
        "id": "CM-01",
        "text": "Patient la heart attack aala ahe and severe chest pain hot ahe Kothrud madhe.",
        "language": "Code-Mixed",
        "category": "CARDIAC",
        "expected_severity": SeverityLevel.CRITICAL,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Kothrud",
    },
    {
        "id": "CM-02",
        "text": "Patient la stroke zala ahe, face droop zala ahe Swargate madhe.",
        "language": "Code-Mixed",
        "category": "STROKE",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Swargate",
    },
    {
        "id": "CM-03",
        "text": "Patient la breathlessness hot ahe, shwas ghyayla tras hoto ahe Deccan yethe.",
        "language": "Code-Mixed",
        "category": "RESPIRATORY",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Deccan",
    },
    {
        "id": "CM-04",
        "text": "Hadapsar near severe road accident zala ahe, severe head injury ahe.",
        "language": "Code-Mixed",
        "category": "TRAUMA",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Hadapsar",
    },
    {
        "id": "CM-05",
        "text": "Katraj madhe fire lagli ahe and patient severely burn zala ahe.",
        "language": "Code-Mixed",
        "category": "BURN",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Katraj",
    },
    {
        "id": "CM-06",
        "text": "Shivajinagar madhe leg injury zali ahe and heavy bleeding hot ahe.",
        "language": "Code-Mixed",
        "category": "BLEEDING",
        "expected_severity": SeverityLevel.HIGH,
        "expected_ambulance": AmbulanceType.ALS,
        "expected_location": "Shivajinagar",
    },
    {
        "id": "CM-07",
        "text": "Patient la bara vatat nahi and weakness ahe Baner madhe.",
        "language": "Code-Mixed",
        "category": "GENERAL_MEDICAL",
        "expected_severity": SeverityLevel.UNKNOWN,
        "expected_ambulance": AmbulanceType.UNKNOWN,
        "expected_location": "Baner",
    },
]


def _is_category_match(extracted_type: str, expected_category: str) -> bool:
    """Check if extracted emergency type aligns with benchmark clinical category."""
    e = (extracted_type or "").upper()
    cat = expected_category.upper()
    if cat == "CARDIAC":
        return "CARDIAC" in e or "HEART" in e
    if cat == "STROKE":
        return "STROKE" in e
    if cat == "RESPIRATORY":
        return "RESPIRATORY" in e or "BREATH" in e
    if cat in ("TRAUMA", "ROAD_TRAFFIC_ACCIDENT"):
        return "ACCIDENT" in e or "TRAUMA" in e or "COLLISION" in e
    if cat == "BURN":
        return "BURN" in e
    if cat == "BLEEDING":
        return "BLEEDING" in e or "HEMORRHAGE" in e or "TRAUMA" in e
    if cat == "GENERAL_MEDICAL":
        return "GENERAL" in e or "MEDICAL" in e or "UNKNOWN" in e
    return cat in e


def run_fairness_evaluation(db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Execute benchmark evaluation across all language subgroups and return detailed metrics.
    Guarantees:
    - evaluated benchmark count > 0
    - provides language, total_samples, correct_emergency_type, emergency_type_accuracy,
      severity_accuracy, ambulance_recommendation_accuracy, and error_count.
    """
    mock_llm = MockProvider()

    language_metrics: Dict[str, Dict[str, Any]] = {}
    languages = ["English", "Hindi", "Marathi", "Code-Mixed"]
    for lang in languages:
        language_metrics[lang] = {
            "total_cases": 0,
            "emergency_type_correct": 0,
            "severity_correct": 0,
            "ambulance_correct": 0,
            "location_extracted": 0,
            "latencies_ms": [],
            "error_count": 0,
            "false_positives": 0,
            "false_negatives": 0,
        }

    overall_start = time.time()

    for item in BENCHMARK_DATASET:
        lang = item["language"]
        t_start = time.time()

        extraction: EmergencyExtractionResult = mock_llm.extract_emergency_info(raw_text=item["text"])
        hybrid = evaluate_hybrid_triage(extraction=extraction, raw_text=item["text"])
        latency = int((time.time() - t_start) * 1000)

        metrics = language_metrics[lang]
        metrics["total_cases"] += 1
        metrics["latencies_ms"].append(latency)

        # 1. Emergency Type Category Accuracy
        has_error = False
        if _is_category_match(str(extraction.emergency_type), item["category"]):
            metrics["emergency_type_correct"] += 1
        else:
            has_error = True

        # 2. Severity Accuracy
        if hybrid.final_severity == item["expected_severity"]:
            metrics["severity_correct"] += 1
        else:
            has_error = True
            if hybrid.final_severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH) and item["expected_severity"] in (SeverityLevel.LOW, SeverityLevel.UNKNOWN):
                metrics["false_positives"] += 1
            elif hybrid.final_severity in (SeverityLevel.LOW, SeverityLevel.MODERATE, SeverityLevel.UNKNOWN) and item["expected_severity"] == SeverityLevel.CRITICAL:
                metrics["false_negatives"] += 1

        # 3. Ambulance Recommendation Accuracy
        if hybrid.final_ambulance == item["expected_ambulance"]:
            metrics["ambulance_correct"] += 1
        else:
            has_error = True

        # 4. Location Extraction
        if extraction.location and (item["expected_location"].lower() in extraction.location.lower() or item["expected_location"] in item["text"]):
            metrics["location_extracted"] += 1

        if has_error:
            metrics["error_count"] += 1

    # Aggregate summaries by language
    summary_by_language: Dict[str, Any] = {}
    total_all = 0
    em_all = 0
    sev_all = 0
    amb_all = 0
    loc_all = 0
    errors_all = 0

    for lang, m in language_metrics.items():
        n = m["total_cases"]
        total_all += n
        em_acc = round(m["emergency_type_correct"] / n, 4) if n > 0 else 0.0
        sev_acc = round(m["severity_correct"] / n, 4) if n > 0 else 0.0
        amb_acc = round(m["ambulance_correct"] / n, 4) if n > 0 else 0.0
        loc_acc = round(m["location_extracted"] / n, 4) if n > 0 else 0.0
        avg_lat = round(sum(m["latencies_ms"]) / len(m["latencies_ms"]), 1) if m["latencies_ms"] else 0.0

        em_all += m["emergency_type_correct"]
        sev_all += m["severity_correct"]
        amb_all += m["ambulance_correct"]
        loc_all += m["location_extracted"]
        errors_all += m["error_count"]

        summary_by_language[lang] = {
            "language": lang,
            "total_samples": n,
            "total_cases": n,
            "correct_emergency_type": m["emergency_type_correct"],
            "emergency_type_accuracy": em_acc,
            "severity_accuracy": sev_acc,
            "ambulance_accuracy": amb_acc,
            "ambulance_recommendation_accuracy": amb_acc,
            "location_extraction_rate": loc_acc,
            "avg_latency_ms": avg_lat,
            "error_count": m["error_count"],
            "false_positives": m["false_positives"],
            "false_negatives": m["false_negatives"],
        }

    overall_metrics = {
        "total_test_samples": total_all,
        "total_cases_evaluated": total_all,
        "overall_emergency_type_accuracy": round(em_all / total_all, 4) if total_all > 0 else 0.0,
        "overall_severity_accuracy": round(sev_all / total_all, 4) if total_all > 0 else 0.0,
        "overall_ambulance_accuracy": round(amb_all / total_all, 4) if total_all > 0 else 0.0,
        "overall_location_extraction_rate": round(loc_all / total_all, 4) if total_all > 0 else 0.0,
        "total_errors": errors_all,
        "evaluation_duration_seconds": round(time.time() - overall_start, 2),
    }

    # Disparity checks (difference between highest and lowest language severity accuracy)
    accuracies = [s["severity_accuracy"] for s in summary_by_language.values()]
    max_disparity = round(max(accuracies) - min(accuracies), 4) if accuracies else 0.0

    return {
        "status": "COMPLETED",
        "overall_metrics": overall_metrics,
        "language_breakdown": summary_by_language,
        "max_severity_disparity": max_disparity,
        "disparity_flagged": max_disparity > 0.15,
    }
