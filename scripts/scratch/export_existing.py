import sys
# Add backend directory to path so it can import services
sys.path.append(r"C:\Users\Guill\teamwork_projects\ai_culling_system\backend")

import requests
from services.xmp_exporter import export_results_to_xmp
from services.settings_manager import load_settings

try:
    # Query current results from the running FastAPI backend
    response = requests.get("http://127.0.0.1:8000/results")
    if not response.ok:
        print("Failed to get results from backend. Is it running?")
        sys.exit(1)
        
    data = response.json()
    results = data.get("results", [])
    
    if not results:
        print("No results available to export.")
        sys.exit(0)
        
    settings = load_settings()
    ratings_map = settings["ratings_mapping"]
    prefs = settings["selection_preferences"]
    overwrite = prefs.get("overwrite_xmp_ratings", False)
    
    print(f"Exporting XMP for {len(results)} photos...")
    xmp_stats = export_results_to_xmp(results, ratings_map, overwrite=overwrite)
    print("XMP Export Complete:", xmp_stats)

except Exception as e:
    print("Error during export:", e)
