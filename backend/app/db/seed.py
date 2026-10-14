from typing import List, Optional
from typing_extensions import TypedDict
from sqlalchemy.orm import Session
from app.models.hospital import Hospital
from app.models.ambulance import Ambulance, AmbulanceStatus
from app.models.case import AmbulanceType, SeverityLevel
from app.models.protocol import EmergencyProtocol
from app.models.user import User, UserRole
from app.core.logging import logger


class SimulatedHospitalData(TypedDict):
    name: str
    address: str
    latitude: float
    longitude: float
    total_beds: int
    available_beds: int
    available_icu_beds: int
    has_trauma_center: bool
    has_cardiac_care: bool
    has_burn_unit: bool
    has_pediatric_icu: bool
    specializations: List[str]
    contact_phone: str


class SimulatedAmbulanceData(TypedDict):
    vehicle_number: str
    ambulance_type: AmbulanceType
    base_station: str
    latitude: float
    longitude: float
    status: AmbulanceStatus
    equipment: List[str]
    driver_name: str
    contact_number: str

SIMULATED_HOSPITALS: List[SimulatedHospitalData] = [
    {
        "name": "Sassoon General Hospital",
        "address": "Near Pune Railway Station, Shivajinagar, Pune 411001",
        "latitude": 18.5283,
        "longitude": 73.8742,
        "total_beds": 1200,
        "available_beds": 150,
        "available_icu_beds": 35,
        "has_trauma_center": True,
        "has_cardiac_care": True,
        "has_burn_unit": True,
        "has_pediatric_icu": True,
        "specializations": ["TRAUMA", "BURNS", "GENERAL", "PEDIATRIC", "TOXICOLOGY"],
        "contact_phone": "+91-20-26128000",
    },
    {
        "name": "Deenanath Mangeshkar Hospital",
        "address": "Near Mhatre Bridge, Erandwane, Pune 411004",
        "latitude": 18.5034,
        "longitude": 73.8290,
        "total_beds": 800,
        "available_beds": 85,
        "available_icu_beds": 22,
        "has_trauma_center": True,
        "has_cardiac_care": True,
        "has_burn_unit": False,
        "has_pediatric_icu": True,
        "specializations": ["CARDIAC", "NEUROLOGY", "TRAUMA", "ONCOLOGY"],
        "contact_phone": "+91-20-40151000",
    },
    {
        "name": "Ruby Hall Clinic",
        "address": "40 Sassoon Road, Sangamvadi, Pune 411001",
        "latitude": 18.5326,
        "longitude": 73.8785,
        "total_beds": 600,
        "available_beds": 60,
        "available_icu_beds": 18,
        "has_trauma_center": True,
        "has_cardiac_care": True,
        "has_burn_unit": False,
        "has_pediatric_icu": True,
        "specializations": ["CARDIAC", "NEUROLOGY", "TRAUMA", "TRANSPLANT"],
        "contact_phone": "+91-20-66455100",
    },
    {
        "name": "Jupiter Hospital Baner",
        "address": "Near Prathamesh Park, Baner, Pune 411045",
        "latitude": 18.5580,
        "longitude": 73.7915,
        "total_beds": 350,
        "available_beds": 45,
        "available_icu_beds": 14,
        "has_trauma_center": True,
        "has_cardiac_care": True,
        "has_burn_unit": False,
        "has_pediatric_icu": True,
        "specializations": ["CARDIAC", "TRAUMA", "NEUROLOGY", "ORTHOPEDIC"],
        "contact_phone": "+91-20-27992222",
    },
    {
        "name": "Aditya Birla Memorial Hospital",
        "address": "Aditya Birla Hospital Marg, Thergaon, Pimpri-Chinchwad 411033",
        "latitude": 18.6231,
        "longitude": 73.7844,
        "total_beds": 500,
        "available_beds": 70,
        "available_icu_beds": 20,
        "has_trauma_center": True,
        "has_cardiac_care": True,
        "has_burn_unit": True,
        "has_pediatric_icu": True,
        "specializations": ["TRAUMA", "BURNS", "CARDIAC", "NEUROLOGY"],
        "contact_phone": "+91-20-30717500",
    },
    {
        "name": "Noble Hospital Hadapsar",
        "address": "153 Magarpatta City Road, Hadapsar, Pune 411013",
        "latitude": 18.5089,
        "longitude": 73.9260,
        "total_beds": 300,
        "available_beds": 35,
        "available_icu_beds": 12,
        "has_trauma_center": True,
        "has_cardiac_care": True,
        "has_burn_unit": False,
        "has_pediatric_icu": False,
        "specializations": ["TRAUMA", "CARDIAC", "GENERAL_SURGERY"],
        "contact_phone": "+91-20-66285000",
    },
    {
        "name": "Bharati Hospital & Research Centre",
        "address": "Pune-Satara Road, Dhankawadi, Katraj, Pune 411043",
        "latitude": 18.4575,
        "longitude": 73.8508,
        "total_beds": 850,
        "available_beds": 90,
        "available_icu_beds": 25,
        "has_trauma_center": True,
        "has_cardiac_care": True,
        "has_burn_unit": False,
        "has_pediatric_icu": True,
        "specializations": ["TRAUMA", "PEDIATRIC", "CARDIAC", "GENERAL"],
        "contact_phone": "+91-20-40555555",
    },
    {
        "name": "Sahyadri Super Speciality Hospital",
        "address": "Plot No 30 C, Erandwane, Karve Road, Deccan, Pune 411004",
        "latitude": 18.5147,
        "longitude": 73.8373,
        "total_beds": 200,
        "available_beds": 25,
        "available_icu_beds": 8,
        "has_trauma_center": False,
        "has_cardiac_care": True,
        "has_burn_unit": False,
        "has_pediatric_icu": False,
        "specializations": ["CARDIAC", "NEUROLOGY", "HEMATOLOGY"],
        "contact_phone": "+91-20-67213000",
    },
]

