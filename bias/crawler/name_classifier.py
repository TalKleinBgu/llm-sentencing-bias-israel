"""
Name Classification System with Bayesian Approach
Uses frequency data from Israeli population registry to classify names by ethnicity.
"""

import pandas as pd
import numpy as np
import re
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')


@dataclass
class NameData:
    """Holds name frequency data for a group."""
    first_names: Dict[str, int]  # name -> count
    last_names: Dict[str, int]   # name -> count
    total_first: int
    total_last: int


class NameClassifier:
    """
    Bayesian name classifier with support for:
    - All possible first/last name combinations
    - Frequency-based priors
    - Fuzzy matching for spelling variations
    - Higher weight for last names
    """
    
    def __init__(self, 
                 first_names_path: str,
                 last_names_paths: Dict[str, str],
                 last_name_weight: float = 2.0,
                 fuzzy_threshold: int = 92,
                 use_fuzzy: bool = True):
        """
        Initialize the classifier.
        
        Args:
            first_names_path: Path to first_name.xlsx
            last_names_paths: Dict mapping group name to last names file path
            last_name_weight: Weight multiplier for last name scores (default 2.0)
            fuzzy_threshold: Minimum score for fuzzy matching (0-100)
            use_fuzzy: Whether to use fuzzy matching as fallback
        """
        self.last_name_weight = last_name_weight
        self.fuzzy_threshold = fuzzy_threshold
        self.use_fuzzy = use_fuzzy
        
        # Load data
        self.groups: Dict[str, NameData] = {}
        self._load_data(first_names_path, last_names_paths)
        
        # Calculate priors based on total population
        self._calculate_priors()
        
        # Build lookup sets for fast exact matching
        self._build_lookup_sets()
        
        # Hebrew spelling variations mapping
        self.spelling_map = self._create_spelling_variations()
    
    def _load_first_names(self, path: str) -> Dict[str, Dict[str, int]]:
        """Load first names with frequencies from Excel file."""
        # New format: sheet names are different
        sheets_config = {
            'Jewish': ['בנים יהודים', 'בנות יהודיות'],
            'Muslim': ['בנים מוסלמים', 'בנות מוסלמיות'],
            'Christian': ['בנים נוצרים-ערבים', 'בנות נוצריות-ערביות'],
            'Druze': ['בנים דרוזים', 'בנות דרוזיות']
        }
        
        result = {group: {} for group in sheets_config}
        
        for group, sheets in sheets_config.items():
            for sheet in sheets:
                try:
                    df = pd.read_excel(path, sheet_name=sheet)
                    
                    # New format: data starts from row 2 (index 2)
                    # Column 0 = name, Column 1 = total count
                    for idx in range(2, len(df)):
                        name = df.iloc[idx, 0]  # First column: name
                        count = df.iloc[idx, 1]  # Second column: total count
                        
                        if pd.isna(name):
                            continue
                        
                        name = str(name).strip()
                        
                        # Parse count - handle special cases
                        if pd.isna(count) or str(count).strip() in ['.', '..', '-', '']:
                            count = 1  # Minimal count for rare names
                        else:
                            try:
                                count = int(float(str(count).replace(',', '')))
                            except:
                                count = 1
                        
                        # Add to existing or create new
                        if name in result[group]:
                            result[group][name] += count
                        else:
                            result[group][name] = count
                            
                except Exception as e:
                    print(f"Warning: Could not load sheet {sheet}: {e}")
        
        return result
    
    def _load_last_names(self, path: str) -> Dict[str, int]:
        """Load last names with frequencies from Excel file."""
        result = {}
        
        try:
            df = pd.read_excel(path)
            
            # New format: find where data starts (skip header rows)
            # Look for first row where column 0 has a Hebrew name and column 1 has a number
            start_idx = 0
            for idx in range(len(df)):
                val0 = df.iloc[idx, 0]
                val1 = df.iloc[idx, 1]
                
                # Skip if it's a header row
                if pd.isna(val0) or str(val0).strip() in ['שם משפחה', 'NaN', '']:
                    continue
                if pd.isna(val1) or str(val1).strip() in ['במספרים מוחלטים', 'NaN', '']:
                    continue
                    
                # Found data start
                start_idx = idx
                break
            
            for idx in range(start_idx, len(df)):
                name = df.iloc[idx, 0]  # First column: name
                count = df.iloc[idx, 1]  # Second column: count
                
                if pd.isna(name) or str(name).strip() == '':
                    continue
                
                name = str(name).strip()
                
                if pd.isna(count):
                    count = 1
                else:
                    try:
                        count = int(float(str(count).replace(',', '')))
                    except:
                        count = 1
                
                result[name] = count
                
        except Exception as e:
            print(f"Warning: Could not load {path}: {e}")
        
        return result
    
    def _load_data(self, first_names_path: str, last_names_paths: Dict[str, str]):
        """Load all name data."""
        # Load first names
        first_names = self._load_first_names(first_names_path)
        
        # Load last names and create NameData objects
        for group in ['Jewish', 'Muslim', 'Christian', 'Druze']:
            last_names = self._load_last_names(last_names_paths.get(group, ''))
            
            self.groups[group] = NameData(
                first_names=first_names.get(group, {}),
                last_names=last_names,
                total_first=sum(first_names.get(group, {}).values()) or 1,
                total_last=sum(last_names.values()) or 1
            )
        
        print(f"Loaded data:")
        for group, data in self.groups.items():
            print(f"  {group}: {len(data.first_names)} first names, {len(data.last_names)} last names")
    
    def _calculate_priors(self):
        """Calculate prior probabilities based on total population."""
        total_population = sum(
            data.total_first + data.total_last 
            for data in self.groups.values()
        )
        
        self.priors = {}
        for group, data in self.groups.items():
            group_total = data.total_first + data.total_last
            self.priors[group] = group_total / total_population if total_population > 0 else 0.25
        
        # Normalize
        total_prior = sum(self.priors.values())
        self.priors = {k: v/total_prior for k, v in self.priors.items()}
        
        print(f"\nCalculated priors: {self.priors}")
    
    def _build_lookup_sets(self):
        """Build sets for fast O(1) lookup."""
        self.first_name_sets = {
            group: set(data.first_names.keys()) 
            for group, data in self.groups.items()
        }
        self.last_name_sets = {
            group: set(data.last_names.keys()) 
            for group, data in self.groups.items()
        }
        
        # Combined sets for any-match lookup
        self.all_first_names = set()
        self.all_last_names = set()
        for group in self.groups:
            self.all_first_names.update(self.first_name_sets[group])
            self.all_last_names.update(self.last_name_sets[group])
    
    def _create_spelling_variations(self) -> Dict[str, List[str]]:
        """Create common Hebrew spelling variations."""
        # These are common variations in Hebrew spelling
        # Note: We're careful not to map between letters that distinguish ethnicities
        # For example, we DON'T map א↔ע freely because עלי (Arab) vs אלי (Jewish)
        variations = {
            # Safe variations (don't change ethnicity meaning)
            'יי': ['י'],      # Double yod to single
            'י': ['יי'],      # Single yod to double (less common)
            'וו': ['ו'],      # Double vav to single
            'ו': ['וו'],      # Single vav to double
            "ג'": ['ג׳', 'ג'],  # Gimel with geresh variations
            'ג׳': ["ג'", 'ג'],
            "ז'": ['ז׳', 'ז'],  # Zayin with geresh
            'ז׳': ["ז'", 'ז'],
            "צ'": ['צ׳', 'צ'],  # Tsadi with geresh
            'צ׳': ["צ'", 'צ'],
            'ח': ["ח'", 'ח׳'],  # Het with/without geresh (for Arabic names)
            "ח'": ['ח', 'ח׳'],
            'ח׳': ['ח', "ח'"],
            'כ': ['ך'],       # Final/non-final kaf
            'ך': ['כ'],
            'מ': ['ם'],       # Final/non-final mem
            'ם': ['מ'],
            'נ': ['ן'],       # Final/non-final nun
            'ן': ['נ'],
            'פ': ['ף'],       # Final/non-final pe
            'ף': ['פ'],
            'צ': ['ץ'],       # Final/non-final tsadi
            'ץ': ['צ'],
        }
        return variations
    
    def _generate_spelling_variants(self, name: str) -> Set[str]:
        """Generate possible spelling variants of a name."""
        variants = {name}
        
        # Apply single substitutions
        for old, replacements in self.spelling_map.items():
            if old in name:
                for repl in replacements:
                    variants.add(name.replace(old, repl))
        
        # Also try removing/adding common prefixes for Arabic names
        # But only for matching, not for changing ethnicity
        
        return variants
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # Cost is 0 if characters match, 1 otherwise
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _is_safe_match(self, name1: str, name2: str, max_distance: int = 1) -> bool:
        """
        Check if two names are safely matchable (same name with minor spelling difference).
        
        This is conservative - we only match if:
        1. Levenshtein distance <= max_distance
        2. The difference is a "safe" Hebrew spelling variation
        
        We specifically AVOID matching names that differ by א/ע or similar
        ethnicity-distinguishing letters.
        """
        dist = self._levenshtein_distance(name1, name2)
        
        if dist > max_distance:
            return False
        
        if dist == 0:
            return True
        
        # Check what the difference is
        # If it's a dangerous substitution (א↔ע, etc.), reject
        dangerous_pairs = [
            ('א', 'ע'),  # עלי vs אלי
            ('ע', 'א'),
            ('ח', 'כ'),  # Can distinguish Arabic/Hebrew
            ('כ', 'ח'),
            ('ט', 'ת'),  # Can be meaningful
            ('ת', 'ט'),
        ]
        
        # Simple check: if both letters appear and one is substituted for another
        for c1, c2 in dangerous_pairs:
            if c1 in name1 and c2 in name2:
                # Check if this is the actual substitution
                test = name1.replace(c1, c2)
                if self._levenshtein_distance(test, name2) < dist:
                    return False  # This was a dangerous substitution
            if c2 in name1 and c1 in name2:
                test = name1.replace(c2, c1)
                if self._levenshtein_distance(test, name2) < dist:
                    return False
        
        return True
    
    def clean_name(self, name_str: str) -> Optional[List[str]]:
        """Clean and normalize a name string."""
        if pd.isna(name_str):
            return None
        
        name_str = str(name_str).strip()
        
        # Remove content in parentheses
        name_str = re.sub(r'\(.*?\)', '', name_str).strip()
        
        # Normalize apostrophes to standard one
        name_str = name_str.replace('\u05f3', "'").replace('\u2019', "'")
        
        # Remove common titles - using word boundaries that work with Hebrew
        # The pattern matches the title optionally followed by space or punctuation
        title_patterns = [
            r"כב['\u0027]?\s*השופט(ת)?\s*",  # כב' השופט
            r"השופט(ת)?\s*",
            r'ד"ר\s*', r'ד״ר\s*',
            r"פרופ['\u0027]?\s*",
            r'עו"ד\s*', r'עו״ד\s*',
            r'רו"ח\s*', r'רו״ח\s*',
            r"הרב\s+",
            r"סגן(ית)?\s+",
            r"נשיא(ת)?\s+",
            r"אלוף\s+", r"תת-אלוף\s+",
            r'רס"ן\s*', r'סא"ל\s*',
            r"גב['\u0027]\s*",  # גב'
            r"גברת\s+",
            r"מר\s+",
            r"כבוד\s+",
        ]
        
        for pattern in title_patterns:
            name_str = re.sub('^' + pattern, '', name_str, flags=re.IGNORECASE).strip()
        
        # Also try removing titles from middle (in case of multiple titles)
        for pattern in title_patterns:
            name_str = re.sub(r'\s+' + pattern, ' ', name_str, flags=re.IGNORECASE).strip()
        
        # Remove extra whitespace
        name_str = ' '.join(name_str.split())
        
        parts = name_str.split()
        return parts if parts else None
    
    def generate_all_combinations(self, parts: List[str]) -> List[Tuple[str, str]]:
        """
        Generate all possible first_name/last_name combinations.
        
        For "מוחמד בן אחמד עבדאללה" generates:
        - (מוחמד, בן אחמד עבדאללה)
        - (מוחמד בן, אחמד עבדאללה)
        - (מוחמד בן אחמד, עבדאללה)
        
        Plus versions with "בן" removed.
        """
        combinations = []
        n = len(parts)
        
        if n < 2:
            return combinations
        
        # All possible split points
        for i in range(1, n):
            first = ' '.join(parts[:i])
            last = ' '.join(parts[i:])
            combinations.append((first, last))
        
        # Also try with "בן" removed (but keep original too)
        if 'בן' in parts:
            parts_no_ben = [p for p in parts if p != 'בן']
            if len(parts_no_ben) >= 2:
                for i in range(1, len(parts_no_ben)):
                    first = ' '.join(parts_no_ben[:i])
                    last = ' '.join(parts_no_ben[i:])
                    if (first, last) not in combinations:
                        combinations.append((first, last))
        
        # Handle "אבו" - it can be part of first OR last name
        # "אבו" alone is usually part of last name (אבו חצירא, אבו רביע)
        # But also try as first name prefix
        for i, part in enumerate(parts):
            if part == 'אבו' and i + 1 < n:
                # Try: first_name = parts[0], last_name = "אבו X Y Z"
                if i > 0:
                    first = ' '.join(parts[:i])
                    last = ' '.join(parts[i:])
                    if (first, last) not in combinations:
                        combinations.append((first, last))
        
        return combinations
    
    def get_name_probability(self, name: str, group: str, is_last: bool) -> float:
        """
        Get probability of a name belonging to a group.
        Uses Laplace smoothing for unseen names.
        """
        data = self.groups[group]
        
        if is_last:
            names_dict = data.last_names
            total = data.total_last
        else:
            names_dict = data.first_names
            total = data.total_first
        
        # Check exact match
        count = names_dict.get(name, 0)
        
        # Try spelling variations if no exact match
        if count == 0:
            for variant in self._generate_spelling_variants(name):
                if variant in names_dict:
                    count = names_dict[variant]
                    break
        
        # Laplace smoothing
        vocab_size = len(names_dict) + 1
        prob = (count + 1) / (total + vocab_size)
        
        return prob
    
    def find_close_match(self, name: str, name_set: Set[str], max_distance: int = 1) -> Optional[str]:
        """
        Find a close match in a name set using Levenshtein distance.
        Only returns matches that pass the safety check.
        
        Args:
            name: Name to search for
            name_set: Set of names to search in
            max_distance: Maximum Levenshtein distance allowed
            
        Returns:
            Matching name or None
        """
        # First try exact match
        if name in name_set:
            return name
        
        # Try spelling variants (these are always safe)
        for variant in self._generate_spelling_variants(name):
            if variant in name_set:
                return variant
        
        # Try Levenshtein matching with safety check
        for candidate in name_set:
            # Quick length check first (optimization)
            if abs(len(candidate) - len(name)) > max_distance:
                continue
            
            if self._is_safe_match(name, candidate, max_distance):
                return candidate
        
        return None
    
    def fuzzy_match_name(self, name: str, is_last: bool) -> Dict[str, float]:
        """
        Find matches for a name across all groups using safe Levenshtein matching.
        Returns dict of group -> match score (1.0 for match, 0.0 for no match).
        """
        results = {}
        
        for group in self.groups:
            name_set = self.last_name_sets[group] if is_last else self.first_name_sets[group]
            
            match = self.find_close_match(name, name_set, max_distance=1)
            if match:
                results[group] = 1.0
        
        return results
    
    def classify_combination(self, first: str, last: str) -> Dict[str, float]:
        """
        Classify a single first/last name combination.
        Returns scores for each group.
        
        Uses actual frequency counts - if a name appears in multiple groups,
        the group with higher frequency wins.
        
        Example: מיכאל has 24000 in Jewish, 216 in Christian
                 -> Jewish should win even if Christian is a match
        """
        scores = {}
        has_any_match = False
        
        for group in self.groups:
            data = self.groups[group]
            
            # Get actual counts (not just boolean match)
            first_count = 0
            last_count = 0
            
            # First name - exact match
            if first in data.first_names:
                first_count = data.first_names[first]
            else:
                # Try spelling variants
                for variant in self._generate_spelling_variants(first):
                    if variant in data.first_names:
                        first_count = data.first_names[variant]
                        break
            
            # Last name - exact match
            if last in data.last_names:
                last_count = data.last_names[last]
            else:
                # Try spelling variants
                for variant in self._generate_spelling_variants(last):
                    if variant in data.last_names:
                        last_count = data.last_names[variant]
                        break
            
            if first_count > 0 or last_count > 0:
                has_any_match = True
            
            # Score based on actual frequency counts
            # log(count + 1) gives proper weight to frequency
            first_score = np.log(first_count + 1)
            last_score = np.log(last_count + 1)
            
            # Combined score:
            # - Last name weighted more (last_name_weight)
            # - Prior adds baseline for the group
            score = first_score + self.last_name_weight * last_score + np.log(self.priors[group] + 1e-10)
            
            scores[group] = score
        
        scores['_has_match'] = has_any_match
        
        return scores
        
        return scores
    
    def classify_name(self, name_str: str) -> Tuple[str, float, Dict]:
        """
        Classify a name string.
        
        Returns:
            (best_group, confidence, details)
        """
        parts = self.clean_name(name_str)
        
        if not parts:
            return 'Unknown', 0.0, {'reason': 'empty_name'}
        
        # Check for anonymous
        if len(parts) == 1 and parts[0] in ['פלוני', 'פלונית', 'אלמוני', 'אלמונית']:
            return 'Anonymous', 1.0, {'reason': 'anonymous'}
        
        # Single name - check all lists
        if len(parts) == 1:
            name = parts[0]
            best_group = None
            best_score = -float('inf')
            
            for group in self.groups:
                # Check if in first or last names
                in_first = name in self.first_name_sets[group]
                in_last = name in self.last_name_sets[group]
                
                if in_first or in_last:
                    # Use the count as score
                    score = 0
                    if in_first:
                        score += self.groups[group].first_names.get(name, 0)
                    if in_last:
                        score += self.groups[group].last_names.get(name, 0)
                    
                    if score > best_score:
                        best_score = score
                        best_group = group
            
            if best_group:
                return best_group, 0.7, {'reason': 'single_name', 'name': name}
            
            # Try fuzzy matching
            if self.use_fuzzy:
                fuzzy_first = self.fuzzy_match_name(name, is_last=False)
                fuzzy_last = self.fuzzy_match_name(name, is_last=True)
                
                all_fuzzy = {}
                for g in set(fuzzy_first.keys()) | set(fuzzy_last.keys()):
                    all_fuzzy[g] = max(fuzzy_first.get(g, 0), fuzzy_last.get(g, 0))
                
                if all_fuzzy:
                    best = max(all_fuzzy.items(), key=lambda x: x[1])
                    return best[0], best[1] * 0.5, {'reason': 'fuzzy_single', 'name': name}
            
            return 'Unknown', 0.0, {'reason': 'single_name_not_found', 'name': name}
        
        # Multiple parts - try all combinations
        combinations = self.generate_all_combinations(parts)
        
        best_result = None
        best_score = -float('inf')
        any_has_match = False
        all_scores = []
        
        for first, last in combinations:
            scores = self.classify_combination(first, last)
            
            # Check if this combination had any match
            has_match = scores.pop('_has_match', False)
            if has_match:
                any_has_match = True
            
            # Find best group for this combination
            best_group_for_combo = max(scores.items(), key=lambda x: x[1])
            
            all_scores.append({
                'first': first,
                'last': last,
                'scores': scores,
                'best': best_group_for_combo,
                'has_match': has_match
            })
            
            # Only consider combinations that have actual matches
            if has_match and best_group_for_combo[1] > best_score:
                best_score = best_group_for_combo[1]
                best_result = {
                    'group': best_group_for_combo[0],
                    'first': first,
                    'last': last,
                    'scores': scores,
                    'has_match': has_match
                }
        
        # If no combination had a match, still set best_result but mark no match
        if not any_has_match and all_scores:
            best_combo = max(all_scores, key=lambda x: x['best'][1])
            best_result = {
                'group': best_combo['best'][0],
                'first': best_combo['first'],
                'last': best_combo['last'],
                'scores': best_combo['scores'],
                'has_match': False
            }
        
        if best_result:
            # Check if we had any actual match
            has_match = best_result.get('has_match', False)
            
            if not has_match:
                # No actual name match found - this is likely a foreign name
                return 'Unknown', 0.0, {'reason': 'no_match_foreign_name', 'name': ' '.join(parts)}
            
            # Calculate confidence based on score difference
            sorted_scores = sorted(
                [(k, v) for k, v in best_result['scores'].items() if k != '_has_match'], 
                key=lambda x: x[1], 
                reverse=True
            )
            if len(sorted_scores) >= 2:
                # Difference between top 2 scores
                confidence = 1.0 / (1.0 + np.exp(-(sorted_scores[0][1] - sorted_scores[1][1])))
            else:
                confidence = 0.5
            
            return (
                best_result['group'], 
                confidence,
                {
                    'reason': 'combination_match',
                    'best_first': best_result['first'],
                    'best_last': best_result['last'],
                    'all_combinations': len(combinations)
                }
            )
        
        # Fallback to fuzzy matching
        if self.use_fuzzy:
            return self._fuzzy_fallback(parts)
        
        return 'Unknown', 0.0, {'reason': 'no_match', 'parts': parts}
    
    def _fuzzy_fallback(self, parts: List[str]) -> Tuple[str, float, Dict]:
        """Use safe Levenshtein matching as fallback."""
        combinations = self.generate_all_combinations(parts)
        
        best_match = None
        best_score = 0
        
        for first, last in combinations:
            first_matches = self.fuzzy_match_name(first, is_last=False)
            last_matches = self.fuzzy_match_name(last, is_last=True)
            
            for group in set(first_matches.keys()) & set(last_matches.keys()):
                # Both first and last name matched in same group
                score = 1.0
                
                if score > best_score:
                    best_score = score
                    best_match = {
                        'group': group,
                        'first': first,
                        'last': last,
                    }
        
        # If no match with both, try with just one
        if not best_match:
            for first, last in combinations:
                first_matches = self.fuzzy_match_name(first, is_last=False)
                last_matches = self.fuzzy_match_name(last, is_last=True)
                
                # Prefer last name match (more reliable)
                for group, score in last_matches.items():
                    weighted_score = score * self.last_name_weight / (1 + self.last_name_weight)
                    if weighted_score > best_score:
                        best_score = weighted_score
                        best_match = {
                            'group': group,
                            'first': first,
                            'last': last,
                            'match_type': 'last_only'
                        }
                
                for group, score in first_matches.items():
                    weighted_score = score / (1 + self.last_name_weight)
                    if weighted_score > best_score:
                        best_score = weighted_score
                        best_match = {
                            'group': group,
                            'first': first,
                            'last': last,
                            'match_type': 'first_only'
                        }
        
        if best_match:
            return (
                best_match['group'],
                best_score * 0.8,  # Reduce confidence for fuzzy matches
                {'reason': 'levenshtein_match', **best_match}
            )
        
        return 'Unknown', 0.0, {'reason': 'no_match'}
    
    def to_ethnic_group(self, nationality: str) -> str:
        """Convert nationality to ethnic group classification."""
        if nationality in ['Muslim', 'Druze', 'Christian']:
            return 'Not Jewish'
        elif nationality == 'Jewish':
            return 'Jewish'
        elif nationality == 'Anonymous':
            return 'Anonymous'
        else:
            return 'Other'  # Foreign names, unknown, etc.
    
    def classify_to_ethnic(self, name_str: str) -> Tuple[str, float, Dict]:
        """Classify and return ethnic group (Jewish/Arab/Unknown)."""
        group, confidence, details = self.classify_name(name_str)
        ethnic = self.to_ethnic_group(group)
        details['original_group'] = group
        return ethnic, confidence, details


