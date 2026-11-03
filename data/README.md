# Example datasets

Each folder contains a data file and a `problem_description.json`. The JSON holds what
you enter on the "Define the Problem" page:
- the project description
- the target column
- a description for each feature

You can paste the JSON into the app or send it as `params` to the
[API](../docs/api.md):

```bash
python examples/api_client.py data/example_1
```

| Folder | Domain | Rows | Target | Kind |
|---|---|---|---|---|
| `example_1` | Soil chemistry | 119 | AL-soluble phosphate (`al_p2o5`) | Cross-sectional, with a categorical soil type |
| `example_2` | Materials (perovskite solar cells) | 33 | Power conversion efficiency | Small cross-sectional dataset (cross-validation only) |
| `example_3` | Neuroscience (connectomes) | 100 to 129k per species | Neuron wire length (`Length`) | Scaling law across eight species |
| `example_4` | Ecology (grassland) | 249 (yearly) | Gross primary production (`GPP`) | Long time series |

## example_1: Soil phosphorus

Soil samples with phosphorus measured by two extraction methods (ammonium lactate and
Mehlich-3), plus organic matter, lime content, pH (KCl) and USDA soil type code. The
task is to predict AL-P2O5 from the other properties. The soil type is an integer code
and is treated as a category.

## example_2: Perovskite solar cells

Perovskite solar cells fabricated under different environmental conditions. The
conditions are temperature, absolute humidity and solvent partial pressure during spin
coating and thermal annealing. The task is to relate them to power conversion
efficiency. With only 33 rows, models are scored by cross-validation alone.

## example_3: Neuron wire length across connectomes

Per-neuron aggregates of wire length, synapse count, degree (number of partners) and
local density. They come from public connectome reconstructions of eight species and
brain regions:
- *C. elegans*
- *Drosophila* larva
- adult *Drosophila* brain (FlyWire, Hemibrain)
- *Drosophila* ventral nerve cord (MANC)
- zebrafish
- mouse visual cortex (MICrONS MM3)
- human cortex (H01)

The question is whether one formula relates structure (length) to connectivity across
species. `problem_description.json` refers to `Celegans_AggregatedData.csv`; the other
files are there for comparison.

## example_4: Grassland productivity

Yearly gross primary production of a grassland from 1772 onwards, together with:
- atmospheric CO₂
- climate indices (AMO, NAO)
- drought and moisture indicators (PDSI, soil moisture index, vapour pressure deficit
  and its variability)
- spring-summer mean temperature

The rows form a long, regular time series. The run detects it, considers lagged and
period features, and holds out the last years chronologically.

## Using your own data

- Upload `.csv`, `.xlsx` or `.xls` files with one row per observation and one column per
  variable.
- Only numeric columns can be features. Encode categories as integer codes; codes with up
  to 10 levels are treated as categories.
- The target must not have missing values. Rows missing a selected feature are dropped,
  and the results say how many were dropped.
- For time series, keep the date or time column in the file, even though it is not a
  feature. It is used to detect the series.
