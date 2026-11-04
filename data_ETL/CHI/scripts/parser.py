"""Convert CHI's Alberta wastewater data to the iMicroSeq schema.

Reads the three files etl.sh downloads from chi-covid-data.pages.dev and writes
one CSV with every record:

    python parser.py --rsvflu rsvFlu.json --covid aplWasteWaterAbData.json \
        --covid-pre2023 wasteWaterAbData.json --output CHI.csv
"""
import argparse
import pandas as pd
import math
import os
from datetime import datetime, timedelta
import re
import tqdm
from dateutil import parser
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
import json

columnNames = ["specimen collector sample ID","sampling site ID","sampling event ID","INSDC Project accession","INSDC Sample accession","INSDC sequence read accession","sample collection project name","organism","taxonomic identification process","purpose of sampling","sample collected by organisation name","sample collected by contact email","data steward contact name","data steward contact email","sample collection data steward name","sample collection start date","sample collection start date null reason","sample collection end date","sample collection end date null reason","sample collection time duration value","sample collection time duration value null reason","sample collection time duration unit","geo loc name (country)","geo loc name (state/province/territory)","geo loc name (site)","geo loc name (city)","geo loc latitude","geo loc longitude","environmental site","proximal environmental site","presampling activity ID","presampling activity date","presampling activity date null reason","presampling activity","presampling activity details","collection device","collection method","environmental material","environmental material properties","anatomical material","anatomical part","body product","experimental specimen role type","specimen processing","specimen processing details","experimental protocol name","experimental protocol url","experimental control details","nucleic acid extraction method","nucleic acid extraction kit","endogenous control details","available data types","available data type details","populated area type","water catchment area human population measurement value","water catchment area human population measurement value null reason","water catchment area human population range","presampling weather conditions","sampling weather conditions","precipitation measurement value","precipitation measurement unit","water depth value","water depth units","sediment depth value","sediment depth units","pH measurement value","total daily flow rate measurement value","total daily flow rate measurement unit","instantaneous flow rate measurement value","instantaneous flow rate measurement unit","turbidity measurement value","turbidity measurement unit","conductivity measurement value","conductivity measurement unit","salinity measurement value","salinity measurement unit","dissolved oxygen measurement value","dissolved oxygen measurement unit","carbonaceous biochemical oxygen demand (CBOD) measurement value","carbonaceous biochemical oxygen demand (CBOD) measurement unit","total suspended solids (TSS) measurement value","total suspended solids (TSS) measurement unit","fecal contamination indicator","fecal contamination value","fecal contamination unit","host (common name)","host (scientific name)","host age","host age null reason","host age unit","host age bin","isolate ID","microbiological method","strain ID","isolated by organisation name","purpose of sequencing","assay type","sequencing date","sequencing date null reason","sequenced by organisation name","sequenced by contact email","sequence submitted by","sequencing protocol","sequencing instrument","library ID","library preparation kit","genomic target enrichment method","genomic target enrichment method details","amplicon pcr primer scheme name","amplicon pcr primer scheme url","amplicon size","amplicon size null reason","raw sequence data processing method","dehosting method","genome sequence file name","sequence assembly software name","sequence assembly software version","consensus sequence software name","consensus sequence software version","breadth of coverage value","depth of coverage value","genome completeness","reference genome accession","bioinformatics protocol url","quality control method name","quality control method version","quality control determination","quality control issues","quality control details","read mapping software name","read mapping software version","taxonomic reference database name","taxonomic reference database version","viral type","viral subtype","viral lineage","viral clade","viral classification scheme","lineage/clade analysis software name","lineage/clade analysis software version","target taxonomic name 1","assay target name 1","gene symbol 1","diagnostic target presence 1","diagnostic measurement value 1","diagnostic measurement unit 1","diagnostic measurement method 1","target taxonomic name 2","assay target name 2","gene symbol 2","diagnostic target presence 2","diagnostic measurement value 2","diagnostic measurement unit 2","diagnostic measurement method 2","target taxonomic name 3","assay target name 3","gene symbol 3","diagnostic target presence 3","diagnostic measurement value 3","diagnostic measurement unit 3","diagnostic measurement method 3","authors","citation URL"]

