# M-COSMIC feldolgozás és vizualizáció

Magyar nyelv? Streamlit alkalmazás az [M-COSMIC](https://docs.autismresearchcentre.com/papers/2010_Clifford_The%20Modified-Classroom%20Observation%20Schedule.pdf) osztálytermi felmérések feldolgozásához.

## Telepítés

`powershell
cd c:\\Users\\User\\Projects\\mcosmic
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
`

## Futtatás

`powershell
streamlit run app.py
`

A böngész?ben tölts fel egy kitöltött CSV vagy Excel (.xlsx) fájlt (pl. mcosmic_gyerek_1.csv). A kategóriákat a program a data/kategoriak.yaml fájlból tölti be.

## Bemeneti fájl formátum

Elfogadott: **CSV** (pontosvessz?vel) vagy **Excel** (.xlsx, .xlsm), ugyanazzal a táblaszerkezettel. A CSV pontosvessz?vel (;) elválasztott, tipikusan Excelb?l exportált:

1. sor: cím
2. sor: metaadatok (Gyermek, Megfigyel?, Dátum/id?szak)
3. sor: fejléc (kontextus, partner, unkció, szerep, orma, jegyzet)
4. sortól: tetsz?leges számú eseménysor (1., 2., … vagy üres sorszámmez?vel is)

Üres sorok automatikusan kiesnek. A számok a data/kategoriak.yaml kódjaira hivatkoznak.

## Kategóriák frissítése (fejleszt?knek)

Ha módosul az Excel kategórialap:

`powershell
python -m mcosmic.export_categories mcosmic_kategoriak.xlsx
`

Ez felülírja a data/kategoriak.yaml fájlt.

## Projektstruktúra

- pp.py — Streamlit felület (CSV / Excel feltöltés)
- mcosmic/loader.py — CSV / Excel ? pandas
- mcosmic/categories.py — magyar címkék
- mcosmic/aggregate.py — összesítések
- mcosmic/viz.py — Plotly diagramok
- data/kategoriak.yaml — rögzített kategóriák