def process_dataframe(df: pd.DataFrame, 
                      classifier: NameClassifier,
                      name_column: str,
                      is_multiple: bool = False,
                      output_prefix: str = None) -> pd.DataFrame:
    """
    Process a dataframe column and add classification columns.
    
    Args:
        df: Input dataframe
        classifier: NameClassifier instance
        name_column: Column containing names to classify
        is_multiple: Whether column contains multiple comma-separated names
        output_prefix: Prefix for output columns (default: name_column)
    
    Returns:
        DataFrame with added classification columns
    """
    if output_prefix is None:
        output_prefix = name_column
    
    results = []
    
    for idx, row in df.iterrows():
        value = row[name_column]
        
        if pd.isna(value):
            results.append({
                'ethnic': 'Unknown',
                'nationality': 'Unknown',
                'confidence': 0.0
            })
            continue
        
        if is_multiple:
            # Multiple names separated by comma
            names = [n.strip() for n in str(value).split(',')]
            # For judges, try to remove title prefix (השופט/השופטת)
            cleaned_names = []
            for n in names:
                # Remove judge titles
                n = re.sub(r'^(השופט|השופטת|כב\'|כבוד)\s*', '', n).strip()
                if n:
                    cleaned_names.append(n)
            names = cleaned_names if cleaned_names else names
        else:
            names = [str(value)]
        
        all_ethnicities = []
        all_nationalities = []
        all_confidences = []
        
        for name in names:
            ethnic, conf, details = classifier.classify_to_ethnic(name)
            all_ethnicities.append(ethnic)
            all_nationalities.append(details.get('original_group', 'Unknown'))
            all_confidences.append(conf)
        
        # Aggregate results
        results.append({
            'ethnic': ', '.join(sorted(set(all_ethnicities))),
            'nationality': ', '.join(sorted(set(all_nationalities))),
            'confidence': np.mean(all_confidences) if all_confidences else 0.0
        })
    
    # Add columns to dataframe
    df[f'{output_prefix}_Ethnic'] = [r['ethnic'] for r in results]
    df[f'{output_prefix}_Nationality'] = [r['nationality'] for r in results]
    df[f'{output_prefix}_Confidence'] = [r['confidence'] for r in results]
    
    return df


