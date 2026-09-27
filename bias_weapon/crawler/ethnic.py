"""
Name Classification following Shayo & Zussman (2011) methodology,
with BISG fallback (Elliott et al., 2009) for unclassified names.

Step 1 - Shayo & Zussman (2011):
Each name component is checked against conditional probabilities from CBS
name frequency data. A component is "Arab" if max(p) > 0.95 AND min(p) > 0.05.
A person is Arab if any component is Arab and none is Jewish, and vice versa.

Step 2 - BISG (Elliott et al., 2009):
For names unclassified by Step 1, Bayesian Improved Surname Geocoding combines
name-based likelihoods with court-location demographic priors:
    P(Arab|name, loc) = P(Arab|loc) * prod(p_i) /
        [P(Arab|loc) * prod(p_i) + P(Jewish|loc) * prod(1-p_i)]

Adaptations from original:
- We use CBS name frequency data (2024) instead of the Population Registry
- Arab = Muslim + Christian + Druze combined
- Court-location priors derived from Shayo-classified cases (Step 1)
"""

import pandas as pd
import numpy as np
import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')


# Thresholds from Shayo & Zussman (2011)
HIGH_THRESHOLD = 0.95
LOW_THRESHOLD = 0.05


class ShayoZussmanClassifier:
    """
    Name classifier following Shayo & Zussman (2011).
    
    For each name component, computes:
        p_fm = P(Arab | first name, male)
        p_ff = P(Arab | first name, female)
        p_lm = P(Arab | last name, male)
        p_lf = P(Arab | last name, female)
    
    Component is "Arab" if max(p) > 0.95 AND min(p) > 0.05
    Component is "Jewish" if max(p) <= 0.95 AND min(p) <= 0.05
    
    Person is Arab if any component is Arab and no component is Jewish.
    Person is Jewish if any component is Jewish and no component is Arab.
    """
    
    def __init__(self, first_names_path: str, last_names_paths: Dict[str, str]):
        """
        Args:
            first_names_path: Path to first_names.xlsx (CBS data with 8 sheets)
            last_names_paths: Dict with keys 'Jewish', 'Muslim', 'Christian', 'Druze'
                              mapping to their respective last names xlsx files
        """
        # Load all frequency data
        self.first_name_counts = {}  # {name: {group_gender: count}}
        self.last_name_counts = {}   # {name: {group: count}}
        
        self._load_first_names(first_names_path)
        self._load_last_names(last_names_paths)
        
        # Compute totals for conditional probability calculation
        self._compute_totals()
        
    def _load_first_names(self, path: str):
        """Load first names from CBS Excel file with 8 sheets."""
        sheets_config = {
            ('Jewish', 'male'): 'בנים יהודים',
            ('Jewish', 'female'): 'בנות יהודיות',
            ('Muslim', 'male'): 'בנים מוסלמים',
            ('Muslim', 'female'): 'בנות מוסלמיות',
            ('Christian', 'male'): 'בנים נוצרים-ערבים',
            ('Christian', 'female'): 'בנות נוצריות-ערביות',
            ('Druze', 'male'): 'בנים דרוזים',
            ('Druze', 'female'): 'בנות דרוזיות',
        }
        
        for (group, gender), sheet_name in sheets_config.items():
            key = f"{group}_{gender}"
            try:
                df = pd.read_excel(path, sheet_name=sheet_name)
                count = 0
                for idx in range(2, len(df)):
                    name = df.iloc[idx, 0]
                    total = df.iloc[idx, 1]
                    
                    if pd.isna(name):
                        continue
                    
                    name = str(name).strip()
                    # Normalize: strip leading/trailing apostrophes and normalize apostrophe chars
                    name = name.strip("'").strip("'").strip("'")
                    name = name.replace('\u05f3', "'").replace('\u2019', "'").replace('\u2018', "'")
                    
                    if pd.isna(total) or str(total).strip() in ['.', '..', '-', '']:
                        total = 1
                    else:
                        try:
                            total = int(float(str(total).replace(',', '')))
                        except:
                            total = 1
                    
                    if name not in self.first_name_counts:
                        self.first_name_counts[name] = {}
                    self.first_name_counts[name][key] = total
                    count += 1
                
                print(f"  Loaded {count} names from {sheet_name}")
                
            except Exception as e:
                print(f"  Warning: Could not load sheet {sheet_name}: {e}")
    
    def _load_last_names(self, paths: Dict[str, str]):
        """Load last names from separate files per group."""
        for group, path in paths.items():
            try:
                df = pd.read_excel(path)
                
                # Find where data starts
                start_idx = 0
                for idx in range(len(df)):
                    val0 = df.iloc[idx, 0]
                    val1 = df.iloc[idx, 1]
                    if pd.isna(val0) or str(val0).strip() in ['שם משפחה', 'NaN', '']:
                        continue
                    if pd.isna(val1) or str(val1).strip() in ['במספרים מוחלטים', 'NaN', '']:
                        continue
                    start_idx = idx
                    break
                
                count = 0
                for idx in range(start_idx, len(df)):
                    name = df.iloc[idx, 0]
                    total = df.iloc[idx, 1]
                    
                    if pd.isna(name) or str(name).strip() == '':
                        continue
                    
                    name = str(name).strip()
                    # Normalize apostrophe chars
                    name = name.replace('\u05f3', "'").replace('\u2019', "'").replace('\u2018', "'")
                    
                    if pd.isna(total):
                        total = 1
                    else:
                        try:
                            total = int(float(str(total).replace(',', '')))
                        except:
                            total = 1
                    
                    if name not in self.last_name_counts:
                        self.last_name_counts[name] = {}
                    self.last_name_counts[name][group] = total
                    count += 1
                
                print(f"  Loaded {count} last names for {group}")
                
            except Exception as e:
                print(f"  Warning: Could not load {path}: {e}")
    
    def _compute_totals(self):
        """Compute total counts for each category (for conditional probabilities)."""
        # First name totals: how many people in each group+gender
        self.first_name_totals = {}
        for name, counts in self.first_name_counts.items():
            for key, count in counts.items():
                self.first_name_totals[key] = self.first_name_totals.get(key, 0) + count
        
        # Last name totals: how many people in each group
        self.last_name_totals = {}
        for name, counts in self.last_name_counts.items():
            for group, count in counts.items():
                self.last_name_totals[group] = self.last_name_totals.get(group, 0) + count
        
        print(f"\nFirst name totals: {self.first_name_totals}")
        print(f"Last name totals: {self.last_name_totals}")
    
    def _find_name_count(self, name: str, names_dict: dict, key: str) -> int:
        """Find name via exact match only."""
        if name in names_dict and key in names_dict[name]:
            return names_dict[name][key]
        return 0

    def compute_p_arab(self, component: str) -> Dict[str, float]:
        """
        Compute conditional probabilities P(Arab|name, context) for a name component,
        following Shayo & Zussman (2011).

        Simplified to 2 contexts (all defendants are male, last names not gendered):
            p_fm = P(Arab | first name, male)
            p_lm = P(Arab | last name)

        Returns dict with keys: p_fm, p_lm
        """
        arab_groups = ['Muslim', 'Christian', 'Druze']
        all_groups = ['Jewish'] + arab_groups

        contexts = {
            'fm': (self.first_name_counts, lambda g: f'{g}_male'),
            'lm': (self.last_name_counts, lambda g: g),
        }

        counts = {}

        for ctx_key, (names_dict, key_fn) in contexts.items():
            for group in all_groups:
                counts[(group, ctx_key)] = self._find_name_count(component, names_dict, key_fn(group))
        
        results = {}

        arab_fm = sum(counts[(g, 'fm')] for g in arab_groups)
        total_fm = arab_fm + counts[('Jewish', 'fm')]
        results['p_fm'] = arab_fm / total_fm if total_fm > 0 else None
        results['total_fm'] = total_fm

        arab_l = sum(counts[(g, 'lm')] for g in arab_groups)
        total_l = arab_l + counts[('Jewish', 'lm')]
        results['p_lm'] = arab_l / total_l if total_l > 0 else None
        results['total_lm'] = total_l

        return results
    
    def classify_component(self, component: str) -> str:
        """
        Classify a single name component as 'Arab', 'Jewish', or 'Unknown'.

        Following Shayo & Zussman (2011):
        - "Arab" if max(p) > 0.95 AND min(p) > 0.05
        - "Jewish" if min(p) <= 0.05 AND max(p) <= 0.95
        - "Unknown" otherwise
        """
        probs = self.compute_p_arab(component)

        # Filter out None values and total counts
        valid_probs = [v for k, v in probs.items()
                       if v is not None and not k.startswith('total_')]

        if not valid_probs:
            return 'Unknown'

        max_p = max(valid_probs)
        min_p = min(valid_probs)

        # Shayo & Zussman classification rules
        if max_p > HIGH_THRESHOLD and min_p > LOW_THRESHOLD:
            return 'Arab'
        elif min_p <= LOW_THRESHOLD and max_p <= HIGH_THRESHOLD:
            return 'Jewish'
        else:
            return 'Unknown'
    
    def clean_name(self, name_str: str) -> Optional[List[str]]:
        """Clean and parse a name string into components."""
        if pd.isna(name_str):
            return None
        
        name_str = str(name_str).strip()
        
        # Remove content in parentheses
        name_str = re.sub(r'\(.*?\)', '', name_str).strip()
        
        # Normalize apostrophes
        name_str = name_str.replace('\u05f3', "'").replace('\u2019', "'")
        
        # Remove common titles
        title_patterns = [
            r"כב['\u0027]?\s*השופט(ת)?\s*",
            r"השופט(ת)?\s*",
            r'ד"ר\s*', r'ד״ר\s*',
            r"פרופ['\u0027]?\s*",
            r'עו"ד\s*', r'עו״ד\s*',
            r'רו"ח\s*', r'רו״ח\s*',
            r"הרב\s+",
            r"סגן(ית)?\s+",
            r"נשיא(ת)?\s+",
            r"גב['\u0027]\s*",
            r"גברת\s+",
            r"מר\s+",
            r"כבוד\s+",
        ]
        
        for pattern in title_patterns:
            name_str = re.sub('^' + pattern, '', name_str, flags=re.IGNORECASE).strip()
            name_str = re.sub(r'\s+' + pattern, ' ', name_str, flags=re.IGNORECASE).strip()
        
        name_str = ' '.join(name_str.split())
        parts = name_str.split()

        # Strip leading/trailing apostrophes from each part (to match CBS normalization)
        parts = [p.strip("'") for p in parts]
        parts = [p for p in parts if p]

        # Merge Arabic compound name prefixes with the following word,
        # but only when they appear in the middle of the name (not as first word),
        # so they are part of a compound last name, not a first name.
        # e.g. ["סלמאן", "אבו", "עליון"] -> ["סלמאן", "אבו עליון"]
        # but  ["בן", "אלפרינק"] stays as ["בן", "אלפרינק"]
        compound_prefixes = {'אבו', 'אל', 'בן', 'אבן', 'עבד', 'אבול'}
        if len(parts) > 2:
            merged = [parts[0]]
            i = 1
            while i < len(parts):
                if parts[i] in compound_prefixes and i + 1 < len(parts):
                    merged.append(parts[i] + ' ' + parts[i + 1])
                    i += 2
                else:
                    merged.append(parts[i])
                    i += 1
            parts = merged

        return parts if parts else None
    
    def classify_name(self, name_str: str) -> Tuple[str, Dict]:
        """
        Classify a person's name following Shayo & Zussman (2011).

        Decompose name into individual components (separated by spaces).
        Classify each component. A person is Arab if at least one component
        is Arab and none is Jewish. A person is Jewish if at least one
        component is Jewish and none is Arab.

        Returns:
            (classification, details_dict)
        """
        parts = self.clean_name(name_str)

        if not parts:
            return 'Unknown', {'reason': 'empty_name'}

        # Check for anonymous
        anon_names = {'פלוני', 'פלונית', 'אלמוני', 'אלמונית'}
        if len(parts) == 1 and parts[0] in anon_names:
            return 'Anonymous', {'reason': 'anonymous'}

        # Classify each component
        component_classifications = {}
        for component in parts:
            component_classifications[component] = self.classify_component(component)

        has_arab = any(c == 'Arab' for c in component_classifications.values())
        has_jewish = any(c == 'Jewish' for c in component_classifications.values())

        details = {
            'components': component_classifications,
            'parts': parts
        }

        # Shayo & Zussman decision rule
        if has_arab and not has_jewish:
            return 'Arab', details
        elif has_jewish and not has_arab:
            return 'Jewish', details
        elif has_arab and has_jewish:
            return 'Unknown', {**details, 'reason': 'conflicting_components'}
        else:
            return 'Unknown', {**details, 'reason': 'no_classifiable_components'}
    
    def bisg_classify_name(self, name_str: str, p_arab_loc: float) -> Tuple[str, Dict]:
        """
        BISG fallback classification (Elliott et al., 2009).

        Combines name-based likelihood ratios with court-location demographic
        prior using Bayes' theorem.

        Args:
            name_str: The person's full name
            p_arab_loc: P(Arab | court location), the geographic prior
        """
        parts = self.clean_name(name_str)
        if not parts:
            return 'Unknown', {'reason': 'empty_name'}

        # Collect all valid probabilities across all components and contexts
        all_probs = []
        component_details = {}
        for comp in parts:
            probs = self.compute_p_arab(comp)
            comp_probs = []
            if probs.get('p_fm') is not None:
                comp_probs.append(probs['p_fm'])
            if probs.get('p_lm') is not None:
                comp_probs.append(probs['p_lm'])
            component_details[comp] = comp_probs
            all_probs.extend(comp_probs)

        if not all_probs:
            return 'Unknown', {'reason': 'no_name_data', 'components': component_details}

        # Compute joint likelihood: prod(p_i) and prod(1-p_i)
        # Clip to [0.001, 0.999] to avoid log(0)
        eps = 0.00001
        log_arab = 0.0
        log_jewish = 0.0
        for p in all_probs:
            p_clipped = max(eps, min(1 - eps, p))
            log_arab += np.log(p_clipped)
            log_jewish += np.log(1 - p_clipped)

        # Add location prior (also clipped)
        p_loc = max(eps, min(1 - eps, p_arab_loc))
        log_arab += np.log(p_loc)
        log_jewish += np.log(1 - p_loc)

        # Posterior via log-sum-exp for numerical stability
        log_denom = np.logaddexp(log_arab, log_jewish)
        p_arab_posterior = np.exp(log_arab - log_denom)

        details = {
            'components': component_details,
            'p_arab_loc': p_arab_loc,
            'p_arab_posterior': p_arab_posterior,
        }

        if p_arab_posterior > HIGH_THRESHOLD:
            return 'Arab', details
        elif p_arab_posterior < LOW_THRESHOLD:
            return 'Jewish', details
        else:
            return 'Unknown', details

    def classify_to_ethnic(self, name_str: str) -> Tuple[str, Dict]:
        """Classify and return ethnic group."""
        return self.classify_name(name_str)