SIMULATED_AMBULANCES: List[SimulatedAmbulanceData] = [
    {
        "vehicle_number": "MH-12-EM-1001",
        "ambulance_type": AmbulanceType.ALS,
        "base_station": "Kothrud Depot Base",
        "latitude": 18.5074,
        "longitude": 73.8077,
        "status": AmbulanceStatus.AVAILABLE,
        "equipment": ["Ventilator", "Defibrillator", "Oxygen", "Advanced Airway Kit", "IV Pumps"],
        "driver_name": "Ramesh Shinde",
        "contact_number": "+91-9822011001",
    },
    {
        "vehicle_number": "MH-12-EM-1002",
        "ambulance_type": AmbulanceType.BLS,
        "base_station": "Shivajinagar Station Base",
        "latitude": 18.5314,
        "longitude": 73.8446,
        "status": AmbulanceStatus.AVAILABLE,
        "equipment": ["Oxygen", "Stretcher", "First Aid Kit", "Automated External Defibrillator (AED)"],
        "driver_name": "Suresh More",
        "contact_number": "+91-9822011002",
    },
    {
        "vehicle_number": "MH-12-EM-1003",
        "ambulance_type": AmbulanceType.ALS,
        "base_station": "Hinjewadi Phase 1 Base",
        "latitude": 18.5913,
        "longitude": 73.7389,
        "status": AmbulanceStatus.AVAILABLE,
        "equipment": ["Ventilator", "Defibrillator", "Oxygen", "Multi-parameter Monitor", "Cervical Collar"],
        "driver_name": "Ajay Patil",
        "contact_number": "+91-9822011003",
    },
    {
        "vehicle_number": "MH-12-EM-1004",
        "ambulance_type": AmbulanceType.BLS,
        "base_station": "Hinjewadi Phase 3 Base",
        "latitude": 18.5830,
        "longitude": 73.6990,
        "status": AmbulanceStatus.AVAILABLE,
        "equipment": ["Oxygen", "Stretcher", "Suction Unit", "First Aid Kit"],
        "driver_name": "Ganesh Kadam",
        "contact_number": "+91-9822011004",
    },
    {
        "vehicle_number": "MH-12-EM-1005",
        "ambulance_type": AmbulanceType.ALS,
        "base_station": "Swargate Bus Stand Base",
        "latitude": 18.5018,
        "longitude": 73.8580,
        "status": AmbulanceStatus.AVAILABLE,
        "equipment": ["Ventilator", "Defibrillator", "Oxygen", "Cardiac Monitor", "Spine Board"],
        "driver_name": "Nitin Jadhav",
        "contact_number": "+91-9822011005",
    },
    {
        "vehicle_number": "MH-12-EM-1006",
        "ambulance_type": AmbulanceType.BLS,
        "base_station": "Hadapsar Gadital Base",
        "latitude": 18.5020,
        "longitude": 73.9310,
        "status": AmbulanceStatus.AVAILABLE,
        "equipment": ["Oxygen", "Stretcher", "Basic Splints", "First Aid Kit"],
        "driver_name": "Vikas Bhosale",
        "contact_number": "+91-9822011006",
    },
    {
        "vehicle_number": "MH-12-EM-1007",
        "ambulance_type": AmbulanceType.ALS,
        "base_station": "Pimpri Chhatrapati Chowk Base",
        "latitude": 18.6279,
        "longitude": 73.8009,
        "status": AmbulanceStatus.AVAILABLE,
        "equipment": ["Ventilator", "Defibrillator", "Oxygen", "ECG", "Infusion Pumps"],
        "driver_name": "Mahesh Pawar",
        "contact_number": "+91-9822011007",
    },
    {
        "vehicle_number": "MH-12-EM-1008",
        "ambulance_type": AmbulanceType.BLS,
        "base_station": "Katraj PMT Depot Base",
        "latitude": 18.4550,
        "longitude": 73.8580,
        "status": AmbulanceStatus.AVAILABLE,
        "equipment": ["Oxygen", "Stretcher", "AED", "First Aid Kit"],
        "driver_name": "Sachin Gaikwad",
        "contact_number": "+91-9822011008",
    },
    {
        "vehicle_number": "MH-12-EM-1009",
        "ambulance_type": AmbulanceType.ALS,
        "base_station": "Viman Nagar Symbiosis Base",
        "latitude": 18.5679,
        "longitude": 73.9143,
        "status": AmbulanceStatus.AVAILABLE,
        "equipment": ["Ventilator", "Defibrillator", "Oxygen", "Trauma Dressing Pack"],
        "driver_name": "Dinesh Jagtap",
        "contact_number": "+91-9822011009",
    },
    {
        "vehicle_number": "MH-12-EM-1010",
        "ambulance_type": AmbulanceType.BLS,
        "base_station": "Baner High Street Base",
        "latitude": 18.5642,
        "longitude": 73.7769,
        "status": AmbulanceStatus.AVAILABLE,
        "equipment": ["Oxygen", "Stretcher", "First Aid Kit"],
        "driver_name": "Santosh Salunkhe",
        "contact_number": "+91-9822011010",
    },
]

