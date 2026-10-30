"""Convert PHAC wastewater surveillance data into the iMicroSeq schema.

Reads the Public Health Agency of Canada's National Wastewater Monitoring of
Pathogens (NWMP) wastewater_aggregate.csv and writes one iMicroSeq row per
input row, i.e. one location, week and target (SARS-CoV-2, influenza A/B or
RSV). Each value is a weekly average viral concentration (w_avg), so records
are described as pooled qPCR measurements and the sequencing fields are Not
Applicable. Collection runs from weekstart (a Sunday) to the following
Saturday. City coordinates are looked up through OpenStreetMap Nominatim and
cached in geocode_cache.json. Targets, provinces or cities the mappings cannot
resolve are filled as Not Provided and listed at the end of the run.

    python parser.py
    python parser.py --input wastewater_aggregate.csv --output PHAC-NWMP.csv

By default this reads ../raw/wastewater_aggregate.csv and writes
../curated/PHAC-NWMP.csv. workflow/run_phac_workflow.sh runs it as step 3.

Owner: Justin Jia
"""

import os
import json
import time
import argparse
from datetime import datetime, timedelta
import pandas as pd
import tqdm
import requests

columnNames = ["specimen collector sample ID","sampling site ID","sampling event ID","INSDC Project accession","INSDC Sample accession","INSDC sequence read accession","sample collection project name","organism","taxonomic identification process","purpose of sampling","sample collected by organisation name","sample collected by contact email","data steward contact name","data steward contact email","sample collection data steward name","sample collection start date","sample collection start date null reason","sample collection end date","sample collection end date null reason","sample collection time duration value","sample collection time duration value null reason","sample collection time duration unit","geo loc name (country)","geo loc name (state/province/territory)","geo loc name (site)","geo loc name (city)","geo loc latitude","geo loc longitude","environmental site","proximal environmental site","presampling activity ID","presampling activity date","presampling activity date null reason","presampling activity","presampling activity details","collection device","collection method","environmental material","environmental material properties","anatomical material","anatomical part","body product","experimental specimen role type","specimen processing","specimen processing details","experimental protocol name","experimental protocol url","experimental control details","nucleic acid extraction method","nucleic acid extraction kit","endogenous control details","available data types","available data type details","populated area type","water catchment area human population measurement value","water catchment area human population measurement value null reason","water catchment area human population range","presampling weather conditions","sampling weather conditions","precipitation measurement value","precipitation measurement unit","water depth value","water depth units","sediment depth value","sediment depth units","pH measurement value","total daily flow rate measurement value","total daily flow rate measurement unit","instantaneous flow rate measurement value","instantaneous flow rate measurement unit","turbidity measurement value","turbidity measurement unit","conductivity measurement value","conductivity measurement unit","salinity measurement value","salinity measurement unit","dissolved oxygen measurement value","dissolved oxygen measurement unit","carbonaceous biochemical oxygen demand (CBOD) measurement value","carbonaceous biochemical oxygen demand (CBOD) measurement unit","total suspended solids (TSS) measurement value","total suspended solids (TSS) measurement unit","fecal contamination indicator","fecal contamination value","fecal contamination unit","host (common name)","host (scientific name)","host age","host age null reason","host age unit","host age bin","isolate ID","microbiological method","strain ID","isolated by organisation name","purpose of sequencing","assay type","sequencing date","sequencing date null reason","sequenced by organisation name","sequenced by contact email","sequence submitted by","sequencing protocol","sequencing instrument","library ID","library preparation kit","genomic target enrichment method","genomic target enrichment method details","amplicon pcr primer scheme name","amplicon pcr primer scheme url","amplicon size","amplicon size null reason","raw sequence data processing method","dehosting method","genome sequence file name","sequence assembly software name","sequence assembly software version","consensus sequence software name","consensus sequence software version","breadth of coverage value","depth of coverage value","genome completeness","reference genome accession","bioinformatics protocol url","quality control method name","quality control method version","quality control determination","quality control issues","quality control details","read mapping software name","read mapping software version","taxonomic reference database name","taxonomic reference database version","viral type","viral subtype","viral lineage","viral clade","viral classification scheme","lineage/clade analysis software name","lineage/clade analysis software version","target taxonomic name 1","assay target name 1","gene symbol 1","diagnostic target presence 1","diagnostic measurement value 1","diagnostic measurement unit 1","diagnostic measurement method 1","target taxonomic name 2","assay target name 2","gene symbol 2","diagnostic target presence 2","diagnostic measurement value 2","diagnostic measurement unit 2","diagnostic measurement method 2","target taxonomic name 3","assay target name 3","gene symbol 3","diagnostic target presence 3","diagnostic measurement value 3","diagnostic measurement unit 3","diagnostic measurement method 3","authors","citation URL"]

