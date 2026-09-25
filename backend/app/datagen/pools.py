"""
datagen/pools.py — Static vocabularies for the synthetic Lucknow dataset.

Names, localities, police stations, cell towers (with lat/lon for maps),
vehicle makes and BNS/NDPS/IT-Act sections. No randomness lives here.
"""

FIRST_M = [
    "Amit", "Rahul", "Vijay", "Sunil", "Anil", "Manoj", "Deepak", "Rajesh",
    "Sandeep", "Ashok", "Pankaj", "Vivek", "Alok", "Nitin", "Rohit", "Arun",
    "Mukesh", "Dinesh", "Harish", "Naresh", "Gaurav", "Saurabh", "Ajay",
    "Imtiaz", "Shahid", "Arif", "Faizan", "Javed", "Rizwan", "Nadeem",
    "Ramesh", "Suresh", "Kamlesh", "Brijesh", "Umesh", "Yogesh", "Prakash",
    "Satish", "Hemant", "Lalit",
]
FIRST_F = [
    "Sunita", "Anita", "Pooja", "Neha", "Priya", "Kavita", "Rekha", "Seema",
    "Geeta", "Meena", "Shabana", "Nazia", "Ruksana", "Anjali", "Shalini",
    "Rashmi", "Nidhi", "Preeti", "Suman", "Kiran", "Aarti", "Mamta",
]
SURNAMES = [
    "Kumar", "Singh", "Yadav", "Verma", "Sharma", "Gupta", "Mishra", "Pandey",
    "Tiwari", "Srivastava", "Shukla", "Tripathi", "Dubey", "Maurya", "Rawat",
    "Chauhan", "Saxena", "Agarwal", "Khan", "Ansari", "Siddiqui", "Qureshi",
    "Rizvi", "Nigam", "Kushwaha", "Rajput", "Awasthi", "Bajpai", "Kashyap",
    "Pal",
]
FEMALE_SURNAMES = ["Devi", "Kumari", "Bano", "Khatoon"]

# Locality -> (police station, cell tower, lat, lon)
LOCALITIES = {
    "Gomti Nagar":    ("PS Gomti Nagar", "Gomti Nagar Tower-3",   26.8500, 80.9990),
    "Vibhuti Khand":  ("PS Gomti Nagar", "Vibhuti Khand Tower-1", 26.8640, 80.9960),
    "Hazratganj":     ("PS Hazratganj",  "Hazratganj Tower-2",    26.8500, 80.9460),
    "Indira Nagar":   ("PS Mahanagar",   "Indira Nagar Tower-1",  26.8830, 80.9980),
    "Mahanagar":      ("PS Mahanagar",   "Mahanagar Tower-4",     26.8720, 80.9580),
    "Alambagh":       ("PS Alambagh",    "Alambagh Tower-2",      26.8140, 80.8980),
    "Charbagh":       ("PS Alambagh",    "Charbagh Tower-5",      26.8320, 80.9200),
    "Aminabad":       ("PS Aminabad",    "Aminabad Tower-1",      26.8460, 80.9250),
    "Chowk":          ("PS Aminabad",    "Chowk Tower-2",         26.8680, 80.9080),
    "Kaiserbagh":     ("PS Kaiserbagh",  "Kaiserbagh Tower-1",    26.8560, 80.9340),
    "Aliganj":        ("PS Vikas Nagar", "Aliganj Tower-3",       26.8960, 80.9420),
    "Vikas Nagar":    ("PS Vikas Nagar", "Vikas Nagar Tower-2",   26.8880, 80.9600),
    "Chinhat":        ("PS Chinhat",     "Chinhat Tower-1",       26.8830, 81.0480),
    "Sarojini Nagar": ("PS Alambagh",    "Sarojini Nagar Tower-1", 26.7700, 80.8800),
}
STATIONS = sorted({v[0] for v in LOCALITIES.values()})
STATION_CODE = {
    "PS Gomti Nagar": "GMN", "PS Hazratganj": "HZG", "PS Mahanagar": "MHN",
    "PS Alambagh": "ALB", "PS Aminabad": "AMN", "PS Kaiserbagh": "KSB",
    "PS Vikas Nagar": "VKN", "PS Chinhat": "CHT",
}

VEHICLE_MODELS = [
    ("Maruti Suzuki", "Swift"), ("Maruti Suzuki", "Wagon R"), ("Hyundai", "i20"),
    ("Tata", "Nexon"), ("Honda", "Activa 6G"), ("Hero", "Splendor Plus"),
    ("Bajaj", "Pulsar 150"), ("TVS", "Apache RTR"), ("Mahindra", "Bolero"),
    ("Toyota", "Innova Crysta"),
]
COLOURS = ["White", "Black", "Silver", "Red", "Blue", "Grey"]

SECTIONS = {
    "cheating":  "BNS 318(4), 316(2)",
    "theft":     "BNS 303(2)",
    "snatching": "BNS 304",
    "hurt":      "BNS 115(2), 352",
    "threat":    "BNS 351(2)",
    "domestic":  "BNS 85, 115(2)",
    "ndps":      "NDPS Act 8/21/29",
    "cyber":     "IT Act 66D, BNS 318(4)",
    "stolen":    "BNS 317(2)",
    "burglary":  "BNS 331(4), 305",
}