SIMULATED_PROTOCOLS = [
    {
        "protocol_code": "CARD-01",
        "category": "CARDIAC",
        "title": "Suspected Acute Coronary Syndrome / Cardiac Arrest",
        "description": "Patient presenting with crushing chest pain, radiating to left arm or jaw, diaphoresis, shortness of breath, or unresponsive collapse.",
        "severity_default": SeverityLevel.CRITICAL,
        "required_ambulance_type": AmbulanceType.ALS,
        "key_symptoms": ["chest pain", "crushing", "heart attack", "left arm pain", "unconscious", "no pulse", "cardiac arrest", "छातीत दुखणे", "हार्ट अटॅक", "सीने में दर्द"],
        "mandatory_equipment": ["Defibrillator", "Oxygen", "Cardiac Monitor", "Advanced Airway Kit"],
        "first_aid_guidance": "Have patient sit upright and rest quietly. If unresponsive and not breathing normally, begin continuous chest compressions at 100-120 bpm in center of chest.",
    },
    {
        "protocol_code": "TRAUMA-01",
        "category": "TRAUMA",
        "title": "Severe Road Traffic Accident / Major Hemorrhage",
        "description": "High-velocity vehicular impact, pedestrian struck, severe bleeding, open fractures, or altered consciousness.",
        "severity_default": SeverityLevel.CRITICAL,
        "required_ambulance_type": AmbulanceType.ALS,
        "key_symptoms": ["accident", "road traffic accident", "bleeding profusely", "head injury", "crush", "broken bone open", "अपघात", "रक्तस्त्राव", "दुर्घटना"],
        "mandatory_equipment": ["Spine Board", "Cervical Collar", "Trauma Dressing Pack", "Oxygen"],
        "first_aid_guidance": "Do NOT move the patient's neck or back unless in immediate danger. Apply firm direct pressure with clean cloth over any active bleeding sites.",
    },
    {
        "protocol_code": "STROKE-01",
        "category": "NEUROLOGICAL",
        "title": "Acute Stroke / Cerebrovascular Event",
        "description": "Sudden onset facial droop, arm weakness, slurred speech, or sudden hemiplegia within acute time window.",
        "severity_default": SeverityLevel.CRITICAL,
        "required_ambulance_type": AmbulanceType.ALS,
        "key_symptoms": ["facial droop", "slurred speech", "paralysis", "stroke", "one side weak", "बोलताना अडखळणे", "पक्षाघात", "लकवा"],
        "mandatory_equipment": ["Oxygen", "Multi-parameter Monitor", "Glucose Monitor"],
        "first_aid_guidance": "Note exact time symptoms began. Keep patient comfortable on their side if vomiting, do NOT give food, water, or aspirin until evaluated.",
    },
    {
        "protocol_code": "RESP-01",
        "category": "RESPIRATORY",
        "title": "Severe Acute Respiratory Distress",
        "description": "Severe breathlessness, inability to speak full sentences, stridor, cyanosis (blue lips), asthma exacerbation.",
        "severity_default": SeverityLevel.HIGH,
        "required_ambulance_type": AmbulanceType.ALS,
        "key_symptoms": ["cannot breathe", "gasping", "shortness of breath", "asthma attack", "choking", "श्वास घेण्यास त्रास", "दम लागणे", "सांस फूलना"],
        "mandatory_equipment": ["Oxygen", "Ventilator", "Nebulizer"],
        "first_aid_guidance": "Assist patient into an upright sitting position. Loosen tight clothing around neck and chest. Help them use their prescribed rescue inhaler if available.",
    },
    {
        "protocol_code": "BURN-01",
        "category": "BURNS",
        "title": "Severe Thermal or Chemical Burns",
        "description": "Burns involving >10% body surface area, face, hands, airway, or chemical/electrical exposure.",
        "severity_default": SeverityLevel.CRITICAL,
        "required_ambulance_type": AmbulanceType.ALS,
        "key_symptoms": ["fire burn", "skin peeling", "chemical burn", "explosion", "भाजले", "आग", "जल गया"],
        "mandatory_equipment": ["Sterile Burn Sheet", "Oxygen", "IV Fluids"],
        "first_aid_guidance": "Cool burn with gentle clean running tap water for 10-20 minutes. Do NOT apply ice, oil, turmeric, or butter. Cover loosely with clean dry cloth.",
    },
    {
        "protocol_code": "OBST-01",
        "category": "OBSTETRICS",
        "title": "Pre-hospital Obstetric Emergency / Imminent Delivery",
        "description": "Full term pregnancy with active labor contractions <2 min apart, crowning, or heavy antepartum bleeding.",
        "severity_default": SeverityLevel.HIGH,
        "required_ambulance_type": AmbulanceType.BLS,
        "key_symptoms": ["delivery", "labor pains", "pregnant bleeding", "water broke", "बाळंतपण", "प्रसूती वेदना", "डिलीवरी"],
        "mandatory_equipment": ["Sterile Delivery Pack", "Oxygen", "Suction Unit"],
        "first_aid_guidance": "Have mother lie back comfortably with knees bent. Keep warm clean towels ready. Do not pull on baby; support head gently as it emerges.",
    },
]