PHACOrganismDictionary = {
    "covN2" : "Severe acute respiratory syndrome coronavirus 2 [NCBITaxon:2697049]",
    "fluA"  : "Influenza A virus [NCBITaxon:11320]",
    "fluB"  : "Influenza B virus [NCBITaxon:11520]",
    "rsv"   : "Respiratory syncytial virus [NCBITaxon:12814]",
}

# province -> GAZ term; blank province = aggregation over multiple provinces.
PHACProvinceDictionary = {
    "Alberta"                   : "Alberta [GAZ:00002566]",
    "British Columbia"          : "British Columbia [GAZ:00002562]",
    "Manitoba"                  : "Manitoba [GAZ:00002571]",
    "New Brunswick"             : "New Brunswick [GAZ:00002570]",
    "Newfoundland and Labrador" : "Newfoundland and Labrador [GAZ:00002567]",
    "Northwest Territories"     : "Northwest Territories [GAZ:00002575]",
    "Nova Scotia"               : "Nova Scotia [GAZ:00002565]",
    "Nunavut"                   : "Nunavut [GAZ:00002574]",
    "Ontario"                   : "Ontario [GAZ:00002563]",
    "Prince Edward Island"      : "Prince Edward Island [GAZ:00002572]",
    "Quebec"                    : "Quebec [GAZ:00002569]",
    "Saskatchewan"              : "Saskatchewan [GAZ:00002564]",
    "Yukon"                     : "Yukon [GAZ:00002576]",
    ""                          : "Not Applicable [GENEPIO:0001619]",
}

PHACCountryDictionary = {
    "Canada" : "Canada [GAZ:00002560]",
}

# Values that could not be resolved automatically; surfaced at the end of a run.
_phacMissing = {"measureid": set(), "province": set(), "coordinates": set()}
_geocodeCachePath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geocode_cache.json")

try:
    with open(_geocodeCachePath) as _f:
        _geocodeCache = json.load(_f)
except Exception:
    _geocodeCache = {}


def geocodeCity(city, province):
    """Look up (latitude, longitude) for a city via OpenStreetMap Nominatim.

    Coordinates are formatted like the iMicroSeq examples ("51.05000 N",
    "114.07000 W"). Results are cached to ``geocode_cache.json``; cities that
    cannot be resolved are collected in ``_phacMissing['coordinates']``.
    """
    city = (city or "").strip()
    if city == "":
        return "", ""
    key = city if not province else city + ", " + province
    if key in _geocodeCache:
        cached = _geocodeCache[key]
        return cached.get("lat", ""), cached.get("lon", "")

    lat = lon = ""
    try:
        query = ", ".join([p for p in [city, province, "Canada"] if p])
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": "iMicroSeq-PHAC-parser/1.0 (claude@bfjia.net)"},
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json()
        if hits:
            latf = float(hits[0]["lat"])
            lonf = float(hits[0]["lon"])
            lat = f"{abs(latf):.5f} " + ("N" if latf >= 0 else "S")
            lon = f"{abs(lonf):.5f} " + ("E" if lonf >= 0 else "W")
        time.sleep(1.1)  # Nominatim usage policy: <= 1 request/second
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] geocode failed for {key!r}: {exc}")

    if lat == "" or lon == "":
        _phacMissing["coordinates"].add(key)
    _geocodeCache[key] = {"lat": lat, "lon": lon}
    return lat, lon