wwCollectionMaterial = {
    'rawWW' : "Waste water",
    'RawWW' : "Waste water",
    'Raw WW' : "Waste water", 
    'pstGrit' : "(Non-standard) Post Grit",
    'pEfflu' : 'Primary wastewater effluent',
    'pSludge' : 'Primary sludge',
    'swrSed' : "Wastewater sediment",
    '' : ''
}

SiteTypeDictionary = {
    "uCampus" : "College or university [ENVO:03501131]",
    "hosptl" : "Hospital [ENVO:00002173]",
    "mSwrPpl" : "Sewer pipe [GENEPIO:0102064]",
    "wwtpMuS" : "Wastewater treatment plant [ENVO:00002272]",
    "wwtpMuC" : "Wastewater treatment plant [ENVO:00002272]",
    "corFcil" : "Correctional facility [ENVO:01001481]",
    "school" : "School [ENVO:03501130]",
    "pStat" : "Influent pump station [ENVO:03501465]",
    "ltcf" : "Long-term care facility [ENVO:01000932]",
    "Upstream site" : "Roadside [ENVO:01000447]",
    "Shelter" : "Homeless shelter [ENVO:03501133]",
    "homeless shelter" : "Homeless shelter [ENVO:03501133]",
    "hospital" : "Hospital [ENVO:00002173]",
    "Odour control" : "Airport [ENVO:03501122]",
    "other" : "!!!NOINFO",
    '' : ''
}

CollectionMethodDictionary = {
    "cp" : "Composite sampling [GENEPIO:0100954]",
    "cpFP24h" : "Automatic composite sampling [GENEPIO:0100956]",
    "cpTP24h" : "Automatic composite sampling [GENEPIO:0100956]",
    "cpgrb" : "Composite sampling [GENEPIO:0100954];Grab sampling [GENEPIO:0100953]",
    "grb" : "Grab sampling [GENEPIO:0100953]",
    "grbCp3h" : "Manual composite sampling [GENEPIO:0100957]",
    "grbCp8h" : "Manual composite sampling [GENEPIO:0100957]",
    "mooreSw" : "Passive composite sampling [GENEPIO:0100955]",
    '' : ''
}

CollectionDeviceDictionary = {
    "cp" : "Automatic composite sampler [GENEPIO:0100950]",
    "cpFP24h" : "Automatic flow-proportional sampler [GENEPIO:0100951]",
    "cpTP24h" : "Automatic sequential (time-proportional) sampler [GENEPIO:0100952]",
    "cpgrb" : "Automatic composite sampler [GENEPIO:0100950]",
    "grb" : "Grab sampler [GENEPIO:0100941]",
    "grbCp3h" : "Grab sampler [GENEPIO:0100941]",
    "grbCp8h" : "Grab sampler [GENEPIO:0100941]",
    "mooreSw" : "Moore swab [GENEPIO:0100949]",
    '' : ''
}

EnvironmentalMaterialsDictionary = {
    "rawWW" : "Wastewater [ENVO:00002001]",
    "RawWW" : "Wastewater [ENVO:00002001]",
    "pSludge" : "Primary sludge [ENVO:00002057]",
    "Raw WW" : "Wastewater [ENVO:00002001]",
    "pstGrit" : "Wastewater [ENVO:00002001]",
    '' : ''
}

EnvironmentalMaterialsPropertiesDictionary = {
    "liquid" : "Liquid [PATO:0001735]",
    "solid" : "Solid [PATO:0001736]",
    "mixed" : "Solid [PATO:0001736];Liquid [PATO:0001735]",
    "solids" : "Solid [PATO:0001736]",
    "Solid" : "Solid [PATO:0001736]",
    "SOLID" : "Solid [PATO:0001736]",
    '' : ''
}