SIMULATED_USERS = [
    {
        "username": "dispatcher1",
        "email": "dispatcher1@sahayai.org",
        "full_name": "Pooja Kulkarni",
        "role": UserRole.DISPATCHER,
        # Plaintext for tests: dispatcher123
        "hashed_password": "$2b$12$GW6jffxl5xlqup0U7ZFuoeb60r9h1QifJMXFGya1nrCVD8GfGFFAO",
        "badge_number": "PUN-DISP-01",
    },
    {
        "username": "supervisor1",
        "email": "supervisor1@sahayai.org",
        "full_name": "Rajesh Deshmukh",
        "role": UserRole.SUPERVISOR,
        # Plaintext for tests: supervisor123
        "hashed_password": "$2b$12$Gxv78UnFcWM7IAhXVbQkz.UK/oat7A/0Nmf0NoWsEp7kUFO0tqgYm",
        "badge_number": "PUN-SUPV-01",
    },
    {
        "username": "admin",
        "email": "admin@sahayai.org",
        "full_name": "System Administrator",
        "role": UserRole.ADMIN,
        # Plaintext for tests: admin123
        "hashed_password": "$2b$12$3KgvjQeys/4Spi.FM1kkEOtuPqhNIYfOLrJYZF2oyyDKwNbfBKDS6",
        "badge_number": "PUN-ADMIN-01",
    },
]


def seed_database(db: Session) -> None:
    """Populate simulated Pune ambulances, hospitals, clinical protocols, and users if not already seeded."""
    # 1. Users
    for u_data in SIMULATED_USERS:
        existing = db.query(User).filter(User.username == u_data["username"]).first()
        if not existing:
            db.add(User(**u_data))

    # 2. Hospitals
    for h_data in SIMULATED_HOSPITALS:
        existing = db.query(Hospital).filter(Hospital.name == h_data["name"]).first()
        if not existing:
            db.add(Hospital(**h_data))
    
    # 3. Ambulances
    for a_data in SIMULATED_AMBULANCES:
        existing = db.query(Ambulance).filter(Ambulance.vehicle_number == a_data["vehicle_number"]).first()
        if not existing:
            db.add(Ambulance(**a_data))

    # 4. Protocols
    for p_data in SIMULATED_PROTOCOLS:
        existing = db.query(EmergencyProtocol).filter(EmergencyProtocol.protocol_code == p_data["protocol_code"]).first()
        if not existing:
            db.add(EmergencyProtocol(**p_data))

    db.commit()
    logger.info("Simulated Pune hospitals, ambulances, protocols, and users successfully seeded.")