def convertPHACintoiMicroSeq(data):
    """Map one PHAC wastewater_aggregate row (dict) to the iMicroSeq schema."""
    measureid = data.get("measureid", "").strip()
    province = data.get("province", "").strip()
    city = data.get("city", "").strip()

    organism = PHACOrganismDictionary.get(measureid)
    if organism is None:
        _phacMissing["measureid"].add(measureid)
        organism = "Not Provided [GENEPIO:0001668]"

    stateProvince = PHACProvinceDictionary.get(province)
    if stateProvince is None:
        _phacMissing["province"].add(province)
        stateProvince = "Not Provided [GENEPIO:0001668]"

    latitude, longitude = geocodeCity(city, province)

    # Parse weekstart (the reported Sunday) and format both collection dates as
    # YYYY-MM-DD; end date = start (Sunday) + 6 days (the following Saturday).
    weekstart = data.get("weekstart", "").strip()
    startDate = endDate = ""
    try:
        ws = datetime.strptime(weekstart, "%Y-%m-%d")
        startDate = ws.strftime("%Y-%m-%d")
        endDate = (ws + timedelta(days=6)).strftime("%Y-%m-%d")
    except ValueError:
        startDate = endDate = ""

    iMicroSeqFormattedMetadata = {}
    # specimen collector sample ID: join week (weekstart), location and target.
    iMicroSeqFormattedMetadata["specimen collector sample ID"] = "PHAC_" + data.get("weekstart", "") + "_" + data.get("Location", "") + "_" + measureid
    iMicroSeqFormattedMetadata["sampling site ID"] = data.get("Location", "")
    iMicroSeqFormattedMetadata["sampling event ID"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["INSDC Project accession"] = ""
    iMicroSeqFormattedMetadata["INSDC Sample accession"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["INSDC sequence read accession"] = ""
    iMicroSeqFormattedMetadata["sample collection project name"] = ""
    iMicroSeqFormattedMetadata["organism"] = organism
    iMicroSeqFormattedMetadata["taxonomic identification process"] = "PCR assay [OBI:0002740]"
    iMicroSeqFormattedMetadata["purpose of sampling"] = "Wastewater pathogen surveillance [GENEPIO:0100872]"
    iMicroSeqFormattedMetadata["sample collected by organisation name"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["sample collected by contact email"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["data steward contact name"] = "Public Health Agency of Canada"
    iMicroSeqFormattedMetadata["data steward contact email"] = "nmlwastewater@phac-aspc.gc.ca."
    iMicroSeqFormattedMetadata["sample collection data steward name"] = ""
    iMicroSeqFormattedMetadata["sample collection start date"] = startDate
    iMicroSeqFormattedMetadata["sample collection start date null reason"] = "" if startDate else "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["sample collection end date"] = endDate
    iMicroSeqFormattedMetadata["sample collection end date null reason"] = "" if endDate else "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["sample collection time duration value"] = "1"
    iMicroSeqFormattedMetadata["sample collection time duration value null reason"] = ""
    iMicroSeqFormattedMetadata["sample collection time duration unit"] = "Week [UO:0000034]"
    iMicroSeqFormattedMetadata["geo loc name (country)"] = PHACCountryDictionary.get(data.get("country", "").strip(), data.get("country", ""))
    iMicroSeqFormattedMetadata["geo loc name (state/province/territory)"] = stateProvince
    iMicroSeqFormattedMetadata["geo loc name (site)"] = data.get("site", "")
    iMicroSeqFormattedMetadata["geo loc name (city)"] = city
    iMicroSeqFormattedMetadata["geo loc latitude"] = latitude
    iMicroSeqFormattedMetadata["geo loc longitude"] = longitude
    iMicroSeqFormattedMetadata["environmental site"] = "Wastewater treatment plant [ENVO:00002272]"
    iMicroSeqFormattedMetadata["proximal environmental site"] = ""
    iMicroSeqFormattedMetadata["presampling activity ID"] = ""
    iMicroSeqFormattedMetadata["presampling activity date"] = ""
    iMicroSeqFormattedMetadata["presampling activity date null reason"] = ""
    iMicroSeqFormattedMetadata["presampling activity"] = ""
    iMicroSeqFormattedMetadata["presampling activity details"] = ""
    iMicroSeqFormattedMetadata["collection device"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["collection method"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["environmental material"] = "Wastewater [ENVO:00002001]"
    iMicroSeqFormattedMetadata["environmental material properties"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["anatomical material"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["anatomical part"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["body product"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["experimental specimen role type"] = ""
    iMicroSeqFormattedMetadata["specimen processing"] = "Pooling specimens [OBI:0600016]"
    iMicroSeqFormattedMetadata["specimen processing details"] = "Sample represents the weekly average of wastewater viral load values across samples collected at this site."
    iMicroSeqFormattedMetadata["experimental protocol name"] = ""
    iMicroSeqFormattedMetadata["experimental protocol url"] = ""
    iMicroSeqFormattedMetadata["experimental control details"] = ""
    iMicroSeqFormattedMetadata["nucleic acid extraction method"] = ""
    iMicroSeqFormattedMetadata["nucleic acid extraction kit"] = ""
    iMicroSeqFormattedMetadata["endogenous control details"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["available data types"] = ""
    iMicroSeqFormattedMetadata["available data type details"] = ""
    iMicroSeqFormattedMetadata["populated area type"] = "Urban [GSSO:011080]"
    iMicroSeqFormattedMetadata["water catchment area human population measurement value"] = ""
    iMicroSeqFormattedMetadata["water catchment area human population measurement value null reason"] = "Missing [GENEPIO:0001618]"
    iMicroSeqFormattedMetadata["water catchment area human population range"] = ""
    iMicroSeqFormattedMetadata["presampling weather conditions"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["sampling weather conditions"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["precipitation measurement value"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["precipitation measurement unit"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["water depth value"] = ""
    iMicroSeqFormattedMetadata["water depth units"] = ""
    iMicroSeqFormattedMetadata["sediment depth value"] = ""
    iMicroSeqFormattedMetadata["sediment depth units"] = ""
    iMicroSeqFormattedMetadata["pH measurement value"] = ""
    iMicroSeqFormattedMetadata["total daily flow rate measurement value"] = ""
    iMicroSeqFormattedMetadata["total daily flow rate measurement unit"] = ""
    iMicroSeqFormattedMetadata["instantaneous flow rate measurement value"] = ""
    iMicroSeqFormattedMetadata["instantaneous flow rate measurement unit"] = ""
    iMicroSeqFormattedMetadata["turbidity measurement value"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["turbidity measurement unit"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["conductivity measurement value"] = ""
    iMicroSeqFormattedMetadata["conductivity measurement unit"] = ""
    iMicroSeqFormattedMetadata["salinity measurement value"] = ""
    iMicroSeqFormattedMetadata["salinity measurement unit"] = ""
    iMicroSeqFormattedMetadata["dissolved oxygen measurement value"] = ""
    iMicroSeqFormattedMetadata["dissolved oxygen measurement unit"] = ""
    iMicroSeqFormattedMetadata["carbonaceous biochemical oxygen demand (CBOD) measurement value"] = ""
    iMicroSeqFormattedMetadata["carbonaceous biochemical oxygen demand (CBOD) measurement unit"] = ""
    iMicroSeqFormattedMetadata["total suspended solids (TSS) measurement value"] = ""
    iMicroSeqFormattedMetadata["total suspended solids (TSS) measurement unit"] = ""
    iMicroSeqFormattedMetadata["fecal contamination indicator"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["fecal contamination value"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["fecal contamination unit"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["host (common name)"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["host (scientific name)"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["host age"] = ""
    iMicroSeqFormattedMetadata["host age null reason"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["host age unit"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["host age bin"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["isolate ID"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["microbiological method"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["strain ID"] = ""
    iMicroSeqFormattedMetadata["isolated by organisation name"] = ""
    iMicroSeqFormattedMetadata["purpose of sequencing"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["assay type"] = "Reverse transcription polymerase chain reaction assay [OBI:0001170]"
    iMicroSeqFormattedMetadata["sequencing date"] = ""
    iMicroSeqFormattedMetadata["sequencing date null reason"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["sequenced by organisation name"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["sequenced by contact email"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["sequence submitted by"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["sequencing protocol"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["sequencing instrument"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["library ID"] = ""
    iMicroSeqFormattedMetadata["library preparation kit"] = ""
    iMicroSeqFormattedMetadata["genomic target enrichment method"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["genomic target enrichment method details"] = ""
    iMicroSeqFormattedMetadata["amplicon pcr primer scheme name"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["amplicon pcr primer scheme url"] = ""
    iMicroSeqFormattedMetadata["amplicon size"] = ""
    iMicroSeqFormattedMetadata["amplicon size null reason"] = ""
    iMicroSeqFormattedMetadata["raw sequence data processing method"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["dehosting method"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["genome sequence file name"] = ""
    iMicroSeqFormattedMetadata["sequence assembly software name"] = ""
    iMicroSeqFormattedMetadata["sequence assembly software version"] = ""
    iMicroSeqFormattedMetadata["consensus sequence software name"] = ""
    iMicroSeqFormattedMetadata["consensus sequence software version"] = ""
    iMicroSeqFormattedMetadata["breadth of coverage value"] = ""
    iMicroSeqFormattedMetadata["depth of coverage value"] = ""
    iMicroSeqFormattedMetadata["genome completeness"] = ""
    iMicroSeqFormattedMetadata["reference genome accession"] = ""
    iMicroSeqFormattedMetadata["bioinformatics protocol url"] = ""
    iMicroSeqFormattedMetadata["quality control method name"] = ""
    iMicroSeqFormattedMetadata["quality control method version"] = ""
    iMicroSeqFormattedMetadata["quality control determination"] = ""
    iMicroSeqFormattedMetadata["quality control issues"] = ""
    iMicroSeqFormattedMetadata["quality control details"] = ""
    iMicroSeqFormattedMetadata["read mapping software name"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["read mapping software version"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["taxonomic reference database name"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["taxonomic reference database version"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["viral type"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["viral subtype"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["viral lineage"] = ""
    iMicroSeqFormattedMetadata["viral clade"] = ""
    iMicroSeqFormattedMetadata["viral classification scheme"] = ""
    iMicroSeqFormattedMetadata["lineage/clade analysis software name"] = ""
    iMicroSeqFormattedMetadata["lineage/clade analysis software version"] = ""
    iMicroSeqFormattedMetadata["target taxonomic name 1"] = organism
    iMicroSeqFormattedMetadata["assay target name 1"] = measureid
    iMicroSeqFormattedMetadata["gene symbol 1"] = ""
    iMicroSeqFormattedMetadata["diagnostic target presence 1"] = "diagnostic target present [GENEPIO:0100987]"
    iMicroSeqFormattedMetadata["diagnostic measurement value 1"] = data.get("w_avg", "")
    iMicroSeqFormattedMetadata["diagnostic measurement unit 1"] = "copies per mililiter (C/ml) [GENEPIO:0102225]"
    iMicroSeqFormattedMetadata["diagnostic measurement method 1"] = "Quantitative real time polymerase chain reaction (qPCR) [OBI:0000893]"
    iMicroSeqFormattedMetadata["target taxonomic name 2"] = ""
    iMicroSeqFormattedMetadata["assay target name 2"] = ""
    iMicroSeqFormattedMetadata["gene symbol 2"] = ""
    iMicroSeqFormattedMetadata["diagnostic target presence 2"] = ""
    iMicroSeqFormattedMetadata["diagnostic measurement value 2"] = ""
    iMicroSeqFormattedMetadata["diagnostic measurement unit 2"] = ""
    iMicroSeqFormattedMetadata["diagnostic measurement method 2"] = ""
    iMicroSeqFormattedMetadata["target taxonomic name 3"] = ""
    iMicroSeqFormattedMetadata["assay target name 3"] = ""
    iMicroSeqFormattedMetadata["gene symbol 3"] = ""
    iMicroSeqFormattedMetadata["diagnostic target presence 3"] = ""
    iMicroSeqFormattedMetadata["diagnostic measurement value 3"] = ""
    iMicroSeqFormattedMetadata["diagnostic measurement unit 3"] = ""
    iMicroSeqFormattedMetadata["diagnostic measurement method 3"] = ""
    iMicroSeqFormattedMetadata["authors"] = "Public Health Agency of Canada"
    iMicroSeqFormattedMetadata["citation URL"] = "https://health-infobase.canada.ca/wastewater/"

    return iMicroSeqFormattedMetadata


def parsePHAC(path):
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df.to_dict("records")


def subSample(df, name, n=10):
    """Write ``n`` randomly-selected rows alongside the full output for review."""
    sample = df.sample(n=min(n, len(df)))
    sample.to_csv(name + '_subsample.csv', index=False)
    print(f"Wrote {len(sample)} random rows -> {name}_subsample.csv")


def parsePHACData(data, name):
    records = []
    with tqdm.tqdm(total=len(data), desc=os.path.basename(name), leave=True) as pbar:
        for row in data:
            records.append(convertPHACintoiMicroSeq(row))
            pbar.update(1)

    df = pd.DataFrame(records, columns=columnNames)
    outDir = os.path.dirname(name)
    if outDir:
        os.makedirs(outDir, exist_ok=True)
    df.to_csv(name, index=False)
    #subSample(df, name)

    # persist the geocoding cache and report any unresolved lookups
    with open(_geocodeCachePath, "w") as f:
        json.dump(_geocodeCache, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(df)} rows -> {name}")
    for kind, values in _phacMissing.items():
        values = sorted(v for v in values if v != "")
        if values:
            print(f"[MISSING] {kind}: {values} — please provide values")


# --- PHAC wastewater_aggregate -> iMicroSeq ---
def main():
    _scriptDir = os.path.dirname(os.path.abspath(__file__))
    defaultInput = os.path.join(_scriptDir, "..", "raw", "wastewater_aggregate.csv")
    defaultOutput = os.path.join(_scriptDir, "..", "curated", "PHAC-NWMP.csv")

    parser = argparse.ArgumentParser(
        description="Convert a PHAC wastewater_aggregate CSV into the iMicroSeq schema."
    )
    parser.add_argument(
        "-i", "--input", default=defaultInput,
        help="Path to the input PHAC wastewater_aggregate CSV "
             "(default: %(default)s)",
    )
    parser.add_argument(
        "-o", "--output", default=defaultOutput,
        help="Path to the output iMicroSeq CSV; parent folders are created "
             "if they do not exist (default: %(default)s)",
    )
    args = parser.parse_args()

    parsePHACData(parsePHAC(args.input), args.output)


if __name__ == "__main__":
    main()