FlowRateUnitDictionary = {
    "L/s" : "liter per second (L/s) [GENEPIO:0102195]",
    "m3/h" : "cubic meter per hour (m^3/h) [GENEPIO:0102194]",
    "m3/hr" : "cubic meter per hour (m^3/h) [GENEPIO:0102194]",
    "m3/d" : "!!!MISSING",
    "m3/day" : "!!!MISSING",
    "ML/D" : "!!!MISSING",
    '' : ''
}

TotalDissolvedSolidsUnitDictionary = {
    "mg/L" : "!!!MISSING",
    '' : ''
}

CarbonousOxygenDemandUnitDictionary = {
    "mg/L" : "milligram per liter (mg/L) [UO:0000273]",
    '' : ''
}

TargetTaxonomyNameDictionary = {
    "covN1" : "Severe acute respiratory syndrome coronavirus 2",
    "covN2" : "Severe acute respiratory syndrome coronavirus 2",
    "nPMMoV" : "Pepper mild mottle virus",
    "covE" : "Severe acute respiratory syndrome coronavirus 2",
    "covN200" : "Severe acute respiratory syndrome coronavirus 2",
    "FRNA G2" : "F-specific RNA bacteriophages Genogroup 2",
    "FRNA" : "F-specific RNA bacteriophages",
    '' : ''
}

AssayTargetNameDictionary = {
    "covN1" : "SARS-CoV-2 N1",
    "covN2" : "SARS-CoV-2 N2",
    "nPMMoV" : "PMMoV",
    "covE" : "SARS-CoV-2 E",
    "covN200" : "SARS-CoV-2 N200",
    "FRNA G2" : "FRNA bacteriophage",
    "FRNA" : "FRNA bacteriophage",
    '' : ''
}

GeneSymbolDictionary = {
    "covN1" : "N",
    "covN2" : "N",
    "nPMMoV" : "",
    "covE" : "E",
    "covN200" : "N",
    "FRNA G2" : "",
    "FRNA" : "",
    '' : ''
}

DiagnosticTargetUnitDictionary = {
    "cpMl" : "copies per mililiter (C/ml) [GENEPIO:0102225]",
    "cpPerson" : "",  # copies per person: no such unit in the iMicroSeq list yet, so left blank
    "gcGs" : "!!!MISSING",
    "gcL" : "copies per liter (C/L) [GENEPIO:0102202]",
    "gcMl" : "!!!MISSING",
    "gcPMMoV" : "!!!MISSING",
    "gcmL" : "!!!MISSING",
    "other" : "!!!MISSING",
    "ppms" : "!!!MISSING",
    "tnms" : "!!!MISSING",
    "gc" : "!!!MISSING",
    '' : ''
}

OrganismDictionary = {
    "inf_a" : "Influenza A virus [NCBITaxon:11320]",
    "inf_b" : "Influenza B virus [NCBITaxon:11520]",
    "rsv" : "Respiratory syncytial virus [NCBITaxon:12814]",
    "covid" : "Severe acute respiratory syndrome coronavirus 2 [NCBITaxon:2697049]"
}

OrganisationDictionary = {
    "Airdrie" : "University of Calgary",
    "Banff" : "University of Alberta",
    "Bonnybrook Wastewater Treatment Plant" : "University of Calgary",
    "Brooks" : "University of Calgary",
    "Canmore" : "University of Calgary",
    "Cold Lake" : "University of Alberta",
    "Drumheller" : "University of Calgary",
    "Edmonton" : "University of Alberta",
    "Edson" : "University of Calgary",
    "Fish Creek Wastewater Treatment Plant" : "University of Calgary",
    "Fort McMurray" : "University of Calgary",
    "Fort Saskatchewan" : "University of Alberta",
    "Grande Prairie" : "University of Alberta",
    "High River" : "University of Alberta",
    "Jasper" : "University of Alberta",
    "Lacombe" : "University of Calgary",
    "Lethbridge" : "University of Alberta",
    "Medicine Hat" : "University of Alberta",
    "Okotoks" : "University of Calgary",
    "Pine Creek Wastewater Treatment Plant" : "University of Calgary",
    "Red Deer" : "University of Alberta",
    "Strathmore" : "University of Calgary",
    "Taber" : "University of Calgary",
    "Calgary" : "University of Calgary"
}

