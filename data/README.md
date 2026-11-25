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
| `example_1` | Soil chemistry | 119 | AL-soluble phosphate (`al_p2o5`) | Measured, cross-sectional, with a categorical soil type |
| `example_2` | Thin-film coating line (synthetic) | 200 | Sheet resistance (`sheet_resistance`) | Known laws, with supplied literature that agrees with the data |
| `example_3` | Thin-film coating line (synthetic) | 200 | Deposition rate (`rate`) | The same data, with supplied literature that contains one false sentence |
| `example_4` | Hydrology (river) | 606 (daily) | Water temperature (`water_temp`) | Measured time series |

These are the four use cases of the Syxplain paper and its supplementary material.

## example_1: Soil phosphorus

Soil samples with phosphorus measured by two extraction methods (ammonium lactate and
Mehlich-3), plus organic matter, lime content, pH (KCl) and USDA soil type code. The
task is to predict AL-P2O5 from the other properties. The soil type is an integer code
and is treated as a category.

## example_2: Coating line, sheet resistance

A fictitious thin-film coating line: 200 samples with process settings (precursor
pressure, temperature, flow, plasma power, deposition time, annealing temperature),
laboratory humidity, and measured chamber pressure, deposition rate, thickness, grain
size, sheet resistance and transmittance. The data are synthetic. `generate.py` holds
the laws they were generated from and the noise of each column, and `ground_truth.json`
the fits of those laws on the generated columns. Run from another directory,
`generate.py` writes its files there.

`pseudo_papers.md` is invented literature for this system (seven short notes). Its text
is also in `problem_description.json` as `literature_text`, so the run reads it as
supplied literature and chooses the recommended equation among the equations that are
coherent with it. The notes agree with the laws of the data.

## example_3: Coating line, deposition rate

The same data with the deposition rate as target. The supplied literature
(`pseudo_papers_false_sentence.md`, also in `problem_description.json`) contains one false
sentence: that the rate does not depend on the substrate temperature. The run shows
what Syxplain reports when the data contradict the literature.

## example_4: River water temperature

Daily mean water temperature, air temperature and discharge of the Neversink River near
Claryville, New York, from 2023-12-01 to 2025-07-28 (US Geological Survey, site 01435000;
public domain, some values provisional). The rows form one time series. The run detects
it, adds earlier values of the target as features, and holds out the last days
chronologically.

## Using your own data

- Upload `.csv`, `.xlsx` or `.xls` files with one row per observation and one column per
  variable.
- Only numeric columns can be features. Encode categories as integer codes; codes with up
  to 10 levels are treated as categories.
- The target must not have missing values. Rows missing a selected feature are dropped,
  and the results say how many were dropped.
- For time series, keep the date or time column in the file, even though it is not a
  feature. It is used to detect the series.
