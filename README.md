# Uncovering Sentencing Bias with LLM-Extracted Case Facts: Evidence from Israeli Courts

Code, LLM prompts and aggregated results for the paper by Tal Klein, Oren Gazal-Ayal, Arnon Sturm and Nir Grinberg.

The pipeline extracts structured case facts from Hebrew sentencing verdicts with an LLM (OpenAI GPT-5-mini, Batch API),
infers defendant and judge ethnicity from names, and estimates sentencing disparities by defendant ethnicity, judicial
district and adjudication period with propensity score matching, in two offense domains: drug offenses and weapons
offenses.

## Data availability

The verdicts were obtained from the [Nevo](https://www.nevo.co.il) legal database under a subscription license and
contain personal information. **No verdicts or case-level data are included in this repository**, and they cannot be
redistributed. The aggregated results behind every table and figure of the paper and its Supplementary Material are
included (`bias_results/results_CSVs/`).

## Repository structure

| Folder | Contents |
|---|---|
| `bias/` | Drug-offense track (Dangerous Drugs Ordinance verdicts) |
| `bias_weapon/` | Weapons-offense track (Penal Law, Section 144) |
| `bias_results/` | Combined statistics, figures (`plots/`) and the Supplementary Material builder |

Each track has the same structure:

| Step | File | What it does |
|---|---|---|
| 1 | `crawler/meta_data_nevo_crawler*.py` | Selenium crawler that collects verdict metadata from Nevo (requires a Nevo account) |
| 2 | `crawler/download_verdicts.py` (weapons) | Downloads the verdict `.docx` files |
| 3 | `build_data.ipynb` | Builds the case-level dataset: full text, defendant filtering, ethnicity classification (`crawler/ethnic.py`, name lists in `csv_for_race/`) |
| 4 | `features_extraction.ipynb` + `crawler/features_extract_*_batch.py` | Builds one OpenAI Batch API job per feature; **all extraction prompts are in `features_extract_*_batch.py`** |
| 4b | `crawler/gpt_fewashot_punishment_boundry.ipynb` | Few-shot extraction of the sentencing range (lower/upper bounds) |
| 5 | `llm_results.ipynb` | Parses the batch outputs into feature tables |
| 6 | `src.ipynb` (R) | Propensity score matching (MatchIt), outcome models, Rosenbaum bounds and E-values, robustness specifications |
| 7 | `bias_results/stats.ipynb` | Combines both tracks; produces the paper figures and the Supplementary Material tables |
| 8 | `bias_results/build_sm.ipynb` | Builds the Supplementary Material document from `results_CSVs/SM/` |

## Setup

```bash
pip install -r requirements.txt          # Python 3.10
Rscript install_r_packages.R             # R packages used by src.ipynb
cp .env.example .env                     # then fill in the keys
```

Credentials are read from environment variables only:

* `OPENAI_API_KEY` for feature extraction (steps 4-5)
* `NEVO_EMAIL`, `NEVO_PASSWORD` for the crawlers (steps 1-2), which require a Nevo subscription

Some notebooks use an absolute `ROOT` path at the top; set it to the location of your clone.

## Reproducing the tables and figures

The Supplementary Material and Figures 4-8 can be rebuilt from the aggregated results included here: run the
corresponding cells of `bias_results/stats.ipynb` and then `bias_results/build_sm.ipynb`. Figures 1 and 3 additionally
read per-analysis result files from `*/matched_outputs/`, which are produced by `src.ipynb`. The final versions of all
figures are in `bias_results/plots/`. Re-running steps 1-6 requires access to the Nevo database.

## Citation

If you use this code, please cite the paper (citation details will be added upon publication).