specimenProcessingDictionary = {
    "University of Alberta" : "Filtration [OBI:0302885]",
    "University of Calgary" : "Centrifugation [OBI:0302886]"
}

specimenProcessingDetailsDictionary = {
    "University of Alberta" : "ultrafiltration method of concentration that is widely employed for recovery of viruses, including SARS-CoV-2, from different aqueous samples including wastewater, recreational water and agricultural run-off (Forés et al., 2021; Lee et al., 2021; Qiu et al., 2016; Qiu et al., 2022; Winona et al., 2001)",
    "University of Calgary" : "affinity column method based on the “4S” direct extraction protocol (Whitney et al., 2021)"
}




def convertAlbertaRsvFluintoiMicroSeq(sampleID, data):
    #print(sampleID)
    #sampleID = 'Sample 2C_Dup_Apr14'
    

    iMicroSeqFormattedMetadata = {}
    iMicroSeqFormattedMetadata["specimen collector sample ID"] = sampleID
    iMicroSeqFormattedMetadata["sampling site ID"] = data["Site"]
    iMicroSeqFormattedMetadata["sampling event ID"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["INSDC Project accession"] = ""
    iMicroSeqFormattedMetadata["INSDC Sample accession"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["INSDC sequence read accession"] = ""
    iMicroSeqFormattedMetadata["sample collection project name"] = ""
    iMicroSeqFormattedMetadata["organism"] = OrganismDictionary[data["Organism"]]
    iMicroSeqFormattedMetadata["taxonomic identification process"] = "PCR assay [OBI:0002740]"
    iMicroSeqFormattedMetadata["purpose of sampling"] = "Wastewater pathogen surveillance [GENEPIO:0100872]"
    iMicroSeqFormattedMetadata["sample collected by organisation name"] = OrganisationDictionary[data["Site"]]
    iMicroSeqFormattedMetadata["sample collected by contact email"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["data steward contact name"] = "Centre for Health Informatics, Cumming School of Medicine, University of Calgary"
    iMicroSeqFormattedMetadata["data steward contact email"] = "chi@ucalgary.ca"
    iMicroSeqFormattedMetadata["sample collection data steward name"] = "Centre for Health Informatics, Cumming School of Medicine, University of Calgary"
    iMicroSeqFormattedMetadata["sample collection start date"] = data['Date']
    iMicroSeqFormattedMetadata["sample collection start date null reason"] = ""
    iMicroSeqFormattedMetadata["sample collection end date"] = (parser.parse(data["Date"]) + timedelta(days=1)).strftime("%Y-%m-%d")
    iMicroSeqFormattedMetadata["sample collection end date null reason"] = ""
    iMicroSeqFormattedMetadata["sample collection time duration value"] = "24"
    iMicroSeqFormattedMetadata["sample collection time duration value null reason"] = ""
    iMicroSeqFormattedMetadata["sample collection time duration unit"] = "Hour [UO:0000032]"
    iMicroSeqFormattedMetadata["geo loc name (country)"] = "Canada [GAZ:00002560]"
    iMicroSeqFormattedMetadata["geo loc name (state/province/territory)"] = "Alberta [GAZ:00002566]"
    iMicroSeqFormattedMetadata["geo loc name (site)"] = data["Site"].replace(" Wastewater Treatment Plant", "") + " WWTP"
    iMicroSeqFormattedMetadata["geo loc name (city)"] = data["Site"].replace(" Wastewater Treatment Plant", "")
    iMicroSeqFormattedMetadata["geo loc latitude"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["geo loc longitude"] = "Not Provided [GENEPIO:0001668]"
    iMicroSeqFormattedMetadata["environmental site"] = "Wastewater treatment plant [ENVO:00002272]"
    iMicroSeqFormattedMetadata["proximal environmental site"] = ""
    iMicroSeqFormattedMetadata["presampling activity ID"] = ""
    iMicroSeqFormattedMetadata["presampling activity date"] = ""
    iMicroSeqFormattedMetadata["presampling activity date null reason"] = ""
    iMicroSeqFormattedMetadata["presampling activity"] = ""
    iMicroSeqFormattedMetadata["presampling activity details"] = ""
    iMicroSeqFormattedMetadata["collection device"] = "Automatic flow-proportional sampler [GENEPIO:0100951]"
    iMicroSeqFormattedMetadata["collection method"] = "Automatic composite sampling [GENEPIO:0100956]"
    iMicroSeqFormattedMetadata["environmental material"] = "Wastewater [ENVO:00002001]"
    iMicroSeqFormattedMetadata["environmental material properties"] = "Untreated [GENEPIO:0101009]"
    iMicroSeqFormattedMetadata["anatomical material"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["anatomical part"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["body product"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["experimental specimen role type"] = "Biological replicate [EFO:0002091]"
    iMicroSeqFormattedMetadata["specimen processing"] = specimenProcessingDictionary[OrganisationDictionary[data["Site"]]]
    iMicroSeqFormattedMetadata["specimen processing details"] = specimenProcessingDetailsDictionary[OrganisationDictionary[data["Site"]]]
    iMicroSeqFormattedMetadata["experimental protocol name"]  = "McCalder et al. 2025"
    iMicroSeqFormattedMetadata["experimental protocol url"] = "https://doi.org/10.3389/fmicb.2025.1547831"
    iMicroSeqFormattedMetadata["experimental control details"] = ""
    iMicroSeqFormattedMetadata["nucleic acid extraction method"] = "McCalder et al. 2025"
    iMicroSeqFormattedMetadata["nucleic acid extraction kit"] = "MagMAX™ Viral RNA Isolation kit" if OrganisationDictionary[data["Site"]] == "University of Alberta" else "Custom, see McCalder et al. 2025"
    iMicroSeqFormattedMetadata["endogenous control details"] = "bovine coronavirus (BCoV) surrogate (Merck catalogue #151921; Merck Animal Health, United States)"
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
    iMicroSeqFormattedMetadata["fecal contamination indicator"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["fecal contamination value"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["fecal contamination unit"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["host (common name)"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["host (scientific name)"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["host age"] = ""
    iMicroSeqFormattedMetadata["host age null reason"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["host age unit"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["host age bin"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["isolate ID"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["microbiological method"] = "Not Applicable [GENEPIO:0001619]"
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
    iMicroSeqFormattedMetadata["amplicon pcr primer scheme name"] = "Missing [GENEPIO:0001618]"
    iMicroSeqFormattedMetadata["amplicon pcr primer scheme url"] = "Missing [GENEPIO:0001618]"
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
    iMicroSeqFormattedMetadata["quality control issues"] = ""
    iMicroSeqFormattedMetadata["quality control determination"] = ""
    iMicroSeqFormattedMetadata["quality control details"] = ""
    iMicroSeqFormattedMetadata["read mapping software name"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["read mapping software version"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["taxonomic reference database name"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["taxonomic reference database version"] = "Not Applicable [GENEPIO:0001619]"
    iMicroSeqFormattedMetadata["viral type"] = "Not Collected [GENEPIO:0001620]"
    iMicroSeqFormattedMetadata["viral subtype"] = "Not Collected [GENEPIO:0001620]"
    iMicroSeqFormattedMetadata["viral lineage"] = ""
    iMicroSeqFormattedMetadata["viral clade"] = ""
    iMicroSeqFormattedMetadata["viral classification scheme"] = ""
    iMicroSeqFormattedMetadata["lineage/clade analysis software name"] = ""
    iMicroSeqFormattedMetadata["lineage/clade analysis software version"] = ""

    if ("V2" in data.keys()):
        i = 1
        iMicroSeqFormattedMetadata["target taxonomic name " + str(i)] = OrganismDictionary[data["Organism"]]
        iMicroSeqFormattedMetadata["assay target name " + str(i)] = "COV_N1"
        iMicroSeqFormattedMetadata["gene symbol " + str(i)] = "N"
        iMicroSeqFormattedMetadata["diagnostic target presence " + str(i)] = "diagnostic target absent [GENEPIO:0100988]" if data["V"] == 0 else "diagnostic target present [GENEPIO:0100987]"
        iMicroSeqFormattedMetadata["diagnostic measurement value " + str(i)] = data['V']
        iMicroSeqFormattedMetadata["diagnostic measurement unit " + str(i)] = DiagnosticTargetUnitDictionary[data["Unit"]]
        iMicroSeqFormattedMetadata["diagnostic measurement method " + str(i)] = "Quantitative real time polymerase chain reaction (qPCR) [OBI:0000893]"
        i = 2
        iMicroSeqFormattedMetadata["target taxonomic name " + str(i)] = OrganismDictionary[data["Organism"]]
        iMicroSeqFormattedMetadata["assay target name " + str(i)] = "COV_N2"
        iMicroSeqFormattedMetadata["gene symbol " + str(i)] = "N"
        iMicroSeqFormattedMetadata["diagnostic target presence " + str(i)] = "diagnostic target absent [GENEPIO:0100988]" if data["V2"] == 0 else "diagnostic target present [GENEPIO:0100987]"
        iMicroSeqFormattedMetadata["diagnostic measurement value " + str(i)] = data['V2']
        iMicroSeqFormattedMetadata["diagnostic measurement unit " + str(i)] = DiagnosticTargetUnitDictionary[data["Unit"]]
        iMicroSeqFormattedMetadata["diagnostic measurement method " + str(i)] = "Quantitative real time polymerase chain reaction (qPCR) [OBI:0000893]"
    else:

        i = 1
        iMicroSeqFormattedMetadata["target taxonomic name " + str(i)] = OrganismDictionary[data["Organism"]]
        iMicroSeqFormattedMetadata["assay target name " + str(i)] = "Not Provided [GENEPIO:0001668]"
        iMicroSeqFormattedMetadata["gene symbol " + str(i)] = "Not Provided [GENEPIO:0001668]"
        iMicroSeqFormattedMetadata["diagnostic target presence " + str(i)] = "diagnostic target absent [GENEPIO:0100988]" if data["V"] == 0 else "diagnostic target present [GENEPIO:0100987]"
        iMicroSeqFormattedMetadata["diagnostic measurement value " + str(i)] = data['V']
        iMicroSeqFormattedMetadata["diagnostic measurement unit " + str(i)] = DiagnosticTargetUnitDictionary[data["Unit"]]
        iMicroSeqFormattedMetadata["diagnostic measurement method " + str(i)] = "Quantitative real time polymerase chain reaction (qPCR) [OBI:0000893]"

    iMicroSeqFormattedMetadata["authors"] = "Centre for Health Informatics, Cumming School of Medicine, University of Calgary"
    iMicroSeqFormattedMetadata["citation URL"] = "https://covid-tracker.chi-csm.ca/"
    
    return iMicroSeqFormattedMetadata


def toDictionary(df):
    """One entry per sample ID, <Site>_<Date>_<Organism>. A record listed more
    than once is kept once if the copies are identical. Copies that differ are
    all kept, numbered in file order: <ID>_1, <ID>_2, ..."""
    df = df.drop_duplicates()
    ids = df.Site + "_" + df.Date + "_" + df.Organism
    number = ids.groupby(ids).cumcount() + 1
    ids = ids.where(~ids.duplicated(keep=False), ids + "_" + number.astype(str))
    return {id: row.to_dict() for id, (_, row) in zip(ids, df.iterrows())}


def parseRSVFluData(path):
    with open(path, "r") as f:
        data = json.load(f)['data']
    rows = []
    for site, organisms in data.items():
        for organism, dates in organisms.items():
            for date, values in dates.items():
                rows.append({
                    "Site": site,
                    "Organism": organism,
                    "Date": date,
                    "V": values.get("v") if len(values) != 0 else 0,
                    "SD": values.get("sd", None),
                    "Unit": "cpMl",
                })

    df = pd.DataFrame(rows).astype(object).fillna("")
    return toDictionary(df)


def parsePre2023COVID(path, skipSiteDates=()):
    """skipSiteDates: (site, date) pairs to leave out, because the post-2023 file has them."""
    with open(path, "r") as f:
        data = json.load(f)['data']
    rows = []
    data = [v for v in data if v["data_type"] == 'raw' and v["location"]!="Calgary"
            and (v["location"], v["date"]) not in skipSiteDates]
    
    for datapoint in data:
        rows.append({
            "Site": datapoint.get('location'),
            "Organism": "covid",
            "Date": datapoint.get('date'),
            "V": datapoint.get("n1_mean", 0),
            "V2": datapoint.get("n2_mean", 0),
            "SD": datapoint.get("n1_sd", ""),
            "SD2": datapoint.get("n2_sd", ""),
            "Unit": "cpMl",
        })

    df = pd.DataFrame(rows).astype(object).fillna("")
    return toDictionary(df)


def parsePost2023COVID(path):
    with open(path, "r") as f:
        data = json.load(f)['data']
    rows = []
    for site, values in data.items():
        for row in values:
            rows.append({
                "Site": site,
                "Organism": "covid",
                "Date": row.get("date"),
                "V": row.get("n1", 0),
                "V2": row.get("n2", 0),
                "Unit": "cpPerson",
            })

    df = pd.DataFrame(rows).astype(object).fillna("")
    return toDictionary(df)

def parseData(datasets, output):
    """datasets: (name, dictionary) pairs. Writes every record to one CSV."""
    records = [d for _, data in datasets for d in data.values()]
    unknownSites = sorted({d["Site"] for d in records} - set(OrganisationDictionary))
    unknownOrganisms = sorted({d["Organism"] for d in records} - set(OrganismDictionary))
    if unknownSites or unknownOrganisms:
        raise SystemExit(f"[MISSING] new site(s) {unknownSites} / organism(s) {unknownOrganisms}: "
                         "add them to OrganisationDictionary / OrganismDictionary in parser.py")

    rows = []
    for name, data in datasets:
        for id, d in tqdm.tqdm(data.items(), desc=name, leave=True):
            rows.append(convertAlbertaRsvFluintoiMicroSeq(id, d))
    df = pd.DataFrame(rows, columns=columnNames)

    for column in df.columns:
        missing = df[column].astype(str).str.startswith("!!!")
        if missing.any():
            print(f"[MISSING] {column}: {missing.sum()} row(s) have no iMicroSeq value -- left blank")
    df = df.replace(r'^!!!.*', '', regex=True)
    df.to_csv(output, index=False)
    print(f"{len(df)} rows -> {output}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rsvflu", required=True, help="rsvFlu.json (influenza A/B and RSV)")
    ap.add_argument("--covid", required=True, help="aplWasteWaterAbData.json (COVID from July 2023)")
    ap.add_argument("--covid-pre2023", required=True, help="wasteWaterAbData.json (COVID up to July 2023)")
    ap.add_argument("--output", required=True, help="CSV to write")
    args = ap.parse_args()

    covid = parsePost2023COVID(args.covid)
    # The two COVID files overlap in July 2023, in different units. The post-2023 file wins.
    covidPre2023 = parsePre2023COVID(args.covid_pre2023, {(d["Site"], d["Date"]) for d in covid.values()})
    parseData([("AlbertaFluRSV", parseRSVFluData(args.rsvflu)),
               ("AlbertaCOVIDPre2023", covidPre2023),
               ("AlbertaCOVIDPost2023", covid)], args.output)
