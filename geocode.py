import json
import requests
from google.cloud import secretmanager

client = secretmanager.SecretManagerServiceClient()
name = "projects/tinyhub-platform-dev/secrets/Maps_API_Key/versions/latest"
API_KEY = client.access_secret_version(request={"name": name}).payload.data.decode("UTF-8")

TARGETS = [
    {"id": "coin-base-1", "name": "Walmart Woodstock", "address": "1275 Lake Ave, Woodstock, IL 60098"},
    {"id": "coin-base-2", "name": "Northwestern Medicine", "address": "3701 Doty Rd, Woodstock, IL 60098"},
    {"id": "coin-base-3", "name": "Jewel-Osco Woodstock", "address": "1030 N Seminary Ave, Woodstock, IL 60098"},
    {"id": "coin-base-4", "name": "Walmart Huntley", "address": "12300 IL Route 47, Huntley, IL 60142"},
    {"id": "coin-base-5", "name": "Woodstock Residential Area", "address": "Woodstock, IL 60098"},
    {"id": "coin-base-6", "name": "Marengo City Hall", "address": "132 E Prairie St, Marengo, IL 60152"},
    {"id": "farm-marengo", "name": "Marengo Solar Farm", "address": "Marengo, IL 60152"},
    {"id": "farm-nexamp", "name": "Nexamp Harvard Solar", "address": "Harvard, IL 60033"},
    {"id": "farm-hebron", "name": "Hebron Solar", "address": "Hebron, IL 60034"},
    {"id": "batt-marengo", "name": "Marengo Battery Storage", "address": "Marengo, IL 60152"},
    {"id": "batt-mchenry", "name": "McHenry Battery Storage", "address": "McHenry, IL 60050"},
    {"id": "buyer-neighbor-1", "name": "Residential Block A", "address": "Crystal Lake, IL 60014"},
    {"id": "buyer-neighbor-2", "name": "Residential Block B", "address": "Woodstock, IL 60098"},
    {"id": "buyer-school-1", "name": "Woodstock North High School", "address": "3000 Raffel Rd, Woodstock, IL 60098"},
    {"id": "buyer-school-2", "name": "Marengo Community High School", "address": "110 Franks Rd, Marengo, IL 60152"},
    {"id": "buyer-biz-1", "name": "Route 47 Strip Mall", "address": "Route 47, Woodstock, IL 60098"},
    {"id": "buyer-biz-2", "name": "Northwestern Medicine McHenry", "address": "4201 Medical Center Dr, McHenry, IL 60050"},
    {"id": "buyer-dc-1", "name": "Google Data Center Aurora", "address": "Aurora, IL 60502"},
    {"id": "buyer-dc-2", "name": "Equinix Chicago", "address": "350 E Cermak Rd, Chicago, IL 60616"},
    {"id": "buyer-grid-1", "name": "ComEd Substation", "address": "Woodstock, IL 60098"},
    {"id": "buyer-muni-1", "name": "Harvard Fire Department", "address": "104 N Hart Blvd, Harvard, IL 60033"},
    {"id": "buyer-muni-2", "name": "Woodstock Police Department", "address": "656 Lake Ave, Woodstock, IL 60098"},
]

def geocode(address):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={API_KEY}"
    r = requests.get(url).json()
    if r["status"] == "OK":
        loc = r["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    return None

results = {}
for t in TARGETS:
    coords = geocode(t["address"])
    if coords:
        results[t["id"]] = {"lat": round(coords[0], 6), "lng": round(coords[1], 6)}
        print(f"  ✅ {t['name']:35} → {coords[0]:.6f}, {coords[1]:.6f}")
    else:
        print(f"  ❌ {t['name']:35} → FAILED")

with open("geocoded.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"\n  Saved {len(results)} coordinates to geocoded.json")