def process_dataframe(df: pd.DataFrame,
                      classifier: ShayoZussmanClassifier,
                      name_column: str,
                      is_multiple: bool = False,
                      output_prefix: str = None) -> pd.DataFrame:
    """Process a dataframe column and add classification columns."""
    if output_prefix is None:
        output_prefix = name_column
    
    results = []
    
    for idx, row in df.iterrows():
        value = row[name_column]
        
        if pd.isna(value):
            results.append({'ethnic': 'Unknown'})
            continue
        
        if is_multiple:
            names = [n.strip() for n in str(value).split(',')]
            cleaned_names = []
            for n in names:
                n = re.sub(r'^(השופט|השופטת|כב\'|כבוד)\s*', '', n).strip()
                if n:
                    cleaned_names.append(n)
            names = cleaned_names if cleaned_names else names
        else:
            names = [str(value)]
        
        all_ethnicities = []
        for name in names:
            ethnic, details = classifier.classify_to_ethnic(name)
            all_ethnicities.append(ethnic)

        if is_multiple:
            if any(e == 'Arab' for e in all_ethnicities):
                panel_ethnic = 'Arab'
            elif all(e == 'Jewish' for e in all_ethnicities):
                panel_ethnic = 'Jewish'
            else:
                panel_ethnic = 'Unknown'
        else:
            panel_ethnic = all_ethnicities[0] if all_ethnicities else 'Unknown'

        results.append({'ethnic': panel_ethnic})
    
    df[output_prefix] = [r['ethnic'] for r in results]

    return df