# Example usage
if __name__ == '__main__':
    # Paths to data files
    first_names_path = '/mnt/user-data/uploads/first_name.xlsx'
    last_names_paths = {
        'Jewish': '/mnt/user-data/uploads/jews_last_names.xlsx',
        'Muslim': '/mnt/user-data/uploads/muslims_last_names.xlsx',
        'Christian': '/mnt/user-data/uploads/christians_last_names.xlsx',
        'Druze': '/mnt/user-data/uploads/druze_last_names.xlsx'
    }
    
    # Initialize classifier
    classifier = NameClassifier(
        first_names_path=first_names_path,
        last_names_paths=last_names_paths,
        last_name_weight=2.0,  # Last name twice as important
        fuzzy_threshold=92,
        use_fuzzy=True
    )
    
    # Test with some examples
    test_names = [
        'משה כהן',
        'מוחמד אגבאריה', 
        'ג\'ורג\' חורי',
        'סלים חלבי',
        'יוסף בן דוד',
        'אחמד בן מוחמד עבדאללה',
        'דוד',
        'פלוני',
        'עליי זועבי',  # Spelling variation
    ]
    
    print("\n" + "="*60)
    print("Testing classification:")
    print("="*60)
    
    for name in test_names:
        ethnic, conf, details = classifier.classify_to_ethnic(name)
        print(f"\n'{name}':")
        print(f"  Ethnic: {ethnic}")
        print(f"  Nationality: {details.get('original_group', 'N/A')}")
        print(f"  Confidence: {conf:.2f}")
        print(f"  Details: {details.get('reason', 'N/A')}")