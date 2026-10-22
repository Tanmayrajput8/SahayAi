"""
Regional Language Medical Terminology Knowledge Base.

Defines standardized clinical concepts, variations, and regional phrasing across:
- Marathi (Devanagari)
- Hindi (Devanagari)
- Code-Mixed (Hinglish & Marathish)
- English

Distinguishes explicitly between:
- EXPLICIT_CONDITION (reported diagnosis, e.g. "हृदयविकाराचा झटका", "heart attack")
- SYMPTOM (clinical sign, e.g. "छातीत दुखत आहे", "chest pain" - NOT confirmed diagnosis)
- ACUITY_MARKER (loss of consciousness, apnea)
- VAGUE_DISTRESS (unspecified malaise, e.g. "तो बरा वाटत नाही")
"""
from typing import Dict, Any, List
from app.models.case import SeverityLevel, AmbulanceType
from app.ai.normalization.schemas import ConceptType

# Medical concept definitions with multi-lingual pattern matches
MEDICAL_TERMS_DB: List[Dict[str, Any]] = [
    # =========================================================================
    # 1. CARDIAC: EXPLICIT CONDITIONS (Heart Attack / Cardiac Arrest)
    # =========================================================================
    {
        "concept_id": "reported_heart_attack",
        "concept_type": ConceptType.EXPLICIT_CONDITION,
        "standardized_text": "reported heart attack",
        "category_hint": "CARDIAC",
        "severity_hint": SeverityLevel.CRITICAL,
        "ambulance_hint": AmbulanceType.ALS,
        "patterns": {
            "mr": [
                "हृदयविकाराचा झटका", "हृदयविकार", "हृदयविकाराची कळ", "हार्ट अटॅक",
                "हार्टअटॅक", "हार्ट अट्याक", "हार्ट अटॅक आला", "हार्ट फेल",
                "हृदय क्रिया बंद", "हृदयाचा ठोका चुकला", "हृदयाचा झटका"
            ],
            "hi": [
                "दिल का दौरा पड़ा", "दिल का दौरा", "हार्ट अटैक पड़ा", "हार्ट अटैक",
                "हार्टअटैक", "दिल की बीमारी का दौरा", "हार्ट अटैक आ गया",
                "दिल की धड़कन रुक", "हार्ट फेल"
            ],
            "en": [
                "cardiac collapse", "heart attack", "cardiac arrest", "cardiac emergency",
                "cardiac", "myocardial infarction", "coronary thrombosis", "heart failure"
            ],
            "code_mixed": [
                "cardiac collapse", "heart attack", "cardiac arrest", "dil ka daura",
                "heart attack ala", "heart attack aala", "heart attack ahe",
                "heart attack zala", "heart attack hua", "heart attack aagaya"
            ],
        },
        "evidence_template": "{lang} expression '{phrase}' indicates explicit reported heart attack (CARDIAC)"
    },

    # =========================================================================
    # 2. CARDIAC: SYMPTOMS (Chest Pain / Angina - NOT confirmed diagnosis!)
    # =========================================================================
    {
        "concept_id": "chest_pain",
        "concept_type": ConceptType.SYMPTOM,
        "standardized_text": "chest pain / discomfort",
        "category_hint": "CARDIAC",
        "severity_hint": SeverityLevel.HIGH,
        "ambulance_hint": AmbulanceType.ALS,
        "patterns": {
            "mr": [
                "छातीत दुखत आहे", "छातीत दुखणे", "छातीत प्रचंड दुखत", "छातीमध्ये वेदना",
                "छातीत कळ येत", "छातीवर वजन", "छाती दाबली जात", "छातीत जळजळ",
                "छातीत भरून आले", "छातीत कळा", "छातीत धडधड", "छाती दुखते"
            ],
            "hi": [
                "सीने में दर्द", "सीने में बहुत दर्द", "छाती में दर्द", "सीने में भारीपन",
                "सीने में जलन", "सीने में खिंचाव", "सीने में चुभन", "छाती में भारीपन"
            ],
            "en": [
                "chest pain", "pain in chest", "chest tightness", "crushing chest pain",
                "chest pressure", "chest discomfort", "angina", "palpitations"
            ],
            "code_mixed": [
                "chest pain", "chest me dard", "chhati madhe pain", "chhati dukhti ahe",
                "chest pain ho raha hai", "chest heaviness"
            ],
        },
        "evidence_template": "{lang} expression '{phrase}' corresponds to acute chest pain symptom (possible cardiac origin)"
    },

    # =========================================================================
    # 3. RESPIRATORY: BREATHING DISTRESS / DYSPNEA
    # =========================================================================
    {
        "concept_id": "difficulty_breathing",
        "concept_type": ConceptType.SYMPTOM,
        "standardized_text": "difficulty breathing / respiratory distress",
        "category_hint": "RESPIRATORY",
        "severity_hint": SeverityLevel.HIGH,
        "ambulance_hint": AmbulanceType.ALS,
        "patterns": {
            "mr": [
                "श्वास घेता येत नाही", "श्वास घ्यायला त्रास", "श्वास गुदमरतोय",
                "दम लागत आहे", "दम भरून आला", "श्वास थांबला", "श्वास अडकला",
                "दम घुटत आहे", "दम लागला", "अस्थमाचा झटका", "श्वास घेण्यास अडचण",
                "श्वास कोंडला", "दम लागतोय", "श्वास घेता येत", "श्वास घेऊ शकत नाही",
                "श्वास घ्यायला प्रचंड त्रास", "श्वास घ्यायला त्रास होतोय"
            ],

            "hi": [
                "सांस लेने में तकलीफ", "सांस नहीं आ रही", "सांस फूल रही है",
                "दम घुट रहा है", "सांस उखड़ रही है", "सांस रुक रही है",
                "सांस नहीं ले पा रहा", "अस्थमा का दौरा", "सांस में दिक्कत",
                "दम फूल रहा", "सांस लेने में परेशानी"
            ],
            "en": [
                "difficulty breathing", "cannot breathe", "can't breathe",
                "shortness of breath", "struggling to breathe", "breathlessness",
                "asthma attack", "choking", "respiratory distress", "gasping"
            ],
            "code_mixed": [
                "breathlessness", "breathing problem", "shwas ghyayla tras",
                "saans lene me dikkat", "cant breathe", "breathing issue",
                "dam lagtoy", "shwas ghyayla problem"
            ],
        },
        "evidence_template": "{lang} expression '{phrase}' indicates acute respiratory distress (RESPIRATORY)"
    },

    # =========================================================================
    # 4. NEUROLOGICAL: SUSPECTED STROKE / PARALYSIS
    # =========================================================================
    {
        "concept_id": "suspected_stroke",
        "concept_type": ConceptType.EXPLICIT_CONDITION,
        "standardized_text": "suspected stroke / acute neurological deficit",
        "category_hint": "STROKE",
        "severity_hint": SeverityLevel.HIGH,
        "ambulance_hint": AmbulanceType.ALS,
        "patterns": {
            "mr": [
                "पक्षाघात", "पक्षाघाताचा झटका", "अर्धांगवायू", "स्ट्रोक आला",
                "तोंड वाकडे झाले", "हात पाय लुळे पडले", "अंग लुळे पडले",
                "बोलता येत नाही अचानक", "पक्षाघात झाला", "स्ट्रोक"
            ],
            "hi": [
                "लकवा मार गया", "लकवा हुआ", "ब्रेन स्ट्रोक", "पक्षाघात",
                "मुंह टेढ़ा हो गया", "हाथ पैर काम नहीं कर रहे", "शरीर सुन्न हो गया",
                "लकवे का दौरा", "स्ट्रोक"
            ],
            "en": [
                "stroke", "brain stroke", "facial drooping", "slurred speech",
                "arm weakness", "sudden paralysis", "hemiplegia", "numbness on one side"
            ],
            "code_mixed": [
                "stroke zala", "stroke aala", "face droop zala", "paralysis zala",
                "stroke hua", "lakwa maar gaya", "half body paralyze"
            ],
        },
        "evidence_template": "{lang} expression '{phrase}' corresponds to suspected acute stroke (STROKE)"
    },

    # =========================================================================
    # 5. BURN INJURY
    # =========================================================================
    {
        "concept_id": "burn_injury",
        "concept_type": ConceptType.EXPLICIT_CONDITION,
        "standardized_text": "thermal / chemical burn injury",
        "category_hint": "BURN",
        "severity_hint": SeverityLevel.HIGH,
        "ambulance_hint": AmbulanceType.ALS,
        "patterns": {
            "mr": [
                "भाजले आहे", "भाजला आहे", "भाजली आहे", "जळाला आहे",
                "जळाली आहे", "आगीत होरपळला", "आगीत भाजले", "गरम पाण्याने भाजले",
                "आगीने जळाले", "सिलेंडरचा स्फोट", "भाजले", "जळाले"
            ],
            "hi": [
                "जल गया है", "जल गई है", "आग से जल गया", "झुलस गया",
                "आग लग गई", "गंभीर रूप से जल गया", "सिलेंडर ब्लास्ट", "जल गया"
            ],
            "en": [
                "burn", "burn injury", "burned", "burnt", "scalded",
                "fire burns", "chemical burn", "flame injury"
            ],
            "code_mixed": [
                "burn zala", "bhajla ahe", "jal gaya hai", "fire burn",
                "aag lagli", "body burn ho gayi"
            ],
        },
        "evidence_template": "{lang} expression '{phrase}' indicates burn trauma (BURN)"
    },

    # =========================================================================
    # 6. SEVERE BLEEDING / HEMORRHAGE
    # =========================================================================
    {
        "concept_id": "severe_bleeding",
        "concept_type": ConceptType.SYMPTOM,
        "standardized_text": "severe hemorrhage / active heavy bleeding",
        "category_hint": "BLEEDING",
        "severity_hint": SeverityLevel.HIGH,
        "ambulance_hint": AmbulanceType.ALS,
        "patterns": {
            "mr": [
                "खूप रक्त वाहत आहे", "फार रक्त येत आहे", "रक्तस्राव थांबत नाही",
                "रक्त वाहत आहे", "रक्ताची धार", "रक्तस्राव सुरू आहे",
                "खूप रक्त जात", "फार रक्त वाहतेय"
            ],
            "hi": [
                "बहुत खून बह रहा है", "खून बंद नहीं हो रहा", "भारी खून निकल रहा",
                "खून की धार", "रक्तस्राव हो रहा", "खून बह रहा है", "बहुत खून"
            ],
            "en": [
                "severe bleeding", "heavy bleeding", "bleeding heavily",
                "profuse bleeding", "uncontrolled bleeding", "arterial bleeding", "hemorrhage"
            ],
            "code_mixed": [
                "heavy bleeding", "bohot khoon beh raha", "khup rakt nighat ahe",
                "blood loss", "bleeding won't stop", "bleeding thambat nahi",
                "blood nikal raha", "bohot blood", "blood nikal raha hai", "blood nikal"
            ],
        },
        "evidence_template": "{lang} expression '{phrase}' indicates severe uncontrolled hemorrhage (BLEEDING/TRAUMA)"
    },

    # =========================================================================
    # 7. ROAD TRAFFIC ACCIDENT (STRICT: ONLY VEHICLE / CRASH INDICATORS!)
    # =========================================================================
    {
        "concept_id": "vehicle_collision",
        "concept_type": ConceptType.EXPLICIT_CONDITION,
        "standardized_text": "motor vehicle collision / road traffic accident",
        "category_hint": "ROAD_TRAFFIC_ACCIDENT",
        "severity_hint": SeverityLevel.HIGH,
        "ambulance_hint": AmbulanceType.ALS,
        "patterns": {
            "mr": [
                "वाहनाची धडक", "गाडीने धडक दिली", "मोटारसायकल अपघात", "कार अपघात",
                "ट्रकची धडक", "बस अपघात", "गाड्यांची टक्कर", "वाहन अपघात",
                "रिक्षा पलटी", "अपघात झाला", "धडक झाली"
            ],
            "hi": [
                "गाड़ी की टक्कर", "बाइक और कार की टक्कर", "सड़क दुर्घटना",
                "रोड एक्सीडेंट", "ट्रक ने टक्कर मारी", "गाड़ी चढ़ गई",
                "वाहन टक्कर", "एक्सीडेंट हो गया", "एक्सीडेंट हुआ", "गाड़ी का एक्सीडेंट",
                "सड़क हादसा", "दुर्घटना", "एक्सीडेंट"
            ],

            "en": [
                "car accident", "bike accident", "motorcycle crash", "vehicle collision",
                "truck accident", "hit by car", "road crash", "bus accident",
                "road traffic accident"
            ],
            "code_mixed": [
                "bike accident zala", "car accident hua", "road accident",
                "gadi ne takkar mari", "bike collision", "car crash",
                "bike slip", "bike slip ho gayi", "scooter slip", "accident zala",
                "bike padli", "accident zala ahe"
            ],
        },

        "evidence_template": "{lang} expression '{phrase}' explicitly identifies road vehicle collision (ROAD_TRAFFIC_ACCIDENT)"
    },

    # =========================================================================
    # 8. NON-VEHICLE TRAUMA / FALL INJURY
    # =========================================================================
    {
        "concept_id": "fall_trauma",
        "concept_type": ConceptType.EXPLICIT_CONDITION,
        "standardized_text": "non-vehicle physical trauma / fall injury",
        "category_hint": "TRAUMA",
        "severity_hint": SeverityLevel.MODERATE,
        "ambulance_hint": AmbulanceType.BLS,
        "patterns": {
            "mr": [
                "पाय घसरून पडले", "जिन्यावरून पडले", "उंचावरून पडले", "खाली पडला",
                "खाली पडली", "हाड मोडले", "फॅक्चर झाले", "जखमी झाले"
            ],
            "hi": [
                "सीढ़ियों से गिर गया", "फिसल कर गिर पड़ा", "ऊंचाई से गिर गया",
                "नीचे गिर गया", "हड्डी टूट गई", "फ्रैक्चर हुआ"
            ],
            "en": [
                "fell down", "slipped and fell", "fall from height", "fracture",
                "broken bone", "broken leg", "broken arm"
            ],
            "code_mixed": [
                "slip houn padla", "fall zala", "gir gaya", "fracture zala"
            ],
        },
        "evidence_template": "{lang} expression '{phrase}' indicates physical fall or blunt trauma without vehicle involvement (TRAUMA)"
    },

    # =========================================================================
    # 9. ACUITY: UNCONSCIOUSNESS / UNRESPONSIVENESS (LIFE THREAT)
    # =========================================================================
    {
        "concept_id": "unconscious",
        "concept_type": ConceptType.ACUITY_MARKER,
        "standardized_text": "loss of consciousness / unresponsive",
        "category_hint": "HIGH_ACUITY",
        "severity_hint": SeverityLevel.CRITICAL,
        "ambulance_hint": AmbulanceType.ALS,
        "patterns": {
            "mr": [
                "शुद्धीवर नाही", "बेशुद्ध पडला आहे", "बेशुद्ध आहे", "बेशुद्ध पडली",
                "जागेवर बेशुद्ध", "शुद्ध हरपली", "बेशुद्ध", "जाणीव नाही"
            ],
            "hi": [
                "बेहोश है", "बेहोश पड़ा है", "अचेत है", "होश नहीं है",
                "होश खो बैठा", "बेहोश"
            ],
            "en": [
                "unconscious", "unresponsive", "passed out", "fainted", "collapsed",
                "collapse", "in shock", "shock"
            ],
            "code_mixed": [
                "unconscious ahe", "behosh hai", "beshuddha ahe", "unresponsive"
            ],
        },
        "evidence_template": "{lang} expression '{phrase}' indicates patient unconsciousness (CRITICAL life-threat marker)"
    },

    # =========================================================================
    # 10. ACUITY: RESPIRATORY ARREST (APNEA - STOPPED BREATHING)
    # =========================================================================
    {
        "concept_id": "stopped_breathing",
        "concept_type": ConceptType.ACUITY_MARKER,
        "standardized_text": "apnea / stopped breathing",
        "category_hint": "HIGH_ACUITY",
        "severity_hint": SeverityLevel.CRITICAL,
        "ambulance_hint": AmbulanceType.ALS,
        "patterns": {
            "mr": [
                "श्वास बंद आहे", "श्वास घेत नाही", "श्वास थांबला आहे", "श्वास बंद"
            ],
            "hi": [
                "सांस नहीं ले रहा", "सांस बंद है", "सांस रुक गई है", "सांस बंद"
            ],
            "en": [
                "not breathing", "stopped breathing", "no breath", "apnea"
            ],
            "code_mixed": [
                "breathing stopped", "saans nahi chal rahi", "shwas ghet nahi"
            ],
        },
        "evidence_template": "{lang} expression '{phrase}' confirms respiratory arrest (CRITICAL life-threat marker)"
    },

    # =========================================================================
    # 11. VAGUE / GENERAL DISTRESS (INSUFFICIENT INFORMATION)
    # =========================================================================
    {
        "concept_id": "general_malaise",
        "concept_type": ConceptType.VAGUE_DISTRESS,
        "standardized_text": "unspecified medical distress / malaise",
        "category_hint": "GENERAL_MEDICAL",
        "severity_hint": SeverityLevel.UNKNOWN,
        "ambulance_hint": AmbulanceType.UNKNOWN,
        "patterns": {
            "mr": [
                "तो बरा वाटत नाही", "तिला बरे वाटत नाही", "बरा वाटत नाही",
                "बरे वाटत नाही", "तब्येत बरी नाही", "काहीतरी त्रास होतोय",
                "अस्वस्थ वाटत आहे", "त तब्येत बरी नाही"
            ],
            "hi": [
                "तबीयत खराब लग रही है", "कुछ ठीक नहीं लग रहा",
                "मरीज को ठीक नहीं लग रहा", "अच्छा नहीं लग रहा", "तबीयत ठीक नहीं"
            ],
            "en": [
                "not feeling well", "he is not feeling well", "she feels sick",
                "feeling unwell", "not feeling right", "feeling sick"
            ],
            "code_mixed": [
                "bara vatat nahi", "theek nahi lag raha", "unwell feel hot ahe",
                "feeling sick ahe", "tabet kharab ahe"
            ],
        },
        "evidence_template": "{lang} expression '{phrase}' indicates vague/insufficient clinical details; requires human dispatcher assessment (GENERAL_MEDICAL / UNKNOWN)"
    },
]