if __name__ == '__main__':
    import os

    # Set TARGET to "defendants" or "judges"
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, 'data')
    names_dir = os.path.join(base_dir, 'csv_for_race')

    # Initialize
    classifier = ShayoZussmanClassifier(
        first_names_path=os.path.join(names_dir, 'first_names.xlsx'),
        last_names_paths={
            'Jewish': os.path.join(names_dir, 'jewish_last_names.xlsx'),
            'Muslim': os.path.join(names_dir, 'muslims_last_names.xlsx'),
            'Christian': os.path.join(names_dir, 'christians_last_names.xlsx'),
            'Druze': os.path.join(names_dir, 'druze_last_names.xlsx'),
        }
    )
    
    #["defendants"]
    for tar in ["defendants"]:
        name_col = "Defendants" if tar == "defendants" else "Judges"
        output_col = "ethnic" if tar == "defendants" else "judge_ethnic"
        for data_file in ['carrying_only.csv','importing_only.csv','possession_only.csv']:
            csv_path = os.path.join(data_dir, 'impute', data_file)
            # csv_path = r'C:\Users\user\OneDrive\טל\projects\justice-tal\bias_weapon\data\features_extractions.csv'

            # Load CSV
            df = pd.read_csv(csv_path)
            print(f"\nLoaded {len(df)} rows from {csv_path}")

            # === Step 1: Shayo & Zussman classification ===
            df = process_dataframe(df, classifier, name_col, is_multiple=(tar == "judges"), output_prefix=output_col)

            shayo_counts = df[output_col].value_counts()
            print("\n" + "=" * 50)
            print("Step 1 - Shayo & Zussman results:")
            print(shayo_counts)

            # === Step 2: BISG fallback for Unknown cases ===
            # Compute location priors from Shayo-classified cases (excluding Unknown/Anonymous)
            classified = df[df[output_col].isin(['Arab', 'Jewish'])]
            location_priors = {}
            for loc, group in classified.groupby('Location'):
                counts = group[output_col].value_counts()
                n_arab = counts.get('Arab', 0)
                n_jewish = counts.get('Jewish', 0)
                total = n_arab + n_jewish
                if total > 0:
                    location_priors[loc] = n_arab / total
            print(location_priors)
            # Overall prior as fallback for locations with no classified cases
            total_arab = (classified[output_col] == 'Arab').sum()
            total_jewish = (classified[output_col] == 'Jewish').sum()
            overall_prior = total_arab / (total_arab + total_jewish)
            print(f"\nBISG location priors (from {len(classified)} classified cases):")
            for loc, prior in sorted(location_priors.items(), key=lambda x: -x[1]):
                print(f"  {loc}: P(Arab)={prior:.3f}")
            print(f"  Overall fallback: P(Arab)={overall_prior:.3f}")

            # Apply BISG to Unknown cases
            unknown_mask = df[output_col] == 'Unknown'
            bisg_resolved = 0
            print("\n" + "=" * 70)
            print(f"Step 2 - BISG for Unknown {tar.capitalize()}")
            print("=" * 70)
            for idx in df[unknown_mask].index:
                name_cell = df.at[idx, name_col]
                location = df.at[idx, 'Location']
                p_arab_loc = location_priors.get(location, overall_prior)

                if tar == "judges":
                    judge_names = [n.strip() for n in str(name_cell).split(',')]
                    judge_names = [re.sub(r'^(השופט|השופטת|כב\'|כבוד)\s*', '', n).strip() for n in judge_names]
                    judge_names = [n for n in judge_names if n]
                    ethnicities = []
                    for jname in judge_names:
                        step1, _ = classifier.classify_name(jname)
                        if step1 == 'Unknown':
                            bisg_r, _ = classifier.bisg_classify_name(jname, p_arab_loc)
                            ethnicities.append(bisg_r)
                        else:
                            ethnicities.append(step1)
                    if any(e == 'Arab' for e in ethnicities):
                        panel_result = 'Arab'
                    elif all(e == 'Jewish' for e in ethnicities):
                        panel_result = 'Jewish'
                    else:
                        panel_result = 'Unknown'
                    if panel_result in ('Arab', 'Jewish'):
                        df.at[idx, output_col] = panel_result
                        bisg_resolved += 1
                        print(f"  BISG resolved: '{name_cell}' @ {location} -> {panel_result}")
                    else:
                        print(f"  Still Unknown: '{name_cell}' @ {location}")
                else:
                    bisg_result, details = classifier.bisg_classify_name(name_cell, p_arab_loc)
                    p_post = details.get('p_arab_posterior')
                    if bisg_result in ('Arab', 'Jewish'):
                        df.at[idx, output_col] = bisg_result
                        bisg_resolved += 1
                        print(f"  BISG resolved: '{name_cell}' @ {location} -> {bisg_result} "
                            f"(P(Arab|name,loc)={p_post:.4f})")
                    else:
                        reason = details.get('reason', '')
                        p_str = f", P(Arab|name,loc)={p_post:.4f}" if p_post is not None else ""
                        print(f"  Still Unknown: '{name_cell}' @ {location} ({reason}{p_str})")

            print(f"\nBISG resolved {bisg_resolved} of {unknown_mask.sum()} Unknown cases")

            # === Step 3: Remaining Unknown stay Unknown ===

            # Save
            df.to_csv(csv_path, index=False)
            print(f"\nSaved results to {csv_path}")

            # Final summary
            print("\n" + "=" * 50)
            print("Final ethnicity distribution:")
            print(df[output_col].value_counts())